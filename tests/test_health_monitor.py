"""Unit tests for rl.health_monitor.HealthMonitor."""

from __future__ import annotations

import unittest

import numpy as np

from rl.health_monitor import HealthMonitor, format_power_cube_bonus_suffix


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


def _hsv_only_hm(**overrides) -> HealthMonitor:
    """Build a HealthMonitor that doesn't touch EasyOCR (HSV path only)."""
    kw = dict(min_total_pixels=20, ocr_primary=False, ocr_enabled=False)
    kw.update(overrides)
    return HealthMonitor(**kw)


class _StubOCR:
    """EasyOCR-compatible stub that returns a scripted sequence of digit reads."""

    def __init__(self, sequence):
        # Each entry is either an int/None (single read) or a list of (bbox, text, prob)
        self._queue = list(sequence)
        self.last_kwargs = None

    def readtext(self, image, **kwargs):
        self.last_kwargs = kwargs
        if not self._queue:
            return []
        item = self._queue.pop(0)
        if item is None:
            return []
        if isinstance(item, int):
            return [([[0, 0], [10, 0], [10, 10], [0, 10]], str(item), 0.95)]
        if isinstance(item, tuple) and len(item) == 2:
            val, prob = item
            if val is None:
                return []
            return [([[0, 0], [10, 0], [10, 10], [0, 10]], str(val), float(prob))]
        return list(item)


def _ocr_hm(seq, **overrides) -> HealthMonitor:
    kw = dict(
        min_total_pixels=20,
        ocr_primary=True,
        ocr_enabled=True,
        ocr_run_in_thread="no",
        ocr_log_terminal=False,
        ocr_full_hp_lock_repeats=2,
        ocr_min_confidence=0.3,
        ocr_damage_drop_min=1,
        hsv_fallback_enabled=True,
        ocr_reader=_StubOCR(seq),
    )
    kw.update(overrides)
    return HealthMonitor(**kw)


# ─────────────────────────────────────────────────────────────────────────────
# HSV pipeline (unchanged behavior, still tested directly)
# ─────────────────────────────────────────────────────────────────────────────


class FormatPowerCubeSuffixTests(unittest.TestCase):
    def test_showdown_frank_example(self):
        s = format_power_cube_bonus_suffix(47900, 84, 400)
        self.assertIn("cubes=84", s)
        self.assertIn("base≈14300", s)
        self.assertIn("+33600", s)


class HsvReadHpBandTests(unittest.TestCase):
    def test_all_green_band_high_pct(self):
        frame = np.zeros((400, 400, 3), dtype=np.uint8)
        player = [100.0, 200.0, 300.0, 220.0]
        _fill_hp_band_green(frame, player, green_ratio=1.0)
        hm = _hsv_only_hm()
        pct, ok, _gr = hm.read_hp_band(frame, player, scale_factor=1.0)
        self.assertTrue(ok)
        self.assertIsNotNone(pct)
        assert pct is not None
        self.assertGreater(pct, 0.92)

    def test_half_half_band_near_half(self):
        frame = np.zeros((400, 400, 3), dtype=np.uint8)
        player = [100.0, 200.0, 300.0, 220.0]
        _fill_hp_band_green(frame, player, green_ratio=0.5)
        hm = _hsv_only_hm()
        pct, ok, _gr = hm.read_hp_band(frame, player, scale_factor=1.0)
        self.assertTrue(ok)
        assert pct is not None
        self.assertAlmostEqual(pct, 0.5, delta=0.08)

    def test_all_red_band_low_pct(self):
        frame = np.zeros((400, 400, 3), dtype=np.uint8)
        player = [100.0, 200.0, 300.0, 220.0]
        _fill_hp_band_green(frame, player, green_ratio=0.0)
        hm = _hsv_only_hm()
        pct, ok, _gr = hm.read_hp_band(frame, player, scale_factor=1.0)
        self.assertTrue(ok)
        assert pct is not None
        self.assertLess(pct, 0.12)

    def test_insufficient_pixels_not_ok(self):
        frame = np.zeros((400, 400, 3), dtype=np.uint8)
        player = [100.0, 200.0, 300.0, 220.0]
        hm = _hsv_only_hm()
        _pct, ok, _gr = hm.read_hp_band(frame, player, scale_factor=1.0)
        self.assertFalse(ok)
        self.assertEqual(hm.last_hp_status, "insufficient_pixels")

    def test_muted_green_still_counts(self):
        """S/V floors used to be 80; dim UI greens must still register as fill."""
        frame = np.zeros((400, 400, 3), dtype=np.uint8)
        player = [100.0, 200.0, 300.0, 220.0]
        x1, y1, x2, y2 = player
        off, bh = 8.0, 14.0
        band_top = max(0, int(y1 - off - bh))
        band_bot = min(400, int(y1 - off))
        bx1, bx2 = max(0, int(x1)), min(400, int(x2))
        frame[band_top:band_bot, bx1:bx2] = (90, 190, 90)
        hm = _hsv_only_hm()
        pct, ok, _gr = hm.read_hp_band(frame, player, scale_factor=1.0)
        self.assertTrue(ok)
        assert pct is not None
        self.assertGreater(pct, 0.7)


class HsvDamageEventFallbackTests(unittest.TestCase):
    """HSV damage events still fire when OCR has not yet latched."""

    def test_sharp_drop_emits_damage_event(self):
        frame_hi = np.zeros((400, 400, 3), dtype=np.uint8)
        frame_lo = np.zeros((400, 400, 3), dtype=np.uint8)
        player = [100.0, 200.0, 300.0, 220.0]
        _fill_hp_band_green(frame_hi, player, green_ratio=1.0)
        _fill_hp_band_green(frame_lo, player, green_ratio=0.3)
        hm = _hsv_only_hm(
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
        hm = _hsv_only_hm(
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
        hm = _hsv_only_hm(
            damage_drop_threshold=0.015,
            prior_window_seconds=0.4,
            min_consecutive_drops=2,
        )
        hm.update(0.0, frame_hi, player, 1.0, None)
        ev1 = hm.update(0.1, frame_lo, player, 1.0, None)
        self.assertIsNone(ev1)


# ─────────────────────────────────────────────────────────────────────────────
# OCR-first pipeline
# ─────────────────────────────────────────────────────────────────────────────


class OcrFirstTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((400, 400, 3), dtype=np.uint8)
        self.player = [100.0, 200.0, 300.0, 220.0]
        _fill_hp_band_green(self.frame, self.player, green_ratio=1.0)

    def test_max_hp_latches_after_repeats(self):
        # Two identical reads of 47900 should latch max_hp.
        hm = _ocr_hm([47900, 47900])
        # First update: seeds the latch candidate but doesn't lock yet.
        hm.update(0.0, self.frame, self.player, 1.0, None)
        self.assertFalse(hm.max_hp_locked)
        # Second update (>= cadence period after first): same value → locked.
        hm.update(0.25, self.frame, self.player, 1.0, None)
        self.assertTrue(hm.max_hp_locked)
        self.assertEqual(hm.observed_max_hp, 47900)
        self.assertEqual(hm.hp_value, 47900)
        self.assertEqual(hm.last_hp_status, "ok")
        self.assertAlmostEqual(hm.last_hp_pct or 0.0, 1.0, delta=1e-3)

    def test_damage_event_from_ocr_drop(self):
        hm = _ocr_hm([47900, 47900, 39700, 39700], damage_drop_threshold=0.015)
        hm.update(0.0, self.frame, self.player, 1.0, None)
        hm.update(0.25, self.frame, self.player, 1.0, None)
        self.assertTrue(hm.max_hp_locked)
        # Third tick — value drops to 39700. Should emit a DamageEvent.
        ev = hm.update(0.50, self.frame, self.player, 1.0, None)
        self.assertIsNotNone(ev)
        assert ev is not None
        self.assertAlmostEqual(ev.drop_pct, (47900 - 39700) / 47900.0, places=3)
        # Fourth tick — same 39700, no new event.
        ev2 = hm.update(0.75, self.frame, self.player, 1.0, None)
        self.assertIsNone(ev2)

    def test_hp_value_pct_property_when_locked(self):
        # Sequence respects the default 0.4 relative-jump guard (10000 → 7500 = 25% drop).
        hm = _ocr_hm([10000, 10000, 7500])
        hm.update(0.0, self.frame, self.player, 1.0, None)
        hm.update(0.25, self.frame, self.player, 1.0, None)
        hm.update(0.50, self.frame, self.player, 1.0, None)
        self.assertTrue(hm.max_hp_locked)
        self.assertAlmostEqual(hm.hp_value_pct or 0.0, 0.75, places=3)

    def test_hsv_fallback_used_when_no_ocr(self):
        """If OCR returns nothing, HSV fills last_hp_pct (pre-latch)."""
        hm = _ocr_hm([None, None, None])
        hm.update(0.0, self.frame, self.player, 1.0, None)
        # OCR returned nothing → HSV (full green band) drove last_hp_pct.
        self.assertFalse(hm.max_hp_locked)
        self.assertIsNotNone(hm.last_hp_pct)
        assert hm.last_hp_pct is not None
        self.assertGreater(hm.last_hp_pct, 0.9)
        self.assertTrue(hm.last_hp_ok)

    def test_ocr_below_confidence_is_ignored(self):
        """A low-confidence read should be dropped (no latch)."""
        # Both reads at prob 0.10 — below default 0.3 floor.
        hm = _ocr_hm([(47900, 0.10), (47900, 0.10)], ocr_min_confidence=0.3)
        hm.update(0.0, self.frame, self.player, 1.0, None)
        hm.update(0.25, self.frame, self.player, 1.0, None)
        self.assertFalse(hm.max_hp_locked)

    def test_reset_match_clears_latch(self):
        hm = _ocr_hm([47900, 47900, 99999, 99999])
        hm.update(0.0, self.frame, self.player, 1.0, None)
        hm.update(0.25, self.frame, self.player, 1.0, None)
        self.assertTrue(hm.max_hp_locked)
        hm.reset_match()
        self.assertFalse(hm.max_hp_locked)
        self.assertEqual(hm.observed_max_hp, 0)
        self.assertIsNone(hm.hp_value)

    def test_respawn_short_circuits(self):
        hm = _ocr_hm([47900])
        ev = hm.update(0.0, self.frame, self.player, 1.0, lambda: True)
        self.assertIsNone(ev)
        self.assertEqual(hm.last_hp_status, "respawn")
        self.assertFalse(hm.max_hp_locked)

    def test_near_equal_reads_latch_to_max(self):
        """EasyOCR jitter within ~2% should still latch (legacy strict-eq stuck)."""
        hm = _ocr_hm([47800, 47900])
        hm.update(0.0, self.frame, self.player, 1.0, None)
        hm.update(0.25, self.frame, self.player, 1.0, None)
        self.assertTrue(hm.max_hp_locked)
        self.assertEqual(hm.observed_max_hp, 47900)

    def test_soft_latch_when_reads_drift(self):
        """If reads keep drifting > tolerance, soft-latch after grace period."""
        hm = _ocr_hm([42000, 47000, 51000, 48000, 49000, 49000])
        # Drive enough ticks past the 6.0s soft-latch threshold.
        for i, t in enumerate([0.0, 0.25, 0.5, 1.0, 6.5, 6.9]):
            hm.update(t, self.frame, self.player, 1.0, None)
        self.assertTrue(hm.max_hp_locked)
        # Soft latch picks the max value seen (51000), not the median.
        self.assertEqual(hm.observed_max_hp, 51000)


if __name__ == "__main__":
    unittest.main()
