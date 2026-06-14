import time
import unittest
from unittest.mock import MagicMock

import numpy as np

from frame_uniformity import (
    VisualFreezeMonitor,
    frame_change_ratio,
    is_solid_color_frame,
    is_spatially_uniform,
    spatial_uniformity_score,
)


class FrameUniformityTests(unittest.TestCase):
    def test_solid_black_frame_is_uniform(self):
        frame = np.zeros((544, 960, 3), dtype=np.uint8)
        self.assertGreaterEqual(spatial_uniformity_score(frame), 0.99)
        self.assertTrue(is_spatially_uniform(frame, 0.35))

    def test_solid_maroon_frame_is_uniform(self):
        frame = np.full((544, 960, 3), (48, 12, 18), dtype=np.uint8)
        self.assertGreaterEqual(spatial_uniformity_score(frame), 0.99)
        self.assertTrue(is_spatially_uniform(frame, 0.35))

    def test_dark_menu_with_ui_is_not_uniform(self):
        frame = np.full((544, 960, 3), (24, 24, 28), dtype=np.uint8)
        frame[220:300, 380:580] = (180, 180, 190)
        frame[80:120, 40:180] = (90, 90, 100)
        frame[360:520, 60:900] = (55, 55, 65)
        self.assertFalse(is_spatially_uniform(frame, 0.35))
        self.assertFalse(is_solid_color_frame(frame))

    def test_frame_change_ratio_detects_identical_frames(self):
        frame = np.full((100, 100, 3), 40, dtype=np.uint8)
        self.assertEqual(frame_change_ratio(frame, frame.copy()), 0.0)

    def test_frame_change_ratio_detects_changed_frames(self):
        previous = np.zeros((100, 100, 3), dtype=np.uint8)
        current = previous.copy()
        current[10:90, 10:90] = 255
        self.assertGreater(frame_change_ratio(previous, current), 0.1)

    def test_monitor_triggers_scrcpy_restart_after_duration(self):
        monitor = VisualFreezeMonitor(
            {
                "visual_freeze_check_interval": 0.0,
                "visual_freeze_restart": 5.0,
                "visual_freeze_diff_threshold": 0.35,
                "low_ips_recovery_cooldown": 0.0,
            }
        )
        frame = np.zeros((544, 960, 3), dtype=np.uint8)
        restart_scrcpy = MagicMock(return_value=True)
        restart_game = MagicMock(return_value=True)
        restart_emulator = MagicMock(return_value=True)
        emit_event = MagicMock()

        start = 1000.0
        self.assertIsNone(
            monitor.observe(
                frame,
                now=start,
                restart_scrcpy=restart_scrcpy,
                restart_game=restart_game,
                restart_emulator=restart_emulator,
                emit_event=emit_event,
            )
        )
        action = monitor.observe(
            frame,
            now=start + 5.5,
            restart_scrcpy=restart_scrcpy,
            restart_game=restart_game,
            restart_emulator=restart_emulator,
            emit_event=emit_event,
        )
        self.assertEqual(action, "restart_scrcpy")
        restart_scrcpy.assert_called_once()
        restart_game.assert_not_called()
        emit_event.assert_called_once()

    def test_monitor_escalates_to_game_restart(self):
        monitor = VisualFreezeMonitor(
            {
                "visual_freeze_check_interval": 0.0,
                "visual_freeze_restart": 1.0,
                "global_freeze_restart": 2.0,
                "visual_freeze_diff_threshold": 0.35,
                "low_ips_recovery_cooldown": 0.0,
            }
        )
        frame = np.zeros((544, 960, 3), dtype=np.uint8)
        restart_scrcpy = MagicMock(return_value=False)
        restart_game = MagicMock(return_value=True)
        restart_emulator = MagicMock(return_value=True)

        start = 1000.0
        monitor.observe(
            frame,
            now=start,
            restart_scrcpy=restart_scrcpy,
            restart_game=restart_game,
            restart_emulator=restart_emulator,
        )
        monitor.observe(
            frame,
            now=start + 1.5,
            restart_scrcpy=restart_scrcpy,
            restart_game=restart_game,
            restart_emulator=restart_emulator,
        )
        action = monitor.observe(
            frame,
            now=start + 4.0,
            restart_scrcpy=restart_scrcpy,
            restart_game=restart_game,
            restart_emulator=restart_emulator,
        )
        self.assertEqual(action, "restart_game")
        restart_game.assert_called_once()

    def test_monitor_resets_when_frame_varies(self):
        monitor = VisualFreezeMonitor(
            {
                "visual_freeze_check_interval": 0.0,
                "visual_freeze_restart": 1.0,
                "visual_freeze_diff_threshold": 0.35,
            }
        )
        uniform = np.zeros((544, 960, 3), dtype=np.uint8)
        varied = np.random.default_rng(0).integers(0, 255, size=(544, 960, 3), dtype=np.uint8)

        monitor.observe(
            uniform,
            now=1000.0,
            restart_scrcpy=MagicMock(return_value=True),
            restart_game=MagicMock(return_value=True),
            restart_emulator=MagicMock(return_value=True),
        )
        monitor.observe(
            varied,
            now=1001.0,
            restart_scrcpy=MagicMock(return_value=True),
            restart_game=MagicMock(return_value=True),
            restart_emulator=MagicMock(return_value=True),
        )
        self.assertIsNone(monitor._uniform_since)


if __name__ == "__main__":
    unittest.main()
