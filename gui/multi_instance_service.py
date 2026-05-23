from __future__ import annotations

from pathlib import Path

from discord_control import DiscordControlServer
from gui.instance_registry import list_instances
from gui.instance_supervisor import InstanceSupervisor
from gui.remote_command_router import RemoteCommandRouter
from runtime_control import RUNNING, write_state
from telegram_control import TelegramControlServer


class MultiInstanceService:
    def __init__(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.supervisor = InstanceSupervisor(self.project_root)
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

    def close(self) -> None:
        self.discord_control.close()
        self.telegram_control.close()

    def list_instances(self):
        return list_instances()

    def start_instance(self, instance_id: str):
        return self.supervisor.start_instance(instance_id)

    def stop_instance(self, instance_id: str):
        return self.supervisor.stop_instance(instance_id)

    def restart_instance(self, instance_id: str):
        return self.supervisor.restart_instance(instance_id)
