import unittest

import cv2
import numpy as np

from play import Play


class RespawnOverlayTests(unittest.TestCase):
    @staticmethod
    def make_play():
        return object.__new__(Play)

    @staticmethod
    def _to_rgb(hsv: tuple, shape: tuple) -> np.ndarray:
        hsv_block = np.full((shape[0], shape[1], 3), hsv, dtype=np.uint8)
        return cv2.cvtColor(hsv_block, cv2.COLOR_HSV2RGB)

    def test_respawn_overlay_detected_with_yellow_bolt_and_white_text(self):
        play = self.make_play()
        h, w = 1080, 1920
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        # Yellow lightning patch in the top-center band
        yellow_rgb = self._to_rgb((28, 230, 255), (140, 140))
        frame[100:240, 940:1080] = yellow_rgb

        # White "Back in:" text strip just below
        white_rgb = self._to_rgb((0, 0, 250), (140, 600))
        frame[260:400, 660:1260] = white_rgb

        self.assertTrue(play.is_respawning_overlay(frame))

    def test_no_overlay_on_blank_frame(self):
        play = self.make_play()
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.assertFalse(play.is_respawning_overlay(frame))

    def test_handles_missing_frame(self):
        play = self.make_play()
        self.assertFalse(play.is_respawning_overlay(None))


if __name__ == "__main__":
    unittest.main()
