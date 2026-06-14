import unittest
from unittest.mock import patch

from gpu_runtime_install import setup_candidate_variants, torch_cuda_install_args


class GpuRuntimeInstallTests(unittest.TestCase):
    def test_setup_candidate_variants_prefers_cuda_for_nvidia(self):
        self.assertEqual(
            setup_candidate_variants([("nvidia", "GeForce RTX 4070")]),
            ["cuda", "directml", "cpu"],
        )

    def test_setup_candidate_variants_uses_directml_for_amd(self):
        self.assertEqual(
            setup_candidate_variants([("amd", "Radeon RX 7900")]),
            ["directml", "cpu"],
        )

    def test_torch_cuda_install_args_for_blackwell(self):
        args = torch_cuda_install_args(10.0)
        self.assertIn("--pre", args)
        self.assertIn("cu128", args[-1])

    def test_torch_cuda_install_args_for_ada(self):
        args = torch_cuda_install_args(8.9)
        self.assertEqual(args[-1], "https://download.pytorch.org/whl/cu124")

    @patch("gpu_runtime_install.subprocess.run")
    @patch("gpu_runtime_install.subprocess.check_call")
    def test_repair_numpy_reinstalls_when_major_version_is_two(self, mock_check_call, mock_run):
        from gpu_runtime_install import repair_numpy

        version_result = mock_run.return_value
        version_result.returncode = 0
        version_result.stdout = "2.4.4\n"

        repaired = repair_numpy(python="python", verbose=False)

        self.assertTrue(repaired)
        mock_check_call.assert_any_call(
            ["python", "-m", "pip", "install", "--force-reinstall", "--no-deps", "numpy<2.0.0"],
        )


if __name__ == "__main__":
    unittest.main()
