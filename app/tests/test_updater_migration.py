import tempfile
import unittest
from pathlib import Path

from tools.updater import find_project_root, is_valid_install, migrate_legacy_layout


class UpdaterMigrationTests(unittest.TestCase):
    def test_is_valid_install_accepts_bundle_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            bundle = install / "app"
            (bundle / "cfg").mkdir(parents=True)
            (bundle / "main.py").write_text("main", encoding="utf-8")
            self.assertTrue(is_valid_install(install))

    def test_migrate_partial_layout_moves_cfg_into_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            bundle = install / "app"
            bundle.mkdir()
            (bundle / "main.py").write_text("main", encoding="utf-8")
            (install / "cfg").mkdir()
            (install / "cfg" / "general_config.toml").write_text("x = 1\n", encoding="utf-8")
            (install / "gui").mkdir()

            migrate_legacy_layout(install)

            self.assertTrue((bundle / "cfg" / "general_config.toml").is_file())
            self.assertTrue((bundle / "gui").is_dir())
            self.assertFalse((install / "cfg").exists())

    def test_find_project_root_detects_bundle_layout_in_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            bundle = install / "app"
            (bundle / "cfg").mkdir(parents=True)
            (bundle / "main.py").write_text("main", encoding="utf-8")
            self.assertEqual(find_project_root(install), install)


if __name__ == "__main__":
    unittest.main()
