import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import runtime_maintenance


def make_old(path: Path, seconds_old: float = 3600.0) -> None:
    stamp = time.time() - seconds_old
    os.utime(path, (stamp, stamp))


class RuntimeMaintenanceTests(unittest.TestCase):
    def test_rotate_large_logs_keeps_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            log_path = logs / "pyla.log"
            log_path.write_text("x" * 64, encoding="utf-8")

            report = runtime_maintenance.rotate_large_logs(logs, max_bytes=10, backups=2)

            self.assertFalse(log_path.exists())
            self.assertEqual((logs / "pyla.log.1").read_text(encoding="utf-8"), "x" * 64)
            self.assertIn(str(log_path), report["rotated"])

    def test_cleanup_stale_update_lock_removes_dead_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "remote_update.lock"
            lock.write_text('{"pid": 999999, "ref": "latest"}', encoding="utf-8")
            make_old(lock)

            with patch("tools.runtime_maintenance._process_is_alive", return_value=False):
                report = runtime_maintenance.cleanup_stale_update_lock(lock, stale_seconds=10)

            self.assertFalse(lock.exists())
            self.assertIn(str(lock), report["removed"])

    def test_cleanup_stale_update_lock_preserves_live_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "remote_update.lock"
            lock.write_text('{"pid": 123, "ref": "latest"}', encoding="utf-8")
            make_old(lock)

            with patch("tools.runtime_maintenance._process_is_alive", return_value=True):
                report = runtime_maintenance.cleanup_stale_update_lock(lock, stale_seconds=10)

            self.assertTrue(lock.exists())
            self.assertEqual(report["removed"], [])

    def test_cleanup_stale_update_temp_dirs_removes_old_pyla_update_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_dir = root / "pyla_update_old"
            fresh_dir = root / "pyla_update_fresh"
            unrelated = root / "other_temp"
            old_dir.mkdir()
            fresh_dir.mkdir()
            unrelated.mkdir()
            make_old(old_dir)

            report = runtime_maintenance.cleanup_stale_update_temp_dirs(
                temp_root=root,
                stale_seconds=10,
            )

            self.assertFalse(old_dir.exists())
            self.assertTrue(fresh_dir.exists())
            self.assertTrue(unrelated.exists())
            self.assertIn(str(old_dir), report["removed"])

    def test_cleanup_update_artifacts_removes_only_old_known_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_pending = root / "updater.exe.new"
            fresh_backup = root / "updater.exe.old"
            cfg = root / "app" / "cfg" / "general_config.toml"
            cfg.parent.mkdir(parents=True)
            old_pending.write_text("pending", encoding="utf-8")
            fresh_backup.write_text("backup", encoding="utf-8")
            cfg.write_text("pyla_version='test'", encoding="utf-8")
            make_old(old_pending)

            report = runtime_maintenance.cleanup_update_artifacts(
                root,
                stale_update_seconds=10,
                stale_backup_seconds=10,
            )

            self.assertFalse(old_pending.exists())
            self.assertTrue(fresh_backup.exists())
            self.assertTrue(cfg.exists())
            self.assertIn(str(old_pending), report["removed"])

    def test_format_report_summarizes_work(self):
        text = runtime_maintenance.format_report(
            {"removed": ["a", "b"], "rotated": ["c"], "warnings": ["d"]}
        )

        self.assertIn("removed 2", text)
        self.assertIn("rotated 1", text)
        self.assertIn("1 warning", text)


if __name__ == "__main__":
    unittest.main()
