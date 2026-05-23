"""Categorized terminal logging with verbosity control."""

from __future__ import annotations

import sys
import time
from enum import IntEnum

DEFAULT_CONFIG_PATH = "./cfg/general_config.toml"

LEVEL_ERROR = 0
LEVEL_WARN = 1
LEVEL_INFO = 2
LEVEL_DEBUG = 3
LEVEL_TRACE = 4


class _Level(IntEnum):
    ERROR = LEVEL_ERROR
    WARN = LEVEL_WARN
    INFO = LEVEL_INFO
    DEBUG = LEVEL_DEBUG
    TRACE = LEVEL_TRACE


CATEGORY_LABELS = {
    "startup": "Startup",
    "state": "State",
    "match": "Match",
    "movement": "Movement",
    "combat": "Combat",
    "queue": "Queue",
    "recovery": "Recovery",
    "perf": "Perf",
}

QUIET_INFO_CATEGORIES = frozenset({"match", "queue", "state", "recovery"})

_config_path = DEFAULT_CONFIG_PATH
_min_level = LEVEL_INFO
_movement_trace = False
_wall_stuck_debug = False
_once_times: dict[str, float] = {}
_trace_times: dict[str, float] = {}
_status_active = False
_last_status_len = 0
_movement_trace_interval = 2.0


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _parse_verbosity(value) -> int:
    name = str(value or "normal").strip().lower()
    if name == "quiet":
        return LEVEL_WARN
    if name == "verbose":
        return LEVEL_DEBUG
    if name == "debug":
        return LEVEL_TRACE
    return LEVEL_INFO


def configure(config_path: str = DEFAULT_CONFIG_PATH) -> None:
    global _config_path, _min_level, _movement_trace, _wall_stuck_debug
    _config_path = config_path
    try:
        from utils import load_toml_as_dict

        config = load_toml_as_dict(config_path)
    except Exception:
        config = {}

    _min_level = _parse_verbosity(config.get("terminal_verbosity", "normal"))
    if _truthy(config.get("super_debug", "no")):
        _min_level = max(_min_level, LEVEL_DEBUG)
    if str(config.get("terminal_verbosity", "normal")).strip().lower() == "debug":
        _min_level = max(_min_level, LEVEL_TRACE)

    _movement_trace = _truthy(config.get("movement_debug", "no"))
    _wall_stuck_debug = _truthy(config.get("wall_stuck_debug", "no"))


def reload_config(config_path: str | None = None) -> None:
    configure(config_path or _config_path)


def movement_trace_enabled() -> bool:
    return _movement_trace or _min_level >= LEVEL_TRACE


def wall_stuck_debug_enabled() -> bool:
    return _wall_stuck_debug


def _should_log(level: int, category: str) -> bool:
    if level == LEVEL_DEBUG and category == "movement" and _wall_stuck_debug:
        return True
    if level == LEVEL_TRACE and category == "movement":
        return movement_trace_enabled()
    if _min_level == LEVEL_WARN and level == LEVEL_INFO:
        return category in QUIET_INFO_CATEGORIES
    return level <= _min_level


def _finish_status_line() -> None:
    global _status_active
    if _status_active:
        sys.stdout.write("\n")
        sys.stdout.flush()
        _status_active = False


def _emit(level: int, category: str, message: str) -> None:
    if not _should_log(level, category):
        return
    _finish_status_line()
    label = CATEGORY_LABELS.get(category, category.title())
    print(f"[{label}] {message}")


def log_error(category: str, message: str) -> None:
    _emit(LEVEL_ERROR, category, message)


def log_warn(category: str, message: str) -> None:
    _emit(LEVEL_WARN, category, message)


def log_info(category: str, message: str) -> None:
    _emit(LEVEL_INFO, category, message)


def log_debug(category: str, message: str) -> None:
    _emit(LEVEL_DEBUG, category, message)


def log_trace(category: str, message: str, *, key: str | None = None, interval: float | None = None) -> None:
    if not _should_log(LEVEL_TRACE, category):
        return
    dedupe_key = key or message
    now = time.time()
    min_interval = _movement_trace_interval if interval is None else interval
    last = _trace_times.get(dedupe_key)
    if last is not None and (now - last) < min_interval:
        return
    _trace_times[dedupe_key] = now
    _emit(LEVEL_TRACE, category, message)


def log_once(key: str, interval: float, level: int, category: str, message: str) -> None:
    now = time.time()
    last = _once_times.get(key)
    if last is not None and (now - last) < interval:
        return
    _once_times[key] = now
    _emit(level, category, message)


def log_status_line(text: str) -> None:
    global _status_active, _last_status_len
    if not _should_log(LEVEL_INFO, "perf"):
        return
    padded = text.ljust(max(_last_status_len, len(text)))
    sys.stdout.write(f"\r{padded}")
    sys.stdout.flush()
    _last_status_len = len(text)
    _status_active = True


def log_status_newline() -> None:
    _finish_status_line()
