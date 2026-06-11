import unittest
from pathlib import Path

INSTALL_ROOT = Path(__file__).resolve().parents[2]
BUNDLE = INSTALL_ROOT / "app"


class ProjectLayoutTests(unittest.TestCase):
    def test_install_root_only_has_launchers_and_app(self):
        names = {path.name for path in INSTALL_ROOT.iterdir()}
        self.assertIn("pyla-rl.bat", names)
        self.assertIn("app", names)
        self.assertNotIn("cfg", names)
        self.assertNotIn("gui", names)
        self.assertNotIn("main.py", names)

    def test_bundle_contains_runtime_and_data_dirs(self):
        self.assertTrue((BUNDLE / "main.py").is_file())
        self.assertTrue((BUNDLE / "setup.py").is_file())
        self.assertTrue((BUNDLE / "cfg").is_dir())
        self.assertTrue((BUNDLE / "gui").is_dir())
        self.assertTrue((BUNDLE / "tools").is_dir())
        self.assertTrue((BUNDLE / "bin" / "adb.exe").is_file())

    def test_pyla_rl_bat_launches_bundle_main(self):
        bat = (INSTALL_ROOT / "pyla-rl.bat").read_text(encoding="utf-8")
        bat_lower = bat.lower()
        self.assertIn("bundle", bat_lower)
        self.assertIn("main.py", bat_lower)
        self.assertIn("app\\cfg", bat_lower.replace("/", "\\"))


if __name__ == "__main__":
    unittest.main()
