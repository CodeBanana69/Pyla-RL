import unittest

import cv2
import numpy as np

from play import Play


class PoisonGasAvoidanceTests(unittest.TestCase):
    def make_play(self):
        play = object.__new__(Play)
        play.fog_hsv_low = (50, 95, 215)
        play.fog_hsv_high = (60, 125, 245)
        play.fog_flee_distance = 130
        play.fog_min_blob_pixels = 20
        play.fog_min_pixels_in_radius = 20
        play._fog_mask_cache_frame_id = None
        play._fog_mask_cache_value = None
        play.get_player_pos = lambda player: ((player[0] + player[2]) / 2, (player[1] + player[3]) / 2)
        return play

    @staticmethod
    def fog_rgb():
        hsv = np.array([[[55, 110, 230]]], dtype=np.uint8)
        return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[0, 0]

    def test_directional_gas_above_moves_down(self):
        play = self.make_play()
        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        frame[75:105, 135:165] = self.fog_rgb()

        angle = play.detect_fog_direction_escape(frame, (150, 150))

        self.assertIsNotNone(angle)
        self.assertAlmostEqual(angle, 90.0)

    def test_directional_gas_above_left_moves_down_right(self):
        play = self.make_play()
        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        frame[75:105, 135:165] = self.fog_rgb()
        frame[135:165, 75:105] = self.fog_rgb()

        angle = play.detect_fog_direction_escape(frame, (150, 150))

        self.assertIsNotNone(angle)
        self.assertAlmostEqual(angle, 45.0)

    def test_no_near_gas_returns_none(self):
        play = self.make_play()
        frame = np.zeros((300, 300, 3), dtype=np.uint8)

        self.assertIsNone(play.detect_fog_direction_escape(frame, (150, 150)))

    def test_playstyle_poison_gas_api_detects_direction(self):
        play = self.make_play()
        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        frame[75:105, 135:165] = self.fog_rgb()
        play.current_frame = frame

        self.assertTrue(play.is_there_poison_gas("up", [135, 135, 165, 165]))
        self.assertFalse(play.is_there_poison_gas("down", [135, 135, 165, 165]))

    def test_playstyle_poison_gas_api_detects_player_inside_gas(self):
        play = self.make_play()
        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        frame[138:162, 138:162] = self.fog_rgb()
        play.current_frame = frame

        self.assertTrue(play.is_there_poison_gas("up", [135, 135, 165, 165]))
        self.assertTrue(play.is_there_poison_gas("down", [135, 135, 165, 165]))

    def test_angle_path_guard_detects_fog_ahead_only(self):
        play = self.make_play()
        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        frame[135:165, 205:235] = self.fog_rgb()

        self.assertTrue(play.angle_points_into_fog(frame, (150, 150), 0))
        self.assertFalse(play.angle_points_into_fog(frame, (150, 150), 180))


if __name__ == "__main__":
    unittest.main()
