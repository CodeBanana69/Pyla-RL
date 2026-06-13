import unittest
from unittest.mock import patch

from tools import fix_gpu_runtime
from gpu_runtime_install import install_and_verify_variant


class FixGpuRuntimeTests(unittest.TestCase):
    @patch("subprocess.check_output", return_value="NVIDIA GeForce RTX 4070")
    def test_auto_selects_cuda_for_nvidia(self, _):
        self.assertEqual(fix_gpu_runtime.detect_runtime_variant(), "cuda")

    def test_auto_candidate_order_tries_cuda_only_for_nvidia(self):
        self.assertEqual(
            fix_gpu_runtime.auto_candidate_variants([("nvidia", "RTX 4070")]),
            ["directml", "cuda", "cpu"],
        )
        self.assertEqual(
            fix_gpu_runtime.auto_candidate_variants([("amd", "Radeon RX")]),
            ["directml", "cpu"],
        )

    @patch("subprocess.check_output", side_effect=FileNotFoundError)
    def test_auto_selects_cpu_without_detectable_gpu(self, _):
        self.assertEqual(fix_gpu_runtime.detect_runtime_variant(), "cpu")

    @patch("gpu_runtime_install.install_variant")
    @patch("gpu_runtime_install.smoke_test_variant")
    def test_install_and_verify_variant_uses_smoke_test(self, mock_smoke, _mock_install):
        mock_smoke.return_value = {
            "variant": "directml",
            "provider": "DmlExecutionProvider",
            "ips": 42.5,
            "ok": True,
        }

        result = fix_gpu_runtime.install_and_verify_variant("directml", smoke_runs=1)

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "DmlExecutionProvider")
        self.assertEqual(result["ips"], 42.5)


if __name__ == "__main__":
    unittest.main()
