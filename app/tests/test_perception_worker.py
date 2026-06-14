import threading
import time
import unittest
from unittest.mock import MagicMock

from perception import PerceptionWorker


class PerceptionWorkerTests(unittest.TestCase):
    def test_worker_publishes_new_frame_snapshot(self):
        play = MagicMock()
        play.perceive.return_value = {"player": [[0, 0, 10, 10]]}
        window_controller = MagicMock()
        frame = object()
        window_controller.get_latest_frame.return_value = (frame, time.time())
        window_controller.get_latest_frame_id.return_value = 1

        worker = PerceptionWorker(play, window_controller)
        thread = threading.Thread(target=worker._loop, daemon=True)
        thread.start()
        time.sleep(0.05)
        worker.stop()
        thread.join(timeout=1.0)
        latest = worker.get_latest()
        self.assertIsNotNone(latest)
        self.assertEqual(latest.frame_id, 1)
        self.assertEqual(latest.data["player"], [[0, 0, 10, 10]])
        play.perceive.assert_called()


if __name__ == "__main__":
    unittest.main()
