import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import toml

from utils import clear_toml_cache


class InstanceConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "cfg").mkdir(parents=True, exist_ok=True)
        (self.root / "instances").mkdir(parents=True, exist_ok=True)
        (self.root / "cfg" / "general_config.toml").write_text(
            toml.dumps({
                "current_emulator": "MuMu",
                "emulator_port": 16384,
                "emulator_profile_index": "auto",
            }),
            encoding="utf-8",
        )
        (self.root / "cfg" / "instances.toml").write_text(
            toml.dumps({
                "multi_instance": {
                    "enabled": True,
                    "default_instance": "default",
                },
                "instances": {},
            }),
            encoding="utf-8",
        )
        (self.root / "latest_brawler_data.json").write_text("[]", encoding="utf-8")
        clear_toml_cache()

    @patch("utils.resolve_project_path")
    @patch("gui.instance_config.resolve_project_path")
    def test_ensure_multi_instance_profiles_creates_default(self, mock_resolve, mock_utils_resolve):
        mock_resolve.side_effect = lambda path: str(self.root / path)
        mock_utils_resolve.side_effect = lambda path: str(self.root / path)

        from gui.instance_config import ensure_multi_instance_profiles, list_instance_profiles

        ensure_multi_instance_profiles()
        clear_toml_cache()
        profiles = list_instance_profiles()
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["id"], "default")
        self.assertEqual(profiles[0]["emulator"], "mumu")
        self.assertEqual(profiles[0]["emulator_port"], 16384)

    @patch("utils.resolve_project_path")
    @patch("gui.instance_config.resolve_project_path")
    def test_upsert_instance_profile_rejects_port_collision(self, mock_resolve, mock_utils_resolve):
        mock_resolve.side_effect = lambda path: str(self.root / path)
        mock_utils_resolve.side_effect = lambda path: str(self.root / path)

        from gui.instance_config import ensure_multi_instance_profiles, upsert_instance_profile

        ensure_multi_instance_profiles()
        clear_toml_cache()
        with self.assertRaisesRegex(ValueError, "already used"):
            upsert_instance_profile("ld-2", {
                "name": "LD 2",
                "emulator": "ldplayer",
                "emulator_port": 16384,
            })

    @patch("utils.resolve_project_path")
    @patch("gui.instance_config.resolve_project_path")
    def test_ensure_multi_instance_profiles_uses_next_free_port(self, mock_resolve, mock_utils_resolve):
        mock_resolve.side_effect = lambda path: str(self.root / path)
        mock_utils_resolve.side_effect = lambda path: str(self.root / path)
        (self.root / "cfg" / "instances.toml").write_text(
            toml.dumps({
                "multi_instance": {
                    "enabled": True,
                    "default_instance": "default",
                },
                "instances": {
                    "ld-2": {
                        "name": "LD 2",
                        "enabled": True,
                        "emulator": "ldplayer",
                        "emulator_port": 16384,
                        "emulator_profile_index": "0",
                        "queue_path": "instances/ld-2/latest_brawler_data.json",
                    },
                },
            }),
            encoding="utf-8",
        )
        clear_toml_cache()

        from gui.instance_config import ensure_multi_instance_profiles, list_instance_profiles

        ensure_multi_instance_profiles()
        clear_toml_cache()
        profiles = {profile["id"]: profile for profile in list_instance_profiles()}
        self.assertIn("default", profiles)
        self.assertIn("ld-2", profiles)
        self.assertEqual(profiles["ld-2"]["emulator_port"], 16384)
        self.assertEqual(profiles["default"]["emulator_port"], 16416)


if __name__ == "__main__":
    unittest.main()
