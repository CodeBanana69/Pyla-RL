from __future__ import annotations

import threading
import time
from typing import Any

from gui.instance_config import is_auto_restart_crashed_enabled, list_instance_profiles
from gui.instance_registry import read_manifest
from runtime_control import process_is_alive


POLL_INTERVAL_SECONDS = 30.0
HEARTBEAT_STALE_MULTIPLIER = 3.0
HEARTBEAT_INTERVAL_SECONDS = 5.0
BACKOFF_INITIAL_SECONDS = 60.0
BACKOFF_MAX_SECONDS = 900.0
BACKOFF_HEALTHY_RESET_SECONDS = 1800.0


class InstanceWatchdog:
    def __init__(self, supervisor, *, poll_interval: float = POLL_INTERVAL_SECONDS):
        self.supervisor = supervisor
        self.poll_interval = float(poll_interval)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._backoff: dict[str, dict[str, Any]] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="instance-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.poll_interval + 2.0)
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.wait(self.poll_interval):
            try:
                self.poll_once()
            except Exception:
                continue

    def poll_once(self) -> list[dict[str, Any]]:
        if not is_auto_restart_crashed_enabled():
            return []

        actions = []
        now = time.time()
        for profile in list_instance_profiles():
            instance_id = profile["id"]
            if not profile.get("enabled", True):
                continue

            manifest = read_manifest(instance_id)
            if not manifest:
                self._mark_healthy(instance_id, now)
                continue

            pid = int(manifest.get("pid") or 0)
            heartbeat_at = float(manifest.get("heartbeat_at", manifest.get("started_at", 0)) or 0)
            stale_after = HEARTBEAT_INTERVAL_SECONDS * HEARTBEAT_STALE_MULTIPLIER

            dead = pid and not process_is_alive(pid)
            frozen = pid and process_is_alive(pid) and heartbeat_at and (now - heartbeat_at) > stale_after

            if not dead and not frozen:
                self._mark_healthy(instance_id, now)
                continue

            if not self._backoff_ready(instance_id, now):
                continue

            reason = "dead" if dead else "frozen"
            if frozen:
                self.supervisor.stop_instance(instance_id)
            ok, message, _meta = self.supervisor.start_instance(instance_id)
            self._record_restart(instance_id, now)
            actions.append({
                "id": instance_id,
                "reason": reason,
                "ok": ok,
                "message": message,
            })
        return actions

    def _backoff_ready(self, instance_id: str, now: float) -> bool:
        entry = self._backoff.get(instance_id) or {}
        next_allowed = float(entry.get("next_allowed_at", 0) or 0)
        return now >= next_allowed

    def _record_restart(self, instance_id: str, now: float) -> None:
        entry = dict(self._backoff.get(instance_id) or {})
        delay = float(entry.get("delay", BACKOFF_INITIAL_SECONDS) or BACKOFF_INITIAL_SECONDS)
        delay = min(max(BACKOFF_INITIAL_SECONDS, delay * 2), BACKOFF_MAX_SECONDS)
        entry["delay"] = delay
        entry["next_allowed_at"] = now + delay
        entry["last_restart_at"] = now
        self._backoff[instance_id] = entry

    def _mark_healthy(self, instance_id: str, now: float) -> None:
        entry = dict(self._backoff.get(instance_id) or {})
        last_restart = float(entry.get("last_restart_at", 0) or 0)
        if last_restart and (now - last_restart) >= BACKOFF_HEALTHY_RESET_SECONDS:
            self._backoff.pop(instance_id, None)
            return
        if entry:
            entry["next_allowed_at"] = 0
            self._backoff[instance_id] = entry
