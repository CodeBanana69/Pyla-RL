import subprocess
import unittest
from unittest.mock import MagicMock, patch

from subprocess_text import SUBPROCESS_TEXT_KWARGS, check_output_text, run_text


class SubprocessTextTests(unittest.TestCase):
    def test_subprocess_text_kwargs_include_utf8_replace(self):
        self.assertEqual(SUBPROCESS_TEXT_KWARGS["encoding"], "utf-8")
        self.assertEqual(SUBPROCESS_TEXT_KWARGS["errors"], "replace")
        self.assertTrue(SUBPROCESS_TEXT_KWARGS["text"])

    @patch("subprocess_text.subprocess.run")
    def test_run_text_forwards_utf8_decode_settings(self, run_mock):
        run_mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
        run_text(["echo", "test"], capture_output=True, timeout=5)
        run_mock.assert_called_once_with(
            ["echo", "test"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=5,
        )

    @patch("subprocess_text.subprocess.check_output")
    def test_check_output_text_forwards_utf8_decode_settings(self, check_mock):
        check_mock.return_value = "ok"
        check_output_text(["echo", "test"], stderr=subprocess.STDOUT)
        check_mock.assert_called_once_with(
            ["echo", "test"],
            encoding="utf-8",
            errors="replace",
            stderr=subprocess.STDOUT,
        )


if __name__ == "__main__":
    unittest.main()
