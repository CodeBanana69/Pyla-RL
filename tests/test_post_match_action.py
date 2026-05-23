import unittest
from unittest.mock import patch

import cv2
import numpy as np

from stage_manager import StageManager


class DummyWindowController:
    width_ratio = 1.0
    height_ratio = 1.0

    def __init__(self):
        self.clicks = []
        self.presses = []
        self.keys_released = []
        self.restart_calls = 0
        self.scrcpy_restart_calls = 0

    def click(self, x, y, **kwargs):
        self.clicks.append((x, y, kwargs))

    def press_key(self, key):
        self.presses.append(key)

    def keys_up(self, keys):
        self.keys_released.append(keys)

    def restart_brawl_stars(self):
        self.restart_calls += 1
        return True

    def restart_scrcpy_client(self):
        self.scrcpy_restart_calls += 1
        return True


class DummyTrophyObserver:
    current_trophies = 250
    current_wins = 0
    win_streak = 0

    def change_trophies(self, value):
        self.current_trophies = value


class DummyLobbyAutomation:
    def __init__(self):
        self.lowest_calls = 0

    def select_lowest_trophy_brawler(self):
        self.lowest_calls += 1
        return True


class PostMatchActionTests(unittest.TestCase):
    def make_manager(self, action):
        manager = object.__new__(StageManager)
        manager.post_match_action = action
        manager.window_controller = DummyWindowController()
        return manager

    def test_play_again_only_when_target_not_reached(self):
        manager = self.make_manager("play_again")

        self.assertTrue(manager.should_use_play_again(value=249, target=250))
        self.assertFalse(manager.should_use_play_again(value=250, target=250))

    def test_play_again_skips_when_target_reached_or_reselection_pending(self):
        manager = self.make_manager("play_again")
        manager.brawlers_pick_data = [
            {"brawler": "colt", "push_until": 250, "trophies": 250, "type": "trophies"},
            {"brawler": "shelly", "push_until": 250, "trophies": 10, "type": "trophies"},
        ]
        manager.Trophy_observer = DummyTrophyObserver()

        self.assertFalse(manager.should_use_play_again(value=249, target=250, active_brawler="colt"))
        manager.Trophy_observer.current_trophies = 249
        manager.pending_brawler_reselection = True
        self.assertFalse(manager.should_use_play_again(value=249, target=250, active_brawler="colt"))

    def test_play_again_skips_when_queue_front_differs_from_active_match(self):
        manager = self.make_manager("play_again")
        manager.brawlers_pick_data = [
            {"brawler": "shelly", "push_until": 500, "trophies": 100, "type": "trophies"},
        ]
        manager.Trophy_observer = DummyTrophyObserver()
        manager.Trophy_observer.current_trophies = 100

        self.assertFalse(
            manager.should_use_play_again(value=100, target=500, active_brawler="colt")
        )

    def test_lobby_mode_never_uses_play_again(self):
        manager = self.make_manager("lobby")

        self.assertFalse(manager.should_use_play_again(value=10, target=250))

    @patch("stage_manager.extract_text_strings", return_value=["play again"])
    def test_play_again_clicks_result_button_from_text_fallback(self, *_):
        manager = self.make_manager("play_again")
        manager.window_controller.screenshot = lambda: np.zeros((1080, 1920, 3), dtype=np.uint8)

        manager.dismiss_end_screen(use_play_again=True)

        self.assertEqual(manager.window_controller.presses, [])
        self.assertEqual(manager.window_controller.clicks[0][0:2], (1215, 935))
        self.assertIn(list("wasd"), manager.window_controller.keys_released)

    @patch("stage_manager.extract_text_strings", return_value=["exit"])
    def test_play_again_missing_clicks_exit_button(self, *_):
        manager = self.make_manager("play_again")
        manager.window_controller.screenshot = lambda: np.zeros((1080, 1920, 3), dtype=np.uint8)

        manager.dismiss_end_screen(use_play_again=True)

        self.assertEqual(manager.window_controller.presses, [])
        self.assertEqual(manager.window_controller.clicks[0][0:2], (1660, 980))
        self.assertIn(list("wasd"), manager.window_controller.keys_released)

    @patch("stage_manager.extract_text_strings", return_value=["exit", "play again"])
    def test_play_again_visible_does_not_exit_even_when_exit_exists(self, *_):
        manager = self.make_manager("play_again")
        manager.window_controller.screenshot = lambda: np.zeros((1080, 1920, 3), dtype=np.uint8)

        manager.dismiss_end_screen(use_play_again=True)

        self.assertEqual(manager.window_controller.presses, [])
        self.assertEqual(manager.window_controller.clicks[0][0:2], (1215, 935))
        self.assertIn(list("wasd"), manager.window_controller.keys_released)

    @patch("stage_manager.extract_text_strings", return_value=[])
    def test_play_again_does_not_click_disabled_or_missing_button(self, *_):
        manager = self.make_manager("play_again")
        screenshot = np.zeros((1080, 1920, 3), dtype=np.uint8)
        screenshot[850:1000, 1030:1390] = (95, 95, 95)
        screenshot[890:950, 1120:1300] = (210, 210, 210)
        manager.window_controller.screenshot = lambda: screenshot

        manager.dismiss_end_screen(use_play_again=True)

        self.assertEqual(manager.window_controller.clicks, [])
        self.assertEqual(manager.window_controller.presses, ["Q"])

    def test_play_again_visual_button_skips_ocr(self):
        manager = self.make_manager("play_again")
        screenshot = np.zeros((1080, 1920, 3), dtype=np.uint8)
        blue_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (108, 210, 220), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        blue_rgb = tuple(int(v) for v in blue_bgr[::-1])
        screenshot[850:1000, 1030:1390] = blue_rgb
        screenshot[890:950, 1120:1300] = (255, 255, 255)
        screenshot[960:1000, 1030:1390] = (5, 5, 5)
        manager.window_controller.screenshot = lambda: screenshot

        with patch("stage_manager.extract_text_strings", side_effect=AssertionError("OCR should not run")):
            manager.dismiss_end_screen(use_play_again=True)

        self.assertEqual(manager.window_controller.clicks[0][0:2], (1215, 935))

    def test_exit_visual_button_skips_ocr_when_play_again_missing(self):
        manager = self.make_manager("play_again")
        screenshot = np.zeros((1080, 1920, 3), dtype=np.uint8)
        blue_bgr = cv2.cvtColor(
            np.full((1, 1, 3), (108, 210, 220), dtype=np.uint8),
            cv2.COLOR_HSV2BGR,
        )[0, 0]
        blue_rgb = tuple(int(v) for v in blue_bgr[::-1])
        screenshot[850:1020, 1480:1860] = blue_rgb
        screenshot[900:970, 1580:1740] = (255, 255, 255)
        screenshot[980:1020, 1480:1860] = (5, 5, 5)
        manager.window_controller.screenshot = lambda: screenshot

        with patch("stage_manager.extract_text_strings", side_effect=AssertionError("OCR should not run")):
            manager.dismiss_end_screen(use_play_again=True)

        self.assertEqual(manager.window_controller.clicks[0][0:2], (1660, 980))

    def test_lobby_mode_presses_continue_key(self):
        manager = self.make_manager("lobby")

        manager.dismiss_end_screen(use_play_again=False)

        self.assertEqual(manager.window_controller.clicks, [])
        self.assertEqual(manager.window_controller.presses, ["Q"])
        self.assertIn(list("wasd"), manager.window_controller.keys_released)

    @patch("stage_manager.save_brawler_data")
    def test_target_completion_in_play_again_mode_returns_to_lobby(self, *_):
        manager = self.make_manager("play_again")
        manager.brawlers_pick_data = [
            {
                "brawler": "first",
                "push_until": 250,
                "trophies": 250,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": False,
                "win_streak": 0,
                "selection_method": "lowest_trophies",
            },
            {
                "brawler": "second",
                "push_until": 250,
                "trophies": 10,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": True,
                "win_streak": 0,
                "selection_method": "lowest_trophies",
            },
        ]
        manager.Trophy_observer = DummyTrophyObserver()
        manager.active_match_brawler = "first"

        self.assertFalse(manager.should_use_play_again(value=250, target=250, active_brawler="first"))
        self.assertTrue(manager.should_return_to_lobby_after_match(active_brawler="first"))

    @patch("stage_manager.save_brawler_data")
    def test_target_completion_stages_queue_without_commit(self, *_):
        manager = self.make_manager("play_again")
        manager.brawlers_pick_data = [
            {
                "brawler": "first",
                "push_until": 250,
                "trophies": 249,
                "wins": 0,
                "type": "trophies",
                "win_streak": 0,
            },
            {
                "brawler": "second",
                "push_until": 250,
                "trophies": 10,
                "wins": 0,
                "type": "trophies",
                "win_streak": 0,
            },
        ]
        manager.Trophy_observer = DummyTrophyObserver()
        manager.Trophy_observer.current_trophies = 250
        manager.active_match_brawler = "first"
        manager.pending_queue = None
        notifications = []
        manager.send_webhook_notification = lambda event, screenshot, details: notifications.append(
            (event, details.get("brawler"), details.get("target"))
        )
        manager._notified_brawler_completions = set()
        manager._stage_next_queue_after_target(250, "trophies", source="target")

        self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "first")
        self.assertEqual(manager.pending_queue[0]["brawler"], "second")
        self.assertFalse(manager.should_use_play_again(value=250, target=250, active_brawler="first"))

    def test_match_row_progress_uses_active_match_brawler(self):
        manager = self.make_manager("play_again")
        manager.brawlers_pick_data = [
            {"brawler": "shelly", "push_until": 500, "trophies": 100, "type": "trophies"},
            {"brawler": "colt", "push_until": 250, "trophies": 250, "type": "trophies"},
        ]
        manager.Trophy_observer = DummyTrophyObserver()
        manager.Trophy_observer.current_trophies = 250
        manager.active_match_brawler = "colt"

        value, target, type_of_push = manager._match_row_progress("colt")

        self.assertEqual(value, 250)
        self.assertEqual(target, 250)
        self.assertEqual(type_of_push, "trophies")


if __name__ == "__main__":
    unittest.main()
