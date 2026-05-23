import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gui.emulator_adb import (
    adb_connect_serial,
    cleanup_conflicting_devices,
    conflicting_serials,
    connect_emulator_adb,
    detect_emulator_process,
    is_adb_ambiguity_error,
    normalize_emulator_name,
    ports_for_emulator,
)
from tools.launcher_bat import LEGACY_BAT_NAMES, RUN_BAT_NAME, create_run_file


class EmulatorAdbTests(unittest.TestCase):
    def test_normalize_emulator_name(self):
        self.assertEqual(normalize_emulator_name("mumu"), "MuMu")
        self.assertEqual(normalize_emulator_name("LDPlayer"), "LDPlayer")
        self.assertEqual(normalize_emulator_name(""), "LDPlayer")

    def test_ports_for_emulator_ldplayer_only(self):
        ports = ports_for_emulator("LDPlayer", 5555)
        self.assertEqual(ports[0], 5555)
        self.assertIn(5557, ports)
        self.assertNotIn(16384, ports)

    def test_ports_for_emulator_mumu_only(self):
        ports = ports_for_emulator("MuMu", 16384)
        self.assertEqual(ports[0], 16384)
        self.assertIn(16416, ports)
        self.assertNotIn(5559, ports)

    def test_conflicting_serials_for_ldplayer_port(self):
        serials = conflicting_serials(5555, keep_serial="127.0.0.1:5555")
        self.assertIn("emulator-5554", serials)
        self.assertNotIn("127.0.0.1:5555", serials)

    def test_is_adb_ambiguity_error(self):
        self.assertTrue(is_adb_ambiguity_error("adb.exe: error: more than one device/emulator"))
        self.assertFalse(is_adb_ambiguity_error("device not found"))

    @patch("gui.emulator_adb.adb_connect_serial")
    @patch("gui.emulator_adb.cleanup_conflicting_devices")
    @patch("gui.emulator_adb.adb_start_server")
    @patch("gui.emulator_adb.list_adb_devices")
    @patch("gui.emulator_adb.is_port_open", return_value=False)
    def test_connect_emulator_adb_cleans_before_connect(
        self,
        _open,
        mock_devices,
        _start,
        mock_cleanup,
        mock_connect,
    ):
        mock_devices.return_value = ([], "")
        mock_connect.return_value = (True, "connected")
        result = connect_emulator_adb("LDPlayer", 5555, probe_open_ports=False)
        self.assertTrue(result["ok"])
        mock_cleanup.assert_called()
        mock_connect.assert_called()

    @patch("gui.emulator_adb.list_adb_devices")
    @patch("gui.emulator_adb.cleanup_conflicting_devices")
    @patch("gui.emulator_adb._run_adb")
    def test_adb_connect_serial_disconnects_conflicts_first(self, mock_run, mock_cleanup, mock_devices):
        mock_devices.side_effect = [
            (["emulator-5554"], ""),
            (["127.0.0.1:5555"], ""),
        ]
        mock_run.side_effect = [
            ("disconnected", ""),
            ("connected to 127.0.0.1:5555", ""),
        ]
        ok, message = adb_connect_serial("127.0.0.1:5555", disconnect_first=True)
        self.assertTrue(ok)
        mock_cleanup.assert_called_once_with(5555, keep_serial="127.0.0.1:5555")
        self.assertIn("connected", message.lower())

    @patch("gui.emulator_adb.adb_start_server")
    @patch("gui.emulator_adb.list_adb_devices")
    @patch("gui.emulator_adb.adb_connect_serial")
    @patch("gui.emulator_adb.is_port_open", return_value=False)
    def test_connect_emulator_adb_tries_ldplayer_ports(self, _open, mock_connect, mock_devices, _start):
        mock_devices.return_value = ([], "")
        mock_connect.side_effect = [
            (False, "fail 5555"),
            (True, "connected"),
        ]
        result = connect_emulator_adb("LDPlayer", 5555, probe_open_ports=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["port"], 5557)
        self.assertEqual(result["serial"], "127.0.0.1:5557")
        tried = [call.args[0] for call in mock_connect.call_args_list]
        self.assertEqual(tried[0], "127.0.0.1:5555")
        self.assertEqual(tried[1], "127.0.0.1:5557")
        self.assertTrue(all(":16384" not in serial for serial in tried))

    @patch("gui.emulator_adb.shutil.which", return_value="tasklist")
    @patch("gui.emulator_adb.subprocess.run")
    def test_detect_ldplayer_process_names(self, mock_run, _which):
        mock_run.return_value.stdout = "LDPlayer.exe"
        mock_run.return_value.returncode = 0
        ok, detail = detect_emulator_process("LDPlayer")
        self.assertTrue(ok)
        self.assertIn("ldplayer.exe", detail.lower())


class LauncherBatTests(unittest.TestCase):
    def test_create_run_file_removes_legacy_and_writes_single_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            legacy = project_dir / LEGACY_BAT_NAMES[0]
            legacy.write_text("legacy", encoding="ascii")

            create_run_file(project_dir, python_executable=r"C:\Python311\python.exe")

            self.assertFalse(legacy.exists())
            run_bat = project_dir / RUN_BAT_NAME
            self.assertTrue(run_bat.exists())
            content = run_bat.read_text(encoding="ascii")
            self.assertIn("main.py", content)
            self.assertIn("py -3.11-64", content)


if __name__ == "__main__":
    unittest.main()
