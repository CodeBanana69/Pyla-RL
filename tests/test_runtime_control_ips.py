import os
import tempfile
import time
import unittest
from pathlib import Path

from runtime_control import (
    IPS_STALE_AFTER,
    _parse_window_args,
    publish_ips,
    read_ips,
)


class RuntimeControlIpsTest(unittest.TestCase):
    def test_publish_then_read_round_trips_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ips_path = Path(temp_dir) / "runtime.ips"

            publish_ips(ips_path, 12.34)
            value, age = read_ips(ips_path)

            self.assertIsNotNone(value)
            self.assertAlmostEqual(value, 12.34, places=4)
            self.assertIsNotNone(age)
            self.assertGreaterEqual(age, 0.0)
            self.assertLess(age, IPS_STALE_AFTER)

    def test_missing_file_returns_none_pair(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ips_path = Path(temp_dir) / "missing.ips"
            self.assertEqual(read_ips(ips_path), (None, None))

    def test_stale_payload_is_filtered(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ips_path = Path(temp_dir) / "runtime.ips"
            publish_ips(ips_path, 7.5)

            old = time.time() - (IPS_STALE_AFTER + 5)
            os.utime(ips_path, (old, old))
            ips_path.write_text(
                f'{{"ips": 7.5, "ts": {old}}}',
                encoding="utf-8",
            )

            self.assertEqual(read_ips(ips_path), (None, None))

    def test_publish_none_clears_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ips_path = Path(temp_dir) / "runtime.ips"
            publish_ips(ips_path, 5.0)
            self.assertTrue(ips_path.exists())

            publish_ips(ips_path, None)

            self.assertFalse(ips_path.exists())
            self.assertEqual(read_ips(ips_path), (None, None))

    def test_parse_window_args_with_ips_tracker_flags(self):
        argv = [
            "runtime_control.py",
            "--window", "logs/runtime.state",
            "--ips", "logs/runtime.ips",
            "--threshold", "4.5",
        ]
        parsed = _parse_window_args(argv)

        self.assertEqual(parsed, ("logs/runtime.state", "logs/runtime.ips", 4.5))

    def test_parse_window_args_without_ips_tracker_flags(self):
        argv = ["runtime_control.py", "--window", "logs/runtime.state"]
        parsed = _parse_window_args(argv)

        self.assertEqual(parsed, ("logs/runtime.state", None, None))

    def test_parse_window_args_rejects_unknown_invocation(self):
        self.assertIsNone(_parse_window_args(["runtime_control.py"]))


if __name__ == "__main__":
    unittest.main()
