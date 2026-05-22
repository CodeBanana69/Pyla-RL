import unittest
from unittest.mock import patch

from stage_manager import StageManager


class DummyTrophyObserver:
    def __init__(self, trophies):
        self.current_trophies = trophies
        self.current_wins = 0
        self.win_streak = 0

    def change_trophies(self, value):
        self.current_trophies = value

    def add_trophies(self, result, _brawler):
        delta = {"win": 8, "loss": -6, "draw": 0}.get(result, 0)
        self.current_trophies += delta

    def add_win(self, _result):
        pass


class DummyWindowController:
    def screenshot(self):
        return None


class DummyLobbyAutomation:
    pass


class MatchTrophySyncTests(unittest.TestCase):
    def make_manager(self, trophies=100):
        manager = StageManager.__new__(StageManager)
        manager.brawlers_pick_data = [
            {
                "brawler": "shelly",
                "push_until": 500,
                "trophies": trophies,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": False,
                "win_streak": 0,
            },
            {
                "brawler": "colt",
                "push_until": 500,
                "trophies": 50,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": True,
                "win_streak": 0,
            },
        ]
        manager.Trophy_observer = DummyTrophyObserver(trophies)
        manager.window_controller = DummyWindowController()
        manager.Lobby_automation = DummyLobbyAutomation()
        manager.last_match_trophy_before = trophies
        manager.last_match_trophy_after = trophies + 8
        manager.last_match_trophy_delta = 8
        manager.last_match_crossed_1000 = False
        return manager

    @patch("stage_manager.save_brawler_data")
    @patch.object(StageManager, "_fetch_api_trophies_with_retry")
    @patch("stage_manager.load_brawl_stars_api_config")
    def test_sync_updates_current_and_queue_rows_from_api(
            self,
            mock_api_config,
            mock_fetch_trophies,
            mock_save,
    ):
        manager = self.make_manager(108)
        mock_api_config.return_value = {
            "api_token": "token",
            "player_tag": "#TAG",
            "sync_trophies_after_match": True,
        }
        mock_fetch_trophies.return_value = {
            "shelly": 112,
            "colt": 55,
        }

        self.assertTrue(manager.sync_trophies_from_api_after_match("shelly"))

        self.assertEqual(manager.Trophy_observer.current_trophies, 112)
        self.assertEqual(manager.brawlers_pick_data[0]["trophies"], 112)
        self.assertEqual(manager.brawlers_pick_data[1]["trophies"], 55)
        self.assertEqual(manager.last_match_trophy_after, 112)
        self.assertEqual(manager.last_match_trophy_delta, 4)
        mock_save.assert_called_once()

    @patch("stage_manager.save_brawler_data")
    @patch.object(StageManager, "_fetch_api_trophies_with_retry")
    @patch("stage_manager.load_brawl_stars_api_config")
    def test_sync_keeps_higher_local_estimate_for_active_brawler(
            self,
            mock_api_config,
            mock_fetch_trophies,
            mock_save,
    ):
        manager = self.make_manager(108)
        manager.Trophy_observer.current_trophies = 120
        mock_api_config.return_value = {
            "api_token": "token",
            "player_tag": "#TAG",
            "sync_trophies_after_match": True,
        }
        mock_fetch_trophies.return_value = {"shelly": 112, "colt": 50}

        self.assertTrue(manager.sync_trophies_from_api_after_match("shelly"))

        self.assertEqual(manager.Trophy_observer.current_trophies, 120)
        self.assertEqual(manager.brawlers_pick_data[0]["trophies"], 120)

    @patch.object(StageManager, "_fetch_api_trophies_with_retry")
    @patch("stage_manager.load_brawl_stars_api_config")
    def test_sync_skipped_when_disabled(self, mock_api_config, mock_fetch_trophies):
        manager = self.make_manager(100)
        mock_api_config.return_value = {
            "api_token": "token",
            "player_tag": "#TAG",
            "sync_trophies_after_match": False,
        }

        self.assertFalse(manager.sync_trophies_from_api_after_match("shelly"))
        mock_fetch_trophies.assert_not_called()

    @patch.object(StageManager, "_fetch_api_trophies_with_retry")
    @patch("stage_manager.load_brawl_stars_api_config")
    def test_sync_skipped_for_wins_mode(self, mock_api_config, mock_fetch_trophies):
        manager = self.make_manager(100)
        manager.brawlers_pick_data[0]["type"] = "wins"
        mock_api_config.return_value = {
            "api_token": "token",
            "player_tag": "#TAG",
            "sync_trophies_after_match": True,
        }

        self.assertFalse(manager.sync_trophies_from_api_after_match("shelly"))
        mock_fetch_trophies.assert_not_called()


if __name__ == "__main__":
    unittest.main()
