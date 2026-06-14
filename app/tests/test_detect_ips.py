import unittest
from unittest.mock import MagicMock, Mock, patch

import numpy as np

from detect import (
    Detect,
    _fp16_allowed_for_provider,
    _make_inference_probe,
    _rows_to_results,
    _session_input_numpy_dtype,
)


class DetectDualConfidenceTests(unittest.TestCase):
    def test_rows_to_results_filters_by_threshold(self):
        rows = np.array(
            [
                [10, 10, 20, 20, 0.8, 0],
                [30, 30, 40, 40, 0.4, 1],
            ],
            dtype=np.float32,
        )
        high = _rows_to_results(rows, ["player", "enemy"], set(), 0.6)
        low = _rows_to_results(rows, ["player", "enemy"], set(), 0.3)
        self.assertEqual(len(high.get("player", [])), 1)
        self.assertEqual(len(low.get("player", [])), 1)
        self.assertEqual(len(low.get("enemy", [])), 1)

    def test_detect_objects_dual_uses_single_infer_rows(self):
        detector = Detect.__new__(Detect)
        detector.classes = ["player", "enemy"]
        detector.ignore_classes = set()
        detector._infer_rows = MagicMock(
            return_value=np.array([[1, 1, 2, 2, 0.7, 0], [3, 3, 4, 4, 0.4, 1]], dtype=np.float32)
        )
        primary, retry = detector.detect_objects_dual(np.zeros((8, 8, 3), dtype=np.uint8), 0.6, 0.35)
        detector._infer_rows.assert_called_once()
        self.assertTrue(primary.get("player"))
        self.assertTrue(retry.get("enemy"))


class DetectFp16PolicyTests(unittest.TestCase):
    def test_fp16_disabled_for_directml(self):
        self.assertFalse(_fp16_allowed_for_provider("DmlExecutionProvider"))

    @patch("detect._use_fp16_models", return_value=True)
    def test_fp16_enabled_for_cuda_when_configured(self, *_):
        self.assertTrue(_fp16_allowed_for_provider("CUDAExecutionProvider"))

    def test_session_input_numpy_dtype_reads_model_io_type(self):
        session = Mock()
        session.get_inputs.return_value = [Mock(type="tensor(float)")]
        self.assertEqual(_session_input_numpy_dtype(session), np.float32)
        session.get_inputs.return_value = [Mock(type="tensor(float16)")]
        self.assertEqual(_session_input_numpy_dtype(session), np.float16)

    def test_validation_probe_does_not_runtime_fallback(self):
        model = Mock()
        model.get_inputs.return_value = [Mock(name="input", type="tensor(float)")]
        model.get_outputs.return_value = [Mock(name="output")]
        model.run.side_effect = RuntimeError("dtype mismatch")
        probe = _make_inference_probe(
            model,
            "DmlExecutionProvider",
            ["player"],
            set(),
            (640, 640),
            "models/main.onnx",
        )
        probe.postprocess = Mock(return_value=[])
        with self.assertRaises(RuntimeError):
            probe._infer_rows(np.zeros((8, 8, 3), dtype=np.uint8), 0.25)
        self.assertFalse(getattr(probe, "_allow_runtime_fallback", True))


if __name__ == "__main__":
    unittest.main()
