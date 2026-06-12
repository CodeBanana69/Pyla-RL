import unittest
from unittest.mock import patch

import numpy as np

import debug_view as dv


class DebugViewTests(unittest.TestCase):
    def test_from_config_uses_visual_debug_from_general_config(self):
        with patch("debug_view.load_toml_as_dict") as mock_load:
            mock_load.side_effect = [
                {"debug_view": "no", "debug_view_fps": 30},
                {"visual_debug": "yes", "visual_debug_max_fps": 24, "advanced_visuals": "yes"},
            ]
            publisher = dv.DebugViewPublisher.from_config()
        self.assertTrue(publisher.enabled)
        self.assertEqual(publisher.max_fps, 24.0)
        self.assertTrue(publisher.advanced_visuals)

    def test_draw_debug_data_renders_state_and_intent(self):
        image = np.zeros((120, 160, 3), dtype=np.uint8)
        dv.draw_debug_data(
            image,
            {
                "state": "match",
                "match_intent": "Shooting",
                "player": [[10, 10, 30, 30]],
                "attack_range": 120,
            },
            160,
            120,
        )
        self.assertTrue(np.any(image))

    def test_draw_close_tile_debug(self):
        image = np.zeros((120, 160, 3), dtype=np.uint8)
        dv.draw_close_tile_debug(
            image,
            {"crop": [20, 20, 80, 80], "source": "close"},
        )
        self.assertTrue(np.any(image[:, :, 2] > 0))

    def test_draw_debug_arrows_and_prediction(self):
        image = np.zeros((120, 160, 3), dtype=np.uint8)
        dv.draw_debug_arrows(
            image,
            [{"from": [10, 60], "to": [90, 60], "color": [0, 255, 255], "label": "MOVE"}],
        )
        dv.draw_enemy_prediction(
            image,
            {
                "current": [40, 40],
                "predicted": [80, 55],
                "lead": [95, 70],
                "velocity": [120.0, 40.0],
                "speed": 126.0,
            },
        )
        self.assertTrue(np.any(image))


if __name__ == "__main__":
    unittest.main()
