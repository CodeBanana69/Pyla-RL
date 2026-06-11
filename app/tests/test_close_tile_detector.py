import unittest
from unittest.mock import MagicMock

import numpy as np

from play import CLOSE_TILE_CROP_SIZE, Play


class CloseTileDetectorTests(unittest.TestCase):
    def _frame_1080p(self):
        return np.zeros((1080, 1920, 3), dtype=np.uint8)

    def test_crop_centered_on_player(self):
        frame = self._frame_1080p()
        crop, x1, y1 = Play.crop_close_tile_region(frame, (960, 540))
        self.assertEqual(crop.shape, (CLOSE_TILE_CROP_SIZE, CLOSE_TILE_CROP_SIZE, 3))
        self.assertEqual((x1, y1), (640, 220))
        self.assertTrue(np.shares_memory(frame[220:860, 640:1280], crop))

    def test_crop_clamps_top_left(self):
        frame = self._frame_1080p()
        _, x1, y1 = Play.crop_close_tile_region(frame, (50, 50))
        self.assertEqual((x1, y1), (0, 0))

    def test_crop_clamps_bottom_right(self):
        frame = self._frame_1080p()
        _, x1, y1 = Play.crop_close_tile_region(frame, (1900, 1050))
        self.assertEqual((x1, y1), (1280, 440))

    def test_crop_returns_none_when_frame_too_small(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        crop, x1, y1 = Play.crop_close_tile_region(frame, (320, 240))
        self.assertIsNone(crop)
        self.assertEqual((x1, y1), (0, 0))

    def test_offset_tile_boxes(self):
        tile_data = {"wall": [[10, 20, 30, 40]], "bush": [[1, 2, 3, 4], [5, 6, 7, 8]]}
        offsetted = Play.offset_tile_boxes(tile_data, 100, 200)
        self.assertEqual(offsetted["wall"], [[110, 220, 130, 240]])
        self.assertEqual(
            offsetted["bush"],
            [[101, 202, 103, 204], [105, 206, 107, 208]],
        )

    def test_get_tile_data_uses_close_detector_when_enabled(self):
        play = Play.__new__(Play)
        play.close_tile_detector_enabled = True
        play.wall_detection_confidence = 0.9
        play.wall_detection_retry_confidence = 0.2
        play.wall_detection_retry_min_objects = 3
        play.last_wall_primary_count = 8
        play.Detect_close_tile_detector = MagicMock()
        play.Detect_close_tile_detector.detect_objects.return_value = {
            "wall": [[10, 20, 30, 40]],
        }
        play.Detect_tile_detector = MagicMock()

        frame = self._frame_1080p()
        result = play.get_tile_data(frame, (960, 540))

        play.Detect_close_tile_detector.detect_objects.assert_called_once()
        play.Detect_tile_detector.detect_objects.assert_not_called()
        crop_arg = play.Detect_close_tile_detector.detect_objects.call_args[0][0]
        self.assertEqual(crop_arg.shape[:2], (CLOSE_TILE_CROP_SIZE, CLOSE_TILE_CROP_SIZE))
        self.assertEqual(result["wall"], [[650, 240, 670, 260]])
        self.assertEqual(play.last_tile_detection_debug["source"], "close")
        self.assertEqual(play.last_tile_detection_debug["crop"], [640, 220, 1280, 860])

    def test_get_tile_data_falls_back_to_full_detector_when_disabled(self):
        play = Play.__new__(Play)
        play.close_tile_detector_enabled = False
        play.wall_detection_confidence = 0.9
        play.wall_detection_retry_confidence = 0.2
        play.wall_detection_retry_min_objects = 3
        play.last_wall_primary_count = 8
        play.Detect_close_tile_detector = MagicMock()
        play.Detect_tile_detector = MagicMock()
        play.Detect_tile_detector.detect_objects.return_value = {"wall": [[0, 0, 10, 10]]}

        frame = self._frame_1080p()
        result = play.get_tile_data(frame, (960, 540))

        play.Detect_close_tile_detector.detect_objects.assert_not_called()
        play.Detect_tile_detector.detect_objects.assert_called_once()
        self.assertEqual(result["wall"], [[0, 0, 10, 10]])
        self.assertEqual(play.last_tile_detection_debug["source"], "full")
        self.assertFalse(play.last_tile_detection_debug["enabled"])

    def test_get_tile_data_falls_back_without_player_pos(self):
        play = Play.__new__(Play)
        play.close_tile_detector_enabled = True
        play.wall_detection_confidence = 0.9
        play.wall_detection_retry_confidence = 0.2
        play.wall_detection_retry_min_objects = 3
        play.last_wall_primary_count = 8
        play.Detect_close_tile_detector = MagicMock()
        play.Detect_tile_detector = MagicMock()
        play.Detect_tile_detector.detect_objects.return_value = {"bush": [[1, 2, 3, 4]]}

        frame = self._frame_1080p()
        result = play.get_tile_data(frame, None)

        play.Detect_close_tile_detector.detect_objects.assert_not_called()
        play.Detect_tile_detector.detect_objects.assert_called_once()
        self.assertEqual(result["bush"], [[1, 2, 3, 4]])
        self.assertEqual(play.last_tile_detection_debug["source"], "full")
        self.assertEqual(play.last_tile_detection_debug["fallback"], "no_player")


if __name__ == "__main__":
    unittest.main()
