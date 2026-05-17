import unittest
from unittest.mock import patch

from tools import fix_gpu_runtime


class FixGpuRuntimeTests(unittest.TestCase):
    @patch("subprocess.check_output", return_value="NVIDIA GeForce RTX 4070")
    def test_auto_selects_directml_for_nvidia(self, _):
        self.assertEqual(fix_gpu_runtime.detect_runtime_variant(), "directml")

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
    def test_auto_selects_directml_without_nvidia(self, _):
        self.assertEqual(fix_gpu_runtime.detect_runtime_variant(), "directml")

    @patch("tools.fix_gpu_runtime.subprocess.run")
    def test_benchmark_variant_parses_marker_output(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = (
            'noise\nPYLA_RUNTIME_BENCHMARK={"variant":"directml","provider":"DmlExecutionProvider","ips":42.5}\n'
        )
        mock_run.return_value.stderr = ""

        result = fix_gpu_runtime.benchmark_variant("directml", runs=1)

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "DmlExecutionProvider")
        self.assertEqual(result["ips"], 42.5)


if __name__ == "__main__":
    unittest.main()
