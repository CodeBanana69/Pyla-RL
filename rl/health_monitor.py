"""Player HP bar reading (HSV fill ratio + optional OCR) and damage events."""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, List, Optional, Sequence, Tuple

import cv2
import numpy as np


@dataclass
class DamageEvent:
    """Emitted when HP bar percentage drops sharply vs. recent baseline."""

    time: float
    drop_pct: float  # approximate fractional drop (e.g. 0.02 = 2 points)


class HealthMonitor:
    """Tracks HP bar fill percentage from green vs red HSV pixels above the player box."""

    def __init__(
        self,
        *,
        band_offset_px: float = 8.0,
        band_height_px: float = 14.0,
        digit_band_extra_px: float = 28.0,
        min_total_pixels: int = 40,
        damage_drop_threshold: float = 0.015,
        prior_window_seconds: float = 0.4,
        history_seconds: float = 2.0,
        ocr_enabled: bool = True,
        ocr_interval_seconds: float = 0.5,
    ) -> None:
        self.band_offset_px = float(band_offset_px)
        self.band_height_px = float(band_height_px)
        self.digit_band_extra_px = float(digit_band_extra_px)
        self.min_total_pixels = int(min_total_pixels)
        self.damage_drop_threshold = float(damage_drop_threshold)
        self.prior_window_seconds = float(prior_window_seconds)
        self.history_seconds = float(history_seconds)
        self.ocr_enabled = bool(ocr_enabled)
        self.ocr_interval_seconds = float(ocr_interval_seconds)

        self._history: Deque[Tuple[float, Optional[float]]] = deque(maxlen=240)
        self._damage_events: Deque[DamageEvent] = deque(maxlen=32)
        self._last_ocr_time = 0.0

        self.last_hp_pct: Optional[float] = None
        self.last_hp_ok: bool = False
        self.hp_value: Optional[int] = None
        self.observed_max_hp: int = 0
        self.last_green_red: Tuple[int, int] = (0, 0)

    def reset_match(self) -> None:
        self._history.clear()
        self._damage_events.clear()
        self._last_ocr_time = 0.0
        self.last_hp_pct = None
        self.last_hp_ok = False
        self.hp_value = None
        self.observed_max_hp = 0
        self.last_green_red = (0, 0)

    @staticmethod
    def _count_green_red(hsv: np.ndarray) -> Tuple[int, int]:
        green = cv2.inRange(hsv, np.array((35, 80, 80), dtype=np.uint8), np.array((85, 255, 255), dtype=np.uint8))
        r1 = cv2.inRange(hsv, np.array((0, 80, 80), dtype=np.uint8), np.array((14, 255, 255), dtype=np.uint8))
        r2 = cv2.inRange(hsv, np.array((170, 80, 80), dtype=np.uint8), np.array((179, 255, 255), dtype=np.uint8))
        red = cv2.bitwise_or(r1, r2)
        return int(cv2.countNonZero(green)), int(cv2.countNonZero(red))

    def read_hp_band(
        self,
        frame_rgb: np.ndarray,
        player_box: Sequence[float],
        scale_factor: float,
    ) -> Tuple[Optional[float], bool, Tuple[int, int]]:
        """Return (hp_pct 0..1 or None, ok, (green_px, red_px))."""
        if frame_rgb is None or frame_rgb.size == 0 or len(player_box) < 4:
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
        band_top = int(y1 - off - bh)
        band_bot = int(y1 - off)
        band_top = max(0, band_top)
        band_bot = min(h, max(band_top + 2, band_bot))

        crop = frame_rgb[band_top:band_bot, bx1:bx2]
        if crop.size == 0:
            return None, False, (0, 0)
        hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
        g, r = self._count_green_red(hsv)
        total = g + r
        self.last_green_red = (g, r)
        if total < self.min_total_pixels:
            return None, False, (g, r)
        pct = float(g) / float(total)
        return pct, True, (g, r)

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
            return None
        if player_box is None or len(player_box) < 4:
            self.last_hp_ok = False
            return None

        hp_pct, ok, _gr = self.read_hp_band(frame_rgb, player_box, scale_factor)
        self.last_hp_pct = hp_pct
        self.last_hp_ok = ok

        if now - self._last_ocr_time >= self.ocr_interval_seconds:
            self._last_ocr_time = now
            ocr_val = self._ocr_hp_value(frame_rgb, player_box, scale_factor)
            if ocr_val is not None:
                self.hp_value = ocr_val
                self.observed_max_hp = max(self.observed_max_hp, ocr_val)

        emitted: Optional[DamageEvent] = None
        if ok and hp_pct is not None:
            prior_max: Optional[float] = None
            for t, p in self._history:
                dt = now - t
                if 1e-6 < dt <= self.prior_window_seconds and p is not None:
                    prior_max = p if prior_max is None else max(prior_max, p)

            self._history.append((now, hp_pct))

            cutoff = now - self.history_seconds
            while self._history and self._history[0][0] < cutoff:
                self._history.popleft()

            if prior_max is not None and hp_pct < prior_max - self.damage_drop_threshold:
                drop = float(prior_max - hp_pct)
                emitted = DamageEvent(time=now, drop_pct=drop)
                self._damage_events.append(emitted)

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
