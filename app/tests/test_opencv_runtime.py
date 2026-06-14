import sys
import unittest
from unittest.mock import MagicMock, patch

from opencv_runtime import OPENCV_REPAIR_CMD, ensure_opencv_runtime, opencv_runtime_ready


class OpenCVRuntimeTests(unittest.TestCase):
    def test_opencv_runtime_ready_requires_version(self):
        broken = MagicMock(imdecode=lambda *_a, **_k: None, IMREAD_COLOR=1)
        del broken.__version__
        self.assertFalse(opencv_runtime_ready(broken))

    def test_opencv_runtime_ready_accepts_full_module(self):
        good = MagicMock(imdecode=lambda *_a, **_k: None, IMREAD_COLOR=1, __version__="4.8.0")
        self.assertTrue(opencv_runtime_ready(good))

    def test_ensure_opencv_runtime_skips_repair_when_ready(self):
        good = MagicMock(imdecode=lambda *_a, **_k: None, IMREAD_COLOR=1, __version__="4.8.0")
        with patch.dict(sys.modules, {"cv2": good}), patch(
            "opencv_runtime.opencv_runtime_ready", return_value=True
        ), patch("opencv_runtime.repair_opencv_runtime") as repair:
            result = ensure_opencv_runtime()
        repair.assert_not_called()
        self.assertIs(result, good)

    def test_ensure_opencv_runtime_calls_repair_when_broken(self):
        broken = MagicMock(imdecode=None, __version__="4.8.0")
        with patch.dict(sys.modules, {"cv2": broken}), patch(
            "opencv_runtime.opencv_runtime_ready", side_effect=[False, True]
        ), patch("opencv_runtime.repair_opencv_runtime") as repair, patch(
            "importlib.reload"
        ):
            ensure_opencv_runtime()
        repair.assert_called_once()

    def test_repair_cmd_mentions_headless(self):
        self.assertIn("opencv-python-headless", OPENCV_REPAIR_CMD)


if __name__ == "__main__":
    unittest.main()
