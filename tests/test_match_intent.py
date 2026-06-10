import io
import unittest
from contextlib import redirect_stdout

import runtime_log
from play import Play


class MatchIntentTests(unittest.TestCase):
    def setUp(self):
        runtime_log._once_times.clear()
        runtime_log.configure()

    def test_update_match_intent_logs_engaging_enemy(self):
        play = Play.__new__(Play)
        play.current_brawler = "shelly"
        play.brawler_ranges = {"shelly": (301, 490, 490)}
        play.brawlers_info = {}
        play.enemy_spacing_enabled = True
        play.enemy_spacing_blend = 0.35
        play._spacing_action = "approach"
        play.get_brawler_range = lambda _brawler: play.brawler_ranges["shelly"]
        play.get_effective_enemy_range = lambda _brawler: 367
        play.is_there_enemy = lambda enemies: bool(enemies)
        play.find_closest_enemy = lambda *_args, **_kwargs: ((600, 100), 550.0)
        play.find_closest_teammate = lambda *_args, **_kwargs: (None, None)
        play.is_enemy_hittable = lambda *_args, **_kwargs: False
        play.get_entity_pos = Play.get_entity_pos

        data = {
            "player": [[0, 0, 100, 100]],
            "enemy": [[400, 0, 500, 100]],
            "teammate": [],
            "wall": [],
        }
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            play._update_match_intent("shelly", data)

        output = buffer.getvalue()
        self.assertIn("[Match]", output)
        self.assertIn("Closing in on enemy", output)
        self.assertEqual(play.match_intent_summary, "Closing in on enemy")

    def test_update_match_intent_logs_shooting(self):
        play = Play.__new__(Play)
        play.current_brawler = "shelly"
        play.brawler_ranges = {"shelly": (301, 490, 490)}
        play.brawlers_info = {}
        play._spacing_action = "hold"
        play.get_brawler_range = lambda _brawler: play.brawler_ranges["shelly"]
        play.get_effective_enemy_range = lambda _brawler: 367
        play.is_there_enemy = lambda enemies: bool(enemies)
        play.find_closest_enemy = lambda *_args, **_kwargs: ((200, 100), 180.0)
        play.find_closest_teammate = lambda *_args, **_kwargs: (None, None)
        play.is_enemy_hittable = lambda *_args, **_kwargs: True
        play.get_entity_pos = Play.get_entity_pos

        data = {
            "player": [[0, 0, 100, 100]],
            "enemy": [[150, 50, 250, 150]],
            "teammate": [],
            "wall": [],
        }
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            play._update_match_intent("shelly", data)

        self.assertIn("shooting", buffer.getvalue().lower())
        self.assertEqual(play.match_intent_summary, "Shooting")


if __name__ == "__main__":
    unittest.main()
