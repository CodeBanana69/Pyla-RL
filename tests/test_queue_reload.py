import os
import tempfile
import unittest

from stage_manager import StageManager


class DummyTrophyObserver:
    current_trophies = 100
    current_wins = 0
    win_streak = 0

    def change_trophies(self, value):
        self.current_trophies = value


class QueueReloadTests(unittest.TestCase):
    def test_reload_queue_from_disk_if_changed(self):
        manager = StageManager.__new__(StageManager)
        manager.brawlers_pick_data = [
            {"brawler": "shelly", "push_until": 500, "trophies": 100, "type": "trophies"},
        ]
        manager.Trophy_observer = DummyTrophyObserver()
        manager._queue_file_mtime = None
        manager.pending_queue = None

        with tempfile.TemporaryDirectory() as tmp:
            queue_path = os.path.join(tmp, "latest_brawler_data.json")
            original_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                import json

                with open(queue_path, "w", encoding="utf-8") as handle:
                    json.dump([
                        {"brawler": "colt", "push_until": 500, "trophies": 50, "type": "trophies"},
                    ], handle)
                manager._queue_file_mtime = None
                changed = manager.reload_queue_from_disk_if_changed()
                self.assertTrue(changed)
                self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "shelly")
                self.assertEqual(manager.pending_queue[0]["brawler"], "colt")
                self.assertEqual(manager.Trophy_observer.current_trophies, 100)
                self.assertTrue(manager.pending_brawler_reselection)

                changed_again = manager.reload_queue_from_disk_if_changed()
                self.assertFalse(changed_again)
            finally:
                os.chdir(original_cwd)

    def test_stage_from_disk_before_runtime_save_preserves_hub_front(self):
        manager = StageManager.__new__(StageManager)
        manager.brawlers_pick_data = [
            {"brawler": "mina", "push_until": 1000, "trophies": 765, "type": "trophies"},
        ]
        manager.Trophy_observer = DummyTrophyObserver()
        manager._queue_file_mtime = None
        manager.pending_queue = None
        manager.pending_brawler_reselection = False
        manager.pending_reselect_brawler = ""
        manager.post_match_action = "play_again"

        with tempfile.TemporaryDirectory() as tmp:
            queue_path = os.path.join(tmp, "latest_brawler_data.json")
            original_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                import json

                with open(queue_path, "w", encoding="utf-8") as handle:
                    json.dump([
                        {"brawler": "shade", "push_until": 1000, "trophies": 100, "type": "trophies"},
                        {"brawler": "mina", "push_until": 1000, "trophies": 765, "type": "trophies"},
                    ], handle)

                manager.stage_queue_from_disk_if_changed()
                self.assertEqual(manager.pending_queue[0]["brawler"], "shade")
                self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "mina")
                self.assertTrue(manager.requires_brawler_reselection("mina"))
                self.assertFalse(
                    manager.should_use_play_again(
                        value=765,
                        target=1000,
                        active_brawler="mina",
                    )
                )

                manager.brawlers_pick_data[0]["trophies"] = 770
                manager._persist_runtime_queue_if_not_staged()

                with open(queue_path, encoding="utf-8") as handle:
                    saved = json.load(handle)
                self.assertEqual(saved[0]["brawler"], "shade")
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
