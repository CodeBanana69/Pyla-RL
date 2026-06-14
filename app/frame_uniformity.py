from __future__ import annotations

import time
from typing import Any, Callable

import numpy as np

_SAMPLE_SIZE = (64, 36)
_PIXEL_TOLERANCE = 10


def _uniformity_min_from_diff_threshold(diff_threshold: float) -> float:
    threshold = float(diff_threshold or 0.35)
    return max(0.94, 1.0 - threshold * 0.1)


def _downsample_frame(frame: np.ndarray, sample_size: tuple[int, int]) -> np.ndarray:
    height, width = frame.shape[:2]
    sample_w, sample_h = sample_size
    if width == sample_w and height == sample_h:
        return frame[:, :, :3]

    y_idx = (np.linspace(0, height - 1, sample_h)).astype(np.int32)
    x_idx = (np.linspace(0, width - 1, sample_w)).astype(np.int32)
    return frame[np.ix_(y_idx, x_idx)][:, :, :3]


def spatial_uniformity_score(frame: np.ndarray, *, tolerance: int = _PIXEL_TOLERANCE) -> float:
    """Return the fraction of sampled pixels near the frame median color."""
    if frame is None or frame.size == 0:
        return 0.0
    if frame.ndim != 3 or frame.shape[2] < 3:
        return 0.0

    height, width = frame.shape[:2]
    if height <= 0 or width <= 0:
        return 0.0

    small = _downsample_frame(frame, _SAMPLE_SIZE)

    pixels = small[:, :, :3].reshape(-1, 3).astype(np.int16)
    median = np.median(pixels, axis=0)
    distance = np.max(np.abs(pixels - median), axis=1)
    return float(np.mean(distance <= tolerance))


def is_spatially_uniform(frame: np.ndarray, diff_threshold: float) -> bool:
    return spatial_uniformity_score(frame) >= _uniformity_min_from_diff_threshold(diff_threshold)


def is_solid_color_frame(frame: np.ndarray) -> bool:
    return spatial_uniformity_score(frame) >= 0.99


def frame_change_ratio(previous: np.ndarray | None, current: np.ndarray) -> float:
    if previous is None or previous.size == 0 or current is None or current.size == 0:
        return 1.0
    if previous.shape != current.shape:
        return 1.0

    prev = previous[:, :, :3].astype(np.float32)
    curr = current[:, :, :3].astype(np.float32)
    return float(np.mean(np.abs(prev - curr)) / 255.0)


class VisualFreezeMonitor:
    def __init__(self, thresholds: dict[str, Any] | None = None):
        thresholds = thresholds or {}
        self.check_interval = float(thresholds.get("visual_freeze_check_interval", 1.0))
        self.restart_after = float(thresholds.get("visual_freeze_restart", 45.0))
        self.diff_threshold = float(thresholds.get("visual_freeze_diff_threshold", 0.35))
        self.global_restart_after = float(thresholds.get("global_freeze_restart", 60.0))
        self.recovery_cooldown = float(thresholds.get("low_ips_recovery_cooldown", 35.0))
        self.emulator_restart_after = int(thresholds.get("global_freeze_emulator_restart_after", 2))

        self._last_check_at = 0.0
        self._uniform_since: float | None = None
        self._previous_frame: np.ndarray | None = None
        self._last_recovery_at = 0.0
        self._scrcpy_attempts = 0
        self._game_attempts = 0

    def reset(self) -> None:
        self._uniform_since = None
        self._previous_frame = None
        self._scrcpy_attempts = 0
        self._game_attempts = 0

    def _is_frozen_frame(self, frame: np.ndarray) -> bool:
        uniformity = spatial_uniformity_score(frame)
        min_uniformity = _uniformity_min_from_diff_threshold(self.diff_threshold)
        change_ratio = frame_change_ratio(self._previous_frame, frame)
        self._previous_frame = frame
        if uniformity < min_uniformity:
            return False
        if is_solid_color_frame(frame):
            return True
        return change_ratio <= self.diff_threshold

    def observe(
        self,
        frame: np.ndarray,
        now: float | None = None,
        *,
        restart_scrcpy: Callable[[], bool],
        restart_game: Callable[[], bool],
        restart_emulator: Callable[[], bool],
        emit_event: Callable[[str, str], None] | None = None,
    ) -> str | None:
        now = time.time() if now is None else now
        if now - self._last_check_at < self.check_interval:
            return None
        self._last_check_at = now

        if not self._is_frozen_frame(frame):
            self._uniform_since = None
            self._scrcpy_attempts = 0
            self._game_attempts = 0
            return None

        if self._uniform_since is None:
            self._uniform_since = now
            return None

        frozen_for = now - self._uniform_since
        if frozen_for < self.restart_after:
            return None
        if now - self._last_recovery_at < self.recovery_cooldown:
            return None

        action = None
        if self._scrcpy_attempts < 1:
            self._scrcpy_attempts += 1
            action = "restart_scrcpy"
            ok = restart_scrcpy()
            detail = f"uniform_for={frozen_for:.1f}s scrcpy_ok={ok}"
        elif frozen_for >= self.global_restart_after and self._game_attempts < self.emulator_restart_after:
            self._game_attempts += 1
            action = "restart_game"
            ok = restart_game()
            detail = f"uniform_for={frozen_for:.1f}s game_ok={ok}"
        elif self._game_attempts >= self.emulator_restart_after:
            action = "restart_emulator"
            ok = restart_emulator()
            detail = f"uniform_for={frozen_for:.1f}s emulator_ok={ok}"
            self.reset()
        else:
            return None

        self._last_recovery_at = now
        self._uniform_since = now
        if emit_event is not None and action is not None:
            emit_event("visual_freeze", detail)
        return action
