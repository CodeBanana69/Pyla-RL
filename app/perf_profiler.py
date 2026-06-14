"""Low-overhead loop profiler for IPS diagnostics."""

from __future__ import annotations

import json
import os
import platform
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from utils import config_bool, load_toml_as_dict, resolve_project_path

_PERF_TRACE_MAX_BYTES = 50 * 1024 * 1024
_SYSTEM_REFRESH_SECONDS = 60.0

_profiler: "PerfProfiler | None" = None


def _truthy(value) -> bool:
    return config_bool(value, False)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * pct))
    index = max(0, min(index, len(ordered) - 1))
    return float(ordered[index])


def _stage_stats(samples: list[float]) -> dict[str, float | int]:
    if not samples:
        return {"count": 0, "total_ms": 0.0, "avg_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    total = float(sum(samples))
    count = len(samples)
    return {
        "count": count,
        "total_ms": round(total, 3),
        "avg_ms": round(total / count, 3),
        "p50_ms": round(_percentile(samples, 0.5), 3),
        "p95_ms": round(_percentile(samples, 0.95), 3),
        "max_ms": round(max(samples), 3),
    }


class _NoOpProfiler:
    enabled = False

    def record(self, stage: str, ms: float) -> None:
        return None

    def record_metric(self, name: str, value: float) -> None:
        return None

    def mark_counter(self, name: str, amount: int = 1) -> None:
        return None

    @contextmanager
    def time_stage(self, stage: str):
        yield

    def rollup(self, *, ips: float = 0.0, feed_fps: float = 0.0, game_state: str = "") -> dict[str, Any]:
        return {}

    def system_snapshot(self, window_controller=None) -> dict[str, Any]:
        return {}

    def write_trace_line(self, payload: dict[str, Any]) -> None:
        return None

    def format_console_suffix(self, rollup: dict[str, Any] | None) -> str:
        return ""

    def maybe_auto_enable(self, ips: float) -> None:
        return None


class PerfProfiler:
    def __init__(self, config: dict[str, Any] | None = None):
        config = config if config is not None else load_toml_as_dict("cfg/debug_settings.toml")
        self._config = config
        self.enabled = _truthy(config.get("perf_instrumentation", "yes"))
        self.trace_jsonl = _truthy(config.get("perf_trace_jsonl", "yes"))
        self.console_breakdown = _truthy(config.get("perf_console_breakdown", "yes"))
        try:
            self.auto_ips_threshold = float(config.get("perf_auto_when_ips_below", 0) or 0)
        except (TypeError, ValueError):
            self.auto_ips_threshold = 0.0

        self._stage_samples: dict[str, list[float]] = defaultdict(list)
        self._counters: dict[str, int] = defaultdict(int)
        self._metrics: dict[str, list[float]] = defaultdict(list)
        self._system_cache: dict[str, Any] = {}
        self._system_cached_at = 0.0
        self._inference_health: dict[str, Any] = {}
        self._trace_path = Path(resolve_project_path("logs")) / f"perf_trace_{os.getpid()}.jsonl"
        self._play_ref = None
        self._window_controller_ref = None

    def bind_runtime(self, play=None, window_controller=None) -> None:
        if play is not None:
            self._play_ref = play
        if window_controller is not None:
            self._window_controller_ref = window_controller

    def set_inference_health(self, health: dict[str, Any]) -> None:
        self._inference_health = dict(health or {})

    def maybe_auto_enable(self, ips: float) -> None:
        if self.enabled or self.auto_ips_threshold <= 0:
            return
        if ips > 0 and ips < self.auto_ips_threshold:
            self.enabled = True
            self.trace_jsonl = True

    def record(self, stage: str, ms: float) -> None:
        if not self.enabled:
            return
        self._stage_samples[str(stage)].append(max(0.0, float(ms)))

    def record_metric(self, name: str, value: float) -> None:
        if not self.enabled:
            return
        self._metrics[str(name)].append(float(value))

    def mark_counter(self, name: str, amount: int = 1) -> None:
        if not self.enabled:
            return
        self._counters[str(name)] += int(amount)

    @contextmanager
    def time_stage(self, stage: str):
        if not self.enabled:
            yield
            return
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record(stage, (time.perf_counter() - started) * 1000.0)

    def _loop_samples(self) -> list[float]:
        keys = (
            "side_tasks",
            "screenshot",
            "stale_feed",
            "duplicate_replay",
            "manage_time_tasks",
            "play_main",
            "max_ips_sleep",
        )
        totals = []
        max_len = max((len(self._stage_samples.get(key, [])) for key in keys), default=0)
        for index in range(max_len):
            total = 0.0
            for key in keys:
                samples = self._stage_samples.get(key, [])
                if index < len(samples):
                    total += samples[index]
            if total > 0:
                totals.append(total)
        play_samples = self._stage_samples.get("play_main", [])
        if play_samples and not totals:
            totals = list(play_samples)
        return totals

    def classify_bottleneck(
        self,
        rollup: dict[str, Any],
        *,
        ips: float,
        feed_fps: float,
        config: dict[str, Any] | None = None,
    ) -> str:
        health = self._inference_health or {}
        if health.get("using_cpu_despite_gpu"):
            return "cpu_inference_fallback"

        stages = rollup.get("stages") or {}
        counters = rollup.get("counters") or {}
        loop_ms = rollup.get("loop_ms") or {}
        loop_avg = float(loop_ms.get("avg_ms") or 0.0)
        if loop_avg <= 0:
            if int(counters.get("duplicate_skip", 0)) > int(counters.get("duplicate_replay", 0)):
                return "idle"
            return "unknown"

        def share(stage_name: str) -> float:
            stats = stages.get(stage_name) or {}
            return float(stats.get("total_ms") or 0.0) / max(loop_avg * max(int(stats.get("count") or 1), 1), 1e-6)

        onnx_total = 0.0
        for name, stats in stages.items():
            if "onnx" in name or name.endswith("_onnx"):
                onnx_total += float(stats.get("total_ms") or 0.0)
        onnx_share = onnx_total / max(float(loop_ms.get("total_ms") or loop_avg), 1e-6)

        debug_stats = stages.get("publish_debug_view") or {}
        debug_share = float(debug_stats.get("total_ms") or 0.0) / max(float(loop_ms.get("total_ms") or loop_avg), 1e-6)
        throttle_stats = stages.get("max_ips_sleep") or {}
        throttle_share = float(throttle_stats.get("total_ms") or 0.0) / max(float(loop_ms.get("total_ms") or loop_avg), 1e-6)
        side_stats = stages.get("side_tasks") or {}
        side_share = float(side_stats.get("total_ms") or 0.0) / max(float(loop_ms.get("total_ms") or loop_avg), 1e-6)

        frame_age = rollup.get("frame_age_ms") or {}
        frame_age_p95 = float(frame_age.get("p95_ms") or 0.0)

        if ips >= 1 and feed_fps >= 1 and feed_fps + 1.5 < ips:
            return "emulator_bound"
        if frame_age_p95 >= 80:
            return "emulator_bound"
        if onnx_share >= 0.4:
            return "inference_bound"
        wall_stats = stages.get("wall_onnx") or {}
        if float(wall_stats.get("p95_ms") or 0.0) > max(float(wall_stats.get("avg_ms") or 0.0) * 2.5, 20.0):
            return "wall_spike"
        if debug_share >= 0.15:
            return "debug_view_bound"
        if throttle_share >= 0.2:
            return "throttled"
        if side_share >= 0.2:
            return "side_tasks_bound"
        if int(counters.get("duplicate_skip", 0)) > int(counters.get("wall_pass", 0)) * 3:
            return "idle"
        return "mixed"

    def rollup(self, *, ips: float = 0.0, feed_fps: float = 0.0, game_state: str = "") -> dict[str, Any]:
        if not self.enabled:
            return {}

        stages = {name: _stage_stats(samples) for name, samples in self._stage_samples.items() if samples}
        loop_samples = self._loop_samples()
        loop_stats = _stage_stats(loop_samples)
        loop_stats["total_ms"] = round(sum(loop_samples), 3) if loop_samples else 0.0

        frame_age_stats = _stage_stats(self._metrics.get("frame_age_ms", []))
        if frame_age_stats["count"]:
            rollup_frame_age = {
                "avg_ms": frame_age_stats["avg_ms"],
                "p95_ms": frame_age_stats["p95_ms"],
                "max_ms": frame_age_stats["max_ms"],
                "count": frame_age_stats["count"],
            }
        else:
            rollup_frame_age = {}

        counters = {key: int(value) for key, value in self._counters.items()}
        result = {
            "stages": stages,
            "loop_ms": loop_stats,
            "frame_age_ms": rollup_frame_age,
            "counters": counters,
        }
        result["bottleneck"] = self.classify_bottleneck(result, ips=ips, feed_fps=feed_fps)

        trace_payload = {
            "ts": time.time(),
            "ips": float(ips),
            "feed_fps": float(feed_fps),
            "state": str(game_state or ""),
            "perf": result,
            "system": self.system_snapshot(self._window_controller_ref),
        }
        self.write_trace_line(trace_payload)

        self._stage_samples.clear()
        self._counters.clear()
        self._metrics.clear()
        return result

    def system_snapshot(self, window_controller=None) -> dict[str, Any]:
        now = time.time()
        if self._system_cache and now - self._system_cached_at < _SYSTEM_REFRESH_SECONDS:
            return dict(self._system_cache)

        general = load_toml_as_dict("cfg/general_config.toml")
        debug_settings = load_toml_as_dict("cfg/debug_settings.toml")
        snapshot: dict[str, Any] = {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "max_ips": general.get("max_ips", 0),
            "scrcpy_max_fps": general.get("scrcpy_max_fps"),
            "scrcpy_max_width": general.get("scrcpy_max_width"),
            "scrcpy_bitrate": general.get("scrcpy_bitrate"),
            "visual_debug": general.get("visual_debug"),
            "advanced_visuals": general.get("advanced_visuals"),
            "debug_view_fps": debug_settings.get("debug_view_fps"),
            "cpu_or_gpu_configured": general.get("cpu_or_gpu", "auto"),
        }
        try:
            import onnxruntime as ort

            snapshot["onnxruntime_version"] = ort.__version__
            snapshot["onnx_available_providers"] = list(ort.get_available_providers())
        except Exception:
            snapshot["onnx_available_providers"] = []

        wc = window_controller or self._window_controller_ref
        if wc is not None:
            snapshot["emulator"] = getattr(wc, "selected_emulator", "")
            snapshot["adb_device"] = getattr(wc, "connected_serial", "")
            snapshot["frame_w"] = getattr(wc, "width", 0) or 0
            snapshot["frame_h"] = getattr(wc, "height", 0) or 0

        if self._inference_health:
            snapshot.update(self._inference_health)

        if self._play_ref is not None:
            try:
                from inference_health import collect_provider_info

                snapshot["onnx_providers"] = collect_provider_info(self._play_ref)
            except Exception:
                pass

        self._system_cache = snapshot
        self._system_cached_at = now
        return dict(snapshot)

    def write_trace_line(self, payload: dict[str, Any]) -> None:
        if not self.trace_jsonl:
            return
        path = self._trace_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > _PERF_TRACE_MAX_BYTES:
            backup = path.with_suffix(path.suffix + ".1")
            try:
                if backup.exists():
                    backup.unlink()
                path.replace(backup)
            except OSError:
                return
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
        except OSError:
            return

    def format_console_suffix(self, rollup: dict[str, Any] | None) -> str:
        if not self.console_breakdown or not rollup:
            return ""
        stages = rollup.get("stages") or {}
        parts = []
        for key in ("main_onnx", "wall_onnx", "publish_debug_view"):
            stats = stages.get(key)
            if stats and stats.get("avg_ms"):
                parts.append(f"{key.split('_')[0]} {stats['avg_ms']:.0f}ms")
        bottleneck = rollup.get("bottleneck")
        if bottleneck:
            parts.append(f"BOTTLENECK:{bottleneck}")
        health = self._inference_health.get("inference_health") or self._inference_health
        provider_label = health.get("provider_summary") if isinstance(health, dict) else None
        if provider_label:
            parts.insert(0, f"PROVIDER:{provider_label}")
        return " | " + " | ".join(parts) if parts else ""


def configure_profiler(config: dict[str, Any] | None = None) -> PerfProfiler | _NoOpProfiler:
    global _profiler
    config = config if config is not None else load_toml_as_dict("cfg/debug_settings.toml")
    if not _truthy(config.get("perf_instrumentation", "yes")):
        threshold = 0.0
        try:
            threshold = float(config.get("perf_auto_when_ips_below", 0) or 0)
        except (TypeError, ValueError):
            threshold = 0.0
        if threshold <= 0:
            _profiler = _NoOpProfiler()
            return _profiler
    _profiler = PerfProfiler(config)
    return _profiler


def get_profiler() -> PerfProfiler | _NoOpProfiler:
    global _profiler
    if _profiler is None:
        return configure_profiler()
    return _profiler


def perf_trace_path_for_pid(pid: int | None = None) -> Path:
    pid = os.getpid() if pid is None else pid
    return Path(resolve_project_path("logs")) / f"perf_trace_{pid}.jsonl"
