import tempfile
import unittest
from pathlib import Path

import toml

from performance_profile import apply_performance_profile
from utils import clear_toml_cache


class PerformanceProfileTest(unittest.TestCase):
    def test_balanced_profile_updates_capture_and_detection_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            general_path = Path(tmp) / "general_config.toml"
            bot_path = Path(tmp) / "bot_config.toml"
            general_path.write_text('max_ips = 45\ncpu_or_gpu = "cpu"\n', encoding="utf-8")
            bot_path.write_text("entity_detection_confidence = 0.7\n", encoding="utf-8")

            clear_toml_cache(str(general_path))
            clear_toml_cache(str(bot_path))
            result = apply_performance_profile("balanced", str(general_path), str(bot_path))

            general = toml.load(general_path)
            bot = toml.load(bot_path)
            self.assertEqual(result["profile"], "balanced")
            self.assertEqual(general["max_ips"], 0)
            self.assertEqual(general["scrcpy_max_fps"], 60)
            self.assertEqual(general["scrcpy_max_width"], 960)
            self.assertEqual(general["scrcpy_bitrate"], 3000000)
            self.assertEqual(general["cpu_or_gpu"], "auto")
            self.assertEqual(general["onnx_cpu_threads"], 4)
            self.assertEqual(bot["entity_detection_confidence"], 0.55)
            self.assertEqual(bot["entity_detection_retry_confidence"], 0.35)

    def test_low_end_profile_uses_lower_frame_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            general_path = Path(tmp) / "general_config.toml"
            bot_path = Path(tmp) / "bot_config.toml"
            general_path.write_text("", encoding="utf-8")
            bot_path.write_text("", encoding="utf-8")

            clear_toml_cache(str(general_path))
            clear_toml_cache(str(bot_path))
            apply_performance_profile("low-end", str(general_path), str(bot_path))

            general = toml.load(general_path)
            self.assertEqual(general["max_ips"], 20)
            self.assertEqual(general["scrcpy_max_fps"], 24)
            self.assertEqual(general["scrcpy_max_width"], 854)
            self.assertEqual(general["used_threads"], 2)

    def test_high_ips_profile_disables_debug_overlays(self):
        with tempfile.TemporaryDirectory() as tmp:
            general_path = Path(tmp) / "general_config.toml"
            bot_path = Path(tmp) / "bot_config.toml"
            time_path = Path(tmp) / "time_tresholds.toml"
            general_path.write_text('visual_debug = "yes"\n', encoding="utf-8")
            bot_path.write_text("fog_check_every_n_frames = 3\n", encoding="utf-8")
            time_path.write_text("wall_detection = 0.75\n", encoding="utf-8")

            clear_toml_cache(str(general_path))
            clear_toml_cache(str(bot_path))
            clear_toml_cache(str(time_path))
            apply_performance_profile("high_ips", str(general_path), str(bot_path), str(time_path))

            general = toml.load(general_path)
            bot = toml.load(bot_path)
            time_cfg = toml.load(time_path)
            self.assertEqual(general["visual_debug"], "no")
            self.assertEqual(general["advanced_visuals"], "no")
            self.assertEqual(bot["fog_check_every_n_frames"], 4)
            self.assertEqual(time_cfg["wall_detection_interval_seconds"], 1.0)

    def test_unknown_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_performance_profile("not-real", save=False)


if __name__ == "__main__":
    unittest.main()
