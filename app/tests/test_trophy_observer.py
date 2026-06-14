import unittest
from unittest.mock import patch

from trophy_observer import TrophyObserver


class TrophyObserverTests(unittest.TestCase):
    def test_trio_showdown_first_place_starts_at_eleven_trophies(self):
        observer = TrophyObserver()
        observer.current_trophies = 0
        observer.win_streak = 1

        self.assertEqual(observer.calc_showdown_delta(0), 11)

    def test_trio_showdown_third_place_keeps_win_streak_as_tie(self):
        observer = TrophyObserver()
        observer.current_trophies = 490
        observer.current_wins = 0
        observer.win_streak = 8

        with patch.object(observer, "save_history"), patch.object(observer, "send_results_to_api"):
            observer.add_trophies("end_trio_showdown_2", "shelly", {"name": "test", "gamemodes": [], "brawlers": []})

        self.assertEqual(observer.win_streak, 8)
        self.assertEqual(observer.current_trophies, 492)

    def test_trio_showdown_fourth_place_resets_win_streak(self):
        observer = TrophyObserver()
        observer.current_trophies = 490
        observer.current_wins = 0
        observer.win_streak = 8

        with patch.object(observer, "save_history"), patch.object(observer, "send_results_to_api"):
            observer.add_trophies("end_trio_showdown_3", "shelly", {"name": "test", "gamemodes": [], "brawlers": []})

        self.assertEqual(observer.win_streak, 0)

    def test_win_streak_bonus_never_goes_negative(self):
        observer = TrophyObserver()
        observer.current_trophies = 100
        observer.win_streak = 1

        self.assertEqual(observer.win_streak_gain(), 0)

    def test_session_stats_track_victory_defeat_and_draw(self):
        observer = TrophyObserver()
        observer.current_trophies = 100
        playstyle = {"name": "test", "gamemodes": [], "brawlers": []}

        with patch.object(observer, "save_history"), patch.object(observer, "send_results_to_api"):
            observer.add_trophies("victory", "shelly", playstyle)
            observer.add_trophies("defeat", "shelly", playstyle)
            observer.add_trophies("draw", "shelly", playstyle)

        self.assertEqual(observer.session_stats(), {
            "session_wins": 1,
            "session_losses": 1,
            "session_draws": 1,
        })

    def test_started_trophies_uses_push_session_not_pre_match_value(self):
        observer = TrophyObserver()
        observer.current_trophies = 500
        observer.begin_brawler_push("shelly", 420)
        playstyle = {"name": "test", "gamemodes": [], "brawlers": []}

        with patch.object(observer, "save_history"), patch.object(observer, "send_results_to_api"):
            observer.add_trophies("victory", "shelly", playstyle)

        self.assertEqual(observer.last_match_record["started_trophies"], 420)
        self.assertEqual(observer.last_match_record["trophies"], 500 + observer.last_match_record["trophy_delta"])


if __name__ == "__main__":
    unittest.main()
