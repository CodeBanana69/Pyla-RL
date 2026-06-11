from __future__ import annotations

from pathlib import Path

from discord_control import DiscordControlServer
from gui.instance_registry import list_instances
from gui.instance_supervisor import InstanceSupervisor
from daily_digest import DailyDigestScheduler
from gui.instance_watchdog import InstanceWatchdog
from gui.remote_command_router import RemoteCommandRouter
from runtime_control import RUNNING, write_state
from telegram_control import TelegramControlServer


class MultiInstanceService:
    def __init__(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.supervisor = InstanceSupervisor(self.project_root)
        self.watchdog = InstanceWatchdog(self.supervisor)
        self.digest_scheduler = DailyDigestScheduler()
        self.router = RemoteCommandRouter()
        self.state_path = self.project_root / "logs" / "runtime_control_supervisor.state"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        write_state(self.state_path, RUNNING)
        self.discord_control = DiscordControlServer(
            self.state_path,
            command_router=self.router,
        )
        self.telegram_control = TelegramControlServer(
            self.state_path,
            command_router=self.router,
        )

    def start(self) -> None:
        self.discord_control.start()
        self.telegram_control.start()
        self.watchdog.start()
        self.digest_scheduler.start()

    def close(self) -> None:
        self.digest_scheduler.stop()
        self.watchdog.stop()
        self.discord_control.close()
        self.telegram_control.close()

    def list_instances(self):
        return list_instances()

    def list_available_emulators(self):
        from gui.instance_config import list_available_emulator_instances, list_unassigned_emulator_instances

        return {
            "all": list_available_emulator_instances(),
            "unassigned": list_unassigned_emulator_instances(),
        }

    def start_instance(self, instance_id: str):
        ok, message, meta = self.supervisor.start_instance(instance_id)
        return ok, message, meta

    def stop_instance(self, instance_id: str):
        ok, message, meta = self.supervisor.stop_instance(instance_id)
        return ok, message, meta

    def restart_instance(self, instance_id: str):
        ok, message, meta = self.supervisor.restart_instance(instance_id)
        return ok, message, meta

    def align_windows(self):
        return self.supervisor.align_windows()

    def start_all_ready(self):
        return self.supervisor.start_all_ready()

    def stop_all(self):
        return self.supervisor.stop_all()

    def quick_add_instances(self, payload: dict | None = None):
        from gui.instance_config import quick_add_emulator_instances

        items = (payload or {}).get("items")
        copy_from = (payload or {}).get("copy_farm_plan_from", "default")
        created = quick_add_emulator_instances(items, copy_farm_plan_from=copy_from or None)
        return created
