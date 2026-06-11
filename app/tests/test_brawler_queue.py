import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gui.brawler_queue import (
    apply_push_all_priority_order,
    load_queue,
    normalize_queue_row,
    queue_state_items,
    save_queue,
)


class BrawlerQueueTests(unittest.TestCase):
    def test_apply_push_all_priority_order(self):
        data = [
            {"brawler": "shelly", "push_until": 1000},
            {"brawler": "colt", "push_until": 1000},
            {"brawler": "nita", "push_until": 1000},
        ]
        ordered = apply_push_all_priority_order(data, ["nita", "shelly"])
        self.assertEqual([row["brawler"] for row in ordered[:2]], ["nita", "shelly"])

    def test_load_and_save_queue(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "queue.json"
            payload = [{"brawler": "shelly", "push_until": 1000, "type": "trophies"}]
            save_queue(payload, path)
            loaded = load_queue(path)
            self.assertEqual(loaded[0]["brawler"], "shelly")
            self.assertEqual(loaded[0]["trophies"], 0)
            self.assertEqual(loaded[0]["win_streak"], 0)
            items = queue_state_items(loaded)
            self.assertEqual(items[0]["brawler"], "shelly")
            self.assertEqual(items[0]["index"], 0)

    def test_normalize_queue_row_forces_auto_pick(self):
        row = normalize_queue_row({
            "brawler": "jacky",
            "push_until": 1000,
            "automatically_pick": False,
        })
        self.assertTrue(row["automatically_pick"])

    def test_normalize_queue_row_fills_missing_trophies(self):
        row = normalize_queue_row({
            "brawler": "jacky",
            "push_until": 1000,
            "wins": 0,
            "type": "trophies",
            "automatically_pick": True,
            "selection_method": "named_brawler",
            "win_streak": 0,
        })
        self.assertEqual(row["trophies"], 0)
        self.assertEqual(row["brawler"], "jacky")

    @patch("gui.brawler_queue.fetch_brawl_stars_player")
    @patch("gui.brawler_queue.load_brawl_stars_api_config")
    def test_get_push_all_data_sorts_lowest_trophies_first(self, mock_config, mock_player):
        from gui.brawler_queue import get_push_all_data

        mock_config.return_value = {"api_token": "x", "player_tag": "#TAG", "timeout_seconds": 15}
        mock_player.return_value = {
            "brawlers": [
                {"name": "Shelly", "trophies": 100},
                {"name": "Colt", "trophies": 900},
                {"name": "Nita", "trophies": 500},
            ]
        }
        rows = get_push_all_data(1000, brawlers=["shelly", "colt", "nita"])
        self.assertEqual([row["brawler"] for row in rows], ["shelly", "nita", "colt"])
        self.assertEqual(rows[0]["selection_method"], "lowest_trophies")

    @patch("gui.brawler_queue.fetch_brawl_stars_player")
    @patch("gui.brawler_queue.load_brawl_stars_api_config")
    def test_get_push_all_data_filters_by_target(self, mock_config, mock_player):
        from gui.brawler_queue import get_push_all_data

        mock_config.return_value = {"api_token": "x", "player_tag": "#TAG", "timeout_seconds": 15}
        mock_player.return_value = {
            "brawlers": [
                {"name": "Shelly", "trophies": 900},
                {"name": "Colt", "trophies": 1100},
            ]
        }
        rows = get_push_all_data(1000, brawlers=["shelly", "colt"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["brawler"], "shelly")


    def test_sort_queue_by_trophies_descending(self):
        from gui.brawler_queue import sort_queue_by_trophies

        queue = sort_queue_by_trophies([
            {"brawler": "shelly", "push_until": 1000, "trophies": 100},
            {"brawler": "colt", "push_until": 1000, "trophies": 900},
            {"brawler": "nita", "push_until": 1000, "trophies": 500},
        ])
        self.assertEqual([row["brawler"] for row in queue], ["colt", "nita", "shelly"])

    def test_sort_queue_modes(self):
        from gui.brawler_queue import sort_queue

        rows = [
            {"brawler": "shelly", "push_until": 1000, "trophies": 100, "type": "trophies"},
            {"brawler": "colt", "push_until": 1500, "trophies": 900, "type": "trophies"},
            {"brawler": "nita", "push_until": 1000, "trophies": 950, "type": "trophies"},
        ]

        self.assertEqual(
            [row["brawler"] for row in sort_queue(rows, mode="cups_asc")],
            ["shelly", "colt", "nita"],
        )
        cups_desc = sort_queue(
            [
                {"brawler": "shelly", "push_until": 1000, "trophies": 100, "selection_method": "lowest_trophies"},
                {"brawler": "colt", "push_until": 1000, "trophies": 900, "selection_method": "lowest_trophies"},
            ],
            mode="cups_desc",
        )
        self.assertEqual([row["brawler"] for row in cups_desc], ["colt", "shelly"])
        self.assertEqual(cups_desc[0]["selection_method"], "highest_trophies")
        self.assertEqual(cups_desc[0]["queue_sort_mode"], "cups_desc")
        gap_asc = sort_queue(
            [
                {"brawler": "shelly", "push_until": 1000, "trophies": 100, "selection_method": "lowest_trophies"},
                {"brawler": "colt", "push_until": 1500, "trophies": 900, "selection_method": "lowest_trophies"},
                {"brawler": "nita", "push_until": 1000, "trophies": 950, "selection_method": "lowest_trophies"},
            ],
            mode="gap_asc",
        )
        self.assertEqual([row["brawler"] for row in gap_asc], ["nita", "colt", "shelly"])
        self.assertEqual(gap_asc[0]["selection_method"], "named_brawler")
        self.assertEqual(gap_asc[0]["queue_sort_mode"], "gap_asc")
        self.assertEqual(
            [row["brawler"] for row in sort_queue(rows, mode="gap_asc")],
            ["nita", "colt", "shelly"],
        )
        self.assertEqual(
            [row["brawler"] for row in sort_queue(rows, mode="target_desc")],
            ["colt", "nita", "shelly"],
        )
        self.assertEqual(
            [row["brawler"] for row in sort_queue(rows, mode="name_asc")],
            ["colt", "nita", "shelly"],
        )
        self.assertEqual(
            [row["brawler"] for row in sort_queue(rows, mode="name_desc")],
            ["shelly", "nita", "colt"],
        )


if __name__ == "__main__":
    unittest.main()
