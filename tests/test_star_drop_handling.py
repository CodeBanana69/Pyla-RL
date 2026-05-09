import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import cv2

from stage_manager import StageManager
from state_finder import get_in_game_state, get_star_drop_type


class DummyDropWindowController:
    def __init__(self):
        self._screenshot = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.clicks = []
        self.keys_released = []

    def screenshot(self):
        return self._screenshot

    def click(self, x, y, delay=0):
        self.clicks.append((x, y, delay))

    def keys_up(self, keys):
        self.keys_released.append(keys)


class StarDropHandlingTests(unittest.TestCase):
    def test_green_reward_like_screen_does_not_trigger_without_template(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        green_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (58, 230, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[110:850, 430:1330] = green_bgr
        image[30:100, 20:430] = (245, 245, 245)

        self.assertIsNone(get_star_drop_type(image))
        self.assertNotEqual(get_in_game_state(image), "star_drop")
        self.assertNotEqual(get_in_game_state(image), "daily_star_drop")

    def test_daily_wins_drop_screen_triggers_standard_star_drop(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        green_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (58, 230, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[90:850, 430:1330] = green_bgr
        image[30:125, 20:520] = (245, 245, 245)
        image[55:125, 40:520] = (10, 10, 10)
        image[45:155, 730:1160] = green_bgr
        image[70:150, 760:1160] = (10, 10, 10)
        image[260:760, 760:1160] = (35, 190, 245)
        image[430:620, 845:1075] = (5, 5, 5)
        image[300:390, 850:980] = (245, 245, 245)

        self.assertEqual(get_star_drop_type(image), "standard")
        self.assertEqual(get_in_game_state(image), "daily_star_drop")

    def test_daily_wins_tap_and_hold_drop_uses_long_press_type(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        purple_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (145, 210, 180), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        cyan_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (96, 180, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        pink_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (155, 160, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[:] = purple_bgr
        image[30:125, 20:520] = (245, 245, 245)
        image[55:125, 40:520] = (10, 10, 10)
        image[200:600, 590:880] = cyan_bgr
        image[200:600, 880:1160] = pink_bgr
        image[245:520, 690:1080] = (245, 245, 245)
        image[330:485, 800:970] = (5, 5, 5)
        image[780:850, 720:1200] = (245, 245, 245)
        image[805:875, 700:1220] = (5, 5, 5)

        self.assertEqual(get_star_drop_type(image), "daily_hold")
        self.assertEqual(get_in_game_state(image), "daily_star_drop")

    @patch("stage_manager.time.sleep", return_value=None)
    @patch("stage_manager.get_star_drop_type", return_value="daily_hold")
    def test_daily_wins_tap_and_hold_drop_uses_long_clicks(self, *_):
        manager = object.__new__(StageManager)
        manager.window_controller = DummyDropWindowController()

        manager.handle_star_drop()

        self.assertEqual(len(manager.window_controller.clicks), 3)
        self.assertTrue(all(click[2] == 0.45 for click in manager.window_controller.clicks))
        self.assertEqual(manager.window_controller.keys_released, [list("wasd")])

    @patch("stage_manager.time.sleep", return_value=None)
    @patch("stage_manager.get_star_drop_type", return_value="standard")
    def test_standard_star_drop_uses_five_fast_clicks(self, *_):
        manager = object.__new__(StageManager)
        manager.window_controller = DummyDropWindowController()

        manager.handle_star_drop()

        self.assertEqual(len(manager.window_controller.clicks), 5)
        self.assertTrue(all(click[2] == 0.04 for click in manager.window_controller.clicks))
        self.assertEqual(manager.window_controller.keys_released, [list("wasd")])

    def test_exact_standard_template_triggers_standard_star_drop(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        green_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (58, 230, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[75:905, 340:1580] = green_bgr
        image[20:175, 690:1230] = (80, 245, 80)
        template_path = Path("images/star_drop_types/star_drop.png")
        template = cv2.imread(str(template_path))
        self.assertIsNotNone(template)

        x, y, w, h = 790, 350, 350, 350
        th, tw = template.shape[:2]
        px = x + (w - tw) // 2
        py = y + (h - th) // 2
        image[py:py + th, px:px + tw] = template

        self.assertEqual(get_star_drop_type(image), "standard")
        self.assertEqual(get_in_game_state(image), "star_drop")

    def test_standard_template_without_drop_background_is_ignored(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        template = cv2.imread("images/star_drop_types/star_drop.png")
        self.assertIsNotNone(template)

        x, y, w, h = 790, 350, 350, 350
        th, tw = template.shape[:2]
        px = x + (w - tw) // 2
        py = y + (h - th) // 2
        image[py:py + th, px:px + tw] = template

        self.assertIsNone(get_star_drop_type(image))
        self.assertNotEqual(get_in_game_state(image), "star_drop")


if __name__ == "__main__":
    unittest.main()
