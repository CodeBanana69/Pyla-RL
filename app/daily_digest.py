from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any

from match_journal import read_all_matches
from recovery_events import read_recent_events
from utils import _config_bool, load_toml_as_dict


def digest_settings() -> dict[str, Any]:
    discord = load_toml_as_dict("cfg/discord_config.toml")
    return {
        "enabled": _config_bool(discord.get("daily_digest_enabled"), False),
        "hour": int(discord.get("daily_digest_hour", 20) or 20),
    }


def should_send_digest(now: datetime | None = None, *, last_sent_at: float = 0.0) -> bool:
    settings = digest_settings()
    if not settings["enabled"]:
        return False
    now = now or datetime.now()
    if now.hour != int(settings["hour"]):
        return False
    if last_sent_at and (time.time() - last_sent_at) < 20 * 3600:
        return False
    return True


def build_daily_digest(*, instance_id: str | None = None, since_hours: float = 24.0) -> dict[str, Any]:
    cutoff = time.time() - (since_hours * 3600.0)
    matches = []
    trophy_delta = 0
    wins = 0
    from farm_analytics import _parse_record_ts

    for record in read_all_matches():
        ts = _parse_record_ts(record)
        if ts and ts < cutoff:
            continue
        matches.append(record)
        try:
            trophy_delta += int(record.get("delta", 0) or 0)
        except (TypeError, ValueError):
            pass
        result = str(record.get("result", "") or "").lower()
        if result in {"victory", "win", "1st", "2nd", "3rd"}:
            wins += 1

    recoveries = [
        event for event in read_recent_events(limit=500)
        if _event_ts(event) >= cutoff
    ]
    recovery_counts: dict[str, int] = {}
    for event in recoveries:
        event_type = str(event.get("event_type", "unknown"))
        recovery_counts[event_type] = recovery_counts.get(event_type, 0) + 1

    uptime_s = 0.0
    if instance_id:
        from gui.instance_registry import read_manifest

        manifest = read_manifest(instance_id) or {}
        started_at = float(manifest.get("started_at", 0) or 0)
        if started_at:
            uptime_s = max(0.0, time.time() - started_at)

    return {
        "instance_id": instance_id or "",
        "matches": len(matches),
        "wins": wins,
        "trophy_delta": trophy_delta,
        "recovery_counts": recovery_counts,
        "uptime_s": uptime_s,
        "since_hours": since_hours,
    }


def format_daily_digest_text(payload: dict[str, Any]) -> str:
    instance = str(payload.get("instance_id") or "").strip()
    prefix = f"[{instance}] " if instance else ""
    recoveries = payload.get("recovery_counts") or {}
    recovery_text = ", ".join(f"{key}={value}" for key, value in sorted(recoveries.items())) or "none"
    uptime_h = float(payload.get("uptime_s", 0) or 0) / 3600.0
    return (
        f"{prefix}Daily digest ({payload.get('since_hours', 24)}h)\n"
        f"Matches: {payload.get('matches', 0)} ({payload.get('wins', 0)} wins)\n"
        f"Trophy delta: {payload.get('trophy_delta', 0):+d}\n"
        f"Recoveries: {recovery_text}\n"
        f"Uptime: {uptime_h:.1f}h"
    )


class DailyDigestScheduler:
    """Background scheduler for multi-instance Hub process."""

    def __init__(self, *, poll_seconds: float = 60.0):
        self.poll_seconds = float(poll_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_sent_at = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="daily-digest", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            self.maybe_send()

    def maybe_send(self, *, instance_id: str | None = None) -> bool:
        if not should_send_digest(last_sent_at=self._last_sent_at):
            return False
        payload = build_daily_digest(instance_id=instance_id)
        text = format_daily_digest_text(payload)
        try:
            import asyncio

            from utils import async_notify_user

            asyncio.run(async_notify_user("daily_digest", None, details={"message": text, **payload}))
            self._last_sent_at = time.time()
            return True
        except Exception:
            return False


def _event_ts(event: dict[str, Any]) -> float:
    raw = str(event.get("ts", "") or "")
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
