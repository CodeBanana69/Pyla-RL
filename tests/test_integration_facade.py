import unittest

from core.integration import clean_queue, migrate_bot_config, normalize_queue, normalize_queue_row


class IntegrationFacadeTests(unittest.TestCase):
    def test_migrate_close_tile_alias(self):
        config = migrate_bot_config({"close_tile_detector_enabled": "yes"})
        self.assertEqual(config.get("centered_wall_detection"), True)

    def test_normalize_queue_row(self):
        row = normalize_queue_row({"brawler": "Shelly", "trophies": "120", "push_until": 1000})
        self.assertEqual(row["brawler"], "shelly")
        self.assertEqual(row["trophies"], 120)
        self.assertTrue(row["automatically_pick"])

    def test_clean_queue_defaults(self):
        rows = clean_queue([{"brawler": "colt", "type": "trophies", "trophies": "", "push_until": "", "wins": 0}])
        self.assertEqual(rows[0]["trophies"], 0)
        self.assertEqual(rows[0]["push_until"], 1000)

    def test_normalize_queue_filters_invalid(self):
        rows = normalize_queue([{"brawler": ""}, {"brawler": "nita", "trophies": 10, "push_until": 1000, "wins": 0, "type": "trophies"}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["brawler"], "nita")


if __name__ == "__main__":
    unittest.main()
