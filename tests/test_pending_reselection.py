import unittest
from unittest.mock import patch

from stage_manager import StageManager


class DummyTrophyObserver:
    current_trophies = 100
    current_wins = 0
    win_streak = 0

    def change_trophies(self, value):
        self.current_trophies = value


class DummyLobbyAutomation:
    def __init__(self, select_ok=True):
        self.select_ok = select_ok
        self.named_calls = []
        self.lowest_calls = 0

    def select_brawler(self, name):
        self.named_calls.append(name)
        return self.select_ok

    def select_lowest_trophy_brawler(self):
        self.lowest_calls += 1
        return self.select_ok


class PendingReselectionTests(unittest.TestCase):
    def make_manager(self, *, select_ok=True):
        manager = StageManager.__new__(StageManager)
        manager.brawlers_pick_data = [
            {
                "brawler": "shelly",
                "push_until": 500,
                "trophies": 100,
                "type": "trophies",
                "selection_method": "named_brawler",
            },
        ]
        manager.Trophy_observer = DummyTrophyObserver()
        manager.Lobby_automation = DummyLobbyAutomation(select_ok=select_ok)
        manager.pending_queue = None
        manager.pending_reselect_brawler = ""
        manager.pending_target_completion = False
        manager.pending_queue_source = ""
        manager.pending_brawler_reselection = False
        manager._queue_file_mtime = None
        manager._sync_observer_to_current_row = lambda: None
        return manager

    def test_stage_queue_update_does_not_mutate_runtime_queue(self):
        manager = self.make_manager()
        new_queue = [
            {"brawler": "colt", "push_until": 750, "trophies": 50, "type": "trophies"},
            {"brawler": "nita", "push_until": 750, "trophies": 25, "type": "trophies"},
        ]

        staged = manager.stage_queue_update(new_queue, reason="remote", reselect_brawler="colt")

        self.assertTrue(staged)
        self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "shelly")
        self.assertEqual(manager.pending_queue[0]["brawler"], "colt")
        self.assertEqual(manager.pending_reselect_brawler, "colt")
        self.assertTrue(manager.requires_brawler_reselection())

    @patch("stage_manager.save_brawler_data")
    @patch("gui.brawler_queue.persist_queue")
    def test_apply_pending_reselection_commits_after_select_success(
        self,
        mock_persist,
        mock_save,
    ):
        manager = self.make_manager(select_ok=True)
        manager.stage_queue_update(
            [{"brawler": "colt", "push_until": 750, "trophies": 50, "type": "trophies"}],
            reason="remote",
            reselect_brawler="colt",
        )

        self.assertTrue(manager.apply_pending_reselection_in_lobby())

        self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "colt")
        self.assertIsNone(manager.pending_queue)
        self.assertFalse(manager.pending_brawler_reselection)
        mock_persist.assert_called_once()
        mock_save.assert_called_once()

    @patch("stage_manager.save_brawler_data")
    @patch("gui.brawler_queue.persist_queue")
    def test_apply_pending_reselection_does_not_commit_on_failure(
        self,
        mock_persist,
        mock_save,
    ):
        manager = self.make_manager(select_ok=False)
        manager.stage_queue_update(
            [{"brawler": "colt", "push_until": 750, "trophies": 50, "type": "trophies"}],
            reason="remote",
            reselect_brawler="colt",
        )

        self.assertFalse(manager.apply_pending_reselection_in_lobby())

        self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "shelly")
        self.assertIsNotNone(manager.pending_queue)
        mock_persist.assert_not_called()
        mock_save.assert_not_called()

    def test_stage_next_queue_after_target_keeps_active_queue(self):
        manager = self.make_manager()
        manager.brawlers_pick_data = [
            {
                "brawler": "first",
                "push_until": 250,
                "trophies": 250,
                "type": "trophies",
                "selection_method": "lowest_trophies",
            },
            {
                "brawler": "second",
                "push_until": 250,
                "trophies": 10,
                "type": "trophies",
                "selection_method": "lowest_trophies",
            },
        ]
        manager.Trophy_observer.current_trophies = 250

        staged = manager._stage_next_queue_after_target(250, "trophies", source="target")

        self.assertTrue(staged)
        self.assertEqual(manager.brawlers_pick_data[0]["brawler"], "first")
        self.assertEqual(manager.pending_queue[0]["brawler"], "second")
        self.assertTrue(manager.pending_target_completion)


if __name__ == "__main__":
    unittest.main()
