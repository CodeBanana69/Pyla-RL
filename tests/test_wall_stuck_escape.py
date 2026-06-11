import time
import unittest

import numpy as np

from play import Play


class WallStuckEscapeTests(unittest.TestCase):
    def make_play(self):
        play = object.__new__(Play)
        play.wall_stuck_enabled = True
        play.wall_stuck_ignore_radius = 150
        play.wall_stuck_sample_interval = 0.2
        play.wall_stuck_shift_threshold = 3.0
        play.wall_stuck_timeout = 1.0
        play.wall_stuck_min_walls = 3
        play.escape_retreat_duration = 0.4
        play.escape_arc_duration = 1.2
        play.escape_arc_degrees = 135.0
        play.wall_stuck_debug = False
        play.wall_stuck_state = {
            "last_sample_time": 0.0,
            "last_wall_centers": None,
            "stationary_since": None,
        }
        play.escape_state = {
            "phase": None,
            "started_at": 0.0,
            "retreat_angle": 0.0,
            "arc_side": 1,
        }
        play._next_arc_side = 1
        return play

    def test_stationary_walls_trigger_after_timeout(self):
        play = self.make_play()
        walls = [[0, 0, 40, 40], [100, 0, 140, 40], [200, 0, 240, 40]]
        t0 = 1000.0
        self.assertFalse(play.detect_wall_stuck(walls, (500, 500), True, t0))
        self.assertFalse(play.detect_wall_stuck(walls, (500, 500), True, t0 + 0.25))
        self.assertTrue(play.detect_wall_stuck(walls, (500, 500), True, t0 + 1.5))

    def test_moving_walls_reset_timer(self):
        play = self.make_play()
        walls_a = [[0, 0, 40, 40], [100, 0, 140, 40], [200, 0, 240, 40]]
        walls_b = [[5, 0, 45, 40], [105, 0, 145, 40], [205, 0, 245, 40]]
        t0 = 2000.0
        play.detect_wall_stuck(walls_a, (500, 500), True, t0)
        play.detect_wall_stuck(walls_a, (500, 500), True, t0 + 0.5)
        self.assertFalse(play.detect_wall_stuck(walls_b, (500, 500), True, t0 + 0.7))

    def test_semicircle_escape_retreat_then_arc(self):
        play = self.make_play()
        t0 = 3000.0
        play.start_semicircle_escape(0.0, t0)
        self.assertAlmostEqual(play.semicircle_escape_step(t0), 180.0)
        self.assertEqual(play.escape_state["phase"], "retreat")
        t_arc = t0 + play.escape_retreat_duration + 0.05
        angle_mid = play.semicircle_escape_step(t_arc)
        self.assertEqual(play.escape_state["phase"], "arc")
        self.assertIsNotNone(angle_mid)
        t_done = t_arc + play.escape_arc_duration + 0.05
        self.assertIsNone(play.semicircle_escape_step(t_done))
        self.assertIsNone(play.escape_state["phase"])

    def test_escape_arc_side_alternates(self):
        play = self.make_play()
        play.start_semicircle_escape(90.0, 100.0)
        first_side = play.escape_state["arc_side"]
        play.escape_state["phase"] = None
        play.start_semicircle_escape(90.0, 200.0)
        self.assertEqual(play.escape_state["arc_side"], -first_side)

    def test_sample_interval_throttles_wall_shift_checks(self):
        play = self.make_play()
        walls = [[0, 0, 40, 40], [100, 0, 140, 40], [200, 0, 240, 40]]
        t0 = 4000.0
        play.detect_wall_stuck(walls, (500, 500), True, t0)
        prev_sample = play.wall_stuck_state["last_sample_time"]
        play.detect_wall_stuck(walls, (500, 500), True, t0 + 0.05)
        self.assertEqual(play.wall_stuck_state["last_sample_time"], prev_sample)


if __name__ == "__main__":
    unittest.main()
