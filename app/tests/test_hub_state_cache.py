import unittest
from unittest.mock import patch

from gui.hub_state import HubStateStore


class HubStateCacheTests(unittest.TestCase):
    def test_static_ui_meta_is_cached(self):
        store = HubStateStore.__new__(HubStateStore)
        store.general_config = {"first_run_wizard": "no", "license_accepted": "yes"}
        store._cached_static_meta = None
        store._cached_source_status = None

        with patch("utils.get_playstyles_list", return_value=[]), patch(
            "utils.get_brawler_list",
            return_value=["colt"],
        ), patch("gui.brawler_queue.brawler_icon_uri", return_value="file:///colt.png"), patch(
            "gui.brawler_queue.load_push_order",
            return_value=[],
        ), patch("gui.official_source.read_build_info", return_value={}), patch(
            "gui.hub_tutorials.tutorial_topics",
            return_value=[],
        ), patch("gui.official_source.verify_official_source") as verify:
            first = store._static_ui_meta()
            second = store._static_ui_meta()

        self.assertIs(first, second)
        verify.assert_called_once()

    def test_invalidate_static_ui_cache_forces_rebuild(self):
        store = HubStateStore.__new__(HubStateStore)
        store.general_config = {"first_run_wizard": "no", "license_accepted": "yes"}
        store._cached_static_meta = {"brawlers": ["colt"]}
        store._cached_source_status = {"ok": True}

        with patch("utils.get_playstyles_list", return_value=[]), patch(
            "utils.get_brawler_list",
            return_value=["nita"],
        ), patch("gui.brawler_queue.brawler_icon_uri", return_value=""), patch(
            "gui.brawler_queue.load_push_order",
            return_value=[],
        ), patch("gui.official_source.read_build_info", return_value={}), patch(
            "gui.hub_tutorials.tutorial_topics",
            return_value=[],
        ), patch("gui.official_source.verify_official_source", return_value={"ok": True}):
            store.invalidate_static_ui_cache()
            meta = store._static_ui_meta()

        self.assertEqual(meta["brawlers"], ["nita"])


if __name__ == "__main__":
    unittest.main()
