from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from runtime_control import PAUSED, RUNNING, STOP_REQUESTED, read_state, request_stop, set_runtime_state
from utils import load_toml_as_dict, resolve_project_path

RECOVERY_LOG_PATH = Path(resolve_project_path("logs/recovery_events.jsonl"))

BOT_CONFIG_ALIASES = {
    "close_tile_detector_enabled": "centered_wall_detection",
}

SHOWDOWN_PLACE_LABELS = {
    "end_trio_showdown_0": "1st",
    "end_trio_showdown_1": "2nd",
    "end_trio_showdown_2": "3rd",
    "end_trio_showdown_3": "4th",
}


def _config_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def migrate_bot_config(bot_config: dict | None = None) -> dict:
    bot_config = dict(bot_config or load_toml_as_dict("cfg/bot_config.toml"))
    if _config_bool(bot_config.get("close_tile_detector_enabled"), False):
        bot_config.setdefault("centered_wall_detection", True)
    bot_config.setdefault("current_playstyle", "team_showdown.pyla")
    bot_config.setdefault("perceived_tile_size", 54)
    bot_config.setdefault("centered_wall_detection", bot_config.get("centered_wall_detection", False))
    if "wall_path_padding" not in bot_config:
        bot_config["wall_path_padding"] = 28
    if "wall_path_probe_tiles" not in bot_config:
        bot_config["wall_path_probe_tiles"] = 1.5
    if "entity_detection_retry_confidence" not in bot_config:
        bot_config["entity_detection_retry_confidence"] = 0.35
    bot_config.setdefault("enemy_spacing_enabled", "yes")
    bot_config.setdefault("enemy_spacing_blend", 0.35)
    bot_config.setdefault("enemy_spacing_tolerance", 40)
    bot_config.setdefault("enemy_spacing_hold_strafe", bot_config.get("strafe_while_attacking", "yes"))
    bot_config.setdefault("multi_enemy_flee_weight", 0.45)
    bot_config.setdefault("combat_los_dodge_enabled", "yes")
    bot_config.setdefault("combat_dodge_blend", 0.45)
    bot_config.setdefault("combat_dodge_jitter_degrees", 18.0)
    bot_config.setdefault("fog_hsv_low", (50, 95, 215))
    bot_config.setdefault("fog_hsv_high", (60, 125, 245))
    bot_config.setdefault("fog_flee_distance", 130)
    bot_config.setdefault("fog_min_blob_pixels", 20)
    bot_config.setdefault("fog_min_pixels_in_radius", 20)
    bot_config.setdefault("fog_check_every_n_frames", 3)
    ensure_support_reporting_defaults()
    return bot_config


def ensure_support_reporting_defaults() -> None:
    from support_reporter import ensure_support_reporting_defaults as _ensure

    _ensure()


def get_queue_path() -> Path:
    try:
        from gui.instance_config import get_queue_path as _instance_queue_path

        return Path(_instance_queue_path())
    except Exception:
        from utils import default_queue_path

        return Path(default_queue_path())


def normalize_queue_row(row: dict) -> dict:
    if not isinstance(row, dict):
        return {}
    normalized = dict(row)
    normalized["brawler"] = str(normalized.get("brawler", "") or "").lower()
    normalized["push_until"] = int(normalized.get("push_until", 1000) or 1000)
    trophies = normalized.get("trophies", 0)
    normalized["trophies"] = int(trophies) if trophies not in ("", None) else 0
    wins = normalized.get("wins", 0)
    normalized["wins"] = int(wins) if wins not in ("", None) else 0
    normalized["type"] = str(normalized.get("type", "trophies") or "trophies")
    normalized["automatically_pick"] = _config_bool(normalized.get("automatically_pick"), True)
    normalized["win_streak"] = int(normalized.get("win_streak", 0) or 0)
    return normalized


def normalize_queue(hub_rows) -> list[dict]:
    if not isinstance(hub_rows, list):
        return []
    cleaned = []
    for row in hub_rows:
        item = normalize_queue_row(row)
        if item.get("brawler"):
            cleaned.append(item)
    return clean_queue(cleaned)


def clean_queue(data):
    cleaned_data = []
    for brawler_data in data:
        row = dict(brawler_data)
        if row.get("type") not in ("trophies", "wins"):
            row["type"] = "trophies"
        push_type = row["type"]
        if row.get(push_type) in ("", None):
            row[push_type] = 0
        if row.get("push_until") in ("", None):
            row["push_until"] = 300 if push_type == "wins" else 1000
        value = row[push_type]
        if isinstance(value, str):
            try:
                row[push_type] = int(value)
            except ValueError:
                row[push_type] = 0
        cleaned_data.append(row)
    return cleaned_data


def save_queue_data(data) -> None:
    queue_path = get_queue_path()
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_webhook_settings() -> dict:
    try:
        from discord_notifier import load_webhook_settings

        return load_webhook_settings()
    except Exception:
        return load_toml_as_dict("cfg/discord_config.toml")


def format_state_label(state: str | None) -> str:
    if not state:
        return "unknown"
    return SHOWDOWN_PLACE_LABELS.get(state, state.replace("_", " "))


def emit_recovery_event(kind: str, detail: str = "") -> None:
    RECOVERY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": time.time(),
        "kind": kind,
        "detail": detail,
    }
    with RECOVERY_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


class RuntimeControlBridge:
    """Adapter expected by upstream lobby/stage code."""

    def __init__(self, state_path: str):
        self.state_path = state_path
        self._lock = threading.Lock()
        self._paused = False
        self._running = True

    def should_stop(self) -> bool:
        state = read_state(self.state_path)
        return state == STOP_REQUESTED

    def should_pause(self) -> bool:
        if self.should_stop():
            return False
        state = read_state(self.state_path)
        with self._lock:
            paused_flag = self._paused
        if state == RUNNING:
            if paused_flag:
                with self._lock:
                    self._paused = False
            return False
        return state == PAUSED or paused_flag

    def mark_paused(self) -> None:
        with self._lock:
            self._paused = True
        set_runtime_state(self.state_path, True)

    def mark_running(self) -> None:
        with self._lock:
            self._paused = False
        set_runtime_state(self.state_path, False)

    def request_stop(self) -> None:
        request_stop(self.state_path)


def build_runtime_control(state_path: str) -> RuntimeControlBridge:
    return RuntimeControlBridge(state_path)


def on_queue_file_changed(stage_manager, queue_path: Path | None = None) -> bool:
    queue_path = queue_path or get_queue_path()
    if not queue_path.exists():
        return False
    try:
        mtime = queue_path.stat().st_mtime
    except OSError:
        return False
    last_mtime = getattr(stage_manager, "_queue_file_mtime", None)
    if last_mtime is not None and mtime <= last_mtime:
        return False
    try:
        rows = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    normalized = normalize_queue(rows if isinstance(rows, list) else [])
    if not normalized:
        return False
    stage_manager.brawlers_pick_data = normalized
    stage_manager._queue_file_mtime = mtime
    return True
