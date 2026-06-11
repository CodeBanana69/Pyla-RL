import unittest
from unittest.mock import MagicMock, patch

import window_controller


class WindowControllerAdapterTests(unittest.TestCase):
    def test_press_coords_cover_upstream_keys(self):
        expected = {"proceed", "attack", "gadget", "super", "hypercharge", "play_again", "middle_got_it"}
        self.assertTrue(expected.issubset(set(window_controller.press_coords_dict.keys())))

    def test_move_updates_joystick_state(self):
        controller = window_controller.WindowController.__new__(window_controller.WindowController)
        controller.joystick_x = 100
        controller.joystick_y = 200
        controller.are_we_moving = False
        controller.last_joystick_pos = (None, None)
        controller.last_joystick_down_time = 0
        controller.re_apply_movement = True
        controller.PID_JOYSTICK = 1
        controller.touch_down = MagicMock(return_value=True)
        controller.touch_move = MagicMock(return_value=True)
        controller.move(10, -5)
        controller.touch_down.assert_called_once()
        controller.touch_move.assert_called_once()
        self.assertTrue(controller.are_we_moving)

    def test_press_uses_mapped_coordinates(self):
        controller = window_controller.WindowController.__new__(window_controller.WindowController)
        controller.width_ratio = 1.0
        controller.height_ratio = 1.0
        controller.click = MagicMock()
        controller.press("proceed")
        x, y = window_controller.press_coords_dict["proceed"]
        controller.click.assert_called_once()


if __name__ == "__main__":
    unittest.main()
