import unittest

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


if __name__ == "__main__":
    unittest.main()
