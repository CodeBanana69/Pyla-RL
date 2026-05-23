import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from lobby_automation import LobbyAutomation


class TestLobbyAutomation(unittest.TestCase):

    @patch("lobby_automation.load_toml_as_dict")
    def setUp(self, mock_load_toml):
        mock_load_toml.return_value = {"lobby": {"brawler_btn": (0, 0), "select_btn": (0, 0)}}
        self.mock_window_controller = MagicMock()
        self.mock_window_controller.width_ratio = 1
        self.mock_window_controller.height_ratio = 1
        self.lobby = LobbyAutomation(self.mock_window_controller)

    @patch("lobby_automation.get_state", return_value="brawler_selection")
    @patch.object(LobbyAutomation, "open_brawler_selection", return_value=True)
    @patch.object(LobbyAutomation, "_verify_brawler_detail_card", return_value=True)
    @patch.object(LobbyAutomation, "_collect_easyocr_grid_matches")
    def test_can_select_brawlers(self, mock_matches, *_):
        """Tests EasyOCR-driven brawler selection clicks the portrait above the label."""
        box = {
            "center": (500, 400),
            "top_left": (470, 380),
            "top_right": (530, 380),
            "bottom_left": (470, 420),
            "bottom_right": (530, 420),
        }
        mock_matches.return_value = [(2.0, "shelly", box, "shelly")]

        test_image = np.zeros((540, 960, 3), dtype=np.uint8)
        self.mock_window_controller.screenshot.return_value = test_image

        self.lobby.coords_cfg = {"lobby": {"brawler_btn": (0, 0), "select_btn": (260, 991)}}
        self.assertTrue(self.lobby.select_brawler("shelly"))
        self.assertTrue(self.mock_window_controller.click.called)

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
        self.assertEqual(first_click, (96, 430))

    @patch.object(LobbyAutomation, "_ensure_lobby_before_brawler_click", return_value=True)
    @patch.object(LobbyAutomation, "_confirm_brawler_menu_open")
    @patch("lobby_automation.extract_text_and_positions", return_value={})
    @patch("lobby_automation.time.sleep", return_value=None)
    @patch("lobby_automation.get_state", return_value="shop")
    def test_retries_upper_brawler_button_band_after_lobby_panels(
        self,
        mock_state,
        _sleep,
        _extract,
        mock_confirm,
        _ensure,
    ):
        automation = object.__new__(LobbyAutomation)
        automation.window_controller = DummyBrawlerMenuController()
        automation.coords_cfg = {"lobby": {"brawler_btn": (110, 490), "select_btn": (0, 0)}}
        mock_confirm.side_effect = (
            lambda *_args, **_kwargs: len(automation.window_controller.clicks) >= 8
        )

        self.assertTrue(automation.open_brawler_selection(attempts=8))

        self.assertIn((76, 420), automation.window_controller.clicks)
        self.assertGreaterEqual(automation.window_controller.back_presses, 1)
        self.assertGreaterEqual(len(automation.window_controller.clicks), 8)

    @patch("lobby_automation.extract_text_and_positions", return_value={"BRAWLERS": {"center": (96, 430)}})
    @patch("lobby_automation.time.sleep", return_value=None)
    @patch("lobby_automation.get_state", side_effect=["lobby", "brawler_selection"])
    def test_uses_visible_brawlers_label_when_available(self, *_):
        automation = object.__new__(LobbyAutomation)
        automation.window_controller = DummyBrawlerMenuController()
        automation.coords_cfg = {"lobby": {"brawler_btn": (110, 490), "select_btn": (0, 0)}}

        self.assertTrue(automation.open_brawler_selection())

        self.assertEqual(automation.window_controller.clicks, [(96, 430)])

    @patch.object(LobbyAutomation, "_try_open_brawler_via_ocr", return_value=False)
    @patch("lobby_automation.extract_text_and_positions", return_value={"brawlers": {"center": (52, 259)}})
    @patch("lobby_automation.time.sleep", return_value=None)
    @patch("lobby_automation.get_state", side_effect=["lobby", "lobby"])
    def test_rejects_ocr_brawlers_label_outside_safe_band(self, *_):
        automation = object.__new__(LobbyAutomation)
        automation.window_controller = DummyBrawlerMenuController()
        automation.coords_cfg = {"lobby": {"brawler_btn": (110, 490), "select_btn": (0, 0)}}

        self.assertFalse(automation.open_brawler_selection(attempts=0))

        self.assertEqual(automation.window_controller.clicks, [])

    @patch("lobby_automation.extract_text_and_positions", return_value={
        "gus": {"center": (420, 300)},
        "jessie": {"center": (720, 300)},
    })
    @patch("lobby_automation.time.sleep", return_value=None)
    @patch("lobby_automation.get_state", side_effect=["lobby", "lobby", "shop"])
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


class TestBrawlerDetailVerification(unittest.TestCase):
    def setUp(self):
        automation = object.__new__(LobbyAutomation)
        automation.known_brawler_names = {"jacky", "shelly", "jessie"}
        self.automation = automation

    @patch.object(LobbyAutomation, "_select_button_visible", return_value=True)
    @patch.object(LobbyAutomation, "_detail_card_texts", return_value=["16/30", "wave hopper"])
    def test_accepts_detail_card_with_gadget_text_when_select_visible(self, *_):
        screenshot = np.zeros((540, 960, 3), dtype=np.uint8)
        self.assertTrue(self.automation._verify_brawler_detail_card(screenshot, "jacky"))

    @patch.object(LobbyAutomation, "_select_button_visible", return_value=True)
    @patch.object(LobbyAutomation, "_detail_card_texts", return_value=["jessie"])
    def test_rejects_conflicting_brawler_name_on_detail_card(self, *_):
        screenshot = np.zeros((540, 960, 3), dtype=np.uint8)
        self.assertFalse(self.automation._verify_brawler_detail_card(screenshot, "jacky"))

    def test_short_brawler_names_require_exact_grid_match(self):
        self.automation.known_brawler_names.add("bo")
        self.assertTrue(self.automation._is_confident_grid_name_match("bo", "bo"))
        self.assertFalse(self.automation._is_confident_grid_name_match("box", "bo"))

    def test_short_brawler_names_accept_ocr_digit_confusions(self):
        self.automation.known_brawler_names.update({"bo", "max", "gus"})
        self.assertEqual(self.automation._normalize_grid_label("8o"), "bo")
        self.assertEqual(self.automation._normalize_grid_label("BO"), "bo")
        self.assertTrue(self.automation._is_confident_grid_name_match("jacky", "jacky"))

    def test_text_box_click_uses_label_bbox(self):
        text_box = {
            "center": (500, 400),
            "top_left": (470, 380),
            "top_right": (530, 380),
            "bottom_left": (470, 420),
            "bottom_right": (530, 420),
        }
        click_x, click_y = self.automation._text_box_click_position(
            text_box,
            full_h=540,
            full_w=960,
        )
        self.assertEqual(click_x, 500)
        self.assertLess(click_y, 380)


class TestBrawlerGridScroll(unittest.TestCase):
    @patch.object(LobbyAutomation, "_wait_for_grid_settle", return_value=None)
    def test_scroll_uses_left_gutter_not_brawler_grid(self, _):
        controller = MagicMock()
        automation = object.__new__(LobbyAutomation)
        automation.window_controller = controller

        automation._scroll_brawler_grid(wr=0.5, hr=0.5)

        controller.swipe.assert_called_once()
        start_x, start_y, end_x, end_y = controller.swipe.call_args[0]
        self.assertEqual(start_x, 160)
        self.assertEqual(end_x, 160)
        self.assertEqual(start_y, 395)
        self.assertEqual(end_y, 285)
        self.assertGreater(start_y, end_y)


if __name__ == "__main__":
    unittest.main()
