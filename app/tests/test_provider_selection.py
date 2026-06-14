import unittest
from unittest.mock import Mock, patch

import numpy as np

from detect import Detect, _build_providers, _configure_session_options_for_provider, _fallback_providers_after_runtime_failure, _provider_name
from utils import DefaultEasyOCR


class ProviderSelectionTests(unittest.TestCase):
    @patch("detect.resolve_inference_device", return_value="directml")
    @patch("detect.primary_vendor", return_value="amd")
    @patch("detect.ort.get_available_providers", return_value=[
        "CUDAExecutionProvider",
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    ])
    def test_auto_prefers_directml_on_amd_when_available(self, *_):
        providers = _build_providers("auto")
        self.assertEqual(_provider_name(providers[0]), "DmlExecutionProvider")

    @patch("detect.resolve_inference_device", return_value="cuda")
    @patch("detect.primary_vendor", return_value="nvidia")
    @patch("detect.ort.get_available_providers", return_value=[
        "CUDAExecutionProvider",
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    ])
    def test_auto_prefers_cuda_on_nvidia_when_available(self, *_):
        providers = _build_providers("auto")
        self.assertEqual(_provider_name(providers[0]), "CUDAExecutionProvider")

    @patch("detect.resolve_inference_device", return_value="directml")
    @patch("detect.primary_vendor", return_value="amd")
    @patch("detect.ort.get_available_providers", return_value=[
        "CUDAExecutionProvider",
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    ])
    def test_gpu_prefers_directml_on_amd_when_available(self, *_):
        providers = _build_providers("gpu")
        self.assertEqual(_provider_name(providers[0]), "DmlExecutionProvider")

    @patch("detect.resolve_inference_device", return_value="cuda")
    @patch("detect.primary_vendor", return_value="nvidia")
    @patch("detect.ort.get_available_providers", return_value=[
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    ])
    def test_auto_uses_cuda_on_nvidia_when_directml_is_not_installed(self, *_):
        providers = _build_providers("auto")
        self.assertEqual(_provider_name(providers[0]), "CUDAExecutionProvider")

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

    @patch("detect.ort.get_available_providers", return_value=[
        "CUDAExecutionProvider",
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    ])
    def test_cuda_runtime_failure_falls_back_to_directml_then_cpu(self, *_):
        providers = _fallback_providers_after_runtime_failure("CUDAExecutionProvider")
        self.assertEqual(providers[0], "DmlExecutionProvider")
        self.assertEqual(providers[-1], "CPUExecutionProvider")

    @patch("detect.ort.get_available_providers", return_value=[
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    ])
    def test_cuda_runtime_failure_falls_back_to_cpu_without_directml(self, *_):
        providers = _fallback_providers_after_runtime_failure("CUDAExecutionProvider")
        self.assertEqual(providers, ["CPUExecutionProvider"])

    def test_directml_session_disables_graph_fusion(self):
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _configure_session_options_for_provider(so, "DmlExecutionProvider")
        self.assertEqual(so.graph_optimization_level, ort.GraphOptimizationLevel.ORT_ENABLE_BASIC)
        self.assertFalse(so.enable_mem_pattern)
        self.assertEqual(so.execution_mode, ort.ExecutionMode.ORT_SEQUENTIAL)

    def test_detect_objects_retries_after_runtime_provider_failure(self):
        detector = Detect.__new__(Detect)
        detector.device = "CUDAExecutionProvider"
        detector.output_names = ["output"]
        detector.input_name = "input"
        detector.classes = ["player"]
        detector.ignore_classes = set()
        detector._use_io_binding = False
        detector._io_binding = None
        detector._input_ortvalue = None
        detector.preprocess_image = Mock(return_value=(np.zeros((1, 3, 10, 10), dtype=np.float32), 10, 10))
        detector.postprocess = Mock(return_value=[])
        detector._fallback_after_runtime_failure = Mock(return_value=True)
        detector.model = Mock()
        detector.model.run.side_effect = [
            RuntimeError("CUDNN_FE failure 11: no kernel image is available for execution on the device"),
            [np.zeros((1, 6), dtype=np.float32)],
        ]

        result = detector.detect_objects(np.zeros((10, 10, 3), dtype=np.uint8))

        self.assertEqual(result, {})
        self.assertEqual(detector.model.run.call_count, 2)
        detector._fallback_after_runtime_failure.assert_called_once()

    @patch("easyocr.Reader")
    def test_easyocr_is_forced_to_cpu(self, mock_reader):
        DefaultEasyOCR()
        self.assertFalse(mock_reader.call_args.kwargs["gpu"])


if __name__ == "__main__":
    unittest.main()
