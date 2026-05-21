import tempfile
import unittest
from pathlib import Path

from match_journal import append_match_record, clear_journal, read_recent_matches


class MatchJournalTests(unittest.TestCase):
    def test_append_and_read_recent_matches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "matches.jsonl"
            append_match_record("shelly", "2nd", delta=6, path=path)
            append_match_record("colt", "4th", delta=-5, path=path)
            recent = read_recent_matches(limit=10, path=path)
            self.assertEqual(len(recent), 2)
            self.assertEqual(recent[0]["brawler"], "colt")
            clear_journal(path)
            self.assertEqual(read_recent_matches(path=path), [])


if __name__ == "__main__":
    unittest.main()
