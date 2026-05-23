import unittest
from unittest.mock import patch

from lobby_automation import LobbyAutomation


class DummyWindowController:
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
        return None


class LowestTrophySelectionTests(unittest.TestCase):
    @patch("lobby_automation.time.sleep", return_value=None)
    def test_sorts_by_least_trophies_in_menu(self, *_):
        automation = object.__new__(LobbyAutomation)
        automation.window_controller = DummyWindowController()
        automation._dismiss_starr_nova_hub_if_present = lambda: False
        automation.ensure_lobby_after_selection = lambda: True

        automation.select_lowest_trophy_brawler()

        self.assertEqual(automation.window_controller.clicks[2], (1210, 426))

    @patch("lobby_automation.time.sleep", return_value=None)
    @patch.object(LobbyAutomation, "_select_brawler_on_open_grid", return_value=True)
    @patch.object(LobbyAutomation, "_apply_brawler_sort")
    @patch.object(LobbyAutomation, "open_brawler_selection", return_value=True)
    @patch.object(LobbyAutomation, "_dismiss_starr_nova_hub_if_present", return_value=False)
    def test_select_lowest_uses_named_grid_pick_for_queue_brawler(
        self,
        _dismiss,
        _open,
        mock_sort,
        mock_grid,
        *_,
    ):
        automation = object.__new__(LobbyAutomation)
        automation.window_controller = DummyWindowController()
        automation.ensure_lobby_after_selection = lambda: True

        self.assertTrue(automation.select_lowest_trophy_brawler("finx"))
        mock_sort.assert_called_once_with("lowest")
        mock_grid.assert_called_once_with("finx", sort_applied=True)

    @patch("lobby_automation.time.sleep", return_value=None)
    def test_always_clicks_first_lowest_trophy_brawler_card(self, *_):
        automation = object.__new__(LobbyAutomation)
        automation.window_controller = DummyWindowController()
        automation.ensure_lobby_after_selection = lambda: True

        automation.select_lowest_trophy_brawler()

        self.assertEqual(automation.window_controller.clicks[3], (422, 359))

    @patch("lobby_automation.time.sleep", return_value=None)
    @patch("lobby_automation.get_state", side_effect=["match", "lobby"])
    def test_recovers_if_lowest_selection_opens_details_screen(self, *_):
        automation = object.__new__(LobbyAutomation)
        automation.window_controller = DummyWindowController()

        self.assertTrue(automation.ensure_lobby_after_selection())
        self.assertEqual(automation.window_controller.back_presses, 1)


if __name__ == "__main__":
    unittest.main()
