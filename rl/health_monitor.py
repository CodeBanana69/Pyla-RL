"""Player HP detection (OCR-first, HSV fallback) and damage events.

OCR-first design
----------------
EasyOCR is the source of truth. At match start, two stable identical reads of
the numeric HP latch ``max_hp``. From then on every accepted read produces
``hp_value`` / ``hp_value_pct`` and feeds the per-frame damage detector. HSV
fill ratio is still computed cheaply, but it is only used as a fallback when
OCR has not yet produced a value (e.g. during the first frames of a match or
when the digit crop is unreadable).

Performance
-----------
The OCR call is throttled to a configurable cadence (``ocr_poll_hz``, default
5 Hz). When CUDA is not available, the OCR pass is dispatched to a single
background worker thread so the live game loop never blocks waiting for
EasyOCR. The main loop submits a fresh job at most once per cadence step and
reads whatever result is currently sitting in the mailbox; stale data by one
frame is fine because HP changes slowly compared to projectiles.
"""

from __future__ import annotations

import re
import threading
import time as _time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, List, Literal, Optional, Sequence, Tuple

import cv2
import numpy as np

HpStatus = Literal[
    "ok",
    "insufficient_pixels",
    "occluded",
    "respawn",
    "inconsistent",
    "ocr_pending",
    "unknown",
]


@dataclass
class DamageEvent:
    """Emitted when HP drops sharply vs. recent baseline.

    ``drop_pct`` is a fractional drop (e.g. 0.17 ≈ 17% of max HP).
    """

    time: float
    drop_pct: float


@dataclass
class _OcrJob:
    crop: np.ndarray
    submitted_at: float


@dataclass
class _OcrResult:
    value: Optional[int]
    prob: float
    done_at: float


class _OcrWorker:
    """Single-slot background OCR worker used when CUDA is not available."""

    def __init__(self, run_inline_fn: Callable[[np.ndarray], Tuple[Optional[int], float]]):
        self._run = run_inline_fn
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._pending: Optional[_OcrJob] = None
        self._latest: Optional[_OcrResult] = None
        self._stop = False
        self._thread = threading.Thread(target=self._loop, name="HpOcrWorker", daemon=True)
        self._thread.start()

    def submit(self, crop: np.ndarray, now: float) -> None:
        with self._cv:
            # Always overwrite — only the most recent crop matters.
            self._pending = _OcrJob(crop=crop, submitted_at=now)
            self._cv.notify()

    def latest(self) -> Optional[_OcrResult]:
        with self._lock:
            return self._latest

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify_all()

    def _loop(self) -> None:
        while True:
            with self._cv:
                while self._pending is None and not self._stop:
                    self._cv.wait()
                if self._stop:
                    return
                job = self._pending
                self._pending = None
            if job is None:
                continue
            try:
                val, prob = self._run(job.crop)
            except Exception:
                val, prob = None, 0.0
            with self._lock:
                self._latest = _OcrResult(value=val, prob=prob, done_at=_time.time())


def format_power_cube_bonus_suffix(max_hp: int, cubes: int, hp_each: int) -> str:
    """Human-readable cube bonus for terminal logs (Showdown)."""
    bonus = int(cubes) * int(hp_each)
    base = int(max_hp) - bonus
    return f" cubes={int(cubes)} base≈{base} (+{bonus} from cubes)"


def _cuda_available() -> bool:
    try:  # torch is an optional dep for the OCR path
        import torch  # type: ignore

        return bool(torch.cuda.is_available())
    except Exception:
        return False


class HealthMonitor:
    """OCR-first HP tracker with HSV fallback and damage event emission."""

    def __init__(
        self,
        *,
        # ── HP-bar / HSV geometry (kept for fallback + visual debug) ──────────
        band_offset_px: float = 8.0,
        band_height_px: float = 14.0,
        search_height_px: float = 40.0,
        band_horizontal_pad_px: float = 26.0,
        band_width_expand_frac: float = 0.22,
        digit_band_extra_px: float = 28.0,
        min_total_pixels: int = 40,
        hsv_min_saturation: int = 52,
        hsv_min_value: int = 52,
        hsv_relaxed_min_saturation: int = 38,
        hsv_relaxed_min_value: int = 38,
        damage_drop_threshold: float = 0.015,
        prior_window_seconds: float = 0.4,
        history_seconds: float = 2.0,
        yellow_enabled: bool = True,
        shield_enabled: bool = True,
        min_consecutive_drops: int = 2,
        # ── Legacy OCR knobs (kept so old configs don't error) ───────────────
        ocr_enabled: bool = True,
        ocr_interval_seconds: float = 0.5,
        ocr_max_relative_jump: float = 0.4,
        ocr_validate_against_hsv: bool = True,
        # ── New OCR-first knobs ──────────────────────────────────────────────
        ocr_primary: bool = True,
        ocr_poll_hz: float = 5.0,
        ocr_run_in_thread: str = "auto",         # "auto" | "yes" | "no"
        ocr_full_hp_lock_repeats: int = 2,
        ocr_min_confidence: float = 0.25,
        ocr_log_terminal: bool = True,
        ocr_damage_drop_min: int = 1,
        hsv_fallback_enabled: bool = True,
        ocr_reader: Optional[Any] = None,        # injected (tests / custom factory)
        # Showdown Power Cube count (OCR strip above numeric HP; +hp_each max HP per cube)
        ocr_power_cubes: str = "auto",           # auto | yes | no
        power_cube_hp_each: int = 400,
        ocr_cube_poll_hz: float = 1.0,
        power_cube_max_hp_gate: int = 3500,    # auto: only OCR cubes when max_hp >= this
        power_cube_strip_px: float = 34.0,     # vertical height of strip above HP digits
    ) -> None:
        # HSV/geometry knobs
        self.band_offset_px = float(band_offset_px)
        self.band_height_px = float(band_height_px)
        self.search_height_px = float(search_height_px)
        self.band_horizontal_pad_px = float(band_horizontal_pad_px)
        self.band_width_expand_frac = float(band_width_expand_frac)
        self.digit_band_extra_px = float(digit_band_extra_px)
        self.min_total_pixels = int(min_total_pixels)
        self.hsv_min_saturation = int(np.clip(hsv_min_saturation, 1, 255))
        self.hsv_min_value = int(np.clip(hsv_min_value, 1, 255))
        self.hsv_relaxed_min_saturation = int(np.clip(hsv_relaxed_min_saturation, 1, 255))
        self.hsv_relaxed_min_value = int(np.clip(hsv_relaxed_min_value, 1, 255))
        self.damage_drop_threshold = float(damage_drop_threshold)
        self.prior_window_seconds = float(prior_window_seconds)
        self.history_seconds = float(history_seconds)
        self.yellow_enabled = bool(yellow_enabled)
        self.shield_enabled = bool(shield_enabled)
        self.min_consecutive_drops = max(1, int(min_consecutive_drops))

        # Legacy OCR knobs
        self.ocr_enabled = bool(ocr_enabled)
        self.ocr_interval_seconds = float(ocr_interval_seconds)
        self.ocr_max_relative_jump = float(ocr_max_relative_jump)
        self.ocr_validate_against_hsv = bool(ocr_validate_against_hsv)

        # OCR-first knobs
        self.ocr_primary = bool(ocr_primary)
        # Honor legacy interval if user explicitly disables the new cadence.
        if float(ocr_poll_hz) <= 0.0 and self.ocr_interval_seconds > 0:
            ocr_poll_hz = 1.0 / max(0.05, self.ocr_interval_seconds)
        self.ocr_poll_hz = max(0.5, float(ocr_poll_hz))
        self.ocr_full_hp_lock_repeats = max(1, int(ocr_full_hp_lock_repeats))
        self.ocr_min_confidence = float(ocr_min_confidence)
        self.ocr_log_terminal = bool(ocr_log_terminal)
        self.ocr_damage_drop_min = max(1, int(ocr_damage_drop_min))
        self.hsv_fallback_enabled = bool(hsv_fallback_enabled)
        self._ocr_reader_override = ocr_reader

        pc = str(ocr_power_cubes).strip().lower()
        if pc in ("yes", "true", "1"):
            self._ocr_power_cubes_mode = "yes"
        elif pc in ("no", "false", "0"):
            self._ocr_power_cubes_mode = "no"
        else:
            self._ocr_power_cubes_mode = "auto"
        self.power_cube_hp_each = max(1, int(power_cube_hp_each))
        self.ocr_cube_poll_hz = max(0.2, float(ocr_cube_poll_hz))
        self.power_cube_max_hp_gate = max(500, int(power_cube_max_hp_gate))
        self.power_cube_strip_px = float(power_cube_strip_px)

        # Threading decision
        choice = str(ocr_run_in_thread).strip().lower()
        if choice == "yes":
            use_thread = True
        elif choice == "no":
            use_thread = False
        else:  # "auto"
            use_thread = not _cuda_available()
        self._use_thread = bool(use_thread) and ocr_reader is None

        # State
        self._history: Deque[Tuple[float, Optional[float]]] = deque(maxlen=240)
        self._damage_events: Deque[DamageEvent] = deque(maxlen=64)
        self._pct_smooth: Deque[Optional[float]] = deque(maxlen=3)
        self._drop_streak = 0

        # OCR runtime state
        self._last_ocr_submit_t: float = 0.0
        self._last_ocr_result_consumed_at: float = 0.0
        self._latch_repeat_val: Optional[int] = None
        self._latch_repeat_count: int = 0
        self._max_hp_locked: bool = False
        self._prev_hp_value: Optional[int] = None
        self._last_log_value: Optional[int] = None
        self._worker: Optional[_OcrWorker] = None
        self._first_after_reset: bool = True
        # Pending diagnostics + soft-latch state
        self._pending_started_at: Optional[float] = None
        self._pending_last_log_at: float = 0.0
        self._pending_read_count: int = 0
        self._pending_max_seen: int = 0
        # After this many seconds in "ocr_pending" with at least N reads, latch to
        # the largest read so far so RL stops fighting the visual-debug overlay.
        self._soft_latch_after_seconds: float = 6.0
        self._soft_latch_min_reads: int = 3
        self._last_cube_ocr_t: float = 0.0

        # Public state (also read by RL / visual debug)
        self.last_hp_pct: Optional[float] = None
        self.last_hp_ok: bool = False
        self.last_hp_status: HpStatus = "unknown"
        self.hp_value: Optional[int] = None
        self.observed_max_hp: int = 0
        self.last_green_red: Tuple[int, int] = (0, 0)
        self.power_cube_count: Optional[int] = None

    # ──────────────────────────────────────────────────────────────────────
    # Match lifecycle
    # ──────────────────────────────────────────────────────────────────────
    def reset_match(self) -> None:
        self._history.clear()
        self._damage_events.clear()
        self._pct_smooth.clear()
        self._drop_streak = 0
        self._last_ocr_submit_t = 0.0
        self._last_ocr_result_consumed_at = 0.0
        self._latch_repeat_val = None
        self._latch_repeat_count = 0
        self._max_hp_locked = False
        self._prev_hp_value = None
        self._last_log_value = None
        self._first_after_reset = True
        self._pending_started_at = None
        self._pending_last_log_at = 0.0
        self._pending_read_count = 0
        self._pending_max_seen = 0
        self.last_hp_pct = None
        self.last_hp_ok = False
        self.last_hp_status = "unknown"
        self.hp_value = None
        self.observed_max_hp = 0
        self.last_green_red = (0, 0)
        self.power_cube_count = None
        self._last_cube_ocr_t = 0.0

    def close(self) -> None:
        if self._worker is not None:
            try:
                self._worker.stop()
            except Exception:
                pass
            self._worker = None

    # ──────────────────────────────────────────────────────────────────────
    # HSV pipeline (fallback only)
    # ──────────────────────────────────────────────────────────────────────
    def _horizontal_crop_x(self, x1: float, x2: float, w: int, sf: float) -> Tuple[int, int]:
        if x2 < x1:
            x1, x2 = x2, x1
        half_w = (x2 - x1) * 0.5
        cx = (x1 + x2) * 0.5
        extra = max(self.band_horizontal_pad_px * sf, half_w * self.band_width_expand_frac)
        bx1 = max(0, int(round(cx - half_w - extra)))
        bx2 = min(int(w), int(round(cx + half_w + extra)))
        return bx1, bx2

    def _hp_digit_band_bounds(
        self,
        frame_rgb: np.ndarray,
        player_box: Sequence[float],
        scale_factor: float,
    ) -> Optional[Tuple[int, int, int, int, int, int]]:
        """(h, w, bx1, bx2, digit_top, digit_bot) for HP number strip above the bar."""
        if frame_rgb is None or frame_rgb.size == 0 or len(player_box) < 4:
            return None
        h, w = frame_rgb.shape[:2]
        sf = max(0.25, float(scale_factor))
        x1, y1, x2, y2 = map(float, player_box[:4])
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        bx1, bx2 = self._horizontal_crop_x(x1, x2, w, sf)
        extra = max(8.0, self.digit_band_extra_px * sf)
        off = max(2.0, self.band_offset_px * sf)
        bh = max(4.0, self.band_height_px * sf)
        digit_top = max(0, int(y1 - off - bh - extra))
        digit_bot = min(h, max(digit_top + 4, int(y1 - off + 4)))
        if digit_bot - digit_top < 6 or bx2 - bx1 < 10:
            return None
        return h, w, bx1, bx2, digit_top, digit_bot

    def _count_fill_pixels(
        self, hsv: np.ndarray, *, relaxed: bool = False
    ) -> Tuple[int, int, int, int]:
        ms = self.hsv_relaxed_min_saturation if relaxed else self.hsv_min_saturation
        mv = self.hsv_relaxed_min_value if relaxed else self.hsv_min_value
        cyan_ms = max(40, ms - 8) if not relaxed else max(32, ms - 10)
        green = cv2.inRange(
            hsv,
            np.array((35, ms, mv), dtype=np.uint8),
            np.array((85, 255, 255), dtype=np.uint8),
        )
        r1 = cv2.inRange(
            hsv,
            np.array((0, ms, mv), dtype=np.uint8),
            np.array((14, 255, 255), dtype=np.uint8),
        )
        r2 = cv2.inRange(
            hsv,
            np.array((170, ms, mv), dtype=np.uint8),
            np.array((179, 255, 255), dtype=np.uint8),
        )
        red = cv2.bitwise_or(r1, r2)
        yellow = np.zeros_like(red)
        if self.yellow_enabled:
            yellow = cv2.inRange(
                hsv,
                np.array((15, ms, mv), dtype=np.uint8),
                np.array((34, 255, 255), dtype=np.uint8),
            )
        cyan = np.zeros_like(red)
        if self.shield_enabled:
            cyan = cv2.inRange(
                hsv,
                np.array((85, cyan_ms, mv), dtype=np.uint8),
                np.array((105, 255, 255), dtype=np.uint8),
            )
        return (
            int(cv2.countNonZero(green)),
            int(cv2.countNonZero(yellow)),
            int(cv2.countNonZero(cyan)),
            int(cv2.countNonZero(red)),
        )

    def _count_fill_pixels_ui_rescue(self, hsv: np.ndarray) -> Tuple[int, int, int, int]:
        ms = max(14, int(self.hsv_relaxed_min_saturation) - 22)
        mv = max(14, int(self.hsv_relaxed_min_value) - 25)
        green = cv2.inRange(
            hsv,
            np.array((22, ms, mv), dtype=np.uint8),
            np.array((92, 255, 255), dtype=np.uint8),
        )
        r1 = cv2.inRange(
            hsv,
            np.array((0, ms, mv), dtype=np.uint8),
            np.array((16, 255, 255), dtype=np.uint8),
        )
        r2 = cv2.inRange(
            hsv,
            np.array((168, ms, mv), dtype=np.uint8),
            np.array((179, 255, 255), dtype=np.uint8),
        )
        red = cv2.bitwise_or(r1, r2)
        yellow = np.zeros_like(red)
        if self.yellow_enabled:
            yellow = cv2.inRange(
                hsv,
                np.array((12, ms, mv), dtype=np.uint8),
                np.array((34, 255, 255), dtype=np.uint8),
            )
        cyan = np.zeros_like(red)
        if self.shield_enabled:
            cyan_ms = max(26, ms - 10)
            cyan = cv2.inRange(
                hsv,
                np.array((80, cyan_ms, mv), dtype=np.uint8),
                np.array((108, 255, 255), dtype=np.uint8),
            )
        return (
            int(cv2.countNonZero(green)),
            int(cv2.countNonZero(yellow)),
            int(cv2.countNonZero(cyan)),
            int(cv2.countNonZero(red)),
        )

    def _row_density(self, hsv_rows: np.ndarray, *, relaxed: bool = False) -> int:
        g, y, c, r = self._count_fill_pixels(hsv_rows, relaxed=relaxed)
        return g + y + c + r

    def read_hp_band(
        self,
        frame_rgb: np.ndarray,
        player_box: Sequence[float],
        scale_factor: float,
    ) -> Tuple[Optional[float], bool, Tuple[int, int]]:
        """HSV fill ratio (0..1). Kept for fallback + visual debug."""
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
        bx1, bx2 = self._horizontal_crop_x(x1, x2, w, sf)
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
            if int(row_counts.max()) <= 0:
                for ri in range(nrow):
                    row_counts[ri] = self._row_density(hsv_full[ri : ri + 1, :, :], relaxed=True)
            for start in range(0, nrow - bh_i + 1):
                slab = int(row_counts[start : start + bh_i].sum())
                if slab > best_score:
                    best_score = slab
                    best_start = start
        crop_hsv = hsv_full[best_start : best_start + min(bh_i, nrow), :, :]
        crop_rows = min(bh_i, nrow)
        crop_cols = max(1, int(crop_hsv.shape[1]))
        crop_area = max(1, crop_rows * crop_cols)
        min_need = max(8, min(self.min_total_pixels, max(12, int(crop_area * 0.017))))
        g, ye, cy, r = self._count_fill_pixels(crop_hsv)
        alive = g + ye + cy
        total = alive + r
        if total < min_need:
            g2, ye2, cy2, r2 = self._count_fill_pixels(crop_hsv, relaxed=True)
            alive2 = g2 + ye2 + cy2
            total2 = alive2 + r2
            if total2 >= min_need:
                g, ye, cy, r = g2, ye2, cy2, r2
                alive, total = alive2, total2
        if total < min_need:
            g3, ye3, cy3, r3 = self._count_fill_pixels_ui_rescue(crop_hsv)
            alive3 = g3 + ye3 + cy3
            total3 = alive3 + r3
            if total3 >= min_need:
                g, ye, cy, r = g3, ye3, cy3, r3
                alive, total = alive3, total3
        self.last_green_red = (alive, r)
        if total < min_need:
            self.last_hp_status = "insufficient_pixels"
            return None, False, (alive, r)
        pct = float(alive) / float(total)
        self.last_hp_status = "ok"
        return pct, True, (alive, r)

    # ──────────────────────────────────────────────────────────────────────
    # OCR preprocessing (small HUD digits)
    # ──────────────────────────────────────────────────────────────────────
    def _preprocess_for_ocr(self, crop_rgb: np.ndarray) -> Optional[np.ndarray]:
        """Bilateral denoise → 4× upscale → unsharp → Otsu binarize → morph open → pad.

        Produces dark digits on light background when possible. Falls back to the
        legacy CLAHE + 2× path if anything fails so degenerate crops still return something.
        """
        if crop_rgb is None or crop_rgb.size == 0:
            return None
        try:
            gray = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY)
            gray = cv2.bilateralFilter(gray, d=5, sigmaColor=35, sigmaSpace=35)
            rh, rw = int(gray.shape[0]), int(gray.shape[1])
            up = cv2.resize(
                gray, (rw * 4, rh * 4), interpolation=cv2.INTER_CUBIC
            )
            blur = cv2.GaussianBlur(up, (0, 0), 1.0)
            sharpened = cv2.addWeighted(up, 1.5, blur, -0.5, 0.0)

            mu = float(np.mean(sharpened))
            if mu < 128.0:
                thresh_kind = cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU
            else:
                thresh_kind = cv2.THRESH_BINARY | cv2.THRESH_OTSU
            _, binary = cv2.threshold(sharpened, 0, 255, thresh_kind)

            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
            bordered = cv2.copyMakeBorder(
                opened,
                top=16,
                bottom=16,
                left=16,
                right=16,
                borderType=cv2.BORDER_CONSTANT,
                value=255,
            )
            return bordered
        except Exception:
            try:
                gray = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
                gray = clahe.apply(gray)
                return cv2.resize(
                    gray,
                    (gray.shape[1] * 2, gray.shape[0] * 2),
                    interpolation=cv2.INTER_CUBIC,
                )
            except Exception:
                return None

    # ──────────────────────────────────────────────────────────────────────
    # OCR pipeline (primary)
    # ──────────────────────────────────────────────────────────────────────
    def _build_digit_crop(
        self,
        frame_rgb: np.ndarray,
        player_box: Sequence[float],
        scale_factor: float,
    ) -> Optional[np.ndarray]:
        """Tiny grayscale crop above the player's HP bar, upscaled for OCR."""
        b = self._hp_digit_band_bounds(frame_rgb, player_box, scale_factor)
        if b is None:
            return None
        _h, _w, bx1, bx2, digit_top, digit_bot = b
        crop = frame_rgb[digit_top:digit_bot, bx1:bx2]
        if crop.size == 0:
            return None
        return self._preprocess_for_ocr(crop)

    def _build_power_cube_count_crop(
        self,
        frame_rgb: np.ndarray,
        player_box: Sequence[float],
        scale_factor: float,
    ) -> Optional[np.ndarray]:
        """Strip above numeric HP (Showdown Power Cube count). Same width as HP digits."""
        b = self._hp_digit_band_bounds(frame_rgb, player_box, scale_factor)
        if b is None:
            return None
        _h, _w, bx1, bx2, digit_top, _digit_bot = b
        sf = max(0.25, float(scale_factor))
        strip = max(14.0, self.power_cube_strip_px * sf)
        cube_bot = max(0, digit_top - 1)
        cube_top = max(0, int(cube_bot - strip))
        if cube_bot <= cube_top or bx2 - bx1 < 10:
            return None
        crop = frame_rgb[cube_top:cube_bot, bx1:bx2]
        if crop.size == 0:
            return None
        return self._preprocess_for_ocr(crop)

    def _power_cubes_ocr_enabled(self) -> bool:
        if self._ocr_power_cubes_mode == "no":
            return False
        if self._ocr_power_cubes_mode == "yes":
            return bool(self.ocr_enabled and self.ocr_primary)
        # auto
        return bool(
            self.ocr_enabled
            and self.ocr_primary
            and self._max_hp_locked
            and int(self.observed_max_hp) >= int(self.power_cube_max_hp_gate)
        )

    def _maybe_update_power_cube_count(
        self,
        now: float,
        frame_rgb: np.ndarray,
        player_box: Sequence[float],
        scale_factor: float,
    ) -> None:
        if not self._power_cubes_ocr_enabled():
            return
        period = 1.0 / self.ocr_cube_poll_hz
        if (now - self._last_cube_ocr_t) < period:
            return
        self._last_cube_ocr_t = now
        crop = self._build_power_cube_count_crop(frame_rgb, player_box, scale_factor)
        if crop is None:
            return
        val, prob = self._run_ocr_inline(crop)
        if val is None:
            return
        min_conf = max(0.12, float(self.ocr_min_confidence) * 0.85)
        if prob < min_conf:
            return
        cubes = int(val)
        if cubes < 1 or cubes > 150:
            return
        full = int(self.observed_max_hp)
        bonus = cubes * int(self.power_cube_hp_each)
        if bonus >= full - 200:
            return
        self.power_cube_count = cubes

    def _cube_suffix_for_log(self) -> str:
        if self.power_cube_count is None or not self._max_hp_locked:
            return ""
        full = int(self.observed_max_hp)
        if full <= 0:
            return ""
        return " " + format_power_cube_bonus_suffix(
            full, int(self.power_cube_count), int(self.power_cube_hp_each)
        )

    def _get_reader(self) -> Optional[Any]:
        if self._ocr_reader_override is not None:
            return self._ocr_reader_override
        try:
            from utils import get_ocr_reader

            return get_ocr_reader()
        except Exception:
            return None

    def _run_ocr_inline(self, crop: np.ndarray) -> Tuple[Optional[int], float]:
        """Synchronous OCR call. Returns (best_int_value, best_prob)."""
        reader = self._get_reader()
        if reader is None:
            return None, 0.0
        _ocr_kw = dict(
            allowlist="0123456789",
            paragraph=False,
            detail=1,
            mag_ratio=2.0,
            text_threshold=0.5,
            low_text=0.3,
            link_threshold=0.3,
            width_ths=0.7,
            contrast_ths=0.05,
            adjust_contrast=0.7,
        )
        try:
            results = reader.readtext(crop, **_ocr_kw)
        except TypeError:
            # Narrower kwargs (some EasyOCR / stub versions omit detector tuning keys).
            try:
                results = reader.readtext(
                    crop,
                    allowlist=_ocr_kw["allowlist"],
                    paragraph=_ocr_kw["paragraph"],
                    detail=_ocr_kw["detail"],
                )
            except TypeError:
                try:
                    results = reader.readtext(crop)
                except Exception:
                    return None, 0.0
            except Exception:
                return None, 0.0
        except Exception:
            return None, 0.0
        best_val: Optional[int] = None
        best_prob = 0.0
        for item in results or []:
            try:
                _bbox, text, prob = item
            except (TypeError, ValueError):
                continue
            digits = re.sub(r"[^\d]", "", str(text))
            if not digits:
                continue
            try:
                val = int(digits)
            except ValueError:
                continue
            if val <= 0:
                continue
            if float(prob) > best_prob:
                best_prob = float(prob)
                best_val = val
        return best_val, best_prob

    def _submit_or_read_ocr(
        self,
        now: float,
        frame_rgb: np.ndarray,
        player_box: Sequence[float],
        scale_factor: float,
    ) -> Optional[Tuple[int, float]]:
        """Returns a *newly available* (value, prob) reading or None.

        Honors the cadence gate (``ocr_poll_hz``). The very first call after
        ``reset_match`` always runs to seed ``max_hp`` quickly.
        """
        if not self.ocr_primary or not self.ocr_enabled:
            return None
        period = 1.0 / max(0.5, self.ocr_poll_hz)
        force_now = self._first_after_reset
        if not force_now and (now - self._last_ocr_submit_t) < period:
            # Still inside cadence window — surface any new threaded result.
            if self._worker is not None:
                res = self._worker.latest()
                if res is not None and res.done_at > self._last_ocr_result_consumed_at:
                    self._last_ocr_result_consumed_at = res.done_at
                    if res.value is not None and res.prob >= self.ocr_min_confidence:
                        return res.value, res.prob
            return None

        crop = self._build_digit_crop(frame_rgb, player_box, scale_factor)
        self._last_ocr_submit_t = now
        self._first_after_reset = False
        if crop is None:
            return None

        if self._use_thread:
            if self._worker is None:
                self._worker = _OcrWorker(self._run_ocr_inline)
            self._worker.submit(crop, now)
            res = self._worker.latest()
            if res is not None and res.done_at > self._last_ocr_result_consumed_at:
                self._last_ocr_result_consumed_at = res.done_at
                if res.value is not None and res.prob >= self.ocr_min_confidence:
                    return res.value, res.prob
            return None

        val, prob = self._run_ocr_inline(crop)
        if val is None or prob < self.ocr_min_confidence:
            return None
        return val, prob

    def _try_latch_max_hp(self, val: int) -> None:
        """Latch ``max_hp`` on N near-equal reads (tolerance ~2%).

        Exact integer equality is too strict — EasyOCR on small HP digits jitters
        by a few HP between frames (e.g. 47900 / 47800 / 47901). We accept reads
        within ~2% (or ±50 HP, whichever is larger) and latch to the maximum
        seen, which mirrors how the HUD shows full HP at match start.
        """
        if self._max_hp_locked:
            return
        prev = self._latch_repeat_val
        if prev is not None:
            tolerance = max(50, int(prev * 0.02))
            if abs(int(val) - int(prev)) <= tolerance:
                self._latch_repeat_count += 1
                self._latch_repeat_val = max(int(prev), int(val))
            else:
                self._latch_repeat_val = int(val)
                self._latch_repeat_count = 1
        else:
            self._latch_repeat_val = int(val)
            self._latch_repeat_count = 1

        if self._latch_repeat_count >= self.ocr_full_hp_lock_repeats:
            self.observed_max_hp = int(self._latch_repeat_val)
            self._max_hp_locked = True
            if self.ocr_log_terminal:
                line = f"[HP] match start full_hp={self.observed_max_hp}{self._cube_suffix_for_log()}"
                print(line)

    def _maybe_soft_latch_max_hp(self, now: float) -> None:
        """Last-resort latch if OCR keeps drifting but values are plausible."""
        if self._max_hp_locked or self._pending_started_at is None:
            return
        if self._pending_read_count < self._soft_latch_min_reads:
            return
        if (now - self._pending_started_at) < self._soft_latch_after_seconds:
            return
        if self._pending_max_seen <= 0:
            return
        self.observed_max_hp = int(self._pending_max_seen)
        self._max_hp_locked = True
        if self.ocr_log_terminal:
            print(
                "[HP] soft-latch full_hp="
                f"{self.observed_max_hp} (after {self._pending_read_count} OCR reads;"
                " values were not stable enough for hard latch)"
                f"{self._cube_suffix_for_log()}"
            )

    def _log_pending_diag(self, now: float, ocr_val: Optional[int]) -> None:
        if not self.ocr_log_terminal:
            return
        if (now - self._pending_last_log_at) < 3.0:
            return
        self._pending_last_log_at = now
        pending_for = (
            now - self._pending_started_at if self._pending_started_at else 0.0
        )
        cur = ocr_val if ocr_val is not None else self.hp_value
        print(
            "[HP] ocr_pending t="
            f"{pending_for:.1f}s reads={self._pending_read_count}"
            f" latest={cur} repeat_val={self._latch_repeat_val}"
            f"x{self._latch_repeat_count} max_seen={self._pending_max_seen}"
        )

    def _log_terminal(self, cur: int) -> None:
        if not self.ocr_log_terminal:
            return
        if self._last_log_value == cur:
            return
        self._last_log_value = cur
        full = max(1, int(self.observed_max_hp))
        dmg = max(0, full - int(cur))
        pct = 100.0 * float(cur) / float(full)
        print(f"[HP] full={full} cur={cur} dmg={dmg} ({pct:.1f}%){self._cube_suffix_for_log()}")

    # ──────────────────────────────────────────────────────────────────────
    # Main update
    # ──────────────────────────────────────────────────────────────────────
    def update(
        self,
        now: float,
        frame_rgb: np.ndarray,
        player_box: Optional[Sequence[float]],
        scale_factor: float,
        respawning_check: Optional[Callable[[], bool]] = None,
    ) -> Optional[DamageEvent]:
        """Update HP state for this frame; return a fresh DamageEvent on big drops."""
        if respawning_check and respawning_check():
            self.last_hp_ok = False
            self.last_hp_status = "respawn"
            return None
        if player_box is None or len(player_box) < 4:
            self.last_hp_ok = False
            self.last_hp_status = "unknown"
            return None

        # OCR-first
        ocr_pair = self._submit_or_read_ocr(now, frame_rgb, player_box, scale_factor)
        ocr_val: Optional[int] = None
        if ocr_pair is not None:
            ocr_val = int(ocr_pair[0])
            # Cheap sanity: a sudden 10× spike vs the prior accepted value is OCR
            # garbage (e.g. "47900" misread as "479000"). Drop it.
            if self._prev_hp_value is not None and self._prev_hp_value > 0:
                base = float(self._prev_hp_value)
                if abs(ocr_val - self._prev_hp_value) / base > self.ocr_max_relative_jump and (
                    self._max_hp_locked or ocr_val > base * 2.0
                ):
                    ocr_val = None
            if ocr_val is not None and self.observed_max_hp > 0:
                if ocr_val > int(self.observed_max_hp * 1.2 + 0.5):
                    ocr_val = None

        # HSV (fallback / visual-debug only)
        hp_pct_raw: Optional[float] = None
        hsv_ok = False
        if self.hsv_fallback_enabled or not self.ocr_primary:
            hp_pct_raw, hsv_ok, _gr = self.read_hp_band(frame_rgb, player_box, scale_factor)
        self._pct_smooth.append(hp_pct_raw if hsv_ok else None)
        hp_pct_med = self._median_smooth_pct()

        # Resolve HP percentage + emit damage events
        emitted: Optional[DamageEvent] = None
        if ocr_val is not None:
            if not self._max_hp_locked:
                if self._pending_started_at is None:
                    self._pending_started_at = now
                self._pending_read_count += 1
                self._pending_max_seen = max(self._pending_max_seen, int(ocr_val))
                self._try_latch_max_hp(ocr_val)
                self._maybe_soft_latch_max_hp(now)
            if self._max_hp_locked:
                full = int(self.observed_max_hp)
                cur = int(ocr_val)
                hp_pct = float(cur) / float(max(1, full))
                hp_pct = float(np.clip(hp_pct, 0.0, 1.0))
                self.last_hp_pct = hp_pct
                self.last_hp_ok = True
                self.last_hp_status = "ok"
                self.hp_value = cur
                self._log_terminal(cur)

                # OCR-driven damage event
                if self._prev_hp_value is not None and self._prev_hp_value > cur:
                    drop_hp = int(self._prev_hp_value - cur)
                    min_drop_hp = max(
                        self.ocr_damage_drop_min,
                        int(full * self.damage_drop_threshold + 0.5),
                    )
                    if drop_hp >= min_drop_hp:
                        drop_pct = float(drop_hp) / float(max(1, full))
                        ev = DamageEvent(time=now, drop_pct=drop_pct)
                        self._damage_events.append(ev)
                        emitted = ev
                self._prev_hp_value = cur
            else:
                # Seen one OCR digit, still latching — surface partial state.
                self.last_hp_pct = 1.0
                self.last_hp_ok = False
                self.last_hp_status = "ocr_pending"
                self.hp_value = ocr_val
                self._log_pending_diag(now, ocr_val)
        else:
            # No OCR this tick: use HSV fallback if enabled and OCR has never latched.
            if (
                self.hsv_fallback_enabled
                and not self._max_hp_locked
                and (hp_pct_med is not None or hp_pct_raw is not None)
            ):
                hp_pct = hp_pct_med if hp_pct_med is not None else hp_pct_raw
                self.last_hp_pct = hp_pct
                self.last_hp_ok = hsv_ok
                if hsv_ok:
                    self.last_hp_status = "ok"
                emitted = self._maybe_emit_hsv_damage(now, hp_pct, hsv_ok)
            elif self._max_hp_locked:
                # Keep the last good OCR percent — don't fall back to HSV after latching.
                self.last_hp_ok = self.last_hp_pct is not None
                if self.last_hp_ok:
                    self.last_hp_status = "ok"
            else:
                self.last_hp_ok = False
                if self.last_hp_status not in ("respawn", "unknown"):
                    self.last_hp_status = "ocr_pending"
                self._log_pending_diag(now, None)
                # Try soft-latch even on no-OCR ticks once enough reads piled up.
                self._maybe_soft_latch_max_hp(now)

        if self._max_hp_locked:
            self._maybe_update_power_cube_count(now, frame_rgb, player_box, scale_factor)

        return emitted

    def _maybe_emit_hsv_damage(
        self,
        now: float,
        hp_use: Optional[float],
        hsv_ok: bool,
    ) -> Optional[DamageEvent]:
        if not hsv_ok or hp_use is None:
            return None
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
            prior_max is not None and hp_use < prior_max - self.damage_drop_threshold
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
            ev = DamageEvent(time=now, drop_pct=drop)
            self._damage_events.append(ev)
            self._drop_streak = 0
            return ev
        return None

    def _median_smooth_pct(self) -> Optional[float]:
        vals = [p for p in self._pct_smooth if p is not None]
        if not vals:
            return None
        return float(np.median(np.asarray(vals, dtype=np.float64)))

    # ──────────────────────────────────────────────────────────────────────
    # External getters
    # ──────────────────────────────────────────────────────────────────────
    def recent_damage_event(self, now: float, lookback_seconds: float) -> Optional[DamageEvent]:
        """Most recent damage event within ``lookback_seconds``."""
        lb = float(lookback_seconds)
        for ev in reversed(self._damage_events):
            if now - ev.time <= lb:
                return ev
        return None

    @property
    def hp_value_pct(self) -> Optional[float]:
        if self.hp_value is None or self.observed_max_hp <= 0:
            return None
        return float(self.hp_value) / float(self.observed_max_hp)

    @property
    def max_hp_locked(self) -> bool:
        return bool(self._max_hp_locked)
