import unittest
from unittest.mock import MagicMock

import numpy as np

from lobby_automation import LobbyAutomation, looks_like_idle_disconnect_dialog


class IdleDisconnectTests(unittest.TestCase):
    def test_detects_dark_low_saturation_dialog(self):
        frame = np.full((540, 960, 3), 40, dtype=np.uint8)
        h, w = frame.shape[:2]
        frame[int(h * 0.32):int(h * 0.62), int(w * 0.24):int(w * 0.76)] = 28
        self.assertTrue(looks_like_idle_disconnect_dialog(frame))

    def test_ignores_bright_gameplay_frame(self):
        frame = np.full((540, 960, 3), 180, dtype=np.uint8)
        self.assertFalse(looks_like_idle_disconnect_dialog(frame))

    def test_check_for_idle_clicks_reload_then_restarts(self):
        automator = LobbyAutomation.__new__(LobbyAutomation)
        automator._idle_strikes = 0
        automator._last_idle_action_at = 0.0
        automator.window_controller = MagicMock()
        automator.window_controller.width_ratio = 1.0
        automator.window_controller.height_ratio = 1.0
        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)

        action = automator.check_for_idle(frame)
        self.assertEqual(action, "clicked")
        automator.window_controller.click.assert_called_once()

        automator._last_idle_action_at = 0.0
        automator._idle_strikes = 2
        action = automator.check_for_idle(frame)
        self.assertEqual(action, "restart")


if __name__ == "__main__":
    unittest.main()
