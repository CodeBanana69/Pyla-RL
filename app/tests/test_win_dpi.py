import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import gui.win_dpi as win_dpi
from utils import get_dpi_scale


class WinDpiTests(unittest.TestCase):
    def setUp(self):
        win_dpi._BOOTSTRAPPED = False

    def test_get_dpi_scale_does_not_set_process_dpi_aware(self):
        user32 = MagicMock()
        user32.GetDpiForSystem.return_value = 120
        with patch.object(win_dpi.sys, "platform", "win32"), patch(
            "utils.ctypes.windll"
        ) as windll:
            windll.user32 = user32
            self.assertEqual(get_dpi_scale(), 120)
        user32.SetProcessDPIAware.assert_not_called()

    def test_get_dpi_scale_non_windows_defaults_to_96(self):
        with patch.object(win_dpi.sys, "platform", "linux"):
            self.assertEqual(get_dpi_scale(), 96)

    def test_bootstrap_windows_dpi_is_idempotent(self):
        user32 = MagicMock()
        user32.SetProcessDpiAwarenessContext.return_value = True
        with patch.object(win_dpi.sys, "platform", "win32"), patch(
            "gui.win_dpi.ctypes.windll"
        ) as windll:
            windll.user32 = user32
            windll.shcore = MagicMock()
            win_dpi.bootstrap_windows_dpi()
            win_dpi.bootstrap_windows_dpi()
        self.assertEqual(user32.SetProcessDpiAwarenessContext.call_count, 1)

    def test_configure_terminal_output_uses_runtime_log(self):
        with patch("runtime_log.configure") as configure, patch(
            "logger_setup.setup_logging_if_enabled",
            return_value=None,
        ), patch("platform.architecture", return_value=("64bit", "WindowsPE")):
            from main import configure_terminal_output

            configure_terminal_output()
        configure.assert_called_once()


if __name__ == "__main__":
    unittest.main()
