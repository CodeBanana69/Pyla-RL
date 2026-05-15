import unittest
from unittest.mock import patch

from detect import _build_providers
from utils import DefaultEasyOCR


class ProviderSelectionTests(unittest.TestCase):
    @patch("detect.ort.get_available_providers", return_value=[
        "CUDAExecutionProvider",
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    ])
    def test_auto_prefers_cuda_before_directml_when_available(self, *_):
        providers = _build_providers("auto")
        self.assertEqual(providers[0][0], "CUDAExecutionProvider")

    @patch("detect.ort.get_available_providers", return_value=[
        "CUDAExecutionProvider",
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    ])
    def test_explicit_cuda_still_selects_cuda(self, *_):
        providers = _build_providers("cuda")
        self.assertEqual(providers[0][0], "CUDAExecutionProvider")

    @patch("detect.ort.get_available_providers", return_value=[
        "CUDAExecutionProvider",
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    ])
    def test_cuda_provider_uses_fast_cudnn_options(self, *_):
        providers = _build_providers("cuda")
        options = providers[0][1]
        self.assertEqual(options["cudnn_conv_algo_search"], "EXHAUSTIVE")
        self.assertEqual(options["cudnn_conv_use_max_workspace"], "1")
        self.assertEqual(options["use_tf32"], "1")

    @patch("easyocr.Reader")
    def test_easyocr_is_forced_to_cpu(self, mock_reader):
        DefaultEasyOCR()
        self.assertFalse(mock_reader.call_args.kwargs["gpu"])


if __name__ == "__main__":
    unittest.main()
