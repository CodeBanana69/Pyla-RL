from __future__ import annotations

import base64
import io
import time
from pathlib import Path
from typing import Any, Callable

from gui.instance_config import REPLIES_DIR
from gui.instance_registry import require_resolved_instance
from utils import resolve_project_path
from runtime_control import (
    PAUSED,
    RUNNING,
    STOP_REQUESTED,
    enqueue_remote_command,
    read_remote_reply,
    read_state,
    write_state,
)


class RemoteCommandRouter:
    def __init__(
            self,
            *,
            local_handlers: dict[str, Callable[..., Any]] | None = None,
            timeout_seconds: float = 30.0,
    ):
        self.local_handlers = local_handlers or {}
        self.timeout_seconds = timeout_seconds

    def _reply_path(self, command_id: str) -> Path:
        return Path(resolve_project_path(REPLIES_DIR)) / f"{command_id}.json"

    def resolve_target(self, instance: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
        return require_resolved_instance(instance)

    def set_runtime_state(self, state_path: str | Path, paused: bool) -> str:
        state = PAUSED if paused else RUNNING
        write_state(state_path, state)
        return state

    def request_stop(self, state_path: str | Path) -> None:
        write_state(state_path, STOP_REQUESTED)

    def dispatch_state_action(self, instance: str | None, action: str) -> tuple[bool, str]:
        target, error = self.resolve_target(instance)
        if error or not target:
            return False, error or "Instance not found."
        state_path = target.get("state_path")
        if not state_path:
            return False, f"Instance '{target['id']}' has no state path."
        if action == "pause":
            self.set_runtime_state(state_path, paused=True)
            return True, f"Paused instance '{target['id']}'."
        if action == "resume":
            self.set_runtime_state(state_path, paused=False)
            return True, f"Resumed instance '{target['id']}'."
        if action == "stop":
            self.request_stop(state_path)
            return True, f"Stop requested for instance '{target['id']}'."
        return False, f"Unknown state action '{action}'."

    def dispatch_remote_action(self, instance: str | None, action: str, args: dict[str, Any] | None = None) -> tuple[bool, Any]:
        target, error = self.resolve_target(instance)
        if error or not target:
            return False, error or "Instance not found."
        state_path = target.get("state_path")
        if not state_path:
            return False, f"Instance '{target['id']}' has no state path."

        handler = self.local_handlers.get(action)
        if handler is not None and not target.get("running"):
            return False, f"Instance '{target['id']}' is not running."

        if handler is not None and target["id"] == (self.local_handlers.get("_local_instance_id")):
            try:
                result = handler(**(args or {})) if args else handler()
                return True, result
            except TypeError:
                result = handler(*(args or {}).values()) if args else handler()
                return True, result
            except Exception as exc:
                return False, f"Command failed: {exc}"

        command_id = str(time.time()).replace(".", "")
        reply_path = str(self._reply_path(command_id))
        enqueue_remote_command(
            state_path,
            {
                "id": command_id,
                "action": action,
                "args": dict(args or {}),
                "reply_path": reply_path,
            },
        )
        deadline = time.time() + self.timeout_seconds
        while time.time() < deadline:
            reply = read_remote_reply(reply_path)
            if reply is not None:
                read_remote_reply(reply_path, clear=True)
                if reply.get("ok"):
                    return True, reply.get("result", reply.get("message", "Command finished."))
                return False, reply.get("error", "Command failed.")
            time.sleep(0.25)
        return False, f"Timed out waiting for instance '{target['id']}'."

    def build_status_provider(self, instance: str | None = None) -> Callable[[], dict[str, Any]] | None:
        target, _ = self.resolve_target(instance)
        if not target:
            return None
        metrics_path = target.get("metrics_path")
        if not metrics_path:
            return None

        def provider():
            from runtime_metrics import read_metrics

            metrics = read_metrics(metrics_path) or {}
            session = metrics.get("session") or {}
            return {
                "state": session.get("state", ""),
                "ips": f"{metrics.get('ips', 0):.2f}",
                "feed_fps": f"{metrics.get('feed_fps', 0):.2f}",
                "brawler": session.get("brawler", ""),
                "target": session.get("target", ""),
                "last_match": session.get("last_match", ""),
                "queue_preview": session.get("queue_preview", ""),
                "last_recovery": session.get("last_recovery", ""),
                "instance_id": target.get("id", ""),
                "instance_name": target.get("name", ""),
            }

        return provider

    def instance_choices(self) -> list[str]:
        from gui.instance_registry import list_instances

        return [item["id"] for item in list_instances() if item.get("running")]


def encode_screenshot_reply(screenshot) -> dict[str, Any]:
    if screenshot is None:
        return {"ok": True, "result": "No screenshot available."}
    try:
        from PIL import Image
        import numpy as np

        if isinstance(screenshot, np.ndarray):
            image = Image.fromarray(screenshot)
        elif isinstance(screenshot, Image.Image):
            image = screenshot
        else:
            return {"ok": False, "error": "Unsupported screenshot type."}
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return {"ok": True, "result": "Screenshot captured.", "screenshot_b64": encoded}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
