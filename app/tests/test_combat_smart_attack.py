import math
import time
import unittest
from unittest.mock import MagicMock

from play import Play


class CombatSmartAttackTests(unittest.TestCase):
    def _make_play(self):
        play = Play.__new__(Play)
        play.smart_aim_enabled = "yes"
        play.aimed_attacks_enabled = "yes"
        play.aim_swipe_radius = 250.0
        play.aim_swipe_duration = 0.09
        play.aim_swipe_hold = 0.02
        play.attack_min_interval = 0.35
        play.projectile_speed_px_s = 1200.0
        play.current_brawler = "shelly"
        play._last_attack_tap_at = 0.0
        play._enemy_track = {"pos": None, "ts": 0.0, "velocity": (0.0, 0.0)}
        play._combat_target = None
        play.persistent_data = {"time_since_holding_attack": None}
        play.window_controller = MagicMock()
        play.window_controller.scale_factor = 1.0
        play.window_controller.press = MagicMock()
        play.window_controller.aim_attack_angle = MagicMock()
        play.is_there_enemy = lambda enemies: bool(enemies)
        play.find_closest_enemy = lambda *_args, **_kwargs: ((300, 100), 200.0)
        play.get_entity_pos = Play.get_entity_pos
        play.get_brawler_range = lambda _brawler: (200, 400, 600)
        play._log_combat_action = lambda *_args, **_kwargs: None
        return play

    def test_velocity_tracker_estimates_motion(self):
        play = self._make_play()
        data = {"player": [[0, 0, 100, 100]], "enemy": [[200, 50, 300, 150]], "wall": []}
        play.track_enemy(data, brawler="shelly")
        first_pos = play._enemy_track["pos"]
        self.assertIsNotNone(first_pos)

        play.find_closest_enemy = lambda *_args, **_kwargs: ((220, 100), 180.0)
        time.sleep(0.02)
        play.track_enemy(data, brawler="shelly")
        vx, vy = play.get_tracked_enemy_velocity()
        self.assertGreater(abs(vx), 0.0)

    def test_velocity_tracker_resets_on_target_jump(self):
        play = self._make_play()
        data = {"player": [[0, 0, 100, 100]], "enemy": [[200, 50, 300, 150]], "wall": []}
        play.track_enemy(data, brawler="shelly")
        play.find_closest_enemy = lambda *_args, **_kwargs: ((900, 900), 50.0)
        play.track_enemy(data, brawler="shelly")
        vx, vy = play.get_tracked_enemy_velocity()
        self.assertEqual((vx, vy), (0.0, 0.0))

    def test_lead_shot_angle_aheads_of_lateral_motion(self):
        angle_stationary = Play.lead_shot_angle((0, 0), (200, 0), (0, 0), projectile_speed_px_s=1000.0)
        angle_moving = Play.lead_shot_angle((0, 0), (200, 0), (0, 400), projectile_speed_px_s=1000.0)
        self.assertAlmostEqual(angle_stationary, 0.0, places=3)
        self.assertGreater(angle_moving, angle_stationary)

    def test_moving_enemy_uses_aim_attack_angle(self):
        play = self._make_play()
        play._combat_target = {
            "player_pos": (50, 50),
            "pos": (300, 50),
            "distance": 250.0,
            "brawler": "shelly",
        }
        play._enemy_track["velocity"] = (0.0, 300.0)
        play.attack()
        play.window_controller.aim_attack_angle.assert_called_once()
        play.window_controller.press.assert_not_called()

    def test_stationary_enemy_uses_directional_aim_swipe(self):
        play = self._make_play()
        play._combat_target = {
            "player_pos": (50, 50),
            "pos": (300, 50),
            "distance": 250.0,
            "brawler": "shelly",
        }
        play._enemy_track["velocity"] = (0.0, 0.0)
        play.attack()
        play.window_controller.aim_attack_angle.assert_called_once()
        play.window_controller.press.assert_not_called()
        args, kwargs = play.window_controller.aim_attack_angle.call_args
        self.assertAlmostEqual(args[0], 0.0, places=3)
        self.assertGreaterEqual(kwargs.get("radius", args[1] if len(args) > 1 else 0), 200.0)
        self.assertGreaterEqual(kwargs.get("duration", 0.0), 0.05)

    def test_attack_pacing_suppresses_rapid_taps(self):
        play = self._make_play()
        play._last_attack_tap_at = time.time()
        play.attack()
        play.window_controller.press.assert_not_called()

    def test_hold_attack_calls_are_not_paced(self):
        play = self._make_play()
        play._last_attack_tap_at = time.time()
        play.attack(touch_up=False, touch_down=True)
        play.window_controller.press.assert_called_once_with("attack", touch_up=False, touch_down=True)

    def test_smart_aim_disabled_falls_back_to_tap_without_aimed_attacks(self):
        play = self._make_play()
        play.smart_aim_enabled = "no"
        play.aimed_attacks_enabled = "no"
        play._combat_target = {
            "player_pos": (50, 50),
            "pos": (300, 50),
            "distance": 250.0,
            "brawler": "shelly",
        }
        play._enemy_track["velocity"] = (0.0, 400.0)
        play.attack()
        play.window_controller.press.assert_called_once()
        play.window_controller.aim_attack_angle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
