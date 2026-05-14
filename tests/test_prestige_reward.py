import unittest
import time
from unittest.mock import patch

import cv2
import numpy as np

from stage_manager import StageManager
from state_finder import (
    get_prestige_next_button_center,
    get_team_invite_reject_button_center,
    is_in_prestige_reward,
)


class DummyTrophyObserver:
    def __init__(self):
        self.current_trophies = 0
        self.current_wins = 0
        self.win_streak = 0

    def change_trophies(self, trophies):
        self.current_trophies = trophies


class DummyLobbyAutomation:
    def __init__(self):
        self.lowest_selected = False

    def select_lowest_trophy_brawler(self):
        self.lowest_selected = True


class DummyWindowController:
    width_ratio = 1.0
    height_ratio = 1.0

    def __init__(self):
        self.clicks = []
        self.presses = []
        self.keys_released = []
        self.device = None

    def keys_up(self, keys):
        self.keys_released.append(keys)

    def click(self, x, y, **kwargs):
        self.clicks.append((x, y))

    def press_key(self, key):
        self.presses.append(key)

    def screenshot(self):
        return np.zeros((1080, 1920, 3), dtype=np.uint8)


class PrestigeRewardTests(unittest.TestCase):
    @staticmethod
    def draw_team_invite_screen(image):
        blue = cv2.cvtColor(
            np.full((1, 1, 3), (105, 220, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        red = cv2.cvtColor(
            np.full((1, 1, 3), (2, 220, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        green = cv2.cvtColor(
            np.full((1, 1, 3), (60, 220, 230), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[220:860, 550:1370] = blue
        image[620:730, 615:950] = red
        image[620:730, 970:1305] = green

    @staticmethod
    def draw_prestige_screen(image, button_box=(1240, 930, 340, 100)):
        green = cv2.cvtColor(
            np.full((1, 1, 3), (60, 220, 220), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        purple = cv2.cvtColor(
            np.full((1, 1, 3), (140, 180, 180), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        blue = cv2.cvtColor(
            np.full((1, 1, 3), (112, 220, 220), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[140:700, 1080:1700] = purple
        image[170:580, 1160:1600] = blue
        x, y, w, h = button_box
        image[y:y + h, x:x + w] = green
        image[y + 25:y + 60, x + 120:x + 220] = (255, 255, 255)

    def test_prestige_reward_detector_requires_green_next_and_purple_badge(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.draw_prestige_screen(image)
        self.assertTrue(is_in_prestige_reward(image))

    def test_prestige_reward_detector_accepts_new_higher_next_button_layout(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.draw_prestige_screen(image, button_box=(1140, 840, 280, 105))

        self.assertTrue(is_in_prestige_reward(image))
        self.assertEqual(get_prestige_next_button_center(image), (1280, 892))

    def test_prestige_reward_detector_rejects_match_noise_without_next_text(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        green = cv2.cvtColor(
            np.full((1, 1, 3), (60, 220, 220), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        purple = cv2.cvtColor(
            np.full((1, 1, 3), (140, 180, 180), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[930:1030, 1240:1580] = green
        image[180:700, 1120:1700] = purple
        self.assertFalse(is_in_prestige_reward(image))

    def test_prestige_reward_detector_rejects_match_noise_without_big_badge(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        green = cv2.cvtColor(
            np.full((1, 1, 3), (60, 220, 220), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        purple = cv2.cvtColor(
            np.full((1, 1, 3), (140, 180, 180), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        blue = cv2.cvtColor(
            np.full((1, 1, 3), (112, 220, 220), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        image[80:700, 980:1740] = purple
        # Broken-up blue patches can happen in match terrain/effects, but the
        # reward screen has one large badge-shaped blue component.
        for y in range(130, 600, 90):
            for x in range(1080, 1660, 120):
                image[y:y + 44, x:x + 56] = blue
        image[840:945, 1140:1420] = green
        image[865:900, 1260:1360] = (255, 255, 255)

        self.assertFalse(is_in_prestige_reward(image))

    def test_prestige_reward_clicks_detected_next_button_advances_queue_and_selects_lowest(self):
        manager = object.__new__(StageManager)
        manager.brawlers_pick_data = [
            {"brawler": "gray", "trophies": 990, "push_until": 1000, "wins": 0, "win_streak": 0},
            {"brawler": "shelly", "trophies": 20, "push_until": 1000, "wins": 0, "win_streak": 0},
        ]
        manager.Trophy_observer = DummyTrophyObserver()
        manager.Trophy_observer.current_trophies = 1000
        manager.last_match_crossed_1000 = True
        manager.Lobby_automation = DummyLobbyAutomation()
        manager.window_controller = DummyWindowController()
        screenshot_bgr = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.draw_prestige_screen(screenshot_bgr, button_box=(1140, 840, 280, 105))
        manager.window_controller.screenshot = lambda: cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2RGB)

        with patch("stage_manager.get_state", return_value="lobby"), \
                patch.object(manager, "read_lobby_trophies_from_screenshot", return_value=0), \
                patch("stage_manager.save_brawler_data"):
            manager.handle_prestige_reward()

        self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "shelly")
        self.assertEqual(manager.Trophy_observer.current_trophies, 20)
        self.assertTrue(manager.Lobby_automation.lowest_selected)
        self.assertIn((1280, 892), manager.window_controller.clicks)

    def test_prestige_reward_does_not_force_switch_when_lobby_trophies_are_not_reset(self):
        manager = object.__new__(StageManager)
        manager.brawlers_pick_data = [
            {"brawler": "gray", "trophies": 999, "push_until": 1000, "wins": 0, "win_streak": 0},
            {"brawler": "shelly", "trophies": 20, "push_until": 1000, "wins": 0, "win_streak": 0},
        ]
        manager.Trophy_observer = DummyTrophyObserver()
        manager.Trophy_observer.current_trophies = 1000
        manager.last_match_crossed_1000 = True
        manager.Lobby_automation = DummyLobbyAutomation()
        manager.window_controller = DummyWindowController()
        screenshot_bgr = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.draw_prestige_screen(screenshot_bgr, button_box=(1140, 840, 280, 105))
        manager.window_controller.screenshot = lambda: cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2RGB)

        with patch("stage_manager.get_state", return_value="lobby"), \
                patch.object(manager, "read_lobby_trophies_from_screenshot", return_value=250), \
                patch("stage_manager.save_brawler_data"):
            manager.handle_prestige_reward()

        self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "gray")
        self.assertEqual(manager.Trophy_observer.current_trophies, 250)
        self.assertFalse(manager.Lobby_automation.lowest_selected)
        self.assertIn((1280, 892), manager.window_controller.clicks)

    def test_prestige_reward_trusts_confirmed_screen_when_lobby_ocr_fails(self):
        manager = object.__new__(StageManager)
        manager.brawlers_pick_data = [
            {"brawler": "gray", "trophies": 1000, "push_until": 1000, "wins": 0, "win_streak": 0},
        ]
        manager.Trophy_observer = DummyTrophyObserver()
        manager.Trophy_observer.current_trophies = 1000
        manager.last_match_crossed_1000 = True
        manager.Lobby_automation = DummyLobbyAutomation()
        manager.window_controller = DummyWindowController()
        manager.stop_after_post_match_rewards = False
        screenshot_bgr = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.draw_prestige_screen(screenshot_bgr, button_box=(1140, 840, 280, 105))
        manager.window_controller.screenshot = lambda: cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2RGB)

        with patch("stage_manager.get_state", return_value="lobby"), \
                patch.object(manager, "read_lobby_trophies_from_screenshot", return_value=None), \
                patch("stage_manager.save_brawler_data"):
            manager.handle_prestige_reward()

        self.assertTrue(manager.stop_after_post_match_rewards)
        self.assertIn("Q", manager.window_controller.presses)
        self.assertIn((1280, 892), manager.window_controller.clicks)

    def test_prestige_reward_handler_ignores_under_1000_trophies(self):
        manager = object.__new__(StageManager)
        manager.Trophy_observer = DummyTrophyObserver()
        manager.last_recorded_result_time = 0.0
        manager.time_since_last_stat_change = 0.0
        manager.last_match_trophy_delta = 0
        manager.last_match_crossed_1000 = False
        manager.brawlers_pick_data = [{"type": "trophies", "push_until": 1000, "trophies": 999}]
        manager.window_controller = DummyWindowController()
        screenshot_bgr = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.draw_prestige_screen(screenshot_bgr, button_box=(1140, 840, 280, 105))
        manager.window_controller.screenshot = lambda: cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2RGB)

        manager.handle_prestige_reward()

        self.assertEqual(manager.window_controller.clicks, [])
        self.assertEqual(manager.window_controller.presses, [])

    def test_prestige_reward_handler_allows_recent_trophy_result_without_1000_crossing(self):
        manager = object.__new__(StageManager)
        manager.Trophy_observer = DummyTrophyObserver()
        manager.Trophy_observer.current_trophies = 678
        manager.last_match_crossed_1000 = False
        manager.last_match_trophy_delta = -3
        manager.last_recorded_result_time = time.time()
        manager.time_since_last_stat_change = time.time()
        manager.brawlers_pick_data = [
            {"brawler": "gray", "type": "trophies", "push_until": 1000, "trophies": 678},
            {"brawler": "shelly", "type": "trophies", "push_until": 1000, "trophies": 20},
        ]
        manager.Lobby_automation = DummyLobbyAutomation()
        manager.window_controller = DummyWindowController()
        screenshot_bgr = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.draw_prestige_screen(screenshot_bgr, button_box=(1140, 840, 280, 105))
        manager.window_controller.screenshot = lambda: cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2RGB)

        with patch("stage_manager.get_state", return_value="lobby"), \
                patch.object(manager, "read_lobby_trophies_from_screenshot", return_value=678), \
                patch("stage_manager.save_brawler_data"):
            manager.handle_prestige_reward()

        self.assertIn((1280, 892), manager.window_controller.clicks)
        self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "gray")
        self.assertFalse(manager.Lobby_automation.lowest_selected)

    def test_prestige_reward_handler_ignores_when_no_recent_trophy_result(self):
        for target in (1250, 1500):
            with self.subTest(target=target):
                manager = object.__new__(StageManager)
                manager.Trophy_observer = DummyTrophyObserver()
                manager.Trophy_observer.current_trophies = target
                manager.last_recorded_result_time = 0.0
                manager.time_since_last_stat_change = 0.0
                manager.last_match_trophy_delta = 0
                manager.last_match_crossed_1000 = False
                manager.brawlers_pick_data = [{"type": "trophies", "push_until": target, "trophies": target}]
                manager.window_controller = DummyWindowController()
                screenshot_bgr = np.zeros((1080, 1920, 3), dtype=np.uint8)
                self.draw_prestige_screen(screenshot_bgr, button_box=(1140, 840, 280, 105))
                manager.window_controller.screenshot = lambda: cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2RGB)

                manager.handle_prestige_reward()

                self.assertEqual(manager.window_controller.clicks, [])
                self.assertEqual(manager.window_controller.presses, [])

    def test_recent_trophy_change_requires_real_delta_and_expires(self):
        manager = object.__new__(StageManager)
        manager.last_recorded_result_time = time.time()
        manager.time_since_last_stat_change = time.time()
        manager.last_match_trophy_delta = 5

        self.assertTrue(manager.had_recent_trophy_change(seconds=30.0))

        manager.last_match_trophy_delta = 0
        self.assertFalse(manager.had_recent_trophy_change(seconds=30.0))

        manager.last_match_trophy_delta = 5
        manager.last_recorded_result_time = time.time() - 31
        manager.time_since_last_stat_change = time.time() - 31
        self.assertFalse(manager.had_recent_trophy_change(seconds=30.0))

    def test_team_invite_reject_releases_movement_and_uses_adb_fallback(self):
        manager = object.__new__(StageManager)
        manager.window_controller = DummyWindowController()
        manager.last_team_invite_reject_time = 0.0
        screenshot_bgr = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.draw_team_invite_screen(screenshot_bgr)
        screenshot_rgb = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2RGB)
        manager.window_controller.screenshot = lambda: screenshot_rgb
        center = get_team_invite_reject_button_center(screenshot_rgb, image_is_rgb=True)
        adb_taps = []

        def adb_fallback(x, y, screenshot_shape=None):
            adb_taps.append((x, y, screenshot_shape))
            return True

        manager.tap_with_adb_fallback = adb_fallback

        manager.close_pop_up()

        self.assertIn(list("wasd"), manager.window_controller.keys_released)
        self.assertIn(center, manager.window_controller.clicks)
        self.assertEqual(adb_taps, [(center[0], center[1], screenshot_rgb.shape)])


if __name__ == "__main__":
    unittest.main()
