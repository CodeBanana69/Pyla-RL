"""Run blocking Hub actions off the Qt GUI thread."""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, Signal, Slot

BLOCKING_HUB_ACTIONS = frozenset({
    "build-push-all",
    "preflight-check",
    "test-emulator",
    "api-test",
    "sort-queue",
    "sort-queue-by-trophies",
    "import-queue",
    "calibrate-performance",
    "check-updates",
    "export-history",
    "refresh-history",
})

PENDING_ACTION_MESSAGES = {
    "build-push-all": "Building farm plan...",
    "preflight-check": "Running pre-flight checks...",
    "test-emulator": "Testing emulator connection...",
    "api-test": "Testing Brawl Stars API...",
    "sort-queue": "Sorting farm plan...",
    "sort-queue-by-trophies": "Sorting farm plan...",
    "import-queue": "Importing farm plan...",
    "calibrate-performance": "Calibrating performance profile...",
    "check-updates": "Checking for updates...",
    "export-history": "Exporting match history...",
    "refresh-history": "Refreshing match history...",
    "start-pyla": "Checking pre-flight...",
}


def is_blocking_hub_action(action: str) -> bool:
    return str(action or "").strip().lower() in BLOCKING_HUB_ACTIONS


def pending_action_message(action: str) -> str:
    return PENDING_ACTION_MESSAGES.get(str(action or "").strip().lower(), "Working...")


class HubActionWorker(QObject):
    finished = Signal(str)

    def __init__(self, bridge, *, action="", payload_json="", start_pyla=False):
        super().__init__()
        self._bridge = bridge
        self._action = action
        self._payload_json = payload_json
        self._start_pyla = start_pyla

    @Slot()
    def run(self):
        try:
            if self._start_pyla:
                payload = self._bridge._start_pyla_sync()
            else:
                payload = self._bridge._run_action_json(self._action, self._payload_json)
        except Exception as exc:
            payload = json.dumps({
                "ok": False,
                "message": str(exc),
                "state": self._bridge._ui_state(),
            })
        self.finished.emit(payload)
