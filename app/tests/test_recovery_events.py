import tempfile
import unittest
from pathlib import Path

from recovery_events import count_session_events_by_type, log_recovery, read_recent_events


class RecoveryEventTests(unittest.TestCase):
    def test_count_session_events_by_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recovery_events.jsonl"
            session_id = "session-123"
            log_recovery("display_repair", "displayId=6->0 action=move", session_id=session_id, path=path)
            log_recovery("scrcpy_restart", "generation=2 clean_stop=false", session_id=session_id, path=path)
            log_recovery("display_repair", "displayId=6->6 action=skipped_passive", session_id=session_id, path=path)
            log_recovery("emulator_restart", "cooldown_skipped=true emulator=MuMu", session_id="other", path=path)

            counts = count_session_events_by_type(session_id=session_id, path=path)
            self.assertEqual(counts["display_repair"], 2)
            self.assertEqual(counts["scrcpy_restart"], 1)
            self.assertNotIn("emulator_restart", counts)

            recent = read_recent_events(limit=10, path=path)
            self.assertEqual(len(recent), 4)

    def test_screenshot_path_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recovery_events.jsonl"
            log_recovery("app_restart", detail="state=lobby", screenshot_path="logs/recovery/1_app_restart.png", path=path)
            events = read_recent_events(limit=1, path=path)
            self.assertEqual(events[0]["screenshot_path"], "logs/recovery/1_app_restart.png")


if __name__ == "__main__":
    unittest.main()
