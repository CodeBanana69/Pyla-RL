import tempfile
import unittest
from pathlib import Path

import toml

from tools.hub_first_run import (
    ensure_hub_first_run_wizard,
    hub_license_acknowledged,
    mark_hub_license_acknowledged,
)


class HubFirstRunTests(unittest.TestCase):
    def test_ensure_sets_wizard_flags_when_license_not_acknowledged(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        config_path = root / "cfg" / "general_config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            'first_run_wizard = "no"\nlicense_accepted = "yes"\n',
            encoding="utf-8",
        )

        changed = ensure_hub_first_run_wizard(root)
        config = toml.load(config_path)

        self.assertTrue(changed)
        self.assertEqual(config["first_run_wizard"], "yes")
        self.assertEqual(config["license_accepted"], "no")

    def test_ensure_skips_after_license_marker_exists(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        config_path = root / "cfg" / "general_config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            'first_run_wizard = "no"\nlicense_accepted = "yes"\n',
            encoding="utf-8",
        )
        mark_hub_license_acknowledged(root)

        changed = ensure_hub_first_run_wizard(root)
        config = toml.load(config_path)

        self.assertFalse(changed)
        self.assertTrue(hub_license_acknowledged(root))
        self.assertEqual(config["license_accepted"], "yes")


if __name__ == "__main__":
    unittest.main()
