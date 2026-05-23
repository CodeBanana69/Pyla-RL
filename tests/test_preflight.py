import unittest
from unittest.mock import patch

from gui.preflight import run_preflight_checks


class PreflightTests(unittest.TestCase):
    def _general_config(self):
        return {"current_emulator": "LDPlayer", "emulator_port": 5555}

    @patch("gui.preflight.save_dict_as_toml")
    @patch("gui.preflight.connect_emulator_adb")
    @patch("gui.preflight.detect_emulator_process")
    @patch("gui.preflight.load_toml_as_dict")
    @patch("gui.preflight._run_adb")
    def test_preflight_ready_when_adb_ok_even_if_process_missing(
        self,
        mock_adb,
        mock_config,
        mock_process,
        mock_connect,
        _save,
    ):
        mock_config.return_value = self._general_config()
        mock_connect.return_value = {
            "ok": True,
            "serial": "127.0.0.1:5555",
            "port": 5555,
            "detail": "Connected to 127.0.0.1:5555",
            "ports_tried": [5555, 5557, 5559, 5554],
        }
        mock_process.return_value = (False, "No LDPlayer process found")
        mock_adb.side_effect = [
            ("com.supercell.brawlstars", ""),
            ("Physical size: 1920x1080", ""),
        ]

        result = run_preflight_checks(correct_zoom=True, persist_port=False)

        self.assertTrue(result["ready"])
        emulator = next(item for item in result["checks"] if item["id"] == "emulator")
        self.assertEqual(emulator["severity"], "recommended")
        self.assertFalse(emulator["ok"])

    @patch("gui.preflight.save_dict_as_toml")
    @patch("gui.preflight.connect_emulator_adb")
    @patch("gui.preflight.detect_emulator_process", return_value=(True, "Detected dnplayer.exe"))
    @patch("gui.preflight.load_toml_as_dict")
    @patch("gui.preflight._run_adb")
    def test_preflight_honors_emulator_override(
        self,
        mock_adb,
        mock_config,
        _process,
        mock_connect,
        _save,
    ):
        mock_config.return_value = {"current_emulator": "MuMu", "emulator_port": 16384}
        mock_connect.return_value = {
            "ok": True,
            "serial": "127.0.0.1:5557",
            "port": 5557,
            "detail": "Connected to 127.0.0.1:5557",
            "ports_tried": [5555, 5557, 5559, 5554],
        }
        mock_adb.side_effect = [
            ("com.supercell.brawlstars", ""),
            ("Physical size: 1920x1080", ""),
        ]

        result = run_preflight_checks(emulator="ldplayer", port=5555, persist_port=False)

        mock_connect.assert_called_once_with("LDPlayer", 5555)
        self.assertEqual(result["emulator"], "LDPlayer")
        self.assertTrue(result["ready"])

    @patch("gui.preflight.save_dict_as_toml")
    @patch("gui.preflight.connect_emulator_adb")
    @patch("gui.preflight.detect_emulator_process", return_value=(True, "Detected dnplayer.exe"))
    @patch("gui.preflight.load_toml_as_dict")
    def test_preflight_fails_when_adb_missing(self, mock_config, _process, mock_connect, _save):
        mock_config.return_value = self._general_config()
        mock_connect.return_value = {
            "ok": False,
            "serial": "",
            "port": 0,
            "detail": "No LDPlayer ADB device online on ports 5555, 5557, 5559, 5554",
            "ports_tried": [5555, 5557, 5559, 5554],
        }

        result = run_preflight_checks(persist_port=False)

        self.assertFalse(result["ready"])
        adb = next(item for item in result["checks"] if item["id"] == "adb")
        self.assertIn("5557", adb["detail"])


if __name__ == "__main__":
    unittest.main()
