"""Unit tests for rl.health_monitor.HealthMonitor."""

from __future__ import annotations

import unittest

import numpy as np

from rl.health_monitor import HealthMonitor


def _fill_hp_band_green(frame: np.ndarray, player_box, *, green_ratio: float = 1.0) -> None:
    """Paint the HP strip above the player with green vs red HSV mix."""
    x1, y1, x2, y2 = map(float, player_box[:4])
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    h, w = frame.shape[:2]
    off = 8.0
    bh = 14.0
    band_top = max(0, int(y1 - off - bh))
    band_bot = min(h, int(y1 - off))
    bx1 = max(0, int(x1))
    bx2 = min(w, int(x2))
    if band_bot <= band_top or bx2 <= bx1:
        return
    band = frame[band_top:band_bot, bx1:bx2]
    gw = max(1, int(band.shape[1] * green_ratio))
    band[:, :gw] = (0, 255, 0)
    band[:, gw:] = (255, 0, 0)


class HealthMonitorTests(unittest.TestCase):
    def test_all_green_band_high_pct(self):
        frame = np.zeros((400, 400, 3), dtype=np.uint8)
        player = [100.0, 200.0, 300.0, 220.0]
        _fill_hp_band_green(frame, player, green_ratio=1.0)
        hm = HealthMonitor(min_total_pixels=20)
        pct, ok, _gr = hm.read_hp_band(frame, player, scale_factor=1.0)
        self.assertTrue(ok)
        self.assertIsNotNone(pct)
        assert pct is not None
        self.assertGreater(pct, 0.92)

    def test_half_half_band_near_half(self):
        frame = np.zeros((400, 400, 3), dtype=np.uint8)
        player = [100.0, 200.0, 300.0, 220.0]
        _fill_hp_band_green(frame, player, green_ratio=0.5)
        hm = HealthMonitor(min_total_pixels=20)
        pct, ok, _gr = hm.read_hp_band(frame, player, scale_factor=1.0)
        self.assertTrue(ok)
        assert pct is not None
        self.assertAlmostEqual(pct, 0.5, delta=0.08)

    def test_all_red_band_low_pct(self):
        frame = np.zeros((400, 400, 3), dtype=np.uint8)
        player = [100.0, 200.0, 300.0, 220.0]
        _fill_hp_band_green(frame, player, green_ratio=0.0)
        hm = HealthMonitor(min_total_pixels=20)
        pct, ok, _gr = hm.read_hp_band(frame, player, scale_factor=1.0)
        self.assertTrue(ok)
        assert pct is not None
        self.assertLess(pct, 0.12)

    def test_insufficient_pixels_not_ok(self):
        frame = np.zeros((400, 400, 3), dtype=np.uint8)
        player = [100.0, 200.0, 105.0, 220.0]
        _fill_hp_band_green(frame, player, green_ratio=1.0)
        hm = HealthMonitor(min_total_pixels=5000)
        _pct, ok, _gr = hm.read_hp_band(frame, player, scale_factor=1.0)
        self.assertFalse(ok)

    def test_sharp_drop_emits_damage_event(self):
        frame_hi = np.zeros((400, 400, 3), dtype=np.uint8)
        frame_lo = np.zeros((400, 400, 3), dtype=np.uint8)
        player = [100.0, 200.0, 300.0, 220.0]
        _fill_hp_band_green(frame_hi, player, green_ratio=1.0)
        _fill_hp_band_green(frame_lo, player, green_ratio=0.3)
        hm = HealthMonitor(
            min_total_pixels=20,
            damage_drop_threshold=0.015,
            prior_window_seconds=0.4,
            min_consecutive_drops=1,
        )
        ev0 = hm.update(0.0, frame_hi, player, 1.0, None)
        self.assertIsNone(ev0)
        ev1 = hm.update(0.1, frame_lo, player, 1.0, None)
        self.assertIsNotNone(ev1)
        assert ev1 is not None
        self.assertGreater(ev1.drop_pct, 0.015)
        self.assertIsNotNone(hm.recent_damage_event(0.11, 0.5))

    def test_gradual_drift_no_event(self):
        hm = HealthMonitor(
            min_total_pixels=20,
            damage_drop_threshold=0.015,
            prior_window_seconds=0.4,
            min_consecutive_drops=1,
        )
        player = [100.0, 200.0, 300.0, 220.0]
        for i in range(15):
            g = 1.0 - i * 0.0008
            frame = np.zeros((400, 400, 3), dtype=np.uint8)
            _fill_hp_band_green(frame, player, green_ratio=max(0.05, min(1.0, g)))
            ev = hm.update(0.01 * i, frame, player, 1.0, None)
            self.assertIsNone(ev)

    def test_debounce_requires_two_frames_when_min2(self):
        frame_hi = np.zeros((400, 400, 3), dtype=np.uint8)
        frame_lo = np.zeros((400, 400, 3), dtype=np.uint8)
        player = [100.0, 200.0, 300.0, 220.0]
        _fill_hp_band_green(frame_hi, player, green_ratio=1.0)
        _fill_hp_band_green(frame_lo, player, green_ratio=0.3)
        hm = HealthMonitor(
            min_total_pixels=20,
            damage_drop_threshold=0.015,
            prior_window_seconds=0.4,
            min_consecutive_drops=2,
        )
        hm.update(0.0, frame_hi, player, 1.0, None)
        ev1 = hm.update(0.1, frame_lo, player, 1.0, None)
        self.assertIsNone(ev1)


if __name__ == "__main__":
    unittest.main()
