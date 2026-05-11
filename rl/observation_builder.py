"""Rich vector observations for SAC movement (live + offline training)."""

from __future__ import annotations

import math
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Deque, List, Optional, Tuple

import numpy as np

if TYPE_CHECKING:
    pass

# One frame: indices are stable across trainer + recorder
OB_PLAYER_CX = 0
OB_PLAYER_CY = 1
OB_VX = 2
OB_VY = 3
OB_HP_FRAC = 4
OB_TIME_SINCE_DAMAGE = 5
OB_SUPER_READY = 6
OB_GADGET_READY = 7
OB_ENEMY1_DX = 8
OB_ENEMY1_DY = 9
OB_ENEMY1_DIST = 10
OB_ENEMY2_DX = 11
OB_ENEMY2_DY = 12
OB_ENEMY2_DIST = 13
OB_TEAM_DX = 14
OB_TEAM_DY = 15
OB_TEAM_DIST = 16
OB_FOG_PX = 17
OB_FOG_NX = 18
OB_FOG_PY = 19
OB_FOG_NY = 20
OB_WALL_Q0 = 21
OB_WALL_Q1 = 22
OB_WALL_Q2 = 23
OB_WALL_Q3 = 24
OB_LAST_AX = 25
OB_LAST_AY = 26

SINGLE_OBS_DIM = 27


@dataclass
class ObservationConfig:
    fog_ray_max_px: float = 200.0
    fog_ray_step_px: float = 4.0
    damage_lookback_norm_seconds: float = 5.0
    velocity_max_scale: float = 2.0  # vx,vy clipped to +- this after diag-normalize
    use_hp: bool = True
    use_fog: bool = True
    use_walls: bool = True
    use_super_gadget: bool = True
    frame_stack: int = 1


@dataclass
class ObservationBuilderState:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    prev_player_pos: Optional[Tuple[float, float]] = None
    prev_time: Optional[float] = None
    stack: Deque[np.ndarray] = field(default_factory=lambda: deque(maxlen=8))
    small_action_since: Optional[float] = None

    def reset_match(self, stack_maxlen: int = 8) -> None:
        self.prev_player_pos = None
        self.prev_time = None
        self.stack = deque(maxlen=max(stack_maxlen, 1))
        self.small_action_since = None
        self.session_id = str(uuid.uuid4())[:8]


def _nearest_two_enemies(
    enemy_boxes: List,
    player_pos: Tuple[float, float],
) -> Tuple[
    Optional[Tuple[float, float, float]],
    Optional[Tuple[float, float, float]],
]:
    if not enemy_boxes:
        return None, None
    px, py = player_pos
    scored: List[Tuple[float, float, float]] = []
    for box in enemy_boxes:
        if len(box) < 4:
            continue
        cx = (float(box[0]) + float(box[2])) * 0.5
        cy = (float(box[1]) + float(box[3])) * 0.5
        dx, dy = cx - px, cy - py
        d = math.hypot(dx, dy)
        scored.append((d, dx, dy))
    if not scored:
        return None, None
    scored.sort(key=lambda t: t[0])
    _, dx1, dy1 = scored[0]
    d1 = math.hypot(dx1, dy1)
    best1 = (dx1, dy1, d1)
    if len(scored) < 2:
        return best1, None
    _, dx2, dy2 = scored[1]
    d2 = math.hypot(dx2, dy2)
    return best1, (dx2, dy2, d2)


def _nearest_teammate(
    teammate_boxes: List,
    player_pos: Tuple[float, float],
) -> Optional[Tuple[float, float, float]]:
    if not teammate_boxes:
        return None
    px, py = player_pos
    best = None
    best_d = float("inf")
    for box in teammate_boxes:
        if len(box) < 4:
            continue
        cx = (float(box[0]) + float(box[2])) * 0.5
        cy = (float(box[1]) + float(box[3])) * 0.5
        dx, dy = cx - px, cy - py
        d = math.hypot(dx, dy)
        if d < best_d:
            best_d = d
            best = (dx, dy, d)
    return best


def _normalize_offset(
    dx: float,
    dy: float,
    d: float,
    half_w: float,
    half_h: float,
    diag: float,
) -> Tuple[float, float, float]:
    return (
        float(np.clip(dx / max(1.0, half_w), -1.0, 1.0)),
        float(np.clip(dy / max(1.0, half_h), -1.0, 1.0)),
        float(np.clip(d / max(1.0, diag), 0.0, 1.0)),
    )


def _fog_ray_distances(
    play,
    player_pos: Tuple[float, float],
    frame_size: Tuple[int, int],
    max_ray: float,
    step_px: float,
) -> Tuple[float, float, float, float]:
    """Return normalized [0,1] distance along +x,-x,+y,-y until fog; 1.0 = no fog in range."""
    frame = getattr(play, "current_frame", None)
    if frame is None:
        return 1.0, 1.0, 1.0, 1.0
    built = play._build_trusted_fog_mask(frame, roi_center=player_pos, roi_radius=int(max_ray) + 40)
    if built is None:
        return 1.0, 1.0, 1.0, 1.0
    mask, (ox, oy) = built
    h_m, w_m = mask.shape[:2]
    px, py = float(player_pos[0]), float(player_pos[1])

    def sample(mx: float, my: float) -> int:
        ix = int(round(mx - ox))
        iy = int(round(my - oy))
        if ix < 0 or iy < 0 or ix >= w_m or iy >= h_m:
            return 0
        return int(mask[iy, ix] > 0)

    def ray(dx: float, dy: float) -> float:
        dist = 0.0
        steps = max(1, int(max_ray / max(1.0, step_px)))
        for _ in range(steps):
            dist += step_px
            nx = px + dx * dist
            ny = py + dy * dist
            if nx < 0 or ny < 0 or nx >= frame_size[0] or ny >= frame_size[1]:
                return min(dist / max_ray, 1.0)
            if sample(nx, ny):
                return min(dist / max_ray, 1.0)
        return 1.0

    return ray(1, 0), ray(-1, 0), ray(0, 1), ray(0, -1)


def wall_quadrant_counts(
    wall_boxes: List,
    player_pos: Tuple[float, float],
) -> Tuple[int, int, int, int]:
    """Wall counts per quadrant (+x/-y, +x/+y, -x/+y, -x/-y) around player."""
    q = [0, 0, 0, 0]
    px, py = player_pos
    for box in wall_boxes or []:
        if len(box) < 4:
            continue
        cx = (float(box[0]) + float(box[2])) * 0.5
        cy = (float(box[1]) + float(box[3])) * 0.5
        if cx >= px and cy < py:
            q[0] += 1
        elif cx >= px and cy >= py:
            q[1] += 1
        elif cx < px and cy >= py:
            q[2] += 1
        else:
            q[3] += 1
    return (q[0], q[1], q[2], q[3])


def _wall_quadrant_features(
    wall_boxes: List,
    player_pos: Tuple[float, float],
    max_normalize: float = 8.0,
) -> Tuple[float, float, float, float]:
    qc = wall_quadrant_counts(wall_boxes, player_pos)
    return tuple(min(float(x) / max_normalize, 1.0) for x in qc)  # type: ignore[return-value]


def observation_size_single(cfg: ObservationConfig) -> int:
    return SINGLE_OBS_DIM


def stacked_observation_size(cfg: ObservationConfig) -> int:
    k = max(1, int(cfg.frame_stack))
    return SINGLE_OBS_DIM * k


class ObservationBuilder:
    """Builds SINGLE_OBS_DIM vector; optional frame stacking in ``build``."""

    def __init__(self, cfg: Optional[ObservationConfig] = None) -> None:
        self.cfg = cfg or ObservationConfig()
        self.state = ObservationBuilderState()
        smax = max(8, max(1, int(self.cfg.frame_stack)))
        self.state.reset_match(smax)

    def reset_match(self) -> None:
        smax = max(8, max(1, int(self.cfg.frame_stack)))
        self.state.reset_match(smax)

    @property
    def session_id(self) -> str:
        return self.state.session_id

    def build_single(
        self,
        play,
        data: dict,
        current_time: float,
        last_action: Optional[np.ndarray],
    ) -> np.ndarray:
        obs = np.zeros(SINGLE_OBS_DIM, dtype=np.float32)

        players = data.get("player") or []
        if not players:
            if last_action is not None:
                obs[OB_LAST_AX : OB_LAST_AY + 1] = np.asarray(
                    last_action, dtype=np.float32
                ).reshape(-1)[:2]
            return obs

        box = players[0]
        player_pos = (
            float(box[0] + box[2]) * 0.5,
            float(box[1] + box[3]) * 0.5,
        )

        frame = getattr(play, "current_frame", None)
        if frame is not None:
            height, width = frame.shape[:2]
        else:
            width, height = 1920, 1080
        diag = float(np.hypot(width, height))
        half_w, half_h = width * 0.5, height * 0.5

        obs[OB_PLAYER_CX] = float(np.clip((player_pos[0] - half_w) / max(1.0, half_w), -1.0, 1.0))
        obs[OB_PLAYER_CY] = float(np.clip((player_pos[1] - half_h) / max(1.0, half_h), -1.0, 1.0))

        dt = 1.0 / 30.0
        if self.state.prev_time is not None and self.state.prev_player_pos is not None:
            dt = max(1e-4, float(current_time - self.state.prev_time))
            vx = (player_pos[0] - self.state.prev_player_pos[0]) / max(1e-6, diag) / dt
            vy = (player_pos[1] - self.state.prev_player_pos[1]) / max(1e-6, diag) / dt
            lim = float(self.cfg.velocity_max_scale)
            obs[OB_VX] = float(np.clip(vx, -lim, lim))
            obs[OB_VY] = float(np.clip(vy, -lim, lim))

        self.state.prev_player_pos = player_pos
        self.state.prev_time = current_time

        if self.cfg.use_hp:
            hm = getattr(play, "health_monitor", None)
            if hm is not None and getattr(hm, "last_hp_ok", False) and hm.last_hp_pct is not None:
                obs[OB_HP_FRAC] = float(np.clip(hm.last_hp_pct, 0.0, 1.0))
            else:
                obs[OB_HP_FRAC] = 0.5
            obs[OB_TIME_SINCE_DAMAGE] = 1.0
            if hm is not None and hm._damage_events:
                last_t = hm._damage_events[-1].time
                tau = max(0.25, float(self.cfg.damage_lookback_norm_seconds))
                obs[OB_TIME_SINCE_DAMAGE] = float(
                    np.clip((current_time - last_t) / tau, 0.0, 1.0)
                )
        else:
            obs[OB_HP_FRAC] = 0.0
            obs[OB_TIME_SINCE_DAMAGE] = 0.0

        if self.cfg.use_super_gadget:
            obs[OB_SUPER_READY] = 1.0 if getattr(play, "is_super_ready", False) else 0.0
            g = getattr(play, "should_use_gadget", False) and getattr(play, "is_gadget_ready", False)
            obs[OB_GADGET_READY] = 1.0 if g else 0.0
        else:
            obs[OB_SUPER_READY] = 0.0
            obs[OB_GADGET_READY] = 0.0

        e1, e2 = _nearest_two_enemies(list(data.get("enemy") or []), player_pos)
        if e1 is not None:
            dx, dy, d = e1
            obs[OB_ENEMY1_DX : OB_ENEMY1_DIST + 1] = _normalize_offset(
                dx, dy, d, half_w, half_h, diag
            )
        else:
            obs[OB_ENEMY1_DIST] = 1.0
        if e2 is not None:
            dx, dy, d = e2
            obs[OB_ENEMY2_DX : OB_ENEMY2_DIST + 1] = _normalize_offset(
                dx, dy, d, half_w, half_h, diag
            )
        else:
            obs[OB_ENEMY2_DIST] = 1.0

        tm = _nearest_teammate(list(data.get("teammate") or []), player_pos)
        if tm is not None:
            dx, dy, d = tm
            obs[OB_TEAM_DX : OB_TEAM_DIST + 1] = _normalize_offset(
                dx, dy, d, half_w, half_h, diag
            )
        else:
            obs[OB_TEAM_DIST] = 1.0

        if self.cfg.use_fog:
            fp, fn, fpy, fny = _fog_ray_distances(
                play,
                player_pos,
                (width, height),
                self.cfg.fog_ray_max_px,
                self.cfg.fog_ray_step_px,
            )
            obs[OB_FOG_PX : OB_FOG_NY + 1] = (fp, fn, fpy, fny)
        else:
            # 1.0 = "no fog in range" so reward_v2 fog proximity does not fire when ablated
            obs[OB_FOG_PX : OB_FOG_NY + 1] = 1.0

        if self.cfg.use_walls:
            wq = _wall_quadrant_features(list(data.get("wall") or []), player_pos)
            obs[OB_WALL_Q0 : OB_WALL_Q3 + 1] = wq
        else:
            obs[OB_WALL_Q0 : OB_WALL_Q3 + 1] = 0.0

        if last_action is not None:
            arr = np.asarray(last_action, dtype=np.float32).reshape(-1)[:2]
            obs[OB_LAST_AX : OB_LAST_AY + 1] = np.clip(arr, -1.0, 1.0)

        return obs

    def build(
        self,
        play,
        data: dict,
        current_time: float,
        last_action: Optional[np.ndarray],
        *,
        track_small_action: bool = False,
        small_mag: float = 0.1,
        small_needed_seconds: float = 2.0,
    ) -> np.ndarray:
        single = self.build_single(play, data, current_time, last_action)
        if track_small_action and last_action is not None:
            mag = float(np.linalg.norm(last_action.reshape(-1)[:2]))
            if mag < small_mag:
                if self.state.small_action_since is None:
                    self.state.small_action_since = current_time
            else:
                self.state.small_action_since = None

        self.state.stack.append(single.astype(np.float32, copy=False))
        k = max(1, int(self.cfg.frame_stack))
        frames: List[np.ndarray] = []
        need_pad = k - len(self.state.stack)
        if need_pad > 0:
            pad = np.zeros_like(single)
            for _ in range(need_pad):
                frames.append(pad)
            frames.extend(list(self.state.stack))
        else:
            tmp = list(self.state.stack)[-k:]
            frames = tmp

        stacked = np.concatenate(frames, axis=0).astype(np.float32, copy=False)
        return stacked


def stationary_seconds(state: ObservationBuilderState, current_time: float, small_mag: float, last_action: Optional[np.ndarray]) -> float:
    if state.small_action_since is None or last_action is None:
        return 0.0
    if float(np.linalg.norm(np.asarray(last_action).reshape(-1)[:2])) >= small_mag:
        return 0.0
    return max(0.0, current_time - state.small_action_since)
