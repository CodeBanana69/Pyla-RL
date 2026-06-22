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

    @patch("tools.dependency_repair.repair_opencv_conflicts")
    @patch("gpu_runtime_install.run_text")
    def test_repair_numpy_reinstalls_when_major_version_is_two(
        self,
        mock_run_text,
        _mock_repair_opencv,
    ):
        from gpu_runtime_install import repair_numpy

        def _side_effect(command, **kwargs):
            result = mock_run_text.return_value
            if command[-1].startswith("import numpy"):
                result.returncode = 0
                result.stdout = "2.4.4\n"
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        mock_run_text.side_effect = _side_effect

        with patch("tools.python_runtime.is_supported_python", return_value=True):
            repaired = repair_numpy(python="python", verbose=False)

        self.assertTrue(repaired)
        mock_run_text.assert_any_call(
            ["python", "-m", "pip", "install", "--force-reinstall", "--no-deps", "numpy<2.0.0"],
            capture_output=True,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
