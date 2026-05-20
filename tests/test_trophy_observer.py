import unittest
from unittest.mock import patch

from trophy_observer import TrophyObserver


class TrophyObserverTests(unittest.TestCase):
    def test_trio_showdown_first_place_starts_at_eleven_trophies(self):
        observer = TrophyObserver(["shelly"])
        observer.current_trophies = 0

        self.assertEqual(observer.calc_showdown_delta(0), 11)

    def test_trio_showdown_third_place_keeps_win_streak_as_tie(self):
        observer = TrophyObserver(["shelly"])
        observer.current_trophies = 490
        observer.current_wins = 0
        observer.win_streak = 8

        with patch.object(observer, "save_history"), patch.object(observer, "_write_trophy_log"):
            observer.add_trophies("3rd", "shelly")

        self.assertEqual(observer.win_streak, 8)
        self.assertEqual(observer.current_trophies, 492)

    def test_trio_showdown_fourth_place_resets_win_streak(self):
        observer = TrophyObserver(["shelly"])
        observer.current_trophies = 490
        observer.current_wins = 0
        observer.win_streak = 8

        with patch.object(observer, "save_history"), patch.object(observer, "_write_trophy_log"):
            observer.add_trophies("4th", "shelly")

        self.assertEqual(observer.win_streak, 0)

    def test_win_streak_bonus_never_goes_negative(self):
        observer = TrophyObserver(["shelly"])
        observer.current_trophies = 100
        observer.win_streak = 0

        self.assertEqual(observer.win_streak_gain(), 0)


if __name__ == "__main__":
    unittest.main()
