import math
import unittest
from unittest.mock import Mock, patch

import numpy as np

from play import Play


class AdvancedVisualsTests(unittest.TestCase):
    def _make_play(self):
        play = Play.__new__(Play)
        play.window_controller = Mock()
        play.window_controller.joystick_x = 220
        play.window_controller.joystick_y = 870
        play.window_controller.width_ratio = 1.0
        play.window_controller.height_ratio = 1.0
        play.brawlers_info = {}
        play.current_line_of_sight_walls = []
        play._last_advanced_visual_context = None
        play.advanced_visuals = True
        return play

    def test_movement_to_angle_from_wasd(self):
        play = self._make_play()
        self.assertAlmostEqual(play._movement_to_angle("wd"), 315.0, places=1)
        self.assertAlmostEqual(play._movement_to_angle(90.0), 90.0, places=1)

    @patch.object(Play, "is_path_blocked_angle", side_effect=lambda _pos, angle, _walls: angle in (0, 90, 180))
    @patch.object(Play, "get_player_pos", return_value=(500, 500))
    @patch.object(Play, "choose_locked_teammate", return_value=([700, 520], 120.0))
    @patch.object(Play, "find_closest_enemy", return_value=([900, 500], 80.0))
    @patch.object(Play, "is_enemy_hittable", return_value=True)
    @patch.object(Play, "get_enemy_pos", return_value=(900, 500))
    def test_build_advanced_visual_context_samples_and_targets(
        self,
        _enemy_pos,
        _hittable,
        _closest_enemy,
        _teammate,
        _player_pos,
        _blocked,
    ):
        play = self._make_play()
        data = {
            "player": [[480, 480, 520, 520]],
            "teammate": [[680, 500, 720, 540]],
            "enemy": [[880, 480, 920, 520]],
            "wall": [[100, 100, 200, 200]],
            "line_of_sight_wall": [],
        }

        context = play.build_advanced_visual_context(data, 45.0, "shelly")

        self.assertEqual(len(context["direction_samples"]), 24)
        self.assertTrue(context["direction_samples"][0]["blocked"])
        self.assertFalse(context["direction_samples"][1]["blocked"])
        self.assertEqual(context["follow_target"], [700, 520])
        self.assertEqual(context["hittable_enemies"], [[900, 500]])
        self.assertEqual(context["attack_target"], [900, 500])
        self.assertEqual(context["movement_angle"], 45.0)

    @patch.object(Play, "is_enemy_hittable", side_effect=lambda _p, _e, _w, _s: False)
    @patch.object(Play, "get_player_pos", return_value=(500, 500))
    @patch.object(Play, "get_enemy_pos", return_value=(900, 500))
    @patch.object(Play, "choose_locked_teammate", return_value=(None, float("inf")))
    @patch.object(Play, "find_closest_enemy", return_value=([900, 500], 80.0))
    @patch.object(Play, "is_path_blocked_angle", return_value=False)
    def test_build_advanced_visual_context_blocked_attack_target(
        self,
        _blocked_angle,
        _closest_enemy,
        _teammate,
        _enemy_pos,
        _hittable,
        _player_pos,
    ):
        play = self._make_play()
        data = {
            "player": [[480, 480, 520, 520]],
            "enemy": [[880, 480, 920, 520]],
            "wall": [],
        }

        context = play.build_advanced_visual_context(data, "w", "colt")

        self.assertEqual(context["hittable_enemies"], [])
        self.assertIsNone(context["attack_target"])
        self.assertEqual(context["blocked_attack_target"], [900, 500])

    def test_draw_advanced_visuals_smoke(self):
        play = self._make_play()
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        scale = 0.5

        def s(value):
            return int(value * scale)

        def sp(point):
            return s(point[0]), s(point[1])

        data = {
            "advanced_visuals": {
                "player_pos": [960, 540],
                "joystick_center": [220, 870],
                "direction_samples": [
                    {"angle": 0.0, "blocked": True},
                    {"angle": 15.0, "blocked": False},
                ],
                "movement_angle": 90.0,
                "follow_target": [1100, 540],
                "hittable_enemies": [[1400, 540]],
                "attack_target": [1400, 540],
                "blocked_attack_target": None,
            }
        }

        play._draw_advanced_visuals(img, data, scale, sp, s)
        self.assertGreater(int(img.sum()), 0)


if __name__ == "__main__":
    unittest.main()
