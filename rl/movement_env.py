"""Gymnasium environment for movement-only RL training.

This env is *driven externally* by the live bot. It does not own a
simulator: each call to ``step`` returns whatever the policy bridge
queued via ``submit_transition`` from the most recent game frame. The
SB3 trainer running in a worker thread/process treats the env as a
normal Gym env, so the standard PPO/SAC training loop works without
custom rollout buffers.

Observation layout (all values clipped to the configured Box bounds):

    [
        player_cx_norm, player_cy_norm,            # in [-1, 1]
        nearest_enemy_dx_norm, nearest_enemy_dy_norm, nearest_enemy_dist_norm,
        nearest_teammate_dx_norm, nearest_teammate_dy_norm, nearest_teammate_dist_norm,
        K * (dx, dy, vx, vy, half_w, half_h, age_sec)   # per projectile
    ]

Action: Box([-1, -1], [1, 1], dtype=float32). The policy bridge maps
this 2D direction to either a joystick angle (showdown) or a WASD
string (3v3 modes).

Reward: shaped to match the user's brief:
    +0.01 / step survival
    + small bonus for staying in the safe band around the nearest enemy
    + small bonus for staying near the closest teammate
    -1.0 (default) when a tracked projectile/super overlaps the player box
    +0.5 episode-end survival bonus on `done`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Optional, Tuple

import numpy as np

try:  # pragma: no cover - import guarded for offline test environments
    import gymnasium as gym
    from gymnasium import spaces
    _GYM_AVAILABLE = True
except Exception:  # pragma: no cover
    gym = None  # type: ignore[assignment]
    spaces = None  # type: ignore[assignment]
    _GYM_AVAILABLE = False


from rl.projectile_tracker import FEATURES_PER_TRACK


PLAYER_FEATURES = 2
ENEMY_FEATURES = 3
TEAMMATE_FEATURES = 3


def observation_size(max_projectiles: int) -> int:
    return (
        PLAYER_FEATURES
        + ENEMY_FEATURES
        + TEAMMATE_FEATURES
        + max_projectiles * FEATURES_PER_TRACK
    )


@dataclass
class RewardConfig:
    survival_per_step: float = 0.01
    safe_distance_bonus: float = 0.02
    safe_distance_band_min: float = 0.35   # normalized vs frame diagonal
    safe_distance_band_max: float = 0.75
    teammate_proximity_bonus: float = 0.01
    teammate_band_min: float = 0.05
    teammate_band_max: float = 0.30
    projectile_hit_penalty: float = -1.0
    survival_episode_bonus: float = 0.5


@dataclass
class MovementTransition:
    obs: np.ndarray
    reward: float = 0.0
    done: bool = False
    info: dict = field(default_factory=dict)


def build_observation(
    player_pos: Optional[Tuple[float, float]],
    nearest_enemy_offset_distance: Optional[Tuple[float, float, float]],
    nearest_teammate_offset_distance: Optional[Tuple[float, float, float]],
    projectile_features: np.ndarray,
    frame_size: Tuple[int, int],
    max_projectiles: int,
) -> np.ndarray:
    """Pure helper to assemble an observation vector.

    Kept top-level so tests can construct observations without a live
    game. All inputs are in screen pixels; this normalizes to [-1, 1].
    """
    width, height = max(1, int(frame_size[0])), max(1, int(frame_size[1]))
    half_w = width * 0.5
    half_h = height * 0.5
    diag = float(np.hypot(width, height))

    obs = np.zeros(observation_size(max_projectiles), dtype=np.float32)

    if player_pos is not None:
        obs[0] = float(np.clip((player_pos[0] - half_w) / max(1.0, half_w), -1.0, 1.0))
        obs[1] = float(np.clip((player_pos[1] - half_h) / max(1.0, half_h), -1.0, 1.0))

    if nearest_enemy_offset_distance is not None:
        edx, edy, edist = nearest_enemy_offset_distance
        obs[2] = float(np.clip(edx / max(1.0, half_w), -1.0, 1.0))
        obs[3] = float(np.clip(edy / max(1.0, half_h), -1.0, 1.0))
        obs[4] = float(np.clip(edist / max(1.0, diag), 0.0, 1.0))
    else:
        obs[4] = 1.0  # max distance proxy when no enemy is visible

    if nearest_teammate_offset_distance is not None:
        tdx, tdy, tdist = nearest_teammate_offset_distance
        obs[5] = float(np.clip(tdx / max(1.0, half_w), -1.0, 1.0))
        obs[6] = float(np.clip(tdy / max(1.0, half_h), -1.0, 1.0))
        obs[7] = float(np.clip(tdist / max(1.0, diag), 0.0, 1.0))
    else:
        obs[7] = 1.0

    if projectile_features is not None and projectile_features.size:
        target = projectile_features.astype(np.float32, copy=False)
        end = min(target.size, max_projectiles * FEATURES_PER_TRACK)
        obs[
            PLAYER_FEATURES + ENEMY_FEATURES + TEAMMATE_FEATURES :
            PLAYER_FEATURES + ENEMY_FEATURES + TEAMMATE_FEATURES + end
        ] = target[:end]

    return obs


def compute_reward(
    obs: np.ndarray,
    projectile_hit: bool,
    cfg: Optional[RewardConfig] = None,
    done: bool = False,
) -> float:
    """Reward function used both online (bridge) and inside step()."""
    cfg = cfg or RewardConfig()

    reward = cfg.survival_per_step

    enemy_dist_norm = float(obs[4])
    if cfg.safe_distance_band_min <= enemy_dist_norm <= cfg.safe_distance_band_max:
        reward += cfg.safe_distance_bonus

    teammate_dist_norm = float(obs[7])
    if cfg.teammate_band_min <= teammate_dist_norm <= cfg.teammate_band_max:
        reward += cfg.teammate_proximity_bonus

    if projectile_hit:
        reward += cfg.projectile_hit_penalty

    if done:
        reward += cfg.survival_episode_bonus
    return float(reward)


class MovementEnv(gym.Env if _GYM_AVAILABLE else object):  # type: ignore[misc]
    """Externally-driven Gym env used by the SB3 trainer.

    The bot's main loop produces observations and rewards from the live
    game; the trainer thread calls ``reset`` / ``step`` on this env and
    receives those queued transitions. ``submit_transition`` is
    thread-safe so the producer and consumer can run on separate
    threads.
    """

    metadata = {"render_modes": []}

    def __init__(self, max_projectiles: int = 6, reward_cfg: Optional[RewardConfig] = None):
        if not _GYM_AVAILABLE:
            raise RuntimeError(
                "gymnasium is not installed; install gymnasium and stable-baselines3 "
                "or set use_rl_movement=no in cfg/bot_config.toml."
            )
        super().__init__()
        self.max_projectiles = int(max_projectiles)
        self.reward_cfg = reward_cfg or RewardConfig()
        size = observation_size(self.max_projectiles)
        self.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(size,), dtype=np.float32)
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(2,), dtype=np.float32)

        self._lock = Lock()
        self._pending: Optional[MovementTransition] = None
        self._latest_obs: np.ndarray = np.zeros(size, dtype=np.float32)
        self._last_action: np.ndarray = np.zeros(2, dtype=np.float32)
        self._terminated = False

    def submit_transition(self, transition: MovementTransition) -> None:
        with self._lock:
            self._pending = transition
            self._latest_obs = transition.obs.copy()
            if transition.done:
                self._terminated = True

    def latest_observation(self) -> np.ndarray:
        with self._lock:
            return self._latest_obs.copy()

    def latest_action(self) -> np.ndarray:
        with self._lock:
            return self._last_action.copy()

    def reset(self, *, seed: Optional[int] = None, options=None):  # type: ignore[override]
        super().reset(seed=seed)
        with self._lock:
            self._terminated = False
            self._pending = None
            obs = self._latest_obs.copy()
        return obs, {}

    def step(self, action):  # type: ignore[override]
        action_arr = np.asarray(action, dtype=np.float32).reshape(-1)[:2]
        with self._lock:
            self._last_action = action_arr.copy()
            transition = self._pending
            self._pending = None

        if transition is None:
            obs = self.latest_observation()
            return obs, 0.0, False, False, {"empty": True}

        terminated = bool(transition.done)
        truncated = False
        info = dict(transition.info)
        return transition.obs.copy(), float(transition.reward), terminated, truncated, info

    def render(self):  # pragma: no cover - not needed for headless training
        return None

    def close(self):  # pragma: no cover
        return None
