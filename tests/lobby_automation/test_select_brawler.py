import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from lobby_automation import LobbyAutomation


class TestLobbyAutomation(unittest.TestCase):

    @patch("lobby_automation.load_toml_as_dict")
    def setUp(self, mock_load_toml):
        mock_load_toml.return_value = {"lobby": {"brawler_btn": (0, 0), "select_btn": (0, 0)}}
        self.mock_window_controller = MagicMock()
        self.mock_window_controller.width_ratio = 1
        self.mock_window_controller.height_ratio = 1
        self.lobby = LobbyAutomation(self.mock_window_controller)

    @patch("lobby_automation.extract_text_and_positions")
    def test_can_select_brawlers(self, mock_extract_text):
        """Tests that bot can select brawlers once he reaches the brawlers selection menu."""
        expected_brawler_x = 2012
        expected_brawler_y = 978
        tolerance = 50

        # The project config uses ocr_scale_down_factor = 0.5, so these are
        # scaled-down OCR coordinates for the expected full-size click.
        mock_extract_text.return_value = {"shelly": {"center": (1006, 536)}}

        test_image = np.array(Image.open("./tests/assets/brawlers_menu.PNG"))
        self.mock_window_controller.screenshot.return_value = test_image

        self.lobby.select_brawler("shelly")

        self.assertTrue(self.mock_window_controller.click.called, "No clicks were made at all")
        self.assert_click_within_tolerance(expected_brawler_x, expected_brawler_y, tolerance)

    def assert_click_within_tolerance(self, expected_x, expected_y, tolerance=50):
        """Check if any click was within tolerance of expected coordinates."""
        self.assertTrue(self.mock_window_controller.click.called, "No clicks were made")

        click_calls = self.mock_window_controller.click.call_args_list

        for call in click_calls:
            actual_x, actual_y = call[0][0], call[0][1]
            distance_x = abs(actual_x - expected_x)
            distance_y = abs(actual_y - expected_y)

            if distance_x <= tolerance and distance_y <= tolerance:
                print(f"Click found at ({actual_x}, {actual_y}) within {tolerance}px of ({expected_x}, {expected_y})")
                return True

        click_coords = [(call[0][0], call[0][1]) for call in click_calls]
        self.fail(
            f"No click within {tolerance}px of ({expected_x}, {expected_y}). "
            f"Actual clicks: {click_coords}"
        )


class DummyBrawlerMenuController:
    width_ratio = 1.0
    height_ratio = 1.0

    def __init__(self):
        self.clicks = []
        self.back_presses = 0

    def click(self, x, y):
        self.clicks.append((x, y))

    def android_back(self):
        self.back_presses += 1
        return True

    def screenshot(self):
        return np.zeros((1080, 1920, 3), dtype=np.uint8)


class TestOpenBrawlerSelection(unittest.TestCase):
    @patch("lobby_automation.extract_text_and_positions", return_value={})
    @patch("lobby_automation.time.sleep", return_value=None)
    @patch("lobby_automation.get_state", side_effect=["lobby", "shop", "lobby", "brawler_selection"])
    def test_retries_when_brawler_button_opens_lobby_panel(self, *_):
        automation = object.__new__(LobbyAutomation)
        automation.window_controller = DummyBrawlerMenuController()
        automation.coords_cfg = {"lobby": {"brawler_btn": (110, 490), "select_btn": (0, 0)}}

        self.assertTrue(automation.open_brawler_selection())

        self.assertEqual(automation.window_controller.back_presses, 1)
        first_click = automation.window_controller.clicks[0]
        self.assertLess(first_click[1], 650)
        self.assertEqual(first_click, (70, 500))

    @patch("lobby_automation.extract_text_and_positions", return_value={})
    @patch("lobby_automation.time.sleep", return_value=None)
    @patch("lobby_automation.get_state", side_effect=["lobby", "shop", "lobby", "shop", "lobby", "shop", "lobby", "shop", "lobby", "shop", "lobby", "shop", "lobby", "shop", "lobby", "brawler_selection"])
    def test_retries_upper_brawler_button_band_after_lobby_panels(self, *_):
        automation = object.__new__(LobbyAutomation)
        automation.window_controller = DummyBrawlerMenuController()
        automation.coords_cfg = {"lobby": {"brawler_btn": (110, 490), "select_btn": (0, 0)}}

        self.assertTrue(automation.open_brawler_selection(attempts=8))

        self.assertIn((76, 420), automation.window_controller.clicks)
        self.assertGreaterEqual(automation.window_controller.back_presses, 7)

    @patch("lobby_automation.extract_text_and_positions", return_value={"BRAWLERS": {"center": (96, 430)}})
    @patch("lobby_automation.time.sleep", return_value=None)
    @patch("lobby_automation.get_state", side_effect=["lobby", "brawler_selection"])
    def test_uses_visible_brawlers_label_when_available(self, *_):
        automation = object.__new__(LobbyAutomation)
        automation.window_controller = DummyBrawlerMenuController()
        automation.coords_cfg = {"lobby": {"brawler_btn": (110, 490), "select_btn": (0, 0)}}

        self.assertTrue(automation.open_brawler_selection())

        self.assertEqual(automation.window_controller.clicks, [(96, 430)])

    @patch("lobby_automation.extract_text_and_positions", return_value={
        "gus": {"center": (420, 300)},
        "jessie": {"center": (720, 300)},
    })
    @patch("lobby_automation.time.sleep", return_value=None)
    @patch("lobby_automation.get_state", side_effect=["lobby", "shop"])
    def test_accepts_brawler_grid_when_state_looks_like_shop(self, *_):
        automation = object.__new__(LobbyAutomation)
        automation.window_controller = DummyBrawlerMenuController()
        automation.coords_cfg = {"lobby": {"brawler_btn": (110, 490), "select_btn": (0, 0)}}
        automation.known_brawler_names = {"gus", "jessie", "shelly"}

        self.assertTrue(automation.open_brawler_selection())
        self.assertEqual(automation.window_controller.back_presses, 0)

    @patch("lobby_automation.extract_text_and_positions", return_value={})
    @patch("lobby_automation.time.sleep", return_value=None)
    @patch("lobby_automation.get_state", return_value="shop")
    def test_selection_failure_does_not_crash_startup(self, *_):
        automation = object.__new__(LobbyAutomation)
        automation.window_controller = DummyBrawlerMenuController()
        automation.coords_cfg = {"lobby": {"brawler_btn": (110, 490), "select_btn": (0, 0)}}

        self.assertFalse(automation.select_brawler("shelly"))
        self.assertGreaterEqual(automation.window_controller.back_presses, 1)


if __name__ == "__main__":
    unittest.main()
