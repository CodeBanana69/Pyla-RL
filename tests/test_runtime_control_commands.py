import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from runtime_control import (
    control_command_path,
    minimize_frameless_window,
    read_and_clear_control_command,
    write_control_command,
)


class RuntimeControlCommandTests(unittest.TestCase):
    def test_command_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "runtime_control_12345.state"
            state_path.write_text("running", encoding="utf-8")
            write_control_command(state_path, "show")
            self.assertEqual(control_command_path(state_path).read_text(encoding="utf-8"), "show")
            self.assertEqual(read_and_clear_control_command(state_path), "show")
            self.assertFalse(control_command_path(state_path).exists())
            self.assertEqual(read_and_clear_control_command(state_path), "")

    @patch("runtime_control.sys.platform", "win32")
    @patch("runtime_control.ctypes.windll.user32.ShowWindow")
    @patch("runtime_control.ctypes.windll.user32.GetParent", return_value=0)
    def test_minimize_frameless_window_uses_win32_api(self, _mock_parent, mock_show):
        window = MagicMock()
        window.winfo_id.return_value = 12345

        self.assertTrue(minimize_frameless_window(window))
        mock_show.assert_called_once_with(12345, 6)


if __name__ == "__main__":
    unittest.main()
