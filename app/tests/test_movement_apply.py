import time
import unittest
from unittest.mock import MagicMock

from play import Play


class MovementApplyTests(unittest.TestCase):
    def test_loop_applies_analog_movement_every_frame(self):
        play = object.__new__(Play)
        play.is_showdown = True
        play.showdown_playstyle_mode = "follow"
        play.minimum_movement_delay = 0.4
        play.time_since_movement = time.time()
        play.last_movement = None
        play.last_movement_time = time.time()
        play.angle_smooth_factor = 0.28
        play.detect_wall_stuck = lambda *_args, **_kwargs: False
        play.semicircle_escape_step = lambda *_args, **_kwargs: None
        play.enemy_pressure_movement_fallback = lambda movement, *_args, **_kwargs: movement
        play.get_showdown_movement = lambda *_args, **_kwargs: 90.0
        play.window_controller = MagicMock()

        data = {"player": [[0, 0, 10, 10]], "enemy": [], "teammate": [], "wall": []}
        play.loop("shelly", data, time.time())
        play.loop("shelly", data, time.time())

        self.assertEqual(play.window_controller.move_joystick_angle.call_count, 2)


class FogCacheTests(unittest.TestCase):
    def test_refresh_fog_cache_populates_threat_and_direction(self):
        play = object.__new__(Play)
        play.detect_fog_threat = MagicMock(return_value=180.0)
        play.detect_fog_direction_escape = MagicMock(return_value=270.0)

        play._refresh_fog_cache(object(), (50, 50))

        self.assertEqual(play._fog_threat_cached, 180.0)
        self.assertEqual(play._fog_direction_escape_cached, 270.0)
        play.detect_fog_threat.assert_called_once()
        play.detect_fog_direction_escape.assert_called_once()


if __name__ == "__main__":
    unittest.main()
