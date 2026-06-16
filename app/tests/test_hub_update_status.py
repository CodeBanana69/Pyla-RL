import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gui.hub_update_status import check_update_status, default_update_status


class HubUpdateStatusTest(unittest.TestCase):
    def test_default_update_status_has_unknown_status(self):
        status = default_update_status()
        self.assertEqual(status["status"], "unknown")
        self.assertIn("currentVersion", status)

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
            ), patch("gui.hub_update_status._current_version", return_value="0.9.0"):
                status = check_update_status(project)
            self.assertEqual(status["status"], "current")
            self.assertEqual(status["localSha"], "abc123de")
            self.assertEqual(status["remoteSha"], "abc123de")

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
            ), patch("gui.hub_update_status._current_version", return_value="0.9.0"):
                status = check_update_status(project)
            self.assertEqual(status["status"], "available")

    def test_check_update_status_unknown_without_remote_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            with patch("gui.hub_update_status.latest_main_sha", return_value=None):
                status = check_update_status(project)
            self.assertEqual(status["status"], "unknown")

    def test_check_update_status_detects_updater_exe(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "updater.exe").write_text("stub", encoding="utf-8")
            with patch("gui.hub_update_status.latest_main_sha", return_value="abc"), patch(
                "gui.hub_update_status.read_local_update_sha",
                return_value="abc",
            ), patch("gui.hub_update_status._latest_release_version", return_value=""), patch(
                "gui.hub_update_status._current_version",
                return_value="1.0",
            ):
                status = check_update_status(project)
            self.assertTrue(status["hasUpdater"])


if __name__ == "__main__":
    unittest.main()
