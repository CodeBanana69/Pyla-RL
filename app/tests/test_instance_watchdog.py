import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import toml

from utils import clear_toml_cache


class InstanceWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "cfg").mkdir(parents=True, exist_ok=True)
        (self.root / "logs" / "instances").mkdir(parents=True, exist_ok=True)
        (self.root / "instances" / "default").mkdir(parents=True, exist_ok=True)
        (self.root / "cfg" / "instances.toml").write_text(
            toml.dumps({
                "multi_instance": {
                    "enabled": True,
                    "default_instance": "default",
                    "auto_restart_crashed": True,
                },
                "instances": {
                    "default": {
                        "name": "Default",
                        "enabled": True,
                        "emulator": "ldplayer",
                        "emulator_port": 5555,
                        "emulator_profile_index": "0",
                        "queue_path": "instances/default/latest_brawler_data.json",
                    },
                },
            }),
            encoding="utf-8",
        )
        clear_toml_cache()

    @patch("utils.resolve_project_path")
    @patch("gui.instance_config.resolve_project_path")
    @patch("gui.instance_watchdog.process_is_alive", return_value=False)
    def test_watchdog_restarts_dead_worker(self, mock_alive, mock_resolve, mock_utils_resolve):
        mock_resolve.side_effect = lambda path: str(self.root / path)
        mock_utils_resolve.side_effect = lambda path: str(self.root / path)

        manifest = {
            "instance_id": "default",
            "pid": 4242,
            "started_at": time.time(),
            "heartbeat_at": time.time(),
        }
        (self.root / "logs" / "instances" / "default.json").write_text(
            __import__("json").dumps(manifest),
            encoding="utf-8",
        )

        supervisor = MagicMock()
        supervisor.start_instance.return_value = (True, "started", {})
        supervisor.stop_instance.return_value = (True, "stopped", {})

        from gui.instance_watchdog import InstanceWatchdog

        with patch("gui.instance_registry.MANIFEST_DIR", str(self.root / "logs" / "instances")):
            watchdog = InstanceWatchdog(supervisor)
            actions = watchdog.poll_once()
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["reason"], "dead")
        supervisor.start_instance.assert_called_once_with("default")

    @patch("utils.resolve_project_path")
    @patch("gui.instance_config.resolve_project_path")
    def test_watchdog_disabled_is_noop(self, mock_resolve, mock_utils_resolve):
        mock_resolve.side_effect = lambda path: str(self.root / path)
        mock_utils_resolve.side_effect = lambda path: str(self.root / path)
        data = toml.loads((self.root / "cfg" / "instances.toml").read_text(encoding="utf-8"))
        data["multi_instance"]["auto_restart_crashed"] = False
        (self.root / "cfg" / "instances.toml").write_text(toml.dumps(data), encoding="utf-8")
        clear_toml_cache()

        supervisor = MagicMock()
        from gui.instance_watchdog import InstanceWatchdog

        watchdog = InstanceWatchdog(supervisor)
        self.assertEqual(watchdog.poll_once(), [])
        supervisor.start_instance.assert_not_called()

    @patch("utils.resolve_project_path")
    @patch("gui.instance_config.resolve_project_path")
    @patch("gui.instance_watchdog.process_is_alive", return_value=True)
    def test_watchdog_restarts_stale_heartbeat(self, mock_alive, mock_resolve, mock_utils_resolve):
        mock_resolve.side_effect = lambda path: str(self.root / path)
        mock_utils_resolve.side_effect = lambda path: str(self.root / path)

        manifest = {
            "instance_id": "default",
            "pid": 4242,
            "started_at": time.time(),
            "heartbeat_at": time.time() - 600,
        }
        (self.root / "logs" / "instances" / "default.json").write_text(
            __import__("json").dumps(manifest),
            encoding="utf-8",
        )

        supervisor = MagicMock()
        supervisor.start_instance.return_value = (True, "started", {})
        supervisor.stop_instance.return_value = (True, "stopped", {})

        from gui.instance_watchdog import InstanceWatchdog

        with patch("gui.instance_registry.MANIFEST_DIR", str(self.root / "logs" / "instances")):
            watchdog = InstanceWatchdog(supervisor)
            actions = watchdog.poll_once()
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["reason"], "frozen")
        supervisor.stop_instance.assert_called_once_with("default")
        supervisor.start_instance.assert_called_once_with("default")

    def test_backoff_progression(self):
        from gui.instance_watchdog import InstanceWatchdog, BACKOFF_INITIAL_SECONDS

        supervisor = MagicMock()
        watchdog = InstanceWatchdog(supervisor)
        now = 1000.0
        watchdog._record_restart("default", now)
        entry = watchdog._backoff["default"]
        self.assertGreaterEqual(entry["next_allowed_at"], now + BACKOFF_INITIAL_SECONDS)
        watchdog._record_restart("default", entry["next_allowed_at"])
        self.assertGreater(entry["delay"], BACKOFF_INITIAL_SECONDS)


if __name__ == "__main__":
    unittest.main()
