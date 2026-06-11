import tempfile
import time
import unittest
from unittest.mock import patch

from farm_analytics import brawler_stats, efficiency_sort_key, stuck_brawlers
from gui.brawler_queue import sort_queue


class FarmAnalyticsTests(unittest.TestCase):
    def test_brawler_stats_math(self):
        now = time.time()
        records = [
            {"ts": now - 3600, "brawler": "shelly", "result": "victory", "delta": 8},
            {"ts": now - 1800, "brawler": "shelly", "result": "defeat", "delta": -6},
            {"ts": now - 900, "brawler": "colt", "result": "victory", "delta": 10},
        ]
        with patch("farm_analytics.read_all_matches", return_value=records):
            stats = brawler_stats(since_hours=168.0)
        self.assertEqual(stats["shelly"]["matches"], 2)
        self.assertEqual(stats["shelly"]["wins"], 1)
        self.assertAlmostEqual(stats["shelly"]["win_rate"], 0.5)
        self.assertEqual(stats["colt"]["trophy_delta"], 10)

    def test_stuck_detection(self):
        now = time.time()
        records = [
            {"ts": now - 3600, "brawler": "shelly", "result": "defeat", "delta": -6}
            for _ in range(12)
        ]
        with patch("farm_analytics.read_all_matches", return_value=records):
            stuck = stuck_brawlers(threshold=0.4, min_matches=10)
        self.assertEqual(stuck, ["shelly"])

    def test_efficiency_sort_with_missing_data(self):
        queue = [
            {"brawler": "untracked", "trophies": 500, "push_until": 1000},
            {"brawler": "colt", "trophies": 700, "push_until": 1000},
        ]
        stats = {"colt": {"trophies_per_hour": 120.0}}
        with patch("farm_analytics.brawler_stats", return_value=stats):
            sorted_queue = sort_queue(queue, mode="efficiency")
        self.assertEqual(sorted_queue[0]["brawler"], "colt")
        self.assertEqual(sorted_queue[1]["brawler"], "untracked")

    def test_efficiency_sort_key_untracked_last(self):
        stats = {"colt": {"trophies_per_hour": 50.0}}
        tracked = efficiency_sort_key({"brawler": "colt", "trophies": 100}, stats=stats)
        untracked = efficiency_sort_key({"brawler": "new", "trophies": 900}, stats=stats)
        self.assertLess(tracked, untracked)


if __name__ == "__main__":
    unittest.main()
