import queue
import sys
import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

import play as play_module
import visual_debug_window as vdw


class OpenCvHighGuiProbeTests(unittest.TestCase):
    def setUp(self):
        vdw.reset_opencv_highgui_cache()
        vdw._opencv_highgui_warned = False

    def tearDown(self):
        vdw.reset_opencv_highgui_cache()
        vdw._opencv_highgui_warned = False

    def test_opencv_highgui_available_caches_success(self):
        with patch.object(cv2, "namedWindow"), patch.object(cv2, "destroyWindow"):
            self.assertTrue(vdw.opencv_highgui_available())
            with patch.object(cv2, "namedWindow", side_effect=cv2.error("blocked", "test")):
                self.assertTrue(vdw.opencv_highgui_available())

    def test_opencv_highgui_available_caches_failure(self):
        with patch.object(cv2, "namedWindow", side_effect=cv2.error("blocked", "test")):
            self.assertFalse(vdw.opencv_highgui_available())
            with patch.object(cv2, "namedWindow"):
                self.assertFalse(vdw.opencv_highgui_available())

    @patch.object(vdw, "opencv_highgui_available", return_value=False)
    @patch.object(vdw.sys, "platform", "win32")
    def test_backend_name_uses_win32_when_opencv_missing(self, _mock_probe):
        self.assertEqual(vdw.visual_debug_backend_name(), "win32")

    @patch.object(vdw, "opencv_highgui_available", return_value=True)
    def test_backend_name_uses_opencv_when_available(self, _mock_probe):
        self.assertEqual(vdw.visual_debug_backend_name(), "opencv")

    @patch.object(vdw, "opencv_highgui_available", return_value=False)
    @patch.object(vdw.sys, "platform", "linux")
    def test_backend_name_unavailable_off_windows(self, _mock_probe):
        self.assertEqual(vdw.visual_debug_backend_name(), "unavailable")


class VisualDebugDisplayPumpTests(unittest.TestCase):
    def setUp(self):
        self._previous_visual_debug = play_module.visual_debug
        play_module.visual_debug = True
        self.play = object.__new__(play_module.Play)
        self.play._visual_debug_display_queue = queue.Queue(maxsize=1)

    def tearDown(self):
        play_module.visual_debug = self._previous_visual_debug

    def test_enqueue_drops_stale_frames(self):
        first = np.zeros((4, 4, 3), dtype=np.uint8)
        second = np.ones((4, 4, 3), dtype=np.uint8) * 255
        play_module.Play._enqueue_visual_debug_display(self.play, first)
        play_module.Play._enqueue_visual_debug_display(self.play, second)
        queued = self.play._visual_debug_display_queue.get_nowait()
        np.testing.assert_array_equal(queued, second)

    @patch("play.show_visual_debug_frame")
    def test_pump_displays_latest_frame(self, mock_show):
        img = np.zeros((8, 8, 3), dtype=np.uint8)
        play_module.Play._enqueue_visual_debug_display(self.play, img)
        play_module.Play.pump_visual_debug_display(self.play)
        mock_show.assert_called_once()
        np.testing.assert_array_equal(mock_show.call_args.args[0], img)

    @patch("play.show_visual_debug_frame")
    def test_pump_noops_when_queue_empty(self, mock_show):
        play_module.Play.pump_visual_debug_display(self.play)
        mock_show.assert_not_called()

    @patch("play.show_visual_debug_frame")
    def test_pump_noops_when_visual_debug_disabled(self, mock_show):
        play_module.visual_debug = False
        play_module.Play._enqueue_visual_debug_display(self.play, np.zeros((2, 2, 3), dtype=np.uint8))
        play_module.Play.pump_visual_debug_display(self.play)
        mock_show.assert_not_called()


class ShowVisualDebugFrameTests(unittest.TestCase):
    def setUp(self):
        vdw.reset_opencv_highgui_cache()
        vdw._opencv_highgui_warned = False

    def tearDown(self):
        vdw.reset_opencv_highgui_cache()
        vdw._opencv_highgui_warned = False

    @patch.object(vdw, "opencv_highgui_available", return_value=True)
    @patch.object(vdw.cv2, "imshow")
    @patch.object(vdw.cv2, "waitKey", return_value=1)
    @patch.object(vdw.cv2, "cvtColor", side_effect=lambda img, _code: img)
    def test_show_visual_debug_frame_uses_opencv(self, _mock_cvt, _mock_wait, mock_imshow, _mock_probe):
        img = np.zeros((6, 6, 3), dtype=np.uint8)
        vdw.show_visual_debug_frame(img)
        mock_imshow.assert_called_once()

    @patch.object(vdw, "opencv_highgui_available", return_value=False)
    @patch.object(vdw.sys, "platform", "win32")
    def test_show_visual_debug_frame_uses_win32_fallback(self, _mock_probe):
        mock_window = MagicMock()
        with patch.object(vdw.Win32VisualDebugWindow, "instance", return_value=mock_window):
            img = np.zeros((6, 6, 3), dtype=np.uint8)
            vdw.show_visual_debug_frame(img)
            mock_window.show.assert_called_once()


if __name__ == "__main__":
    unittest.main()
