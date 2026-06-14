import unittest
from unittest.mock import MagicMock, patch

from play import Play


class MatchWarmupTests(unittest.TestCase):
    def test_warmup_match_inference_runs_once_and_logs(self):
        play = object.__new__(Play)
        play.match_warmup_seconds = 10.0
        play._match_warmup_done = False
        play.Detect_main_info = MagicMock()
        play.Detect_main_info.model_path = "models/main.onnx"
        play.Detect_main_info.warmup_frame.return_value = 12.5
        play.Detect_tile_detector = MagicMock()
        play.Detect_tile_detector.model_path = "models/wall.onnx"
        play.Detect_tile_detector.warmup_frame.return_value = 8.0
        play.Detect_close_tile_detector = None

        frame = object()
        with patch("runtime_log.log_info") as log_info:
            self.assertTrue(play.warmup_match_inference(frame))
            self.assertTrue(play._match_warmup_done)
            self.assertFalse(play.warmup_match_inference(frame))
            play.Detect_main_info.warmup_frame.assert_called_once_with(frame, label="main:main.onnx")
            play.Detect_tile_detector.warmup_frame.assert_called_once_with(frame, label="wall:wall.onnx")
            messages = [call.args[1] for call in log_info.call_args_list]
            self.assertTrue(any("Starting inference warmup 10s into match" in msg for msg in messages))
            self.assertTrue(any("Match inference warmup complete" in msg for msg in messages))

    def test_warmup_skipped_when_disabled(self):
        play = object.__new__(Play)
        play.match_warmup_seconds = 0.0
        play._match_warmup_done = False
        self.assertFalse(play.warmup_match_inference(object()))

    def test_reset_match_control_state_clears_warmup_flag(self):
        play = object.__new__(Play)
        play._match_warmup_done = True
        play.reset_match_control_state()
        self.assertFalse(play._match_warmup_done)


if __name__ == "__main__":
    unittest.main()
