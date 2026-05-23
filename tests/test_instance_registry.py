import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gui.instance_config import (
    default_port_for_emulator,
    infer_profile_index,
    normalize_instance_profile,
    set_active_instance,
)
from gui.instance_registry import build_manifest, resolve_instance, write_manifest


class InstanceRegistryTest(unittest.TestCase):
    def tearDown(self):
        set_active_instance(None)

    def test_normalize_ldplayer_profile(self):
        profile = normalize_instance_profile("ld-1", {
            "name": "LD 1",
            "emulator": "ldplayer",
            "emulator_port": 5557,
        })
        self.assertEqual(profile["emulator"], "ldplayer")
        self.assertEqual(profile["emulator_port"], 5557)
        self.assertEqual(profile["emulator_profile_index"], "1")

    def test_infer_profile_index(self):
        self.assertEqual(infer_profile_index("ldplayer", 5555), "0")
        self.assertEqual(infer_profile_index("mumu", 16416), "1")

    def test_default_ports(self):
        self.assertEqual(default_port_for_emulator("ldplayer"), 5555)
        self.assertEqual(default_port_for_emulator("mumu"), 16384)

    def test_build_manifest(self):
        payload = build_manifest(
            "ld-1",
            pid=1234,
            state_path="logs/runtime_control_1234.state",
            metrics_path="logs/runtime_metrics_1234.json",
            snapshot={"brawler": "colt", "session_wins": 2},
        )
        self.assertEqual(payload["instance_id"], "ld-1")
        self.assertEqual(payload["brawler"], "colt")

    def test_write_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("gui.instance_registry.manifest_path") as mock_path:
                path = Path(temp_dir) / "ld-1.json"
                mock_path.return_value = path
                write_manifest("ld-1", {"instance_id": "ld-1", "pid": 99})
                self.assertTrue(path.exists())

    def test_resolve_instance(self):
        with patch("gui.instance_registry.list_instances", return_value=[
            {"id": "ld-1", "name": "LD 1", "running": True},
        ]):
            self.assertEqual(resolve_instance("ld-1")["id"], "ld-1")
            self.assertEqual(resolve_instance("LD 1")["id"], "ld-1")


if __name__ == "__main__":
    unittest.main()
