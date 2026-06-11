import unittest

import cv2
import numpy as np

from stage_manager import StageManager
from state_finder import (
    get_in_game_state,
    get_skin_reward_continue_button_center,
    get_skin_reward_equip_button_center,
    is_in_reward_unlock,
)


class DummyWindowController:
    def __init__(self, screenshot):
        self._screenshot = screenshot
        self.clicks = []
        self.presses = []
        self.keys_released = []

    def screenshot(self):
        return self._screenshot

    def click(self, x, y, **kwargs):
        self.clicks.append((x, y))

    def press_key(self, key):
        self.presses.append(key)

    def keys_up(self, keys):
        self.keys_released.append(keys)


class RewardUnlockTests(unittest.TestCase):
    @staticmethod
    def draw_reward_unlock_screen():
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        blue = cv2.cvtColor(
            np.full((1, 1, 3), (104, 210, 215), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        light_blue = cv2.cvtColor(
            np.full((1, 1, 3), (98, 70, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        yellow = cv2.cvtColor(
            np.full((1, 1, 3), (28, 220, 245), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[:, :] = blue
        image[160:230, 760:1180] = (245, 245, 245)
        image[175:245, 750:1190] = (10, 10, 10)
        image[160:230, 760:1180] = (245, 245, 245)
        image[300:520, 780:1140] = light_blue
        image[520:620, 820:1100] = (0, 0, 0)
        image[650:730, 770:1160] = (0, 0, 0)
        image[630:710, 790:1140] = yellow
        return image

    @staticmethod
    def draw_skin_reward_screen():
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        pink = cv2.cvtColor(
            np.full((1, 1, 3), (160, 190, 210), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        green = cv2.cvtColor(
            np.full((1, 1, 3), (58, 230, 210), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        blue = cv2.cvtColor(
            np.full((1, 1, 3), (110, 220, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[:, :] = pink
        image[20:85, 1020:1680] = (245, 245, 245)
        image[42:100, 1010:1700] = (5, 5, 5)
        image[20:85, 1020:1680] = (245, 245, 245)
        image[210:520, 900:1720] = green
        image[280:470, 900:1420] = (245, 245, 245)
        image[850:1000, 885:1305] = (5, 5, 5)
        image[850:975, 885:1305] = blue
        image[890:950, 975:1215] = (245, 245, 245)
        return image

    @staticmethod
    def draw_skin_reward_equip_screen():
        image = RewardUnlockTests.draw_skin_reward_screen()
        green = cv2.cvtColor(
            np.full((1, 1, 3), (58, 230, 210), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[850:1000, 1330:1850] = (5, 5, 5)
        image[850:975, 1330:1850] = green
        image[890:950, 1420:1765] = (245, 245, 245)
        return image

    def test_reward_unlock_detector_accepts_blue_unlocked_screen(self):
        image = self.draw_reward_unlock_screen()

        self.assertTrue(is_in_reward_unlock(image))
        self.assertEqual(get_in_game_state(image), "reward_unlock")

    def test_reward_unlock_detector_rejects_match_like_screen(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        image[:, :] = (70, 60, 80)
        image[160:230, 760:1180] = (245, 245, 245)
        image[630:710, 790:1140] = (0, 220, 255)

        self.assertFalse(is_in_reward_unlock(image))
        self.assertNotEqual(get_in_game_state(image), "reward_unlock")

    def test_skin_reward_detector_accepts_continue_screen(self):
        image = self.draw_skin_reward_screen()

        self.assertTrue(is_in_reward_unlock(image))
        self.assertEqual(get_in_game_state(image), "reward_unlock")
        self.assertEqual(get_skin_reward_continue_button_center(image), (1095, 925))

    def test_skin_reward_handler_clicks_continue_button(self):
        image_bgr = self.draw_skin_reward_screen()
        screenshot_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        manager = object.__new__(StageManager)
        manager.window_controller = DummyWindowController(screenshot_rgb)

        manager.handle_reward_unlock()

        self.assertIn(list("wasd"), manager.window_controller.keys_released)
        self.assertEqual(manager.window_controller.clicks, [(1095, 925)])
        self.assertEqual(manager.window_controller.presses, [])

    def test_skin_reward_handler_clicks_equip_now_before_continue(self):
        image_bgr = self.draw_skin_reward_equip_screen()
        screenshot_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        manager = object.__new__(StageManager)
        manager.window_controller = DummyWindowController(screenshot_rgb)

        manager.handle_trophy_reward()

        self.assertTrue(is_in_reward_unlock(image_bgr))
        self.assertEqual(get_skin_reward_equip_button_center(image_bgr), (1590, 920))
        self.assertIn(list("wasd"), manager.window_controller.keys_released)
        self.assertEqual(manager.window_controller.clicks, [(1590, 920)])
        self.assertEqual(manager.window_controller.presses, [])


if __name__ == "__main__":
    unittest.main()
