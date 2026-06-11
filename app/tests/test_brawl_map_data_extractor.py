import unittest

from tools.extract_brawl_map_data import build_filtered_index, map_objects, summarize_map


class TestBrawlMapDataExtractor(unittest.TestCase):
    def test_summarize_map_classifies_tile_codes(self):
        base_tiles = {
            ".": {"blocks_movement": False, "blocks_projectiles": False, "forest": False, "damage": 0},
            "M": {"blocks_movement": True, "blocks_projectiles": True, "forest": False, "damage": 0},
            "F": {"blocks_movement": False, "blocks_projectiles": False, "forest": True, "damage": 0},
            "W": {"blocks_movement": True, "blocks_projectiles": False, "forest": False, "damage": 0},
            "G": {"blocks_movement": False, "blocks_projectiles": False, "forest": False, "damage": 1000},
        }

        summary = summarize_map([".MFW", "G..M"], base_tiles)

        self.assertEqual(summary["width"], 4)
        self.assertEqual(summary["height"], 2)
        self.assertEqual(summary["blocking_codes"], ["M", "W"])
        self.assertEqual(summary["projectile_blocking_codes"], ["M"])
        self.assertEqual(summary["forest_codes"], ["F"])
        self.assertEqual(summary["damaging_codes"], ["G"])

    def test_map_objects_returns_non_open_tiles_with_flags(self):
        base_tiles = {
            ".": {"name": "Open", "blocks_movement": False},
            "M": {"name": "Wall1", "blocks_movement": True, "blocks_projectiles": True, "destructible": True},
            "F": {"name": "Forest", "forest": True},
        }

        objects = map_objects([".M", "F."], base_tiles)

        self.assertEqual(len(objects), 2)
        self.assertEqual(objects[0]["code"], "M")
        self.assertEqual(objects[0]["x"], 1)
        self.assertEqual(objects[0]["y"], 0)
        self.assertTrue(objects[0]["blocks_movement"])
        self.assertEqual(objects[1]["name"], "Forest")
        self.assertTrue(objects[1]["forest"])

    def test_filter_to_trio_showdown_maps_deduplicates_shared_grids(self):
        index = {
            "source_apk": "test.apk",
            "tile_count": 2,
            "tiles": {},
            "base_tiles": {".": {}, "M": {"name": "Wall1", "blocks_movement": True}},
            "maps": {
                "Survival_1": ["M."],
                "Gemgrab_1": [".."],
            },
            "map_summaries": {
                "Survival_1": {"width": 2, "height": 1},
                "Gemgrab_1": {"width": 2, "height": 1},
            },
            "locations": {
                "SurvivalTrio1": {"map": "Survival_1", "mode": "TrioShowdown", "disabled": False},
                "SurvivalTrioDuplicate": {"map": "Survival_1", "mode": "TrioShowdown", "disabled": False},
                "Gemgrab1": {"map": "Gemgrab_1", "mode": "GemGrab", "disabled": False},
            },
        }

        filtered = build_filtered_index(index, modes=["TrioShowdown"], include_objects=True)

        self.assertEqual(filtered["map_count"], 1)
        self.assertEqual(filtered["location_count"], 2)
        self.assertEqual(list(filtered["maps"].keys()), ["Survival_1"])
        self.assertEqual(filtered["map_objects"]["Survival_1"][0]["code"], "M")


if __name__ == "__main__":
    unittest.main()
