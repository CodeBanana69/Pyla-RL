import unittest
from unittest.mock import MagicMock, patch

from gui.preflight import run_preflight_checks
from gui.preflight_fixes import run_preflight_fix


class PreflightFixTests(unittest.TestCase):
    @patch("gui.preflight.save_dict_as_toml")
    @patch("gui.preflight.connect_emulator_adb")
    @patch("gui.preflight.detect_emulator_process", return_value=(False, "No LDPlayer process found"))
    @patch("gui.preflight.load_toml_as_dict")
    @patch("gui.preflight._run_adb")
    def test_fix_descriptors_on_failures(self, mock_adb, mock_config, _process, mock_connect, _save):
        mock_config.return_value = {"current_emulator": "LDPlayer", "emulator_port": 5555}
        mock_connect.return_value = {
            "ok": False,
            "detail": "ADB offline",
            "serial": "",
            "port": 5555,
        }
        mock_adb.return_value = ("", "")

        result = run_preflight_checks(correct_zoom=True, persist_port=False)
        adb = next(item for item in result["checks"] if item["id"] == "adb")
        emulator = next(item for item in result["checks"] if item["id"] == "emulator")
        self.assertEqual(adb["fix"]["action"], "reconnect_adb")
        self.assertEqual(emulator["fix"]["action"], "start_emulator")

    @patch("gui.preflight_fixes.connect_emulator_adb")
    @patch("gui.preflight_fixes.run_adb")
    def test_dispatch_reconnect_adb(self, mock_run_adb, mock_connect):
        mock_connect.return_value = {"ok": True, "detail": "connected", "serial": "127.0.0.1:5555"}
        ok, message = run_preflight_fix("reconnect_adb", emulator="ldplayer", port=5555)
        self.assertTrue(ok)
        mock_run_adb.assert_called_with(["kill-server"])

    def test_unknown_action(self):
        ok, message = run_preflight_fix("not_a_real_action")
        self.assertFalse(ok)
        self.assertIn("Unknown fix action", message)

    @patch("gui.preflight_fixes._start_emulator", return_value=(True, "started"))
    def test_fix_noop_when_check_passes_not_required(self, mock_start):
        ok, message = run_preflight_fix("start_emulator")
        self.assertTrue(ok)
        mock_start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
