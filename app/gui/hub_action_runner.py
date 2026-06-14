"""Run blocking Hub actions off the Qt GUI thread."""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, Signal, Slot
from i18n import translate

BLOCKING_HUB_ACTIONS = frozenset({
    "build-push-all",
    "preflight-check",
    "preflight-fix",
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

PENDING_ACTION_KEYS = {
    "build-push-all": "hub.action.buildQueueRunning",
    "preflight-check": "hub.action.preflightRunning",
    "preflight-fix": "hub.action.preflightRunning",
    "test-emulator": "hub.action.testEmulatorRunning",
    "api-test": "hub.action.apiTestRunning",
    "sort-queue": "hub.action.sortQueueRunning",
    "sort-queue-by-trophies": "hub.action.sortQueueRunning",
    "import-queue": "hub.action.importQueueRunning",
    "calibrate-performance": "hub.action.calibrateRunning",
    "check-updates": "hub.action.checkUpdatesRunning",
    "export-history": "hub.action.exportHistoryRunning",
    "refresh-history": "hub.action.refreshHistoryRunning",
    "start-pyla": "hub.action.startingPyla",
}


def is_blocking_hub_action(action: str) -> bool:
    return str(action or "").strip().lower() in BLOCKING_HUB_ACTIONS


def pending_action_message(action: str) -> str:
    key = PENDING_ACTION_KEYS.get(str(action or "").strip().lower())
    if key:
        return translate(key)
    return translate("status.working")


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
