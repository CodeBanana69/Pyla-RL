import unittest
from unittest.mock import patch

from tools.dependency_repair import (
    repair_all_conflicts,
    verify_pip_health,
)


class DependencyRepairTests(unittest.TestCase):
    @patch("tools.dependency_repair.repair_scrcpy_stack")
    @patch("tools.dependency_repair.repair_opencv_conflicts")
    @patch("gpu_runtime_install.repair_numpy")
    def test_repair_all_conflicts_runs_numpy_then_opencv_then_scrcpy(
        self,
        mock_repair_numpy,
        mock_repair_opencv,
        mock_repair_scrcpy,
    ):
        repair_all_conflicts(["python"], verbose=True)

        mock_repair_numpy.assert_called_once()
        mock_repair_opencv.assert_called_once()
        mock_repair_scrcpy.assert_called_once()

    @patch("tools.dependency_repair.run_text")
    def test_verify_pip_health_allows_known_easyocr_warning(self, mock_run_text):
        mock_run_text.return_value.returncode = 1
        mock_run_text.return_value.stdout = (
            "easyocr 1.7.2 requires opencv-python-headless, which is not installed.\n"
        )
        mock_run_text.return_value.stderr = ""

        ok, issues = verify_pip_health(["python"])

        self.assertTrue(ok)
        self.assertEqual(issues, [])

    @patch("tools.dependency_repair.run_text")
    def test_verify_pip_health_allows_known_scrcpy_has_requirement_warning(self, mock_run_text):
        mock_run_text.return_value.returncode = 1
        mock_run_text.return_value.stdout = (
            "scrcpy-client 0.4.7 has requirement adbutils<2.0.0,>=1.0.8, but you have adbutils 2.12.0.\n"
        )
        mock_run_text.return_value.stderr = ""

        ok, issues = verify_pip_health(["python"])

        self.assertTrue(ok)
        self.assertEqual(issues, [])

    @patch("tools.dependency_repair.run_text")
    def test_verify_pip_health_fails_on_unknown_conflict(self, mock_run_text):
        mock_run_text.return_value.returncode = 1
        mock_run_text.return_value.stdout = "somepackage 1.0 requires missing-dep, which is not installed.\n"
        mock_run_text.return_value.stderr = ""

        ok, issues = verify_pip_health(["python"])

        self.assertFalse(ok)
        self.assertEqual(len(issues), 1)


if __name__ == "__main__":
    unittest.main()
