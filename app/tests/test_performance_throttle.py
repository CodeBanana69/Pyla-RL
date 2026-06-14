import time
import unittest
from unittest.mock import MagicMock

from play import Play


class PerformanceThrottleTests(unittest.TestCase):
    def test_refresh_fog_cache_populates_threat_and_direction(self):
        play = object.__new__(Play)
        play.detect_fog_threat = MagicMock(return_value=180.0)
        play.detect_fog_direction_escape = MagicMock(return_value=270.0)

        play._refresh_fog_cache(object(), (50, 50))

        self.assertEqual(play._fog_threat_cached, 180.0)
        self.assertEqual(play._fog_direction_escape_cached, 270.0)
        play.detect_fog_threat.assert_called_once()
        play.detect_fog_direction_escape.assert_called_once()

    def test_wall_tick_skips_retry_when_previous_primary_count_was_healthy(self):
        play = object.__new__(Play)
        play.close_tile_detector_enabled = False
        play.wall_detection_confidence = 0.9
        play.wall_detection_retry_confidence = 0.2
        play.wall_detection_retry_min_objects = 3
        play.last_wall_primary_count = 8
        play.Detect_tile_detector = MagicMock()
        play.Detect_tile_detector.detect_objects.side_effect = [
            {"wall": [[0, 0, 10, 10]]},
            {"wall": [[0, 0, 10, 10], [20, 20, 30, 30], [40, 40, 50, 50], [60, 60, 70, 70]]},
        ]

        play.get_tile_data(object())

        self.assertEqual(play.Detect_tile_detector.detect_objects.call_count, 1)

    def test_entity_retry_skips_when_player_recently_seen(self):
        play = object.__new__(Play)
        play.entity_detection_confidence = 0.55
        play.entity_detection_retry_confidence = 0.35
        play.entity_retry_grace_seconds = 0.4
        play.time_since_player_last_found = time.time()
        play.stabilize_entity_roles = lambda _frame, data: data
        play.Detect_main_info = MagicMock()
        play.Detect_main_info.detect_objects.return_value = {"player": [], "enemy": []}

        play.get_main_data(object())

        self.assertEqual(play.Detect_main_info.detect_objects.call_count, 1)

    def test_entity_retry_runs_when_player_missing_for_a_while(self):
        play = object.__new__(Play)
        play.entity_detection_confidence = 0.55
        play.entity_detection_retry_confidence = 0.35
        play.entity_retry_grace_seconds = 0.4
        play.time_since_player_last_found = time.time() - 2.0
        play.stabilize_entity_roles = lambda _frame, data: data
        play.Detect_main_info = MagicMock()
        play.Detect_main_info.detect_objects.side_effect = [
            {"player": [], "enemy": []},
            {"player": [[1, 1, 2, 2]], "enemy": []},
        ]

        data = play.get_main_data(object())

        self.assertEqual(play.Detect_main_info.detect_objects.call_count, 2)
        self.assertTrue(data.get("player"))

    def test_replay_main_reuses_cached_snapshot_without_onnx(self):
        play = object.__new__(Play)
        play._cached_play_snapshot = {
            "player": [[10, 10, 30, 30]],
            "enemy": [],
            "teammate": [],
            "wall": [[0, 0, 20, 20]],
            "bushes": [],
            "map_objects": {"wall": [[0, 0, 20, 20]]},
            "line_of_sight_wall": [[0, 0, 20, 20]],
        }
        play.validate_game_data = Play.validate_game_data
        play.track_no_detections = MagicMock()
        play.time_since_player_last_found = time.time()
        play.no_detection_proceed_delay = 8.5
        play.time_since_last_proceeding = time.time()
        play.refresh_ready_abilities = MagicMock()
        play.loop = MagicMock(return_value=(100.0, 0.0))
        play.publish_debug_view = MagicMock()
        play.do_movement = MagicMock()
        play.get_main_data = MagicMock()
        play.get_tile_data = MagicMock()
        play.window_controller = MagicMock()
        main = MagicMock()
        main.get_latest_state.return_value = "match"

        play.main(object(), "shelly", main, replay=True)

        play.get_main_data.assert_not_called()
        play.get_tile_data.assert_not_called()
        play.loop.assert_called_once()
        play.do_movement.assert_called_once()


if __name__ == "__main__":
    unittest.main()
