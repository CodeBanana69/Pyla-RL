import tempfile
import unittest
from pathlib import Path

from tools.updater import find_project_root, is_distribution_root, migrate_legacy_layout


class UpdaterMigrationTests(unittest.TestCase):
    def test_is_distribution_root_accepts_app_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cfg").mkdir()
            (root / "app").mkdir()
            (root / "app" / "main.py").write_text("main", encoding="utf-8")
            self.assertTrue(is_distribution_root(root))

    def test_migrate_legacy_layout_moves_modules_and_adb(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cfg").mkdir()
            (root / "main.py").write_text("main", encoding="utf-8")
            (root / "play.py").write_text("play", encoding="utf-8")
            (root / "adb.exe").write_text("adb", encoding="utf-8")
            (root / "latest_brawler_data.json").write_text("[]", encoding="utf-8")

            migrate_legacy_layout(root)

            self.assertFalse((root / "main.py").exists())
            self.assertTrue((root / "app" / "main.py").is_file())
            self.assertTrue((root / "app" / "play.py").is_file())
            self.assertTrue((root / "bin" / "adb.exe").is_file())
            self.assertTrue((root / "data" / "latest_brawler_data.json").is_file())

    def test_find_project_root_detects_app_layout_in_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            extracted = Path(tmp)
            (extracted / "cfg").mkdir()
            (extracted / "app").mkdir()
            (extracted / "app" / "main.py").write_text("main", encoding="utf-8")
            self.assertEqual(find_project_root(extracted), extracted)


if __name__ == "__main__":
    unittest.main()
