import unittest
from unittest.mock import MagicMock, patch

import numpy as np

import play as play_module
import visual_debug_window as vdw


class VisualDebugShimTests(unittest.TestCase):
    def test_backend_name_is_subprocess(self):
        self.assertEqual(vdw.visual_debug_backend_name(), "subprocess")

    @patch("visual_debug_window.DebugViewPublisher.from_config")
    def test_log_startup_reports_subprocess_backend(self, mock_from_config):
        mock_from_config.return_value = MagicMock(enabled=True)
        with patch.object(vdw, "opencv_highgui_available", return_value=True):
            vdw.log_visual_debug_startup()


class PublishDebugViewTests(unittest.TestCase):
    def setUp(self):
        self.play = play_module.Play.__new__(play_module.Play)
        self.play.window_controller = MagicMock()
        self.play.window_controller.joystick_x = 100
        self.play.window_controller.joystick_y = 200
        self.play.window_controller.scale_factor = 1.0
        self.play.advanced_visuals = False
        self.play.current_brawler = "shelly"
        self.play.brawlers_info = {}
        self.play.last_tile_detection_debug = None
        self.play.match_intent_summary = "Shooting"
        self.play.window_controller.debug_view = MagicMock(enabled=True, advanced_visuals=False)

    def test_publish_debug_view_forwards_payload(self):
        frame = np.zeros((4, 4, 3), dtype=np.uint8)
        data = {"player": [[1, 1, 3, 3]], "enemy": [], "teammate": [], "wall": []}
        with patch.object(play_module.Play, "get_brawler_range", return_value=(0, 120, 240)), patch.object(
            play_module.Play, "get_effective_enemy_range", return_value=150
        ), patch.object(play_module.Play, "is_there_poison_gas", return_value={}), patch.object(
            play_module.Play, "get_player_foot_circle", return_value=(2, 3, 10)
        ):
            play_module.Play.publish_debug_view(self.play, frame, data, "match")

        self.play.window_controller.debug_view.publish.assert_called_once()
        published_frame, published_data = self.play.window_controller.debug_view.publish.call_args.args
        self.assertIs(published_frame, frame)
        self.assertEqual(published_data["state"], "match")
        self.assertEqual(published_data["match_intent"], "Shooting")
        self.assertEqual(published_data["player_hit_circle"], [2, 3, 10])
        self.assertIn("arrows", published_data)

    def test_build_debug_overlay_hints_adds_movement_arrow(self):
        play = play_module.Play.__new__(play_module.Play)
        play.match_intent_summary = "Shooting"
        play.is_showdown = False
        play._evasion_active = False
        play._dodge_vector = None
        play._fog_direction_escape_cached = None
        play._fog_threat_cached = None
        play._spacing_action = "hold"
        play.escape_state = {"phase": None}
        play._enemy_track = {"pos": (50, 50), "velocity": (20.0, 0.0)}
        play.window_controller = MagicMock(scale_factor=1.0)
        play.projectile_speed_px_s = 1200.0
        with patch.object(play_module.Play, "movement_to_vector", return_value=(60.0, 0.0)), patch.object(
            play_module.Play, "is_there_enemy", return_value=True
        ), patch.object(
            play_module.Play, "find_closest_enemy", return_value=((80, 50), 30.0)
        ), patch.object(
            play_module.Play, "get_tracked_enemy_velocity", return_value=(20.0, 0.0)
        ), patch.object(
            play_module.Play, "get_player_pos", return_value=(40.0, 50.0)
        ), patch.object(
            play_module.Play, "get_player_foot_circle", return_value=(40.0, 52.0, 10.0)
        ):
            hints = play_module.Play._build_debug_overlay_hints(
                play,
                {"player": [[30, 30, 50, 55]], "enemy": [[70, 40, 90, 60]], "wall": []},
                (60.0, 0.0),
            )
        self.assertTrue(hints["arrows"])
        self.assertIsNotNone(hints["enemy_prediction"])

    def test_publish_debug_view_noops_when_disabled(self):
        self.play.window_controller.debug_view.enabled = False
        play_module.Play.publish_debug_view(self.play, np.zeros((2, 2, 3), dtype=np.uint8), {}, "lobby")
        self.play.window_controller.debug_view.publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
