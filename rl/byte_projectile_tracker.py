"""ByteTrack-backed projectile tracker (supervision.ByteTrack).

``play.py`` chooses this class or ``ProjectileTracker`` based on config.
Requires ``supervision`` (``ByteTrack``) + ``numpy``.
"""

from __future__ import annotations

import math
import time
from collections import deque
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    from supervision.tracker.byte_tracker.core import ByteTrack as _ByteTrackCore
except Exception:  # pragma: no cover - optional dependency path
    _ByteTrackCore = None  # type: ignore[misc, assignment]

from rl.projectile_tracker import (
    ProjectileTrack,
    ProjectileTracker,
    _box_center_size,
    _center_inside_any_ui,
)
from rl.universal_projectiles import box_iou

BYTE_TRACK_AVAILABLE = _ByteTrackCore is not None

_SOURCE_CONF_DEFAULT = {"labeled": 0.85, "residual": 0.55, "motion": 0.40}


def _iou_xyxy(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) < 4 or len(b) < 4:
        return 0.0
    return float(box_iou(list(a[:4]), list(b[:4])))


class ByteProjectileTracker(ProjectileTracker):
    """Same public API as ``ProjectileTracker``; association uses ByteTrack."""

    def __init__(
        self,
        history_seconds: float = 0.6,
        velocity_alpha: float = 0.45,
        max_match_distance: float = 120.0,
        min_speed_px_s: float = 25.0,
        incoming_min_alignment: float = 0.2,
        enemy_origin_radius: float = 140.0,
        motion_enemy_origin_radius: float = 80.0,
        friendly_origin_radius: float = 100.0,
        require_enemy_origin: bool = True,
        require_enemy_origin_strict: bool = False,
        min_hits_to_promote: int = 1,
        max_speed_px_s: float = 1.0e9,
        max_accel_px_s2: float = 1.0e9,
        max_line_residual_frac: float = 1.0,
        *,
        track_activation_threshold: float = 0.5,
        minimum_matching_threshold: float = 0.8,
        lost_track_buffer_frames: int = 15,
        frame_rate: float = 30.0,
        minimum_consecutive_frames: int = 1,
        source_confidences: Optional[dict] = None,
    ) -> None:
        if _ByteTrackCore is None:
            raise ImportError("supervision with ByteTrack is not available")
        super().__init__(
            history_seconds=history_seconds,
            velocity_alpha=velocity_alpha,
            max_match_distance=max_match_distance,
            min_speed_px_s=min_speed_px_s,
            incoming_min_alignment=incoming_min_alignment,
            enemy_origin_radius=enemy_origin_radius,
            motion_enemy_origin_radius=motion_enemy_origin_radius,
            friendly_origin_radius=friendly_origin_radius,
            require_enemy_origin=require_enemy_origin,
            require_enemy_origin_strict=require_enemy_origin_strict,
            min_hits_to_promote=min_hits_to_promote,
            max_speed_px_s=max_speed_px_s,
            max_accel_px_s2=max_accel_px_s2,
            max_line_residual_frac=max_line_residual_frac,
        )
        self._source_conf = dict(_SOURCE_CONF_DEFAULT)
        if source_confidences:
            self._source_conf.update(
                {str(k): float(v) for k, v in source_confidences.items()}
            )
        self._frame_rate = max(1.0, float(frame_rate))
        self._bt = _ByteTrackCore(
            track_activation_threshold=float(track_activation_threshold),
            lost_track_buffer=int(lost_track_buffer_frames),
            minimum_matching_threshold=float(minimum_matching_threshold),
            frame_rate=float(frame_rate),
            minimum_consecutive_frames=int(minimum_consecutive_frames),
        )
        self._born_meta: Dict[int, Tuple[float, float, Optional[bool], str]] = {}
        self._last_center_by_id: Dict[int, Tuple[float, float, float]] = {}

    def reset(self) -> None:
        self._tracks.clear()
        self._born_meta.clear()
        self._last_center_by_id.clear()
        self._bt.reset()

    def update(
        self,
        boxes: Sequence[Sequence[float]],
        now: Optional[float] = None,
        cls: str = "projectile",
        enemy_boxes: Optional[Sequence[Sequence[float]]] = None,
        friendly_boxes: Optional[Sequence[Sequence[float]]] = None,
        box_sources: Optional[Sequence[str]] = None,
        ui_exclude_boxes: Optional[Sequence[Sequence[float]]] = None,
    ) -> List[ProjectileTrack]:
        if now is None:
            now = time.time()

        prev_snap: Dict[int, ProjectileTrack] = {t.track_id: t for t in self._tracks}

        rows: List[List[float]] = []
        sources: List[str] = []
        for i, box in enumerate(boxes or []):
            if len(box) < 4:
                continue
            cx, cy, _, _ = _box_center_size(box)
            if _center_inside_any_ui(cx, cy, ui_exclude_boxes):
                continue
            src = "labeled"
            if box_sources is not None and i < len(box_sources):
                src = str(box_sources[i])
            conf = float(self._source_conf.get(src, 0.5))
            x1, y1, x2, y2 = map(float, box[:4])
            rows.append([x1, y1, x2, y2, conf])
            sources.append(src)

        if not rows:
            self._tracks = []
            return []

        tensors = np.asarray(rows, dtype=np.float32)
        self._bt.update_with_tensors(tensors)

        all_stracks = list(self._bt.tracked_tracks) + list(self._bt.lost_tracks)
        out_tracks: List[ProjectileTrack] = []

        for st in all_stracks:
            ext_id = int(st.external_track_id)
            if ext_id < 0:
                continue
            tlbr = st.tlbr
            x1, y1, x2, y2 = map(float, tlbr)
            cx = (x1 + x2) * 0.5
            cy = (y1 + y2) * 0.5
            hw = max(1.0, (x2 - x1) * 0.5)
            hh = max(1.0, (y2 - y1) * 0.5)

            best_i = -1
            best_iou = 0.0
            for idx, row in enumerate(rows):
                iou = _iou_xyxy(row[:4], tlbr)
                if iou > best_iou:
                    best_iou = iou
                    best_i = idx
            src = sources[best_i] if best_i >= 0 else "labeled"

            vx_w = vy_w = 0.0
            if st.mean is not None and len(st.mean) >= 6:
                vx_w = float(st.mean[4]) * self._frame_rate
                vy_w = float(st.mean[5]) * self._frame_rate

            if ext_id not in self._born_meta:
                er = self._enemy_radius_for_source(src)
                fe = self._classify_origin(cx, cy, enemy_boxes, friendly_boxes, er)
                self._born_meta[ext_id] = (cx, cy, fe, src)

            origin_cx, origin_cy, from_enemy, born_src = self._born_meta[ext_id]

            prev_center = self._last_center_by_id.get(ext_id)
            inst_vx = inst_vy = 0.0
            if prev_center is not None:
                pcx, pcy, pt = prev_center
                dt = max(1e-3, now - pt)
                inst_vx = (cx - pcx) / dt
                inst_vy = (cy - pcy) / dt
            self._last_center_by_id[ext_id] = (cx, cy, now)

            existing = prev_snap.get(ext_id)
            if existing is not None:
                ema_vx = (1 - self.velocity_alpha) * existing.vx + self.velocity_alpha * inst_vx
                ema_vy = (1 - self.velocity_alpha) * existing.vy + self.velocity_alpha * inst_vy
                if math.hypot(vx_w, vy_w) < 1e-3:
                    vx, vy = ema_vx, ema_vy
                else:
                    vx = 0.5 * vx_w + 0.5 * ema_vx
                    vy = 0.5 * vy_w + 0.5 * ema_vy
                match_streak = max(1, int(getattr(st, "tracklet_len", 1) or 1))
                hist = deque(existing.center_history, maxlen=12)
                hist.append((cx, cy))
                out_tracks.append(
                    ProjectileTrack(
                        track_id=ext_id,
                        cx=cx,
                        cy=cy,
                        half_w=0.6 * existing.half_w + 0.4 * hw,
                        half_h=0.6 * existing.half_h + 0.4 * hh,
                        vx=vx,
                        vy=vy,
                        last_seen=now,
                        born_at=existing.born_at,
                        cls=cls,
                        origin_cx=origin_cx,
                        origin_cy=origin_cy,
                        from_enemy=from_enemy,
                        source=born_src,
                        match_streak=match_streak,
                        center_history=hist,
                        _inst_vx=inst_vx,
                        _inst_vy=inst_vy,
                        confidence_confirmed=existing.confidence_confirmed,
                    )
                )
            else:
                match_streak = max(1, int(getattr(st, "tracklet_len", 1) or 1))
                hist = deque([(cx, cy)], maxlen=12)
                out_tracks.append(
                    ProjectileTrack(
                        track_id=ext_id,
                        cx=cx,
                        cy=cy,
                        half_w=hw,
                        half_h=hh,
                        vx=vx_w,
                        vy=vy_w,
                        last_seen=now,
                        born_at=now,
                        cls=cls,
                        origin_cx=origin_cx,
                        origin_cy=origin_cy,
                        from_enemy=from_enemy,
                        source=born_src,
                        match_streak=match_streak,
                        center_history=hist,
                        _inst_vx=inst_vx,
                        _inst_vy=inst_vy,
                        confidence_confirmed=False,
                    )
                )

        cutoff = now - self.history_seconds
        self._tracks = [tr for tr in out_tracks if tr.last_seen >= cutoff]

        alive_ids = {t.track_id for t in self._tracks}
        for dead in list(self._born_meta.keys()):
            if dead not in alive_ids:
                del self._born_meta[dead]
        for dead in list(self._last_center_by_id.keys()):
            if dead not in alive_ids:
                del self._last_center_by_id[dead]

        return self._tracks
