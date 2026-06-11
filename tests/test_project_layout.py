import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProjectLayoutTests(unittest.TestCase):
    def test_install_root_has_launchers_and_app_bundle(self):
        self.assertTrue((ROOT / "pyla-rl.bat").is_file())
        self.assertTrue((ROOT / "app" / "main.py").is_file())
        self.assertTrue((ROOT / "app" / "setup.py").is_file())
        self.assertTrue((ROOT / "cfg").is_dir())
        self.assertTrue((ROOT / "bin" / "adb.exe").is_file())

    def test_runtime_modules_not_at_install_root(self):
        self.assertFalse((ROOT / "play.py").exists())
        self.assertFalse((ROOT / "utils.py").exists())
        self.assertTrue((ROOT / "app" / "play.py").is_file())
        self.assertTrue((ROOT / "app" / "utils.py").is_file())

    def test_pyla_rl_bat_launches_app_main(self):
        bat = (ROOT / "pyla-rl.bat").read_text(encoding="utf-8")
        bat_lower = bat.lower()
        self.assertIn("bundle", bat_lower)
        self.assertIn("main.py", bat_lower)
        self.assertIn("pythonpath", bat_lower)


if __name__ == "__main__":
    unittest.main()
