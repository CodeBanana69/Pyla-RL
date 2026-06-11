from __future__ import annotations

import statistics
import time
from typing import Any

from utils import _config_bool, load_toml_as_dict, save_dict_as_toml


TUNING_RUNGS = [
    {"scrcpy_max_fps": 60, "scrcpy_max_width": 960, "ocr_scale_down_factor": 0.5},
    {"scrcpy_max_fps": 45, "scrcpy_max_width": 854, "ocr_scale_down_factor": 0.5},
    {"scrcpy_max_fps": 30, "scrcpy_max_width": 720, "ocr_scale_down_factor": 0.45},
    {"scrcpy_max_fps": 24, "scrcpy_max_width": 640, "ocr_scale_down_factor": 0.4},
    {"scrcpy_max_fps": 20, "scrcpy_max_width": 540, "ocr_scale_down_factor": 0.35},
]


def is_performance_autotune_enabled() -> bool:
    general = load_toml_as_dict("cfg/general_config.toml")
    return _config_bool(general.get("performance_autotune"), False)


def set_performance_autotune(enabled: bool) -> dict[str, Any]:
    general_path = "cfg/general_config.toml"
    general = dict(load_toml_as_dict(general_path))
    general["performance_autotune"] = "yes" if enabled else "no"
    save_dict_as_toml(general, general_path)
    return general


def _rung_index_for_settings(settings: dict[str, Any]) -> int:
    fps = int(settings.get("scrcpy_max_fps", 60) or 60)
    width = int(settings.get("scrcpy_max_width", 960) or 960)
    ocr = float(settings.get("ocr_scale_down_factor", 0.5) or 0.5)
    best = 0
    best_distance = float("inf")
    for index, rung in enumerate(TUNING_RUNGS):
        distance = (
            abs(fps - int(rung["scrcpy_max_fps"]))
            + abs(width - int(rung["scrcpy_max_width"])) / 100.0
            + abs(ocr - float(rung["ocr_scale_down_factor"])) * 10.0
        )
        if distance < best_distance:
            best_distance = distance
            best = index
    return best


class PerformanceAutoTuner:
    def __init__(self, *, target_ips: float = 0.0):
        self.target_ips = float(target_ips or 0)
        self._window_started_at = 0.0
        self._low_streak = 0
        self._high_streak = 0
        self._rung_index = _rung_index_for_settings(load_toml_as_dict("cfg/general_config.toml"))
        self._last_apply_at = 0.0

    def observe_ips(self, ips_history) -> None:
        if not is_performance_autotune_enabled():
            return
        if not ips_history:
            return
        now = time.time()
        if not self._window_started_at:
            self._window_started_at = now
        if now - self._window_started_at < 60.0:
            return

        samples = [float(value) for value in ips_history if value is not None]
        if not samples:
            self._window_started_at = now
            return

        median_ips = statistics.median(samples)
        target = self.target_ips if self.target_ips > 0 else max(samples)
        low_threshold = target * 0.85
        high_threshold = target * 1.10

        if median_ips < low_threshold:
            self._low_streak += 1
            self._high_streak = 0
        elif median_ips > high_threshold:
            self._high_streak += 1
            self._low_streak = 0
        else:
            self._low_streak = 0
            self._high_streak = 0

        self._window_started_at = now

    def should_step_down(self) -> bool:
        return self._low_streak >= 2

    def should_step_up(self) -> bool:
        return self._high_streak >= 5

    def apply_pending_adjustment(self, window_controller) -> str | None:
        if not is_performance_autotune_enabled():
            return None
        if not self.should_step_down() and not self.should_step_up():
            return None
        if time.time() - self._last_apply_at < 30.0:
            return None

        if self.should_step_down() and self._rung_index < len(TUNING_RUNGS) - 1:
            self._rung_index += 1
            direction = "down"
        elif self.should_step_up() and self._rung_index > 0:
            self._rung_index -= 1
            direction = "up"
        else:
            self._low_streak = 0
            self._high_streak = 0
            return None

        rung = TUNING_RUNGS[self._rung_index]
        general_path = "cfg/general_config.toml"
        general = dict(load_toml_as_dict(general_path))
        general.update(rung)
        save_dict_as_toml(general, general_path)

        window_controller.scrcpy_max_fps = int(rung["scrcpy_max_fps"])
        window_controller.scrcpy_max_width = int(rung["scrcpy_max_width"])
        window_controller.restart_scrcpy_client()

        self._low_streak = 0
        self._high_streak = 0
        self._last_apply_at = time.time()

        import runtime_log

        runtime_log.log_info(
            "performance",
            f"Auto-tuned {direction} to fps={rung['scrcpy_max_fps']} width={rung['scrcpy_max_width']}",
        )
        return direction


def calibrate_performance_profile(seconds: float = 4.0) -> dict[str, Any]:
    from window_controller import WindowController

    controller = WindowController()
    original = {
        "width": controller.scrcpy_max_width,
        "fps": controller.scrcpy_max_fps,
        "bitrate": controller.scrcpy_bitrate,
    }
    from tools.live_ips_tuner import PROFILES, apply_profile, measure_profile, score_result

    best = {"name": "current", "score": -1, "result": {}}
    for profile in PROFILES:
        apply_profile(controller, profile, original)
        result = measure_profile(controller, seconds)
        score = score_result(result)
        if score > best["score"]:
            best = {"name": profile["name"], "score": score, "result": result, "profile": profile}

    apply_profile(controller, {"name": "current", "width": None, "fps": None, "bitrate": None}, original)

    profile_name = "balanced"
    if best["name"] in {"540w_15fps_800kb", "640w_20fps_1mb", "720w_20fps_1_5mb"}:
        profile_name = "low_end"
    elif best["name"] in {"720w_30fps_1_5mb", "854w_30fps_2mb"}:
        profile_name = "balanced"
    elif best["name"] in {"960w_30fps_3mb"}:
        profile_name = "high_ips"

    from performance_profile import apply_performance_profile

    apply_performance_profile(profile_name)
    return {
        "recommended_profile": profile_name,
        "best_capture": best["name"],
        "feed_fps": (best.get("result") or {}).get("feed_fps", 0),
    }
