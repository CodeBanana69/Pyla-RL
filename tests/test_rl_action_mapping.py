import unittest

import numpy as np

from rl.policy_bridge import _action_to_angle, _action_to_movement, _angle_to_wasd


class ActionAngleTests(unittest.TestCase):
    def test_zero_action_returns_none(self):
        self.assertIsNone(_action_to_angle(np.array([0.0, 0.0])))

    def test_right_action_is_zero_degrees(self):
        angle = _action_to_angle(np.array([1.0, 0.0]))
        self.assertAlmostEqual(angle, 0.0, places=4)

    def test_down_action_is_ninety_degrees(self):
        angle = _action_to_angle(np.array([0.0, 1.0]))
        self.assertAlmostEqual(angle, 90.0, places=4)


class WasdMappingTests(unittest.TestCase):
    def test_right_maps_to_d(self):
        self.assertIn("D", _angle_to_wasd(0.0))
        self.assertNotIn("A", _angle_to_wasd(0.0))

    def test_down_left_combines_a_and_s(self):
        wasd = _angle_to_wasd(135.0)
        self.assertIn("A", wasd)
        self.assertIn("S", wasd)

    def test_up_right_combines_w_and_d(self):
        wasd = _angle_to_wasd(315.0)
        self.assertIn("W", wasd)
        self.assertIn("D", wasd)


class ActionMovementTests(unittest.TestCase):
    def test_showdown_returns_float_angle(self):
        movement = _action_to_movement(np.array([1.0, 0.0]), is_showdown=True)
        self.assertIsInstance(movement, float)

    def test_3v3_returns_wasd_string(self):
        movement = _action_to_movement(np.array([0.0, -1.0]), is_showdown=False)
        self.assertIsInstance(movement, str)
        self.assertIn("W", movement)

    def test_zero_action_returns_none_or_empty(self):
        self.assertIsNone(_action_to_movement(np.array([0.0, 0.0]), is_showdown=True))
        self.assertEqual(_action_to_movement(np.array([0.0, 0.0]), is_showdown=False), "")


if __name__ == "__main__":
    unittest.main()
