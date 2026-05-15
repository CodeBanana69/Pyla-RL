import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cuda_runtime_paths


class CudaRuntimePathTests(unittest.TestCase):
    def test_finds_torch_and_nvidia_cuda_dll_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            torch_lib = root / "torch" / "lib"
            cublas_bin = root / "nvidia" / "cublas" / "bin"
            cudnn_bin = root / "nvidia" / "cudnn" / "bin"
            torch_lib.mkdir(parents=True)
            cublas_bin.mkdir(parents=True)
            cudnn_bin.mkdir(parents=True)

            with patch.object(cuda_runtime_paths, "_site_package_roots", return_value=[root]):
                paths = [Path(path) for path in cuda_runtime_paths.find_cuda_dll_directories()]

        self.assertIn(torch_lib, paths)
        self.assertIn(cublas_bin, paths)
        self.assertIn(cudnn_bin, paths)

    def test_reports_missing_cuda_dependency_dlls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            torch_lib = root / "torch" / "lib"
            torch_lib.mkdir(parents=True)
            (torch_lib / "cublasLt64_12.dll").write_text("")

            with patch.object(cuda_runtime_paths, "_site_package_roots", return_value=[root]):
                ok, missing = cuda_runtime_paths.has_cuda_dependency_dlls()

        self.assertFalse(ok)
        self.assertEqual(missing, ["cudnn64_9.dll"])


if __name__ == "__main__":
    unittest.main()
