"""Player HP bar reading (HSV fill ratio + optional OCR) and damage events."""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, List, Literal, Optional, Sequence, Tuple

import cv2
import numpy as np

HpStatus = Literal["ok", "insufficient_pixels", "occluded", "respawn", "inconsistent", "unknown"]


@dataclass
class DamageEvent:
    """Emitted when HP bar percentage drops sharply vs. recent baseline."""

    time: float
    drop_pct: float  # approximate fractional drop (e.g. 0.02 = 2 points)


class HealthMonitor:
    """Tracks HP bar fill percentage from HSV pixels above the player box."""

    def __init__(
        self,
        *,
        band_offset_px: float = 8.0,
        band_height_px: float = 14.0,
        search_height_px: float = 40.0,
        digit_band_extra_px: float = 28.0,
        min_total_pixels: int = 40,
        damage_drop_threshold: float = 0.015,
        prior_window_seconds: float = 0.4,
        history_seconds: float = 2.0,
        ocr_enabled: bool = True,
        ocr_interval_seconds: float = 0.5,
        yellow_enabled: bool = True,
        shield_enabled: bool = True,
        min_consecutive_drops: int = 2,
        ocr_max_relative_jump: float = 0.4,
        ocr_validate_against_hsv: bool = True,
    ) -> None:
        self.band_offset_px = float(band_offset_px)
        self.band_height_px = float(band_height_px)
        self.search_height_px = float(search_height_px)
        self.digit_band_extra_px = float(digit_band_extra_px)
        self.min_total_pixels = int(min_total_pixels)
        self.damage_drop_threshold = float(damage_drop_threshold)
        self.prior_window_seconds = float(prior_window_seconds)
        self.history_seconds = float(history_seconds)
        self.ocr_enabled = bool(ocr_enabled)
        self.ocr_interval_seconds = float(ocr_interval_seconds)
        self.yellow_enabled = bool(yellow_enabled)
        self.shield_enabled = bool(shield_enabled)
        self.min_consecutive_drops = max(1, int(min_consecutive_drops))
        self.ocr_max_relative_jump = float(ocr_max_relative_jump)
        self.ocr_validate_against_hsv = bool(ocr_validate_against_hsv)

        self._history: Deque[Tuple[float, Optional[float]]] = deque(maxlen=240)
        self._damage_events: Deque[DamageEvent] = deque(maxlen=64)
        self._last_ocr_time = 0.0
        self._pct_smooth: Deque[Optional[float]] = deque(maxlen=3)
        self._drop_streak = 0
        self._ocr_repeat_val: Optional[int] = None
        self._ocr_same_count = 0
        self._prior_ocr_value: Optional[int] = None

        self.last_hp_pct: Optional[float] = None
        self.last_hp_ok: bool = False
        self.last_hp_status: HpStatus = "unknown"
        self.hp_value: Optional[int] = None
        self.observed_max_hp: int = 0
        self.last_green_red: Tuple[int, int] = (0, 0)

    def reset_match(self) -> None:
        self._history.clear()
        self._damage_events.clear()
        self._last_ocr_time = 0.0
        self._pct_smooth.clear()
        self._drop_streak = 0
        self._ocr_repeat_val = None
        self._ocr_same_count = 0
        self._prior_ocr_value = None
        self.last_hp_pct = None
        self.last_hp_ok = False
        self.last_hp_status = "unknown"
        self.hp_value = None
        self.observed_max_hp = 0
        self.last_green_red = (0, 0)

    def _count_fill_pixels(self, hsv: np.ndarray) -> Tuple[int, int, int, int]:
        """Returns (green, yellow_orange, shield_cyan, red) pixel counts."""
        green = cv2.inRange(
            hsv, np.array((35, 80, 80), dtype=np.uint8), np.array((85, 255, 255), dtype=np.uint8)
        )
        r1 = cv2.inRange(
            hsv, np.array((0, 80, 80), dtype=np.uint8), np.array((14, 255, 255), dtype=np.uint8)
        )
        r2 = cv2.inRange(
            hsv, np.array((170, 80, 80), dtype=np.uint8), np.array((179, 255, 255), dtype=np.uint8)
        )
        red = cv2.bitwise_or(r1, r2)

        yellow = np.zeros_like(red)
        if self.yellow_enabled:
            yellow = cv2.inRange(
                hsv, np.array((15, 80, 80), dtype=np.uint8), np.array((34, 255, 255), dtype=np.uint8)
            )

        cyan = np.zeros_like(red)
        if self.shield_enabled:
            cyan = cv2.inRange(
                hsv, np.array((85, 60, 80), dtype=np.uint8), np.array((105, 255, 255), dtype=np.uint8)
            )

        return (
            int(cv2.countNonZero(green)),
            int(cv2.countNonZero(yellow)),
            int(cv2.countNonZero(cyan)),
            int(cv2.countNonZero(red)),
        )

    def _row_density(self, hsv_rows: np.ndarray) -> int:
        g, y, c, r = self._count_fill_pixels(hsv_rows)
        return g + y + c + r

    def read_hp_band(
        self,
        frame_rgb: np.ndarray,
        player_box: Sequence[float],
        scale_factor: float,
    ) -> Tuple[Optional[float], bool, Tuple[int, int]]:
        """Return (hp_pct 0..1 or None, ok, (alive_px, red_px))."""
        if frame_rgb is None or frame_rgb.size == 0 or len(player_box) < 4:
            self.last_hp_status = "unknown"
            return None, False, (0, 0)
        h, w = frame_rgb.shape[:2]
        sf = max(0.25, float(scale_factor))
        x1, y1, x2, y2 = map(float, player_box[:4])
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1

        bx1 = max(0, int(x1))
        bx2 = min(w, int(x2))
        off = max(2.0, self.band_offset_px * sf)
        bh = max(4.0, self.band_height_px * sf)
        search_h = max(bh, self.search_height_px * sf)

        band_bot = int(y1 - off)
        search_top = max(0, int(band_bot - search_h))
        search_bot = min(h, max(search_top + 2, band_bot))
        if search_bot <= search_top or bx2 <= bx1:
            self.last_hp_status = "insufficient_pixels"
            return None, False, (0, 0)

        search_strip = frame_rgb[search_top:search_bot, bx1:bx2]
        if search_strip.size == 0:
            self.last_hp_status = "insufficient_pixels"
            return None, False, (0, 0)

        hsv_full = cv2.cvtColor(search_strip, cv2.COLOR_RGB2HSV)
        nrow = hsv_full.shape[0]
        bh_i = max(2, int(round(bh)))
        best_start = 0
        best_score = -1
        if nrow >= bh_i:
            row_counts = np.zeros(nrow, dtype=np.int32)
            for ri in range(nrow):
                row_counts[ri] = self._row_density(hsv_full[ri : ri + 1, :, :])
            for start in range(0, nrow - bh_i + 1):
                slab = int(row_counts[start : start + bh_i].sum())
                if slab > best_score:
                    best_score = slab
                    best_start = start
        crop_hsv = hsv_full[best_start : best_start + min(bh_i, nrow), :, :]
        g, ye, cy, r = self._count_fill_pixels(crop_hsv)
        alive = g + ye + cy
        total = alive + r
        self.last_green_red = (alive, r)

        if total < self.min_total_pixels:
            self.last_hp_status = "insufficient_pixels"
            return None, False, (alive, r)

        pct = float(alive) / float(total)
        self.last_hp_status = "ok"
        return pct, True, (alive, r)

    def _ocr_hp_value(self, frame_rgb: np.ndarray, player_box: Sequence[float], scale_factor: float) -> Optional[int]:
        if not self.ocr_enabled:
            return None
        h, w = frame_rgb.shape[:2]
        sf = max(0.25, float(scale_factor))
        x1, y1, x2, y2 = map(float, player_box[:4])
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        bx1 = max(0, int(x1))
        bx2 = min(w, int(x2))
        extra = max(8.0, self.digit_band_extra_px * sf)
        off = max(2.0, self.band_offset_px * sf)
        bh = max(4.0, self.band_height_px * sf)
        digit_top = int(y1 - off - bh - extra)
        digit_bot = int(y1 - off + 4)
        digit_top = max(0, digit_top)
        digit_bot = min(h, max(digit_top + 4, digit_bot))
        crop = frame_rgb[digit_top:digit_bot, bx1:bx2]
        if crop.size == 0 or crop.shape[0] < 4 or crop.shape[1] < 8:
            return None
        try:
            from utils import get_ocr_reader

            reader = get_ocr_reader()
            results = reader.readtext(crop)
        except Exception:
            return None
        best_val: Optional[int] = None
        best_prob = 0.0
        for _bbox, text, prob in results:
            digits = re.sub(r"[^\d]", "", str(text))
            if not digits:
                continue
            try:
                val = int(digits)
            except ValueError:
                continue
            if prob > best_prob and val > 0:
                best_prob = prob
                best_val = val
        return best_val

    def _median_smooth_pct(self) -> Optional[float]:
        vals = [p for p in self._pct_smooth if p is not None]
        if not vals:
            return None
        return float(np.median(np.asarray(vals, dtype=np.float64)))

    def update(
        self,
        now: float,
        frame_rgb: np.ndarray,
        player_box: Optional[Sequence[float]],
        scale_factor: float,
        respawning_check: Optional[Callable[[], bool]] = None,
    ) -> Optional[DamageEvent]:
        """Append HP reading; emit DamageEvent on sharp drop. Returns latest event if any this frame."""
        if respawning_check and respawning_check():
            self.last_hp_ok = False
            self.last_hp_status = "respawn"
            return None
        if player_box is None or len(player_box) < 4:
            self.last_hp_ok = False
            self.last_hp_status = "unknown"
            return None

        hp_pct_raw, ok, _gr = self.read_hp_band(frame_rgb, player_box, scale_factor)
        self._pct_smooth.append(hp_pct_raw if ok else None)
        hp_pct_med = self._median_smooth_pct()
        self.last_hp_pct = hp_pct_med if hp_pct_med is not None else hp_pct_raw
        self.last_hp_ok = ok and hp_pct_med is not None

        if now - self._last_ocr_time >= self.ocr_interval_seconds:
            self._last_ocr_time = now
            ocr_raw = self._ocr_hp_value(frame_rgb, player_box, scale_factor)
            if ocr_raw is not None:
                if self.observed_max_hp > 0 and ocr_raw > int(self.observed_max_hp * 1.2 + 0.5):
                    ocr_raw = None
                if ocr_raw is not None and self._prior_ocr_value is not None:
                    base = max(1, int(self._prior_ocr_value))
                    if abs(ocr_raw - self._prior_ocr_value) / float(base) > self.ocr_max_relative_jump:
                        ocr_raw = None
                if ocr_raw is not None:
                    if ocr_raw == self._ocr_repeat_val:
                        self._ocr_same_count += 1
                    else:
                        self._ocr_repeat_val = ocr_raw
                        self._ocr_same_count = 1
                    if self._ocr_same_count >= 2:
                        self.observed_max_hp = max(self.observed_max_hp, ocr_raw)
                    self.hp_value = ocr_raw
                    self._prior_ocr_value = ocr_raw
                    if (
                        self.ocr_validate_against_hsv
                        and hp_pct_med is not None
                        and self.observed_max_hp > 0
                    ):
                        ocr_frac = float(ocr_raw) / float(max(1, self.observed_max_hp))
                        if abs(ocr_frac - float(hp_pct_med)) > 0.25:
                            self.last_hp_status = "inconsistent"
                        elif ok:
                            self.last_hp_status = "ok"
                    elif ok:
                        self.last_hp_status = "ok"

        emitted: Optional[DamageEvent] = None
        hp_use = hp_pct_med if hp_pct_med is not None else hp_pct_raw
        if ok and hp_use is not None:
            prior_max: Optional[float] = None
            for t, p in self._history:
                dt = now - t
                if 1e-6 < dt <= self.prior_window_seconds and p is not None:
                    prior_max = p if prior_max is None else max(prior_max, p)

            self._history.append((now, hp_use))

            cutoff = now - self.history_seconds
            while self._history and self._history[0][0] < cutoff:
                self._history.popleft()

            dropping = (
                prior_max is not None
                and hp_use < prior_max - self.damage_drop_threshold
            )
            if dropping:
                self._drop_streak += 1
            else:
                self._drop_streak = 0

            if (
                prior_max is not None
                and hp_use < prior_max - self.damage_drop_threshold
                and self._drop_streak >= self.min_consecutive_drops
            ):
                drop = float(prior_max - hp_use)
                emitted = DamageEvent(time=now, drop_pct=drop)
                self._damage_events.append(emitted)
                self._drop_streak = 0

        return emitted

    def recent_damage_event(self, now: float, lookback_seconds: float) -> Optional[DamageEvent]:
        """Most recent damage event within ``lookback_seconds``."""
        lb = float(lookback_seconds)
        best: Optional[DamageEvent] = None
        for ev in reversed(self._damage_events):
            if now - ev.time <= lb:
                best = ev
                break
        return best

    @property
    def hp_value_pct(self) -> Optional[float]:
        if self.hp_value is None or self.observed_max_hp <= 0:
            return None
        return float(self.hp_value) / float(self.observed_max_hp)
