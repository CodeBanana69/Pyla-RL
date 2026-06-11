import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import toml

from utils import clear_toml_cache


class InstanceSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "cfg").mkdir(parents=True, exist_ok=True)
        (self.root / "instances" / "default").mkdir(parents=True, exist_ok=True)
        (self.root / "cfg" / "general_config.toml").write_text(
            toml.dumps({"current_emulator": "LDPlayer", "emulator_port": 5555}),
            encoding="utf-8",
        )
        (self.root / "cfg" / "instances.toml").write_text(
            toml.dumps({
                "multi_instance": {"enabled": True, "default_instance": "default"},
                "instances": {
                    "default": {
                        "name": "Default",
                        "enabled": True,
                        "emulator": "ldplayer",
                        "emulator_port": 5555,
                        "emulator_profile_index": "0",
                        "queue_path": "instances/default/latest_brawler_data.json",
                    },
                },
            }),
            encoding="utf-8",
        )
        (self.root / "instances" / "default" / "latest_brawler_data.json").write_text("[]", encoding="utf-8")
        clear_toml_cache()

    @patch("utils.resolve_project_path")
    @patch("gui.instance_config.resolve_project_path")
    def test_validate_start_rejects_empty_queue(self, mock_resolve, mock_utils_resolve):
        mock_resolve.side_effect = lambda path: str(self.root / path)
        mock_utils_resolve.side_effect = lambda path: str(self.root / path)

        from gui.instance_supervisor import InstanceSupervisor

        supervisor = InstanceSupervisor(self.root)
        ok, message, meta = supervisor.validate_start("default")
        self.assertFalse(ok)
        self.assertIn("no brawler queue", message.lower())
        self.assertEqual(meta.get("action"), "edit_farm_plan")

    @patch("utils.resolve_project_path")
    @patch("gui.instance_config.resolve_project_path")
    def test_validate_start_accepts_queue_with_data(self, mock_resolve, mock_utils_resolve):
        mock_resolve.side_effect = lambda path: str(self.root / path)
        mock_utils_resolve.side_effect = lambda path: str(self.root / path)
        queue_path = self.root / "instances" / "default" / "latest_brawler_data.json"
        queue_path.write_text(json.dumps([{"brawler": "shelly", "push_until": 1000}]), encoding="utf-8")
        clear_toml_cache()

        from gui.instance_supervisor import InstanceSupervisor

        supervisor = InstanceSupervisor(self.root)
        ok, message, _meta = supervisor.validate_start("default")
        self.assertTrue(ok, message)


if __name__ == "__main__":
    unittest.main()
