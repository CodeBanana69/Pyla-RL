import unittest
from unittest.mock import patch

from gui.preflight import run_preflight_checks


class PreflightTests(unittest.TestCase):
    def _devices_output(self):
        return "List of devices attached\n127.0.0.1:5555\tdevice", ""

    def _general_config(self):
        return {"current_emulator": "LDPlayer", "emulator_port": 5555}

    @patch("gui.preflight.load_toml_as_dict")
    @patch("gui.preflight._adb_executable")
    @patch("gui.preflight._run_adb")
    @patch("gui.preflight.shutil.which")
    def test_preflight_marks_required_checks(self, mock_which, mock_adb, mock_adb_exe, mock_config):
        mock_config.return_value = self._general_config()
        mock_which.return_value = "tasklist"
        mock_adb_exe.return_value = r"C:\project\adb.exe"
        mock_adb.side_effect = [
            self._devices_output(),
            self._devices_output(),
            ("com.supercell.brawlstars", ""),
            ("Physical size: 1920x1080", ""),
        ]
        with patch("gui.preflight.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "dnplayer.exe"
            mock_run.return_value.returncode = 0
            result = run_preflight_checks(correct_zoom=True)
        self.assertTrue(any(item["id"] == "adb" for item in result["checks"]))
        self.assertIn("severity", result["checks"][0])
        resolution = next(item for item in result["checks"] if item["id"] == "resolution")
        self.assertTrue(resolution["ok"])
        self.assertIn("1920x1080", resolution["detail"])

    @patch("gui.preflight.load_toml_as_dict")
    @patch("gui.preflight._adb_executable")
    @patch("gui.preflight._run_adb")
    @patch("gui.preflight.shutil.which")
    def test_preflight_accepts_half_scale_1080p(self, mock_which, mock_adb, mock_adb_exe, mock_config):
        mock_config.return_value = self._general_config()
        mock_which.return_value = "tasklist"
        mock_adb_exe.return_value = r"C:\project\adb.exe"
        mock_adb.side_effect = [
            self._devices_output(),
            self._devices_output(),
            ("com.supercell.brawlstars", ""),
            ("Physical size: 960x540", ""),
        ]
        with patch("gui.preflight.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "dnplayer.exe"
            mock_run.return_value.returncode = 0
            result = run_preflight_checks(correct_zoom=True)
        resolution = next(item for item in result["checks"] if item["id"] == "resolution")
        self.assertTrue(resolution["ok"])
        self.assertIn("half-scale", resolution["detail"])

    @patch("gui.preflight.load_toml_as_dict")
    @patch("gui.preflight._adb_executable")
    @patch("gui.preflight._run_adb")
    @patch("gui.preflight.shutil.which")
    def test_preflight_connects_before_adb_check(self, mock_which, mock_adb, mock_adb_exe, mock_config):
        mock_config.return_value = self._general_config()
        mock_which.return_value = "tasklist"
        mock_adb_exe.return_value = r"C:\project\adb.exe"
        mock_adb.side_effect = [
            ("List of devices attached", ""),
            ("List of devices attached", ""),
            ("List of devices attached", ""),
            ("connected to 127.0.0.1:5555", ""),
            self._devices_output(),
            ("com.supercell.brawlstars", ""),
            ("Physical size: 1280x720", ""),
        ]
        with patch("gui.preflight.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "dnplayer.exe"
            mock_run.return_value.returncode = 0
            result = run_preflight_checks(correct_zoom=True)
        adb = next(item for item in result["checks"] if item["id"] == "adb")
        self.assertTrue(adb["ok"])
        connect_calls = [
            call for call in mock_adb.call_args_list
            if call.args and call.args[0] and call.args[0][0] == "connect"
        ]
        self.assertEqual(len(connect_calls), 1)


if __name__ == "__main__":
    unittest.main()
