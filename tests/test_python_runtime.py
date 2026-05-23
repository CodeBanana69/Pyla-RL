import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.python_runtime import (
    probe_cv2,
    read_python_pin,
    verify_cv2_import,
    write_python_pin,
    write_setup_status,
)


class PythonRuntimeTests(unittest.TestCase):
    def test_write_and_read_python_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            write_python_pin(project_dir, r"C:\Python311\python.exe")
            self.assertEqual(read_python_pin(project_dir), r"C:\Python311\python.exe")

    def test_probe_cv2_success(self):
        with patch("tools.python_runtime.subprocess.check_output", return_value='{"ok": true, "cv2": "4.8.0.76"}'):
            result = probe_cv2(["python"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["cv2"], "4.8.0.76")

    def test_verify_cv2_import_raises_when_missing(self):
        with patch("tools.python_runtime.probe_cv2", return_value={"ok": False, "executable": "python", "error": "No module named 'cv2'"}):
            with self.assertRaises(RuntimeError):
                verify_cv2_import(["python"])

    def test_write_setup_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            path = write_setup_status(
                project_dir,
                python_executable=r"C:\project\.venv\Scripts\python.exe",
                cv2_version="4.8.0.76",
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["cv2_version"], "4.8.0.76")


if __name__ == "__main__":
    unittest.main()
