import unittest
from unittest.mock import MagicMock

import numpy as np

from detect import Detect, _rows_to_results


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


if __name__ == "__main__":
    unittest.main()
