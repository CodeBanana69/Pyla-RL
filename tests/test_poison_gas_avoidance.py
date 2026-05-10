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
        play.jump_pad_detection_enabled = True
        play.jump_pad_escape_distance = 260
        play.jump_pad_escape_min_distance = 20
        play.jump_pad_escape_requires_edge = False
        play.jump_pad_escape_edge_margin = 0.22
        play.jump_pad_escape_teammate_safe_distance = 100
        play.jump_pad_smoke_early_distance = 220
        play.current_frame = np.zeros((300, 300, 3), dtype=np.uint8)
        play.TILE_SIZE = 60
        play.wall_box_min_size = 10
        play.wall_box_merge_iou = 0.25
        play.wall_box_merge_center_distance = 35
        play._fog_mask_cache_frame_id = None
        play._fog_mask_cache_value = None
        play.get_player_pos = lambda player: ((player[0] + player[2]) / 2, (player[1] + player[3]) / 2)
        play.get_distance = Play.get_distance
        play.angle_from_direction = Play.angle_from_direction
        play.is_path_blocked_angle = lambda *_args, **_kwargs: False
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

    @staticmethod
    def draw_jump_pad(frame, center=(210, 150)):
        cx, cy = center
        cv2.rectangle(frame, (cx - 36, cy - 36), (cx + 36, cy + 36), (86, 91, 105), -1)
        cv2.rectangle(frame, (cx - 29, cy - 29), (cx + 29, cy + 29), (58, 63, 75), -1)
        arrow = np.array(
            [
                (cx - 22, cy - 11),
                (cx + 6, cy - 11),
                (cx + 6, cy - 23),
                (cx + 28, cy),
                (cx + 6, cy + 23),
                (cx + 6, cy + 11),
                (cx - 22, cy + 11),
            ],
            dtype=np.int32,
        )
        yellow_rgb = cv2.cvtColor(np.array([[[28, 230, 240]]], dtype=np.uint8), cv2.COLOR_HSV2RGB)[0, 0]
        cv2.fillPoly(frame, [arrow], yellow_rgb.tolist())

    def test_detects_jump_pad_by_yellow_arrow_and_gray_tile(self):
        play = self.make_play()
        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        self.draw_jump_pad(frame)

        pads = play.detect_jump_pads(frame)

        self.assertTrue(pads)
        x1, y1, x2, y2 = pads[0]
        self.assertLessEqual(x1, 210)
        self.assertGreaterEqual(x2, 210)
        self.assertLessEqual(y1, 150)
        self.assertGreaterEqual(y2, 150)

    def test_fog_escape_prefers_near_reachable_jump_pad(self):
        play = self.make_play()
        player_pos = (150, 150)
        jump_pads = [[175, 115, 245, 185]]

        angle = play.find_jump_pad_escape_angle(player_pos, jump_pads, [], fog_flee_angle=0.0)

        self.assertIsNotNone(angle)
        self.assertAlmostEqual(angle, 0.0, delta=20.0)

    def test_jump_pad_escape_requires_map_edge_when_enabled(self):
        play = self.make_play()
        play.jump_pad_escape_requires_edge = True
        jump_pads = [[175, 115, 245, 185]]

        self.assertIsNone(play.find_jump_pad_escape_angle((150, 150), jump_pads, [], fog_flee_angle=0.0))
        self.assertIsNotNone(play.find_jump_pad_escape_angle((35, 150), jump_pads, [], fog_flee_angle=0.0))

    def test_jump_pad_escape_skips_when_teammate_is_close(self):
        play = self.make_play()
        play.jump_pad_escape_requires_edge = True
        player_pos = (35, 150)
        jump_pads = [[175, 115, 245, 185]]
        close_teammate = [[65, 130, 95, 170]]

        angle = play.find_jump_pad_escape_angle(
            player_pos,
            jump_pads,
            [],
            fog_flee_angle=0.0,
            teammate_data=close_teammate,
        )

        self.assertIsNone(angle)

    def test_jump_pad_smoke_escape_detects_fog_a_bit_farther_out(self):
        play = self.make_play()
        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        frame[135:165, 220:250] = self.fog_rgb()

        angle = play.detect_jump_pad_smoke_escape(frame, (35, 150))

        self.assertIsNotNone(angle)
        self.assertAlmostEqual(angle, 180.0, delta=12.0)


if __name__ == "__main__":
    unittest.main()
