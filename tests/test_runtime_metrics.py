import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from runtime_control import draw_ips_sparkline
from runtime_metrics import (
    format_session_summary,
    format_uptime,
    metrics_path_for_pid,
    read_metrics,
    write_metrics,
)


class RuntimeMetricsTests(unittest.TestCase):
    def test_metrics_path_for_pid(self):
        path = metrics_path_for_pid(12345)
        self.assertEqual(path.name, "runtime_metrics_12345.json")
        self.assertEqual(path.parent.name, "logs")

    def test_write_read_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.json"
            history = [10.0, 12.5, 11.0, 13.2]
            write_metrics(path, 13.2, 28.0, history)
            data = read_metrics(path)
            self.assertIsNotNone(data)
            self.assertAlmostEqual(data["ips"], 13.2)
            self.assertAlmostEqual(data["feed_fps"], 28.0)
            self.assertEqual(data["history"], history)

    def test_write_falls_back_when_replace_is_locked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.json"
            write_metrics(path, 9.0, 20.0, [9.0])
            original_replace = os.replace

            def locked_replace(src, dst):
                if Path(dst) == path:
                    raise PermissionError(5, "Access is denied")
                return original_replace(src, dst)

            with patch("runtime_metrics.os.replace", side_effect=locked_replace):
                write_metrics(path, 11.5, 24.0, [9.0, 11.5])
            data = read_metrics(path)
            self.assertIsNotNone(data)
            self.assertAlmostEqual(data["ips"], 11.5)
            self.assertEqual(data["history"], [9.0, 11.5])

    def test_write_truncates_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.json"
            history = list(range(20))
            write_metrics(path, 19.0, 30.0, history, max_samples=5)
            data = read_metrics(path)
            self.assertEqual(data["history"], [15, 16, 17, 18, 19])

    def test_read_missing_returns_none(self):
        self.assertIsNone(read_metrics(Path("logs/does_not_exist_metrics.json")))

    def test_write_read_session_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.json"
            session = {
                "uptime_s": 725.0,
                "state": "match",
                "brawler": "shelly",
                "target": 500,
                "trophies": 437,
                "session_wins": 3,
                "session_losses": 1,
                "notice": "Running",
            }
            write_metrics(path, 18.2, 60.0, [17.0, 18.2], session=session)
            data = read_metrics(path)
            self.assertIsNotNone(data)
            self.assertEqual(data["session"]["brawler"], "shelly")
            self.assertEqual(data["session"]["target"], "500")
            self.assertEqual(data["session"]["trophies"], 437)
            self.assertEqual(data["session"]["session_wins"], 3)
            self.assertEqual(data["session"]["session_losses"], 1)

    def test_read_metrics_without_session_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.json"
            path.write_text('{"ips": 9.5, "feed_fps": 30.0, "history": [9.5]}', encoding="utf-8")
            data = read_metrics(path)
            self.assertIsNotNone(data)
            self.assertNotIn("session", data)

    def test_format_uptime(self):
        self.assertEqual(format_uptime(45), "45s")
        self.assertEqual(format_uptime(125), "2m 5s")
        self.assertEqual(format_uptime(3725), "1h 2m")

    def test_format_session_summary(self):
        summary = format_session_summary(
            {
                "ips": 18.2,
                "session": {
                    "uptime_s": 720,
                    "brawler": "shelly",
                    "target": "500",
                    "trophies": 437,
                    "session_wins": 3,
                    "session_losses": 1,
                    "state": "match",
                    "notice": "Running",
                },
            }
        )
        self.assertIn("PylaAi-XXZ", summary)
        self.assertIn("shelly -> 500 (437)", summary)
        self.assertIn("W3 L1", summary)
        self.assertIn("IPS 18.2", summary)

    def test_format_session_summary_handles_missing_data(self):
        summary = format_session_summary(None)
        self.assertIn("status unavailable", summary)

    def test_draw_ips_sparkline_handles_sample_counts(self):
        canvas = MagicMock()
        for samples in ([], [5.0], list(range(10))):
            draw_ips_sparkline(canvas, samples, "#30d158")
        self.assertTrue(canvas.delete.called)
        self.assertTrue(canvas.create_line.called)


if __name__ == "__main__":
    unittest.main()
