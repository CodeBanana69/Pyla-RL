from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from gui.instance_config import (
    find_port_collision,
    get_instance_profile,
    is_multi_instance_enabled,
    queue_has_data,
)
from gui.instance_registry import list_instances, read_manifest, resolve_instance
from gui.window_arranger import arrange_emulator_windows
from runtime_control import STOP_REQUESTED, process_is_alive, write_state


class InstanceSupervisor:
    def __init__(self, project_root: str | Path | None = None):
        self.project_root = Path(project_root or Path(__file__).resolve().parent.parent)
        self._processes: dict[str, subprocess.Popen] = {}

    def _python_cmd(self, instance_id: str) -> list[str]:
        return [sys.executable, str(self.project_root / "main.py"), "--instance", instance_id]

    def validate_start(self, instance_id: str) -> tuple[bool, str, dict]:
        from gui.i18n import t

        meta: dict = {}
        if not is_multi_instance_enabled():
            return False, t("instances.multi_instance_disabled_msg"), {
                "action": "enable_multi_instance",
                "actionLabel": t("instances.enable_multi_instance"),
            }
        profile = get_instance_profile(instance_id)
        if not profile:
            return False, t("instances.readiness_unknown", id=instance_id), meta
        if not profile.get("enabled", True):
            return False, t("instances.instance_disabled", id=instance_id), meta
        collision = find_port_collision(instance_id, profile["emulator_port"])
        if collision:
            return False, t(
                "instances.port_in_use",
                port=profile["emulator_port"],
                collision=collision,
            ), {
                "action": "fix_port",
                "actionLabel": t("instances.fix_port"),
                "instanceId": instance_id,
            }
        live = resolve_instance(instance_id)
        if live and live.get("running"):
            return False, t("instances.already_running", id=instance_id), meta

        queue_path = self.project_root / str(profile.get("queue_path", ""))
        if not queue_path.exists() or not queue_has_data(queue_path):
            from utils import DEFAULT_QUEUE_PATH, LEGACY_QUEUE_PATH

            default_queue = self.project_root / DEFAULT_QUEUE_PATH
            if not default_queue.exists():
                default_queue = self.project_root / LEGACY_QUEUE_PATH
            if default_queue.exists() and queue_has_data(default_queue):
                queue_path.parent.mkdir(parents=True, exist_ok=True)
                queue_path.write_text(default_queue.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                return False, t("instances.no_queue_yet", id=instance_id), {
                    "action": "edit_farm_plan",
                    "actionLabel": t("instances.edit_farm_plan"),
                    "instanceId": instance_id,
                }
        return True, "OK", meta

    def start_instance(self, instance_id: str) -> tuple[bool, str, dict]:
        from gui.i18n import t

        ok, message, meta = self.validate_start(instance_id)
        if not ok:
            return False, message, meta
        process = subprocess.Popen(
            self._python_cmd(instance_id),
            cwd=str(self.project_root),
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if sys.platform == "win32" else 0,
        )
        self._processes[instance_id] = process
        self.align_windows(wait_seconds=2.0)
        return True, t("instances.started_instance", id=instance_id, pid=process.pid), meta

    def align_windows(self, wait_seconds: float = 0.0) -> tuple[bool, str]:
        from gui.i18n import t

        try:
            configured = len(list_instances())
            count = arrange_emulator_windows(max_windows=configured or None, wait_seconds=wait_seconds)
        except Exception as exc:
            return False, t("instances.align_failed", error=exc)
        if count <= 0:
            return False, t("instances.no_windows_to_align")
        return True, t("instances.aligned_windows", count=count)

    def stop_instance(self, instance_id: str, *, timeout: float = 20.0) -> tuple[bool, str, dict]:
        from gui.i18n import t

        live = resolve_instance(instance_id)
        state_path = live.get("state_path") if live else ""
        if state_path:
            write_state(state_path, STOP_REQUESTED)
        process = self._processes.get(instance_id)
        if process and process.poll() is None:
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
        elif live and live.get("pid"):
            deadline = time.time() + timeout
            while time.time() < deadline:
                if not process_is_alive(int(live["pid"])):
                    break
                time.sleep(0.5)
        self._processes.pop(instance_id, None)
        if live and live.get("pid") and process_is_alive(int(live["pid"])):
            return False, t("instances.stop_timeout", id=instance_id), {}
        return True, t("instances.stop_requested", id=instance_id), {}

    def restart_instance(self, instance_id: str) -> tuple[bool, str, dict]:
        ok, message, meta = self.stop_instance(instance_id)
        if not ok and "did not stop" in message:
            return False, message, meta
        return self.start_instance(instance_id)

    def start_all_ready(self) -> tuple[list[dict], str]:
        from gui.i18n import t
        from gui.instance_config import compute_instance_readiness

        results = []
        for profile in list_instances():
            instance_id = profile["id"]
            readiness = profile.get("readiness") or compute_instance_readiness(instance_id)
            if readiness.get("status") != "ready":
                results.append({
                    "id": instance_id,
                    "ok": False,
                    "message": readiness.get("message", t("common.unknown")),
                    **{k: readiness[k] for k in ("action", "actionLabel") if k in readiness},
                })
                continue
            if profile.get("running"):
                results.append({"id": instance_id, "ok": True, "message": t("instances.already_running_short")})
                continue
            ok, message, meta = self.start_instance(instance_id)
            results.append({"id": instance_id, "ok": ok, "message": message, **meta})
        started = sum(1 for item in results if item.get("ok"))
        return results, t("instances.started_summary", started=started, total=len(results))

    def stop_all(self) -> tuple[list[dict], str]:
        from gui.i18n import t

        results = []
        for profile in list_instances():
            if not profile.get("running"):
                results.append({"id": profile["id"], "ok": True, "message": t("instances.already_stopped")})
                continue
            ok, message, meta = self.stop_instance(profile["id"])
            results.append({"id": profile["id"], "ok": ok, "message": message, **meta})
        stopped = sum(1 for item in results if item.get("ok"))
        return results, t("instances.stop_summary", stopped=stopped)

    def list_status(self) -> list[dict]:
        statuses = []
        for item in list_instances():
            manifest = read_manifest(item["id"]) or {}
            process = self._processes.get(item["id"])
            pid = manifest.get("pid") or (process.pid if process and process.poll() is None else None)
            statuses.append({
                **item,
                "pid": pid,
                "running": bool(pid and process_is_alive(int(pid))),
            })
        return statuses
