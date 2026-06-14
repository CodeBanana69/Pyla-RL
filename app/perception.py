from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class PerceptionSnapshot:
    frame_id: int
    frame_time: float
    frame: Any
    data: dict


class PerceptionWorker:
    def __init__(self, play, window_controller, *, use_concurrent_wall=False):
        self.play = play
        self.window_controller = window_controller
        self.use_concurrent_wall = use_concurrent_wall
        self._lock = threading.Lock()
        self._latest: PerceptionSnapshot | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_processed_frame_id = -1

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="pyla-perception")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def get_latest(self) -> PerceptionSnapshot | None:
        with self._lock:
            return self._latest

    def _loop(self):
        perceive = self.play.perceive_concurrent if self.use_concurrent_wall else self.play.perceive
        while not self._stop_event.is_set():
            frame, frame_time = self.window_controller.get_latest_frame()
            frame_id = self.window_controller.get_latest_frame_id()
            if frame is None or frame_id <= self._last_processed_frame_id:
                self._stop_event.wait(0.001)
                continue
            try:
                data = perceive(frame, current_time=time.time())
            except Exception:
                self._stop_event.wait(0.005)
                continue
            snapshot = PerceptionSnapshot(
                frame_id=frame_id,
                frame_time=frame_time,
                frame=frame,
                data=data,
            )
            with self._lock:
                self._latest = snapshot
            self._last_processed_frame_id = frame_id
