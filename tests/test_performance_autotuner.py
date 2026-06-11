import tempfile
import time
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import MagicMock, patch

import toml

from performance_autotuner import PerformanceAutoTuner, TUNING_RUNGS, is_performance_autotune_enabled
from utils import clear_toml_cache


class PerformanceAutoTunerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "cfg").mkdir(parents=True, exist_ok=True)
        (self.root / "cfg" / "general_config.toml").write_text(
            toml.dumps({
                "performance_autotune": "yes",
                "max_ips": 20,
                "scrcpy_max_fps": 60,
                "scrcpy_max_width": 960,
                "ocr_scale_down_factor": 0.5,
            }),
            encoding="utf-8",
        )
        clear_toml_cache()

    @patch("performance_autotuner.load_toml_as_dict")
    @patch("performance_autotuner.save_dict_as_toml")
    @patch("performance_autotuner.is_performance_autotune_enabled", return_value=True)
    def test_step_down_on_sustained_low_ips(self, _enabled, mock_save, mock_load):
        mock_load.return_value = {
            "scrcpy_max_fps": 60,
            "scrcpy_max_width": 960,
            "ocr_scale_down_factor": 0.5,
        }
        tuner = PerformanceAutoTuner(target_ips=20.0)
        tuner._window_started_at = time.time() - 61.0
        low_history = deque([10.0] * 20)

        tuner.observe_ips(low_history)
        tuner._window_started_at = time.time() - 61.0
        tuner.observe_ips(low_history)
        self.assertTrue(tuner.should_step_down())

        controller = MagicMock()
        direction = tuner.apply_pending_adjustment(controller)
        self.assertEqual(direction, "down")
        controller.restart_scrcpy_client.assert_called_once()
        mock_save.assert_called_once()

    @patch("performance_autotuner.is_performance_autotune_enabled", return_value=True)
    def test_step_up_requires_more_windows(self, _enabled):
        tuner = PerformanceAutoTuner(target_ips=20.0)
        high_history = deque([30.0] * 20)

        for _ in range(4):
            tuner._window_started_at = time.time() - 61.0
            tuner.observe_ips(high_history)
        self.assertFalse(tuner.should_step_up())

        tuner._window_started_at = time.time() - 61.0
        tuner.observe_ips(high_history)
        self.assertTrue(tuner.should_step_up())

    @patch("performance_autotuner.is_performance_autotune_enabled", return_value=False)
    def test_disabled_flag_is_noop(self, _enabled):
        tuner = PerformanceAutoTuner(target_ips=20.0)
        tuner._window_started_at = time.time() - 61.0
        tuner.observe_ips(deque([1.0] * 20))
        self.assertFalse(tuner.should_step_down())

    def test_rung_clamping_at_lowest(self):
        tuner = PerformanceAutoTuner(target_ips=20.0)
        tuner._rung_index = len(TUNING_RUNGS) - 1
        tuner._low_streak = 3
        controller = MagicMock()
        with patch("performance_autotuner.is_performance_autotune_enabled", return_value=True):
            self.assertIsNone(tuner.apply_pending_adjustment(controller))
        controller.restart_scrcpy_client.assert_not_called()

    @patch("utils.resolve_project_path")
    def test_disabled_config_flag(self, mock_resolve):
        mock_resolve.side_effect = lambda path: str(self.root / path)
        data = toml.loads((self.root / "cfg" / "general_config.toml").read_text(encoding="utf-8"))
        data["performance_autotune"] = "no"
        (self.root / "cfg" / "general_config.toml").write_text(toml.dumps(data), encoding="utf-8")
        clear_toml_cache()
        with patch("performance_autotuner.load_toml_as_dict", return_value=data):
            self.assertFalse(is_performance_autotune_enabled())


if __name__ == "__main__":
    unittest.main()
