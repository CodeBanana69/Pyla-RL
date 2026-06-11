import tempfile
import unittest.mock
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import toml

from daily_digest import (
    DailyDigestScheduler,
    build_daily_digest,
    format_daily_digest_text,
    should_send_digest,
)
from utils import clear_toml_cache


class DailyDigestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "cfg").mkdir(parents=True, exist_ok=True)
        (self.root / "cfg" / "discord_config.toml").write_text(
            toml.dumps({"daily_digest_enabled": True, "daily_digest_hour": 20}),
            encoding="utf-8",
        )
        clear_toml_cache()

    @patch("daily_digest.load_toml_as_dict")
    def test_should_send_at_configured_hour(self, mock_load):
        mock_load.return_value = {"daily_digest_enabled": True, "daily_digest_hour": 9}
        now = datetime(2026, 6, 11, 9, 30)
        self.assertTrue(should_send_digest(now=now, last_sent_at=0.0))
        self.assertFalse(should_send_digest(now=datetime(2026, 6, 11, 10, 0), last_sent_at=0.0))

    @patch("daily_digest.load_toml_as_dict")
    def test_should_not_resend_within_20_hours(self, mock_load):
        mock_load.return_value = {"daily_digest_enabled": True, "daily_digest_hour": 9}
        now = datetime(2026, 6, 11, 9, 30)
        self.assertFalse(should_send_digest(now=now, last_sent_at=time.time() - 3600))

    @patch("recovery_events.read_recent_events", return_value=[])
    @patch("farm_analytics._parse_record_ts")
    @patch("daily_digest.read_all_matches")
    def test_build_daily_digest_aggregation(self, mock_matches, mock_ts, _recoveries):
        now = time.time()
        mock_matches.return_value = [
            {"ts": "2026-06-11T10:00:00+00:00", "brawler": "colt", "result": "victory", "delta": 8},
            {"ts": "2026-06-10T10:00:00+00:00", "brawler": "colt", "result": "defeat", "delta": -6},
        ]
        mock_ts.side_effect = lambda record: (
            now - 3600 if "2026-06-11" in str(record.get("ts")) else now - 48 * 3600
        )
        payload = build_daily_digest(since_hours=24.0)
        self.assertEqual(payload["matches"], 1)
        self.assertEqual(payload["wins"], 1)
        self.assertEqual(payload["trophy_delta"], 8)

    def test_empty_day_handling(self):
        with patch("daily_digest.read_all_matches", return_value=[]):
            with patch("recovery_events.read_recent_events", return_value=[]):
                payload = build_daily_digest()
        self.assertEqual(payload["matches"], 0)
        text = format_daily_digest_text(payload)
        self.assertIn("Matches: 0", text)

    @patch("daily_digest.should_send_digest", return_value=True)
    @patch("daily_digest.build_daily_digest", return_value={"matches": 1, "wins": 1, "trophy_delta": 5, "since_hours": 24})
    @patch("utils.async_notify_user", new_callable=unittest.mock.AsyncMock, return_value=True)
    def test_scheduler_send(self, mock_notify, _build, _should):
        scheduler = DailyDigestScheduler(poll_seconds=0.01)
        sent = scheduler.maybe_send()
        self.assertTrue(sent)
        mock_notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
