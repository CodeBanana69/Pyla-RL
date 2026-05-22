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
        play.detect_wall_stuck = lambda *_args, **_kwargs: False
        play.semicircle_escape_step = lambda *_args, **_kwargs: None
        play.enemy_pressure_movement_fallback = lambda movement, *_args, **_kwargs: movement
        play.get_showdown_movement = lambda *_args, **_kwargs: 90.0
        play.window_controller = MagicMock()

        data = {"player": [[0, 0, 10, 10]], "enemy": [], "teammate": [], "wall": []}
        play.loop("shelly", data, time.time())
        play.loop("shelly", data, time.time())

        self.assertEqual(play.window_controller.move_joystick_angle.call_count, 2)


if __name__ == "__main__":
    unittest.main()
