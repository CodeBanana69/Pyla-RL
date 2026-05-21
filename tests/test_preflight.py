import unittest
from unittest.mock import patch

from gui.preflight import run_preflight_checks


class PreflightTests(unittest.TestCase):
    @patch("gui.preflight._run_adb")
    @patch("gui.preflight.shutil.which")
    def test_preflight_marks_required_checks(self, mock_which, mock_adb):
        mock_which.return_value = "tasklist"
        mock_adb.side_effect = [
            ("List of devices attached\n127.0.0.1:5555\tdevice", ""),
            ("Physical size: 1920x1080", ""),
        ]
        with patch("gui.preflight.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "dnplayer.exe"
            mock_run.return_value.returncode = 0
            result = run_preflight_checks(correct_zoom=True)
        self.assertTrue(any(item["id"] == "adb" for item in result["checks"]))
        self.assertIn("severity", result["checks"][0])


if __name__ == "__main__":
    unittest.main()
