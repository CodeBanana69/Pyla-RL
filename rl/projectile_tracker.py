"""Lightweight projectile tracker for the RL observation space.

The current vision model (`models/mainInGameModel.onnx`) only ships with
classes `enemy / teammate / player`, so by default the projectile inputs
will be empty. Once additional classes (e.g. "projectile", "super",
"bullet") are added to the dataset and the model is retrained, the
detector starts emitting boxes for those classes and this tracker turns
them into per-track velocity / hitbox features for the RL policy.

The matching is intentionally tiny (no Kalman filter, no scipy):
    - exponential-moving-average velocity per track
    - greedy nearest-neighbour assignment between previous tracks and
      current detections, capped by a max distance gate
    - tracks that fail to match for `history_seconds` are dropped

Public surface:
    ProjectileTracker(...)
    ProjectileTracker.update(boxes, now) -> list[ProjectileTrack]
    ProjectileTracker.observation_features(player_pos, k, frame_size)
        -> np.ndarray of shape (k * FEATURES_PER_TRACK,)
    ProjectileTracker.is_player_hit(player_box, now, lookahead_seconds)
        -> bool, used by the reward function as a damage proxy
    extract_projectile_boxes(data, classes) -> list of [x1,y1,x2,y2]

Coordinates use the same screen frame as the rest of play.py: top-left
origin, x grows right, y grows down. Velocities are in px/sec.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np


FEATURES_PER_TRACK = 7  # dx, dy, vx, vy, half_w, half_h, age_sec


@dataclass
class ProjectileTrack:
    """A single tracked projectile in screen coordinates."""

    track_id: int
    cx: float
    cy: float
    half_w: float
    half_h: float
    vx: float = 0.0
    vy: float = 0.0
    last_seen: float = 0.0
    born_at: float = 0.0
    confidence: float = 1.0
    cls: str = "projectile"
    # Origin classification, set when the track is first created.
    #   True  = first appeared near an enemy hitbox (counts as projectile)
    #   False = first appeared near the player/teammate (friendly fire)
    #           or in empty space with enemies visible elsewhere
    #   None  = could not classify (no entity boxes were available at
    #           birth); allowed through so we don't go blind in bushes
    from_enemy: Optional[bool] = None
    origin_cx: float = 0.0
    origin_cy: float = 0.0
    _matched: bool = field(default=False, repr=False)

    def predict(self, now: float) -> Tuple[float, float]:
        dt = max(0.0, now - self.last_seen)
        return self.cx + self.vx * dt, self.cy + self.vy * dt

    def expanded_box(self, padding: float = 0.0) -> Tuple[float, float, float, float]:
        return (
            self.cx - self.half_w - padding,
            self.cy - self.half_h - padding,
            self.cx + self.half_w + padding,
            self.cy + self.half_h + padding,
        )

    def alignment_to_player(self, player_pos: Tuple[float, float]) -> float:
        """Cosine of the angle between velocity and (player - projectile).

        Returns 0.0 when either vector has near-zero magnitude. A value of
        +1 means the projectile is heading straight at the player; -1 means
        it is moving directly away.
        """
        speed = math.hypot(self.vx, self.vy)
        if speed <= 1e-6:
            return 0.0
        dx = player_pos[0] - self.cx
        dy = player_pos[1] - self.cy
        dist = math.hypot(dx, dy)
        if dist <= 1e-6:
            return 0.0
        return (self.vx * dx + self.vy * dy) / (speed * dist)

    def is_incoming(
        self,
        player_pos: Tuple[float, float],
        min_alignment: float = 0.2,
        min_speed_px_s: float = 25.0,
    ) -> bool:
        """True when the track is moving fast enough and aimed at the player."""
        if math.hypot(self.vx, self.vy) < float(min_speed_px_s):
            return False
        return self.alignment_to_player(player_pos) >= float(min_alignment)

    def confidence_score(
        self,
        player_pos: Tuple[float, float],
        ref_speed_px_s: float = 600.0,
    ) -> float:
        """0..1 score combining directional alignment and speed magnitude.

        Alignment is mapped from [-1, 1] to [0, 1]; speed is clipped to
        ``ref_speed_px_s`` and normalised to [0, 1]. The geometric mean of
        the two keeps both signals important — a fast but sideways blob
        scores lower than a slower one heading right at the player.
        """
        alignment = self.alignment_to_player(player_pos)
        align_norm = max(0.0, (alignment + 1.0) * 0.5)
        speed = math.hypot(self.vx, self.vy)
        speed_norm = max(0.0, min(1.0, speed / max(1.0, float(ref_speed_px_s))))
        return math.sqrt(align_norm * speed_norm)


def _box_center_size(box: Sequence[float]) -> Tuple[float, float, float, float]:
    x1, y1, x2, y2 = box[:4]
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return (
        (x1 + x2) * 0.5,
        (y1 + y2) * 0.5,
        max(1.0, (x2 - x1) * 0.5),
        max(1.0, (y2 - y1) * 0.5),
    )


def _dist_point_to_box(box: Sequence[float], px: float, py: float) -> float:
    """Distance from a point to the nearest edge of an axis-aligned box.

    Returns 0 if the point is inside the box. Used so a projectile that
    spawns just outside a brawler's hitbox still counts as originating
    from that brawler.
    """
    x1, y1, x2, y2 = box[:4]
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    dx = max(x1 - px, 0.0, px - x2)
    dy = max(y1 - py, 0.0, py - y2)
    return math.hypot(dx, dy)


def _boxes_overlap(
    a: Sequence[float],
    b: Sequence[float],
    padding: float = 0.0,
) -> bool:
    ax1, ay1, ax2, ay2 = a[:4]
    bx1, by1, bx2, by2 = b[:4]
    return not (
        ax2 + padding < bx1
        or bx2 + padding < ax1
        or ay2 + padding < by1
        or by2 + padding < ay1
    )


def extract_projectile_boxes(
    data: Optional[dict],
    classes: Iterable[str],
) -> List[List[float]]:
    """Pull projectile-like detections out of the per-frame data dict.

    `data` is the same dict produced by Play.get_main_data — keys are
    detector class names, values are lists of `[x1, y1, x2, y2]`. This
    function gathers every box whose class name appears in `classes`.
    """
    if not data:
        return []
    out: List[List[float]] = []
    for cls in classes:
        boxes = data.get(cls)
        if not boxes:
            continue
        for box in boxes:
            if len(box) >= 4:
                out.append([float(box[0]), float(box[1]), float(box[2]), float(box[3])])
    return out


class ProjectileTracker:
    """Greedy matcher with EMA velocity smoothing for projectile boxes.

    Parameters
    ----------
    history_seconds:
        How long a track is kept alive without a fresh match before it is
        dropped.
    velocity_alpha:
        EMA factor on velocity updates. Higher = react faster, noisier.
    max_match_distance:
        Maximum pixel distance allowed when matching a previous track's
        predicted position to a new detection center.
    min_speed_px_s:
        Tracks whose smoothed speed stays below this are still kept (a
        slow-moving super counts) but they are reported with vx=vy=0 in
        is_player_hit's lookahead so we don't extrapolate noise.
    """

    def __init__(
        self,
        history_seconds: float = 0.6,
        velocity_alpha: float = 0.45,
        max_match_distance: float = 120.0,
        min_speed_px_s: float = 25.0,
        incoming_min_alignment: float = 0.2,
        enemy_origin_radius: float = 140.0,
        friendly_origin_radius: float = 100.0,
        require_enemy_origin: bool = True,
    ) -> None:
        self.history_seconds = float(history_seconds)
        self.velocity_alpha = float(velocity_alpha)
        self.max_match_distance = float(max_match_distance)
        self.min_speed_px_s = float(min_speed_px_s)
        self.incoming_min_alignment = float(incoming_min_alignment)
        self.enemy_origin_radius = float(enemy_origin_radius)
        self.friendly_origin_radius = float(friendly_origin_radius)
        self.require_enemy_origin = bool(require_enemy_origin)
        self._tracks: List[ProjectileTrack] = []
        self._next_id = 1

    @property
    def tracks(self) -> List[ProjectileTrack]:
        return list(self._tracks)

    def reset(self) -> None:
        self._tracks.clear()

    def _classify_origin(
        self,
        cx: float,
        cy: float,
        enemy_boxes: Optional[Sequence[Sequence[float]]],
        friendly_boxes: Optional[Sequence[Sequence[float]]],
    ) -> Optional[bool]:
        """Decide if a brand-new detection at (cx, cy) is enemy-spawned.

        Returns True when the spawn point is within ``enemy_origin_radius``
        of an enemy box AND not within ``friendly_origin_radius`` of any
        player/teammate box. Returns False when enemies are visible but
        the point isn't near one (or is closer to a friendly). Returns
        None when no entity boxes are available — we can't decide, so
        downstream filters let it pass.
        """
        has_enemy_info = enemy_boxes is not None
        has_friendly_info = friendly_boxes is not None
        if not has_enemy_info and not has_friendly_info:
            return None
        near_friendly = False
        if friendly_boxes:
            for b in friendly_boxes:
                if len(b) < 4:
                    continue
                if _dist_point_to_box(b, cx, cy) <= self.friendly_origin_radius:
                    near_friendly = True
                    break
        if near_friendly:
            return False
        if not enemy_boxes:
            # Friendlies visible but enemies are not; we can rule out
            # friendly-fire above but otherwise we can't confirm enemy.
            return None
        for b in enemy_boxes:
            if len(b) < 4:
                continue
            if _dist_point_to_box(b, cx, cy) <= self.enemy_origin_radius:
                return True
        return False

    def update(
        self,
        boxes: Sequence[Sequence[float]],
        now: Optional[float] = None,
        cls: str = "projectile",
        enemy_boxes: Optional[Sequence[Sequence[float]]] = None,
        friendly_boxes: Optional[Sequence[Sequence[float]]] = None,
    ) -> List[ProjectileTrack]:
        """Match detections to existing tracks and return live tracks.

        ``enemy_boxes`` and ``friendly_boxes`` (player + teammate) are
        used at track birth to mark whether the projectile actually came
        from an enemy. Tracks born away from any enemy are flagged so
        the consumer-side filters (`incoming_tracks`, `is_player_hit`)
        can drop them.
        """
        if now is None:
            now = time.time()

        for tr in self._tracks:
            tr._matched = False

        detections = []
        for box in boxes or []:
            cx, cy, hw, hh = _box_center_size(box)
            detections.append((cx, cy, hw, hh, False))  # last bool = consumed

        for tr in list(self._tracks):
            best_idx = -1
            best_dist = self.max_match_distance
            pred_cx, pred_cy = tr.predict(now)
            for idx, det in enumerate(detections):
                if det[4]:
                    continue
                dx = det[0] - pred_cx
                dy = det[1] - pred_cy
                d = math.hypot(dx, dy)
                if d < best_dist:
                    best_dist = d
                    best_idx = idx
            if best_idx < 0:
                continue
            cx, cy, hw, hh, _ = detections[best_idx]
            detections[best_idx] = (cx, cy, hw, hh, True)
            dt = max(1e-3, now - tr.last_seen)
            new_vx = (cx - tr.cx) / dt
            new_vy = (cy - tr.cy) / dt
            tr.vx = (1 - self.velocity_alpha) * tr.vx + self.velocity_alpha * new_vx
            tr.vy = (1 - self.velocity_alpha) * tr.vy + self.velocity_alpha * new_vy
            tr.cx = cx
            tr.cy = cy
            tr.half_w = 0.6 * tr.half_w + 0.4 * hw
            tr.half_h = 0.6 * tr.half_h + 0.4 * hh
            tr.last_seen = now
            tr._matched = True

        for det in detections:
            cx, cy, hw, hh, consumed = det
            if consumed:
                continue
            track = ProjectileTrack(
                track_id=self._next_id,
                cx=cx,
                cy=cy,
                half_w=hw,
                half_h=hh,
                last_seen=now,
                born_at=now,
                cls=cls,
                origin_cx=cx,
                origin_cy=cy,
                from_enemy=self._classify_origin(
                    cx, cy, enemy_boxes, friendly_boxes
                ),
            )
            track._matched = True
            self._next_id += 1
            self._tracks.append(track)

        cutoff = now - self.history_seconds
        self._tracks = [tr for tr in self._tracks if tr.last_seen >= cutoff]
        return self._tracks

    def _passes_origin_gate(self, tr: ProjectileTrack) -> bool:
        """True unless the track was confirmed to NOT originate from an enemy."""
        if not self.require_enemy_origin:
            return True
        return tr.from_enemy is not False

    def incoming_tracks(
        self,
        player_pos: Tuple[float, float],
        min_alignment: Optional[float] = None,
        min_speed_px_s: Optional[float] = None,
    ) -> List[ProjectileTrack]:
        """Tracks whose velocity actually heads at the player.

        Brand-new tracks (one frame of evidence, no smoothed velocity yet)
        are kept in the candidate set so the first-frame observation isn't
        always empty; once they have a velocity the gate filters them.
        Tracks that were confirmed at birth to originate from a friendly
        (or far from any enemy when enemies were visible) are dropped.
        """
        if not self._tracks:
            return []
        align = self.incoming_min_alignment if min_alignment is None else float(min_alignment)
        speed = self.min_speed_px_s if min_speed_px_s is None else float(min_speed_px_s)
        out: List[ProjectileTrack] = []
        for tr in self._tracks:
            if not self._passes_origin_gate(tr):
                continue
            if math.hypot(tr.vx, tr.vy) < speed:
                continue
            if tr.alignment_to_player(player_pos) < align:
                continue
            out.append(tr)
        return out

    def nearest_tracks(
        self,
        player_pos: Tuple[float, float],
        k: int,
        only_incoming: bool = True,
    ) -> List[ProjectileTrack]:
        if k <= 0 or not self._tracks:
            return []
        px, py = player_pos
        if only_incoming:
            candidates = self.incoming_tracks(player_pos)
        else:
            # Even when callers ask for "all tracks", still drop the ones
            # we proved did not come from an enemy.
            candidates = [
                tr for tr in self._tracks if self._passes_origin_gate(tr)
            ]
        if not candidates:
            return []
        scored = [
            (math.hypot(tr.cx - px, tr.cy - py), tr)
            for tr in candidates
        ]
        scored.sort(key=lambda t: t[0])
        return [tr for _, tr in scored[:k]]

    def observation_features(
        self,
        player_pos: Tuple[float, float],
        k: int,
        frame_size: Tuple[int, int],
        now: Optional[float] = None,
    ) -> np.ndarray:
        """Flatten K nearest projectiles into a normalized feature vector.

        Layout per track: [dx, dy, vx, vy, half_w, half_h, age_sec],
        all normalized to [-1, 1] (positions/velocities by frame size,
        sizes by 0.5 * frame extent, age by history_seconds).
        Empty slots are zero-filled.
        """
        if now is None:
            now = time.time()
        width, height = max(1, int(frame_size[0])), max(1, int(frame_size[1]))
        diag = math.hypot(width, height)
        out = np.zeros((k, FEATURES_PER_TRACK), dtype=np.float32)
        nearest = self.nearest_tracks(player_pos, k)
        px, py = player_pos
        for i, tr in enumerate(nearest):
            dx = (tr.cx - px) / max(1.0, diag * 0.5)
            dy = (tr.cy - py) / max(1.0, diag * 0.5)
            vx = tr.vx / max(1.0, diag)
            vy = tr.vy / max(1.0, diag)
            hw = tr.half_w / max(1.0, width * 0.5)
            hh = tr.half_h / max(1.0, height * 0.5)
            age = max(0.0, now - tr.born_at) / max(1e-3, self.history_seconds)
            out[i, 0] = max(-1.0, min(1.0, dx))
            out[i, 1] = max(-1.0, min(1.0, dy))
            out[i, 2] = max(-1.0, min(1.0, vx))
            out[i, 3] = max(-1.0, min(1.0, vy))
            out[i, 4] = max(0.0, min(1.0, hw))
            out[i, 5] = max(0.0, min(1.0, hh))
            out[i, 6] = max(0.0, min(1.0, age))
        return out.reshape(-1)

    def is_player_hit(
        self,
        player_box: Sequence[float],
        now: Optional[float] = None,
        padding: float = 0.0,
        lookahead_seconds: float = 0.0,
        require_incoming: bool = True,
    ) -> bool:
        """Return True if any tracked projectile overlaps the player box.

        Used by the reward function as a "took damage" proxy. With
        `lookahead_seconds > 0`, fast projectiles that will overlap the
        player within that horizon also count as a hit (cheap forward
        Euler step using the smoothed velocity).

        With ``require_incoming=True`` (default) tracks whose velocity is
        not pointed at the player are ignored — this prevents spurious
        penalties from particles, friendly shots flying away, and idle
        background animations.
        """
        if now is None:
            now = time.time()
        if not self._tracks:
            return False
        player_cx = (float(player_box[0]) + float(player_box[2])) * 0.5
        player_cy = (float(player_box[1]) + float(player_box[3])) * 0.5
        player_pos = (player_cx, player_cy)
        for tr in self._tracks:
            if not self._passes_origin_gate(tr):
                continue
            currently_overlapping = _boxes_overlap(
                player_box, tr.expanded_box(padding=padding)
            )
            if currently_overlapping and not require_incoming:
                return True
            if require_incoming and not tr.is_incoming(
                player_pos,
                min_alignment=self.incoming_min_alignment,
                min_speed_px_s=self.min_speed_px_s,
            ):
                continue
            if currently_overlapping:
                return True
            if lookahead_seconds <= 0:
                continue
            speed = math.hypot(tr.vx, tr.vy)
            if speed < self.min_speed_px_s:
                continue
            dt_total = max(0.0, lookahead_seconds)
            steps = max(1, int(dt_total / 0.05))
            step_dt = dt_total / steps
            cx, cy = tr.cx, tr.cy
            for _ in range(steps):
                cx += tr.vx * step_dt
                cy += tr.vy * step_dt
                projected = (
                    cx - tr.half_w - padding,
                    cy - tr.half_h - padding,
                    cx + tr.half_w + padding,
                    cy + tr.half_h + padding,
                )
                if _boxes_overlap(player_box, projected):
                    return True
        return False
