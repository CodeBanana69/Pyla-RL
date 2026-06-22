import json
import unittest
from unittest.mock import MagicMock, patch

from tools.easyocr_runtime import (
    EASYOCR_MANUAL_DEPS,
    EASYOCR_REPAIR_HINT,
    install_easyocr_stack,
    probe_easyocr_runtime,
    verify_easyocr_runtime,
)


class EasyOCRRuntimeTest(unittest.TestCase):
    def test_manual_deps_include_scipy_and_pyyaml(self):
        self.assertIn("scipy", EASYOCR_MANUAL_DEPS)
        self.assertIn("PyYAML", EASYOCR_MANUAL_DEPS)
        self.assertIn("scikit-image", EASYOCR_MANUAL_DEPS)

    @patch("tools.easyocr_runtime.subprocess.run")
    def test_probe_easyocr_runtime_parses_json(self, mock_run):
        payload = {
            "ok": True,
            "executable": r"C:\venv\python.exe",
            "versions": {"torch": "2.1.0"},
            "models_ready": False,
            "error": "",
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(payload) + "\n",
            stderr="",
        )
        result = probe_easyocr_runtime([r"C:\venv\python.exe"], smoke_test=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["versions"]["torch"], "2.1.0")
        mock_run.assert_called_once()
        self.assertIn("smoke_test = False", mock_run.call_args.args[0][-1])

    @patch("tools.easyocr_runtime.subprocess.run")
    def test_probe_easyocr_runtime_smoke_test_flag(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"ok": True, "models_ready": True, "error": "", "versions": {}}) + "\n",
            stderr="",
        )
        probe_easyocr_runtime(["python"], smoke_test=True)
        self.assertIn("smoke_test = True", mock_run.call_args.args[0][-1])

    @patch("tools.easyocr_runtime.probe_easyocr_runtime")
    def test_verify_easyocr_runtime_raises_on_failure(self, mock_probe):
        mock_probe.return_value = {"ok": False, "error": "scipy: missing", "executable": "python"}
        with self.assertRaises(RuntimeError) as ctx:
            verify_easyocr_runtime(["python"])
        self.assertIn("scipy: missing", str(ctx.exception))
        self.assertIn("setup.cmd", EASYOCR_REPAIR_HINT)

    @patch("tools.easyocr_runtime.subprocess.check_call")
    def test_install_easyocr_stack_sequence(self, mock_check_call):
        install_easyocr_stack(["python"])
        self.assertEqual(mock_check_call.call_count, 3)
        torch_call = mock_check_call.call_args_list[0].args[0]
        self.assertIn("torch", torch_call)
        self.assertIn("torchvision", torch_call)
        easyocr_call = mock_check_call.call_args_list[1].args[0]
        self.assertIn("--no-deps", easyocr_call)
        self.assertIn("easyocr", easyocr_call)
        deps_call = mock_check_call.call_args_list[2].args[0]
        for dep in EASYOCR_MANUAL_DEPS:
            self.assertIn(dep, deps_call)


if __name__ == "__main__":
    unittest.main()
