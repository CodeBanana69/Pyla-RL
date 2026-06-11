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
        self.assertIn("emulator_status", result)
        self.assertIn("ldplayer", result["emulator_status"])
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

        mock_connect.assert_any_call("LDPlayer", 5555)
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
        self.assertFalse(result["emulator_status"]["ldplayer"]["ok"])
        adb = next(item for item in result["checks"] if item["id"] == "adb")
        self.assertIn("5557", adb["detail"])
        emulator = next(item for item in result["checks"] if item["id"] == "emulator")
        self.assertTrue(emulator["ok"])
        self.assertIn("Detected dnplayer.exe", emulator["detail"])
        self.assertNotIn("ADB device online", emulator["detail"])

    @patch("gui.preflight.save_dict_as_toml")
    @patch("gui.preflight.connect_emulator_adb")
    @patch("gui.preflight.detect_emulator_process")
    @patch("gui.preflight.load_toml_as_dict")
    @patch("gui.preflight._run_adb")
    def test_preflight_emulator_status_keeps_process_and_adb_details_separate(
        self,
        mock_adb,
        mock_config,
        mock_process,
        mock_connect,
        _save,
    ):
        mock_config.return_value = {"current_emulator": "MuMu", "emulator_port": 16384}
        mock_process.return_value = (True, "Detected mumuplayer.exe")
        mock_connect.return_value = {
            "ok": False,
            "serial": "",
            "port": 0,
            "detail": (
                "MuMu is running but local ADB is not reachable on 127.0.0.1:16384. "
                "Ignoring non-local device(s): 192.168.1.116:5555"
            ),
            "ports_tried": [16384, 16416, 16448, 7555, 5558, 5557, 5556, 5555, 5554],
        }
        mock_adb.return_value = ("", "")

        result = run_preflight_checks(persist_port=False)

        mumu_status = result["emulator_status"]["mumu"]
        self.assertTrue(mumu_status["process_ok"])
        self.assertFalse(mumu_status["adb_ok"])
        self.assertEqual(mumu_status["process_detail"], "Detected mumuplayer.exe")
        self.assertIn("local ADB is not reachable", mumu_status["detail"])
        emulator = next(item for item in result["checks"] if item["id"] == "emulator")
        self.assertEqual(emulator["detail"], "Detected mumuplayer.exe")


if __name__ == "__main__":
    unittest.main()
