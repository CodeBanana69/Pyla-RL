import unittest

from gui.remote_formatting import format_queue_lines
from gui.remote_queue_commands import (
    prioritize_brawler_in_queue,
    remove_brawler_from_queue,
    set_active_target,
    skip_current_brawler,
)
from gui.brawler_queue import normalize_queue_row


def _row(brawler, push_until=1000, trophies=0):
    return normalize_queue_row({
        "brawler": brawler,
        "push_until": push_until,
        "trophies": trophies,
    })


class RemoteQueueCommandsTest(unittest.TestCase):
    def test_push_moves_former_active_to_index_one(self):
        queue = [_row("nita", 750, 500), _row("colt", 800, 400), _row("shelly", 900, 300)]
        new_queue, message = prioritize_brawler_in_queue(queue, "colt")

        self.assertEqual(new_queue[0]["brawler"], "colt")
        self.assertEqual(new_queue[1]["brawler"], "nita")
        self.assertEqual(new_queue[2]["brawler"], "shelly")
        self.assertIn("Prioritized Colt", message)

    def test_push_dedupes_brawler_already_in_queue(self):
        queue = [_row("nita"), _row("colt"), _row("shelly")]
        new_queue, _ = prioritize_brawler_in_queue(queue, "shelly")

        names = [row["brawler"] for row in new_queue]
        self.assertEqual(names, ["shelly", "nita", "colt"])

    def test_push_same_brawler_updates_target_only(self):
        queue = [_row("nita", 750, 500), _row("colt")]
        new_queue, message = prioritize_brawler_in_queue(queue, "nita", 900)

        self.assertEqual([row["brawler"] for row in new_queue], ["nita", "colt"])
        self.assertEqual(new_queue[0]["push_until"], 900)
        self.assertIn("Updated target", message)

    def test_push_creates_queue_when_empty(self):
        new_queue, message = prioritize_brawler_in_queue([], "colt", 750)

        self.assertEqual(len(new_queue), 1)
        self.assertEqual(new_queue[0]["brawler"], "colt")
        self.assertEqual(new_queue[0]["push_until"], 750)
        self.assertIn("Created farm plan", message)

    def test_skip_rotates_front_down(self):
        queue = [_row("colt"), _row("nita"), _row("shelly")]
        new_queue, message = skip_current_brawler(queue)

        self.assertEqual([row["brawler"] for row in new_queue], ["nita", "colt", "shelly"])
        self.assertIn("Skipped colt", message)

    def test_skip_requires_two_brawlers(self):
        queue = [_row("colt")]
        new_queue, message = skip_current_brawler(queue)

        self.assertEqual(new_queue, queue)
        self.assertIn("at least two", message.lower())

    def test_remove_active_promotes_next(self):
        queue = [_row("colt"), _row("nita"), _row("shelly")]
        new_queue, message = remove_brawler_from_queue(queue, "colt")

        self.assertEqual([row["brawler"] for row in new_queue], ["nita", "shelly"])
        self.assertIn("now playing nita", message.lower())

    def test_remove_non_active_leaves_front(self):
        queue = [_row("colt"), _row("nita"), _row("shelly")]
        new_queue, message = remove_brawler_from_queue(queue, "shelly")

        self.assertEqual([row["brawler"] for row in new_queue], ["colt", "nita"])
        self.assertIn("Removed shelly", message)

    def test_target_updates_front_row_only(self):
        queue = [_row("colt", 750), _row("nita", 800)]
        new_queue, message = set_active_target(queue, 900)

        self.assertEqual(new_queue[0]["push_until"], 900)
        self.assertEqual(new_queue[1]["push_until"], 800)
        self.assertIn("set target for colt", message.lower())

    def test_format_queue_lines_marks_active_row(self):
        queue = [_row("colt", 750, 520), _row("nita", 800, 400)]
        text = format_queue_lines(queue)

        self.assertIn("▶ Colt", text)
        self.assertIn("  Nita", text)
        self.assertIn("520 / 750", text)

    def test_session_stats_win_rate(self):
        from gui.remote_formatting import build_session_stats, format_win_rate

        self.assertEqual(format_win_rate(0, 0, 0), "N/A")
        self.assertEqual(format_win_rate(7, 3, 0), "70.0%")
        self.assertEqual(format_win_rate(2, 2, 1), "40.0%")
        stats = build_session_stats({
            "session_wins": 5,
            "session_losses": 3,
            "session_draws": 1,
            "uptime_s": 3661,
            "brawler": "colt",
            "trophies": 520,
        })
        self.assertEqual(stats["wins"], 5)
        self.assertEqual(stats["losses"], 3)
        self.assertEqual(stats["draws"], 1)
        self.assertEqual(stats["matches"], 9)
        self.assertEqual(stats["win_rate"], "55.6%")
        self.assertEqual(stats["uptime"], "1h 1m")


if __name__ == "__main__":
    unittest.main()
