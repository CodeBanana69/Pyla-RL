import time
import unittest
from unittest.mock import MagicMock

from play import Play


class MovementApplyTests(unittest.TestCase):
    def test_do_movement_and_sustain_reapply_vector(self):
        play = object.__new__(Play)
        play.window_controller = MagicMock()
        play._last_commanded_movement = None

        play.do_movement((90.0, 0.0))
        play.window_controller.move.assert_called_once_with(90.0, 0.0)

        play.window_controller.move.reset_mock()
        play.sustain_movement()
        play.window_controller.move.assert_called_once_with(90.0, 0.0)

    def test_do_movement_invalid_vector_releases(self):
        play = object.__new__(Play)
        play.window_controller = MagicMock()
        play._last_commanded_movement = (10.0, 5.0)

        play.do_movement("")
        play.window_controller.release_movement.assert_called_once()
        self.assertIsNone(play._last_commanded_movement)

    def test_decide_applies_movement_only_for_valid_vectors(self):
        play = object.__new__(Play)
        play.window_controller = MagicMock()
        play._last_commanded_movement = None
        play.validate_game_data = lambda data: data
        play.track_no_detections = lambda *_args, **_kwargs: None
        play.time_since_player_last_found = time.time()
        play.time_since_last_proceeding = time.time()
        play.no_detection_proceed_delay = 999
        play.refresh_ready_abilities = lambda *_args, **_kwargs: None
        play.frame = object()
        play.loop = MagicMock(return_value="")
        play.publish_debug_view = lambda *_args, **_kwargs: None
        play._cached_play_snapshot = None
        play.last_decide_ms = 0.0
        main = MagicMock()
        main.get_latest_state = lambda: "match"

        play.decide(object(), {"player": [[0, 0, 1, 1]]}, "shelly", main)
        play.window_controller.move.assert_not_called()
        play.window_controller.release_movement.assert_not_called()

        play.loop.return_value = (120.0, -40.0)
        play.decide(object(), {"player": [[0, 0, 1, 1]]}, "shelly", main)
        play.window_controller.move.assert_called_once_with(120.0, -40.0)


class FogCacheTests(unittest.TestCase):
    def test_refresh_fog_cache_populates_threat_and_direction(self):
        play = object.__new__(Play)
        play.detect_fog_threat = MagicMock(return_value=180.0)
        play.detect_fog_direction_escape = MagicMock(return_value=270.0)

        play._refresh_fog_cache(object(), (50, 50))

        self.assertEqual(play._fog_threat_cached, 180.0)
        self.assertEqual(play._fog_direction_escape_cached, 270.0)
        play.detect_fog_threat.assert_called_once()
        play.detect_fog_direction_escape.assert_called_once()


if __name__ == "__main__":
    unittest.main()
