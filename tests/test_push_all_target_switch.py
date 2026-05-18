import unittest
from unittest.mock import patch

from stage_manager import StageManager


class DummyTrophyObserver:
    def __init__(self, trophies):
        self.current_trophies = trophies
        self.current_wins = 0
        self.win_streak = 0
        self.changed_to = None

    def change_trophies(self, value):
        self.changed_to = value
        self.current_trophies = value


class DummyWindowController:
    def __init__(self):
        self.pressed = []
        self.keys_released = []
        self.closed = False

    def screenshot(self):
        return None

    def keys_up(self, keys):
        self.keys_released.extend(keys)

    def press_key(self, key):
        self.pressed.append(key)

    def close(self):
        self.closed = True


class DummyLobbyAutomation:
    def __init__(self):
        self.lowest_calls = 0
        self.named_calls = []

    def select_lowest_trophy_brawler(self):
        self.lowest_calls += 1
        return True

    def select_brawler(self, name):
        self.named_calls.append(name)


class PushAllTargetSwitchTest(unittest.TestCase):
    def make_manager(self, target):
        manager = object.__new__(StageManager)
        manager.brawlers_pick_data = [
            {
                "brawler": "first",
                "push_until": target,
                "trophies": target,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": False,
                "win_streak": 0,
                "selection_method": "lowest_trophies",
            },
            {
                "brawler": "second",
                "push_until": target,
                "trophies": 0,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": True,
                "win_streak": 0,
                "selection_method": "lowest_trophies",
            },
        ]
        manager.started_trophies_by_brawler = {"first": target, "second": 0}
        manager.Trophy_observer = DummyTrophyObserver(target)
        manager.window_controller = DummyWindowController()
        manager.Lobby_automation = DummyLobbyAutomation()
        manager.send_webhook_notification = lambda *args, **kwargs: None
        manager.push_all_needs_selection = False
        manager.stop_after_post_match_rewards = False
        return manager

    @patch.object(StageManager, "refresh_push_all_trophies_from_api", return_value=False)
    @patch("stage_manager.save_brawler_data")
    @patch("stage_manager.time.sleep", return_value=None)
    @patch("stage_manager.get_state", return_value="lobby")
    def test_push_all_targets_switch_by_lowest_trophy_sort(self, *_):
        for target in (250, 500, 750, 1000, 1250, 1500):
            with self.subTest(target=target):
                manager = self.make_manager(target)

                manager.start_game()

                self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "second")
                self.assertEqual(manager.Trophy_observer.changed_to, 0)
                self.assertEqual(manager.Lobby_automation.lowest_calls, 1)
                self.assertEqual(manager.Lobby_automation.named_calls, [])
                self.assertIn("Q", manager.window_controller.pressed)

    @patch.object(StageManager, "refresh_push_all_trophies_from_api", return_value=False)
    @patch("stage_manager.save_brawler_data")
    @patch("stage_manager.time.sleep", return_value=None)
    @patch("stage_manager.get_state", return_value="lobby")
    def test_push_all_500_resorts_and_skips_already_completed_rows(self, *_):
        manager = self.make_manager(500)
        manager.brawlers_pick_data = [
            {
                "brawler": "first",
                "push_until": 500,
                "trophies": 500,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": False,
                "win_streak": 0,
                "selection_method": "lowest_trophies",
            },
            {
                "brawler": "almost_done",
                "push_until": 500,
                "trophies": 499,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": True,
                "win_streak": 0,
                "selection_method": "lowest_trophies",
            },
            {
                "brawler": "lowest",
                "push_until": 500,
                "trophies": 120,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": True,
                "win_streak": 0,
                "selection_method": "lowest_trophies",
            },
            {
                "brawler": "already_done",
                "push_until": 500,
                "trophies": 500,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": True,
                "win_streak": 0,
                "selection_method": "lowest_trophies",
            },
        ]

        manager.start_game()

        self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "lowest")
        self.assertEqual(manager.Trophy_observer.changed_to, 120)
        self.assertEqual(manager.Lobby_automation.lowest_calls, 1)
        self.assertEqual([row["brawler"] for row in manager.brawlers_pick_data], ["lowest", "almost_done"])

    @patch.object(StageManager, "refresh_push_all_trophies_from_api", return_value=False)
    @patch("stage_manager.save_brawler_data")
    @patch("stage_manager.time.sleep", return_value=None)
    @patch("stage_manager.get_state", return_value="lobby")
    def test_push_all_switches_when_saved_row_reached_target_even_if_observer_is_stale(self, *_):
        for target in (250, 500, 750, 1000, 1250, 1500):
            with self.subTest(target=target):
                manager = self.make_manager(target)
                manager.brawlers_pick_data[0]["trophies"] = target
                manager.Trophy_observer = DummyTrophyObserver(target - 1)

                manager.start_game()

                self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "second")
                self.assertEqual(manager.Trophy_observer.current_trophies, 0)
                self.assertEqual(manager.Lobby_automation.lowest_calls, 1)

    @patch("stage_manager.save_brawler_data")
    @patch("stage_manager.fetch_brawl_stars_player")
    @patch("stage_manager.load_brawl_stars_api_config")
    @patch("stage_manager.time.sleep", return_value=None)
    @patch("stage_manager.get_state", return_value="lobby")
    def test_push_all_switches_when_api_says_current_reached_target(
            self,
            _mock_get_state,
            _mock_sleep,
            mock_api_config,
            mock_fetch_player,
            _mock_save,
    ):
        for target in (500, 750, 1000, 1250, 1500):
            with self.subTest(target=target):
                manager = self.make_manager(target)
                manager.brawlers_pick_data[0]["trophies"] = target - 5
                manager.Trophy_observer = DummyTrophyObserver(target - 5)
                mock_api_config.return_value = {
                    "api_token": "token",
                    "player_tag": "#TAG",
                    "timeout_seconds": 15,
                }
                mock_fetch_player.return_value = {
                    "brawlers": [
                        {"name": "FIRST", "trophies": target},
                        {"name": "SECOND", "trophies": 25},
                    ]
                }

                manager.start_game()

                self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "second")
                self.assertTrue(manager.brawlers_pick_data[0]["automatically_pick"])
                self.assertEqual(manager.Trophy_observer.current_trophies, 25)
                self.assertEqual(manager.Lobby_automation.lowest_calls, 1)
                mock_fetch_player.reset_mock()

    @patch("stage_manager.save_brawler_data")
    @patch("stage_manager.fetch_brawl_stars_player")
    @patch("stage_manager.load_brawl_stars_api_config")
    @patch("stage_manager.time.sleep", return_value=None)
    @patch("stage_manager.get_state", return_value="lobby")
    def test_push_all_keeps_current_brawler_after_api_refresh_until_target(
            self,
            _mock_get_state,
            _mock_sleep,
            mock_api_config,
            mock_fetch_player,
            _mock_save,
    ):
        manager = self.make_manager(1000)
        manager.brawlers_pick_data = [
            {
                "brawler": "tara",
                "push_until": 1000,
                "trophies": 560,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": False,
                "win_streak": 0,
                "selection_method": "lowest_trophies",
            },
            {
                "brawler": "gale",
                "push_until": 1000,
                "trophies": 120,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": True,
                "win_streak": 0,
                "selection_method": "lowest_trophies",
            },
        ]
        manager.Trophy_observer = DummyTrophyObserver(560)
        mock_api_config.return_value = {
            "api_token": "token",
            "player_tag": "#TAG",
            "timeout_seconds": 15,
        }
        mock_fetch_player.return_value = {
            "brawlers": [
                {"name": "TARA", "trophies": 408},
                {"name": "GALE", "trophies": 120},
            ]
        }

        manager.start_game()

        self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "tara")
        self.assertEqual(manager.brawlers_pick_data[0]["trophies"], 560)
        self.assertEqual(manager.Trophy_observer.current_trophies, 560)
        self.assertEqual(manager.Lobby_automation.lowest_calls, 0)

    @patch("stage_manager.save_brawler_data")
    @patch("stage_manager.fetch_brawl_stars_player")
    @patch("stage_manager.load_brawl_stars_api_config")
    @patch("stage_manager.time.sleep", return_value=None)
    @patch("stage_manager.get_state", return_value="lobby")
    def test_push_all_api_refresh_does_not_roll_current_trophies_backwards(
            self,
            _mock_get_state,
            _mock_sleep,
            mock_api_config,
            mock_fetch_player,
            _mock_save,
    ):
        manager = self.make_manager(1000)
        manager.brawlers_pick_data = [
            {
                "brawler": "lumi",
                "push_until": 1000,
                "trophies": 48,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": False,
                "win_streak": 0,
                "selection_method": "lowest_trophies",
            },
            {
                "brawler": "tara",
                "push_until": 1000,
                "trophies": 37,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": True,
                "win_streak": 0,
                "selection_method": "lowest_trophies",
            },
        ]
        manager.Trophy_observer = DummyTrophyObserver(48)
        mock_api_config.return_value = {
            "api_token": "token",
            "player_tag": "#TAG",
            "timeout_seconds": 15,
        }
        mock_fetch_player.return_value = {
            "brawlers": [
                {"name": "LUMI", "trophies": 37},
                {"name": "TARA", "trophies": 37},
            ]
        }

        manager.start_game()

        self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "lumi")
        self.assertEqual(manager.brawlers_pick_data[0]["trophies"], 48)
        self.assertEqual(manager.Trophy_observer.current_trophies, 48)
        self.assertEqual(manager.Lobby_automation.lowest_calls, 0)

    @patch("stage_manager.save_brawler_data")
    @patch("stage_manager.fetch_brawl_stars_player")
    @patch("stage_manager.load_brawl_stars_api_config")
    @patch("stage_manager.time.sleep", return_value=None)
    @patch("stage_manager.get_state", return_value="lobby")
    def test_push_all_forces_token_refresh_after_access_denied(
            self,
            _mock_get_state,
            _mock_sleep,
            mock_api_config,
            mock_fetch_player,
            _mock_save,
    ):
        manager = self.make_manager(1000)
        manager.Trophy_observer = DummyTrophyObserver(560)
        mock_api_config.side_effect = [
            {"api_token": "old_token", "player_tag": "#TAG", "timeout_seconds": 15},
            {"api_token": "new_token", "player_tag": "#TAG", "timeout_seconds": 15},
        ]
        mock_fetch_player.side_effect = [
            RuntimeError("Brawl Stars API accessDenied. token rejected."),
            {"brawlers": [
                {"name": "FIRST", "trophies": 560},
                {"name": "SECOND", "trophies": 25},
            ]},
        ]

        manager.start_game()

        self.assertEqual(mock_api_config.call_args_list[0].kwargs.get("force_refresh"), False)
        self.assertEqual(mock_api_config.call_args_list[1].kwargs.get("force_refresh"), True)
        self.assertEqual(mock_fetch_player.call_count, 2)
        self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "first")
        self.assertEqual(manager.Lobby_automation.lowest_calls, 0)


if __name__ == "__main__":
    unittest.main()
