import unittest

from gui.remote_queue_commands import prioritize_brawler_in_queue, remove_brawler_from_queue
from gui.brawler_queue import normalize_queue_row


def _row(brawler, push_until=1000, trophies=0):
    return normalize_queue_row({
        "brawler": brawler,
        "push_until": push_until,
        "trophies": trophies,
        "automatically_pick": True,
    })


class RemoteQueueLivePickTests(unittest.TestCase):
    def test_push_then_remove_leaves_only_new_front(self):
        queue = [_row("bea", 900, 850)]
        queue, _ = prioritize_brawler_in_queue(queue, "piper")
        self.assertEqual([row["brawler"] for row in queue], ["piper", "bea"])

        queue, message = remove_brawler_from_queue(queue, "bea")
        self.assertEqual([row["brawler"] for row in queue], ["piper"])
        self.assertIn("Removed bea", message)


if __name__ == "__main__":
    unittest.main()
