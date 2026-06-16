import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gui.hub_update_status import (
    check_update_status,
    default_update_status,
    launch_updater,
    read_effective_local_sha,
    resolve_updater_launcher,
)


class HubUpdateStatusTest(unittest.TestCase):
    def test_default_update_status_has_unknown_status(self):
        status = default_update_status()
        self.assertEqual(status["status"], "unknown")
        self.assertIn("currentVersion", status)
        self.assertEqual(status["updateSource"], "none")

    def test_check_update_status_current_when_shas_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            bundle = project / "app" / "cfg"
            bundle.mkdir(parents=True)
            (bundle / "update_info.json").write_text(
                json.dumps({"main_sha": "abc123def456", "updated_at": "2026-01-01"}),
                encoding="utf-8",
            )
            with patch("gui.hub_update_status.latest_main_sha", return_value="abc123def456"), patch(
                "gui.hub_update_status._latest_release_version",
                return_value="1.0.0",
            ), patch("gui.hub_update_status._current_version", return_value="0.9.0"), patch(
                "gui.hub_update_status.read_git_head_sha",
                return_value=None,
            ):
                status = check_update_status(project)
            self.assertEqual(status["status"], "current")
            self.assertEqual(status["localSha"], "abc123de")
            self.assertEqual(status["remoteSha"], "abc123de")
            self.assertEqual(status["updateSource"], "marker")

    def test_check_update_status_available_when_behind_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            bundle = project / "app" / "cfg"
            bundle.mkdir(parents=True)
            (bundle / "update_info.json").write_text(
                json.dumps({"main_sha": "oldsha111111", "updated_at": "2026-01-01"}),
                encoding="utf-8",
            )
            with patch("gui.hub_update_status.latest_main_sha", return_value="newsha222222"), patch(
                "gui.hub_update_status._latest_release_version",
                return_value="",
            ), patch("gui.hub_update_status._current_version", return_value="0.9.0"), patch(
                "gui.hub_update_status.read_git_head_sha",
                return_value=None,
            ):
                status = check_update_status(project)
            self.assertEqual(status["status"], "available")

    def test_check_update_status_unknown_without_remote_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            with patch("gui.hub_update_status.latest_main_sha", return_value=None):
                status = check_update_status(project)
            self.assertEqual(status["status"], "unknown")

    def test_check_update_status_detects_updater_exe_at_install_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "updater.exe").write_text("stub", encoding="utf-8")
            with patch("gui.hub_update_status.latest_main_sha", return_value="abc"), patch(
                "gui.hub_update_status.read_effective_local_sha",
                return_value=("abc", "marker"),
            ), patch("gui.hub_update_status._latest_release_version", return_value=""), patch(
                "gui.hub_update_status._current_version",
                return_value="1.0",
            ):
                status = check_update_status(project)
            self.assertTrue(status["hasUpdater"])
            self.assertEqual(status["updaterLauncher"], "updater.exe")

    def test_resolve_updater_launcher_prefers_exe_over_cmd(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "updater.exe").write_text("exe", encoding="utf-8")
            (project / "update.cmd").write_text("@echo off", encoding="utf-8")
            launcher = resolve_updater_launcher(project)
            self.assertEqual(launcher["kind"], "exe")

    def test_resolve_updater_launcher_falls_back_to_update_cmd(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "update.cmd").write_text("@echo off", encoding="utf-8")
            launcher = resolve_updater_launcher(project)
            self.assertEqual(launcher["kind"], "cmd")
            self.assertEqual(launcher["label"], "update.cmd")

    def test_read_effective_local_sha_prefers_git_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            bundle = project / "app" / "cfg"
            bundle.mkdir(parents=True)
            (bundle / "update_info.json").write_text(
                json.dumps({"main_sha": "oldsha111111"}),
                encoding="utf-8",
            )
            with patch("gui.hub_update_status.read_git_head_sha", return_value="gitsha999999"):
                sha, source = read_effective_local_sha(project)
            self.assertEqual(sha, "gitsha999999")
            self.assertEqual(source, "git")

    def test_check_update_status_current_when_git_head_matches_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            bundle = project / "app" / "cfg"
            bundle.mkdir(parents=True)
            (bundle / "update_info.json").write_text(
                json.dumps({"main_sha": "oldsha111111", "updated_at": "2026-01-01"}),
                encoding="utf-8",
            )
            with patch("gui.hub_update_status.latest_main_sha", return_value="gitsha999999"), patch(
                "gui.hub_update_status.read_git_head_sha",
                return_value="gitsha999999",
            ), patch("gui.hub_update_status.write_local_update_info") as write_mock, patch(
                "gui.hub_update_status._latest_release_version",
                return_value="",
            ), patch(
                "gui.hub_update_status._current_version",
                return_value="1.0",
            ):
                status = check_update_status(project)
            self.assertEqual(status["status"], "current")
            self.assertEqual(status["updateSource"], "git")
            write_mock.assert_called_once()

    def test_launch_updater_uses_cmd_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "update.cmd").write_text("@echo off", encoding="utf-8")
            with patch("gui.hub_update_status.subprocess.Popen") as popen_mock:
                ok, message = launch_updater(project)
            self.assertTrue(ok)
            self.assertIn("update.cmd", message)
            argv = popen_mock.call_args[0][0]
            self.assertEqual(argv[0], "cmd")


if __name__ == "__main__":
    unittest.main()
