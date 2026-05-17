import unittest
from unittest.mock import Mock, patch

from window_controller import (
    WindowController,
    _is_adb_serial_online,
    _is_local_adb_serial,
    _ADB_ONLINE_CACHE,
    _infer_ldplayer_index,
    _infer_mumu_index,
    _normalize_emulator_config,
)


class EmulatorProfileMappingTest(unittest.TestCase):
    def test_mumu_ports_map_to_matching_profile_index(self):
        self.assertEqual(_infer_mumu_index(16384), 0)
        self.assertEqual(_infer_mumu_index(16416), 1)
        self.assertEqual(_infer_mumu_index(16448), 2)

    def test_ldplayer_ports_map_to_matching_profile_index(self):
        self.assertEqual(_infer_ldplayer_index(5555), 0)
        self.assertEqual(_infer_ldplayer_index(5557), 1)
        self.assertEqual(_infer_ldplayer_index(5559), 2)

    def test_old_unsupported_emulator_config_never_uses_adb_server_port(self):
        emulator, port = _normalize_emulator_config("BlueStacks", 5037)

        self.assertEqual(emulator, "LDPlayer")
        self.assertEqual(port, 0)

    def test_mumu_config_keeps_supported_port(self):
        emulator, port = _normalize_emulator_config("MuMu", 16448)

        self.assertEqual(emulator, "MuMu")
        self.assertEqual(port, 16448)

    def test_restart_target_follows_actual_connected_mumu_device(self):
        controller = object.__new__(WindowController)
        controller.selected_emulator = "MuMu"
        controller.connected_serial = "127.0.0.1:16448"
        controller.configured_port = 16384
        controller.configured_serial = "127.0.0.1:16384"
        controller.emulator_profile_index = 0
        controller.emulator_profile_index_is_auto = True

        controller.sync_restart_target_to_connected_device()

        self.assertEqual(controller.configured_port, 16448)
        self.assertEqual(controller.configured_serial, "127.0.0.1:16448")
        self.assertEqual(controller.emulator_profile_index, 2)

    def test_local_adb_serial_detection(self):
        self.assertTrue(_is_local_adb_serial("127.0.0.1:16448"))
        self.assertTrue(_is_local_adb_serial("emulator-5554"))
        self.assertFalse(_is_local_adb_serial("192.168.10.231:5555"))

    def test_adb_online_check_uses_cache(self):
        _ADB_ONLINE_CACHE.clear()
        _ADB_ONLINE_CACHE["127.0.0.1:16448"] = (__import__("time").time(), True)

        self.assertTrue(_is_adb_serial_online("127.0.0.1:16448"))

    @patch("window_controller.os.name", "nt")
    @patch("window_controller.ctypes.windll")
    @patch("window_controller.subprocess.run")
    def test_emulator_launch_retries_with_uac_when_windows_requires_elevation(self, mock_run, mock_windll):
        controller = object.__new__(WindowController)
        controller.selected_emulator = "LDPlayer"
        controller.emulator_profile_index = 0
        controller.configured_serial = "127.0.0.1:5555"
        controller.emulator_launch_command = ["C:\\LDPlayer\\ldconsole.exe", "launch", "--index", "0"]
        error = OSError("The requested operation requires elevation")
        error.winerror = 740
        mock_run.side_effect = error
        mock_windll.shell32.ShellExecuteW.return_value = 33

        self.assertTrue(controller.run_emulator_command("launch", wait=True))
        mock_windll.shell32.ShellExecuteW.assert_called_once()

    @patch("window_controller.os.name", "nt")
    @patch("window_controller.ctypes.windll")
    def test_elevated_emulator_launch_reports_cancelled_uac(self, mock_windll):
        controller = object.__new__(WindowController)
        controller.selected_emulator = "LDPlayer"
        mock_windll.shell32.ShellExecuteW.return_value = 5

        self.assertFalse(controller._run_emulator_command_elevated(["C:\\LDPlayer\\ldconsole.exe"], "launch"))


if __name__ == "__main__":
    unittest.main()
