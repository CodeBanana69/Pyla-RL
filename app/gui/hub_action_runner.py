"""Run blocking Hub actions off the Qt GUI thread."""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, Signal, Slot

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

PENDING_ACTION_MESSAGE_KEYS = {
    "build-push-all": "msg.building_farm_plan",
    "preflight-check": "msg.running_preflight",
    "preflight-fix": "msg.applying_preflight_fix",
    "test-emulator": "msg.testing_emulator",
    "api-test": "msg.testing_api",
    "sort-queue": "msg.sorting_farm_plan",
    "sort-queue-by-trophies": "msg.sorting_farm_plan",
    "import-queue": "msg.importing_farm_plan",
    "calibrate-performance": "msg.calibrating_performance",
    "check-updates": "msg.checking_updates",
    "export-history": "msg.exporting_history",
    "refresh-history": "msg.refreshing_history",
    "start-pyla": "msg.checking_preflight",
}


def is_blocking_hub_action(action: str) -> bool:
    return str(action or "").strip().lower() in BLOCKING_HUB_ACTIONS


def pending_action_message(action: str) -> str:
    from gui.i18n import t

    key = PENDING_ACTION_MESSAGE_KEYS.get(str(action or "").strip().lower())
    return t(key) if key else t("msg.working")


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
