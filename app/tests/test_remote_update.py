import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from telegram_control import TelegramControlServer
from tools import remote_update


class RemoteUpdateTests(unittest.TestCase):
    def test_build_updater_command_defaults_to_latest(self):
        command = remote_update.build_updater_command()

        self.assertEqual(command[0], sys.executable)
        self.assertTrue(command[1].endswith("updater.py"))
        self.assertIn("latest", command)

    def test_build_updater_command_supports_force_and_skip_setup(self):
        command = remote_update.build_updater_command("previous", force=True, skip_setup=True)

        self.assertIn("previous", command)
        self.assertIn("--force", command)
        self.assertIn("--skip-setup", command)

    def test_build_restart_command_single_uses_resume(self):
        command = remote_update.build_restart_command("single")

        self.assertEqual(command[0], sys.executable)
        self.assertTrue(command[1].endswith("main.py"))
        self.assertIn("--resume", command)

    def test_build_restart_command_instance_keeps_instance_id(self):
        command = remote_update.build_restart_command("instance", "ld-1")

        self.assertIn("--instance", command)
        self.assertIn("ld-1", command)
        self.assertNotIn("--resume", command)

    def test_request_stop_writes_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "runtime.state"
            remote_update.request_stop(state_path)

            self.assertEqual(state_path.read_text(encoding="utf-8"), "stop_requested")

    @patch("tools.remote_update.subprocess.Popen")
    def test_spawn_remote_update_passes_restart_metadata(self, mock_popen):
        mock_popen.return_value.pid = 123

        process = remote_update.spawn_remote_update(
            mode="instance",
            instance_id="ld-1",
            state_path="logs/runtime.state",
            ref="previous",
            force=True,
            pid=99,
            stop_delay=0,
        )

        command = mock_popen.call_args.args[0]
        self.assertEqual(process.pid, 123)
        self.assertIn("--mode", command)
        self.assertIn("instance", command)
        self.assertIn("--instance", command)
        self.assertIn("ld-1", command)
        self.assertIn("--state-path", command)
        self.assertIn("logs/runtime.state", command)
        self.assertIn("--ref", command)
        self.assertIn("previous", command)
        self.assertIn("--force", command)

    def test_telegram_update_args_parse_ref_and_force(self):
        ref, reinstall, immediate = TelegramControlServer._parse_update_args(["previous", "force"])

        self.assertEqual(ref, "previous")
        self.assertFalse(reinstall)
        self.assertTrue(immediate)

    def test_telegram_update_args_parse_reinstall_separately(self):
        ref, reinstall, immediate = TelegramControlServer._parse_update_args(["latest", "reinstall"])

        self.assertEqual(ref, "latest")
        self.assertTrue(reinstall)
        self.assertFalse(immediate)

    def test_update_lock_rejects_second_active_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "remote_update.lock"
            with patch("tools.remote_update.update_lock_path", return_value=lock_path):
                first_ok, _first = remote_update.acquire_update_lock(ref="latest")
                second_ok, second = remote_update.acquire_update_lock(ref="previous")

                self.assertTrue(first_ok)
                self.assertFalse(second_ok)
                self.assertEqual(second["ref"], "latest")

    def test_release_update_lock_removes_lock_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "remote_update.lock"
            with patch("tools.remote_update.update_lock_path", return_value=lock_path):
                remote_update.acquire_update_lock(ref="latest")
                remote_update.release_update_lock()

                self.assertFalse(lock_path.exists())

    def test_format_version_info_includes_version_and_commit(self):
        text = remote_update.format_version_info(
            {
                "version": "0.9.0",
                "commit": "abcdef123456",
                "commitSource": "git",
                "python": "3.11.9",
            }
        )

        self.assertIn("0.9.0", text)
        self.assertIn("abcdef12", text)
        self.assertIn("3.11.9", text)

    def test_format_update_status_available(self):
        text = remote_update.format_update_status(
            {
                "status": "available",
                "currentVersion": "0.9.0",
                "latestReleaseVersion": "1.0.0",
                "localSha": "oldsha",
                "remoteSha": "newsha",
                "updaterLauncher": "tools.updater",
            }
        )

        self.assertIn("Update available", text)
        self.assertIn("oldsha", text)
        self.assertIn("newsha", text)


if __name__ == "__main__":
    unittest.main()
