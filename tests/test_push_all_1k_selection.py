import unittest
from unittest.mock import patch

from gui.select_brawler import SelectBrawler


class PushAll1kSelectionTest(unittest.TestCase):
    def test_start_bot_closes_selector_before_heavy_startup(self):
        obj = object.__new__(SelectBrawler)
        obj.brawlers_data = [{"brawler": "shelly"}]
        obj._closing = False
        obj._filter_after_id = None
        obj._image_render_after_id = None
        calls = []

        def close_app():
            calls.append("close")

        def data_setter(data):
            calls.append(("start", data))

        class DummyApp:
            def quit(self):
                calls.append("quit")

        obj._hide_window = close_app
        obj.app = DummyApp()
        obj.data_setter = data_setter

        SelectBrawler.start_bot(obj)

        self.assertEqual(calls[0], "close")
        self.assertEqual(calls[1], ("start", [{"brawler": "shelly"}]))
        self.assertEqual(calls[2], "quit")

    def test_ocr_match_accepts_close_brawler_name(self):
        brawler = SelectBrawler._match_brawler_from_ocr_texts(["M1NA"], ["meg", "mina", "ziggy"])

        self.assertEqual(brawler, "mina")

    def test_ocr_match_uses_names_alias_file(self):
        brawler = SelectBrawler._match_brawler_from_ocr_texts(["larrys lawrie"], ["larry & lawrie", "leon"])

        self.assertEqual(brawler, "larry & lawrie")

    def test_selected_game_brawler_moves_to_front_and_flags_update(self):
        data = [
            {"brawler": "meg", "automatically_pick": False, "trophies": 0},
            {"brawler": "mina", "automatically_pick": True, "trophies": 0},
            {"brawler": "ziggy", "automatically_pick": True, "trophies": 0},
        ]

        reordered = SelectBrawler._move_brawler_to_front(data, "mina")

        self.assertEqual(reordered[0]["brawler"], "mina")
        self.assertFalse(reordered[0]["automatically_pick"])
        self.assertTrue(reordered[1]["automatically_pick"])
        self.assertTrue(reordered[2]["automatically_pick"])

    def test_push_all_target_filters_and_sets_target_amount(self):
        obj = object.__new__(SelectBrawler)
        obj.brawlers = ["shelly", "colt", "meg"]
        player_data = {
            "brawlers": [
                {"name": "Shelly", "trophies": 249},
                {"name": "Colt", "trophies": 500},
                {"name": "Meg", "trophies": 750},
            ]
        }

        with patch("gui.select_brawler.load_brawl_stars_api_config", return_value={
            "api_token": "token",
            "player_tag": "TAG",
            "timeout_seconds": 15,
        }), patch("gui.select_brawler.fetch_brawl_stars_player", return_value=player_data):
            data = SelectBrawler.get_push_all_data(obj, 500)

        self.assertEqual([row["brawler"] for row in data], ["shelly"])
        self.assertEqual(data[0]["push_until"], 500)
        self.assertFalse(data[0]["automatically_pick"])
        self.assertEqual(data[0]["selection_method"], "lowest_trophies")

    def test_push_all_targets_all_use_lowest_trophies_selection_method(self):
        obj = object.__new__(SelectBrawler)
        obj.brawlers = ["shelly", "colt", "meg"]
        player_data = {
            "brawlers": [
                {"name": "Shelly", "trophies": 100},
                {"name": "Colt", "trophies": 200},
                {"name": "Meg", "trophies": 300},
            ]
        }

        with patch("gui.select_brawler.load_brawl_stars_api_config", return_value={
            "api_token": "token",
            "player_tag": "TAG",
            "timeout_seconds": 15,
        }), patch("gui.select_brawler.fetch_brawl_stars_player", return_value=player_data):
            for target in (250, 500, 750, 1000, 1250, 1500):
                with self.subTest(target=target):
                    data = SelectBrawler.get_push_all_data(obj, target)

                    self.assertTrue(data)
                    self.assertTrue(all(row["push_until"] == target for row in data))
                    self.assertTrue(all(row["selection_method"] == "lowest_trophies" for row in data))
                    self.assertFalse(data[0]["automatically_pick"])
                    self.assertTrue(all(row["automatically_pick"] for row in data[1:]))


if __name__ == "__main__":
    unittest.main()
