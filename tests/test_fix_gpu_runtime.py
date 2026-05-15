import unittest
from unittest.mock import patch

from tools import fix_gpu_runtime


class FixGpuRuntimeTests(unittest.TestCase):
    @patch("subprocess.check_output", return_value="NVIDIA GeForce RTX 4070")
    def test_auto_selects_cuda_for_nvidia(self, _):
        self.assertEqual(fix_gpu_runtime.detect_runtime_variant(), "cuda")

    @patch("subprocess.check_output", side_effect=FileNotFoundError)
    def test_auto_selects_directml_without_nvidia(self, _):
        self.assertEqual(fix_gpu_runtime.detect_runtime_variant(), "directml")


if __name__ == "__main__":
    unittest.main()
