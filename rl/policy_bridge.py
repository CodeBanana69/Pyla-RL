"""Stable-Baselines3 policy bridge used by Play.loop().

The bridge is responsible for:
  - Building an observation from the live game data (uses the same
    helpers as the Gym env so train/inference observations match).
  - Loading or initializing a PPO policy and running ``predict`` per
    frame to choose movement.
  - Mapping the 2D action vector back to either a joystick angle
    (showdown) or a WASD string (3v3 modes), so the rest of play.py
    keeps using the existing ``do_movement`` path unchanged.
  - When training is enabled, publishing transitions to the env and
    triggering periodic ``learn(total_timesteps=N)`` calls on a worker
    thread so the game frame loop never blocks on gradient steps.

If stable-baselines3 / gymnasium are unavailable, importing this
module raises ImportError; ``Play.compute_rl_movement`` catches that
and falls back to the heuristic movement path with a one-time warning.
"""

from __future__ import annotations

import math
import os
import threading
import time
from typing import Optional, Tuple

import numpy as np

from rl.movement_env import (
    MovementEnv,
    MovementTransition,
    RewardConfig,
    build_observation,
    compute_reward,
    observation_size,
)
from rl.projectile_tracker import FEATURES_PER_TRACK


def _action_to_angle(action: np.ndarray) -> Optional[float]:
    if action is None or len(action) < 2:
        return None
    ax, ay = float(action[0]), float(action[1])
    if abs(ax) < 1e-3 and abs(ay) < 1e-3:
        return None
    return math.degrees(math.atan2(ay, ax)) % 360


def _angle_to_wasd(angle_degrees: float) -> str:
    """Convert a 0-360 angle (0=right, 90=down) to a WASD string."""
    angle = angle_degrees % 360
    parts = []
    if angle < 67.5 or angle >= 292.5:
        parts.append("D")
    if 112.5 <= angle < 247.5:
        parts.append("A")
    if 22.5 <= angle < 157.5:
        parts.append("S")
    if 202.5 <= angle < 337.5:
        parts.append("W")
    if not parts:
        parts.append("D")
    return "".join(parts)


def _action_to_movement(action: np.ndarray, is_showdown: bool):
    angle = _action_to_angle(action)
    if angle is None:
        return None if is_showdown else ""
    if is_showdown:
        return float(angle)
    return _angle_to_wasd(angle)


def _player_box_from_data(data) -> Optional[Tuple[float, float, float, float]]:
    if not data:
        return None
    players = data.get("player") or []
    if not players:
        return None
    box = players[0]
    return (float(box[0]), float(box[1]), float(box[2]), float(box[3]))


def _player_pos_from_box(box) -> Tuple[float, float]:
    return (box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5


def _nearest_offset_distance(
    boxes,
    player_pos: Tuple[float, float],
) -> Optional[Tuple[float, float, float]]:
    if not boxes:
        return None
    best = None
    best_d = float("inf")
    px, py = player_pos
    for box in boxes:
        cx = (box[0] + box[2]) * 0.5
        cy = (box[1] + box[3]) * 0.5
        dx, dy = cx - px, cy - py
        d = math.hypot(dx, dy)
        if d < best_d:
            best_d = d
            best = (dx, dy, d)
    return best


class RLMovementBridge:
    """Glue between Play.loop and Stable-Baselines3 PPO."""

    def __init__(
        self,
        model_path: str,
        is_showdown: bool,
        train: bool,
        train_steps_per_update: int = 256,
        save_every_seconds: float = 120.0,
        max_projectiles: int = 6,
        reward_cfg: Optional[RewardConfig] = None,
    ) -> None:
        try:
            from stable_baselines3 import PPO  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "stable-baselines3 is required for use_rl_movement=yes. "
                "Run python setup.py --pyla-install or pip install stable-baselines3 gymnasium."
            ) from exc

        self.model_path = model_path
        self.is_showdown = bool(is_showdown)
        self.train = bool(train)
        self.train_steps_per_update = int(train_steps_per_update)
        self.save_every_seconds = float(save_every_seconds)
        self.max_projectiles = int(max_projectiles)
        self.reward_cfg = reward_cfg or RewardConfig()

        self.env = MovementEnv(max_projectiles=self.max_projectiles, reward_cfg=self.reward_cfg)
        self.model = self._load_or_create_model()

        self._last_action = np.zeros(2, dtype=np.float32)
        self._last_obs: Optional[np.ndarray] = None
        self._steps_since_update = 0
        self._last_save_time = time.time()
        self._train_thread: Optional[threading.Thread] = None
        self._train_lock = threading.Lock()
        self._train_busy = False

        print(
            f"RL movement bridge ready (showdown={self.is_showdown}, train={self.train}, "
            f"model={self.model_path}, max_projectiles={self.max_projectiles})."
        )

    def _load_or_create_model(self):
        from stable_baselines3 import PPO

        if self.model_path and os.path.exists(self.model_path):
            try:
                model = PPO.load(self.model_path, env=self.env)
                print(f"Loaded RL movement policy from {self.model_path}")
                return model
            except Exception as exc:
                print(f"Failed to load RL policy at {self.model_path}: {exc}; creating a fresh policy.")

        model = PPO(
            "MlpPolicy",
            self.env,
            n_steps=max(64, self.train_steps_per_update),
            batch_size=64,
            verbose=0,
        )
        if self.train and self.model_path:
            try:
                os.makedirs(os.path.dirname(self.model_path) or ".", exist_ok=True)
                model.save(self.model_path)
                print(f"Saved freshly initialised RL movement policy to {self.model_path}")
            except Exception as exc:
                print(f"Could not save initial RL policy: {exc}")
        return model

    def on_match_reset(self) -> None:
        if self._last_obs is None:
            return
        transition = MovementTransition(
            obs=self._last_obs.copy(),
            reward=self.reward_cfg.survival_episode_bonus if self.train else 0.0,
            done=True,
            info={"reason": "match_reset"},
        )
        self.env.submit_transition(transition)
        self._steps_since_update = 0

    def _build_observation(self, play, data) -> Tuple[np.ndarray, Optional[Tuple[float, float, float, float]]]:
        player_box = _player_box_from_data(data)
        if player_box is None:
            return np.zeros(observation_size(self.max_projectiles), dtype=np.float32), None

        player_pos = _player_pos_from_box(player_box)
        frame = play.current_frame
        if frame is not None:
            height, width = frame.shape[:2]
        else:
            width, height = 1920, 1080
        frame_size = (width, height)

        enemy_offset = _nearest_offset_distance(data.get("enemy") or [], player_pos)
        teammate_offset = _nearest_offset_distance(data.get("teammate") or [], player_pos)

        if play.projectile_tracker is not None:
            projectile_features = play.projectile_tracker.observation_features(
                player_pos=player_pos,
                k=self.max_projectiles,
                frame_size=frame_size,
            )
        else:
            projectile_features = np.zeros(self.max_projectiles * FEATURES_PER_TRACK, dtype=np.float32)

        obs = build_observation(
            player_pos=player_pos,
            nearest_enemy_offset_distance=enemy_offset,
            nearest_teammate_offset_distance=teammate_offset,
            projectile_features=projectile_features,
            frame_size=frame_size,
            max_projectiles=self.max_projectiles,
        )
        return obs, player_box

    def _maybe_kick_training(self):
        if not self.train:
            return
        with self._train_lock:
            if self._train_busy:
                return
            if self._steps_since_update < self.train_steps_per_update:
                return
            self._train_busy = True
            steps = self._steps_since_update
            self._steps_since_update = 0

        def _run_training():
            try:
                self.model.learn(
                    total_timesteps=steps,
                    reset_num_timesteps=False,
                    progress_bar=False,
                )
                now = time.time()
                if self.model_path and now - self._last_save_time >= self.save_every_seconds:
                    try:
                        self.model.save(self.model_path)
                        self._last_save_time = now
                    except Exception as exc:
                        print(f"Saving RL movement policy failed: {exc}")
            except Exception as exc:
                print(f"RL movement training step failed: {exc}")
            finally:
                with self._train_lock:
                    self._train_busy = False

        self._train_thread = threading.Thread(target=_run_training, name="rl-train", daemon=True)
        self._train_thread.start()

    def predict(self, play, data, current_time):
        obs, player_box = self._build_observation(play, data)

        projectile_hit = False
        if (
            self.train
            and player_box is not None
            and play.projectile_tracker is not None
        ):
            projectile_hit = play.projectile_tracker.is_player_hit(
                player_box,
                now=current_time,
                padding=play.rl_projectile_hit_radius_padding,
                lookahead_seconds=0.15,
            )

        if self.train and self._last_obs is not None:
            reward = compute_reward(
                obs,
                projectile_hit=projectile_hit,
                cfg=self.reward_cfg,
                done=False,
            )
            transition = MovementTransition(
                obs=obs,
                reward=reward,
                done=False,
                info={"projectile_hit": projectile_hit},
            )
            self.env.submit_transition(transition)
            self._steps_since_update += 1
            self._maybe_kick_training()

        action, _ = self.model.predict(obs, deterministic=not self.train)
        action = np.asarray(action, dtype=np.float32).reshape(-1)
        self._last_action = action.copy()
        self._last_obs = obs.copy()

        movement = _action_to_movement(action, self.is_showdown)
        return movement
