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
                self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "colt")
                self.assertEqual(manager.Trophy_observer.current_trophies, 50)

                changed_again = manager.reload_queue_from_disk_if_changed()
                self.assertFalse(changed_again)
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
