"""SAC movement policy + optional transition recording for offline RL training."""

from __future__ import annotations

import math
import os
import time
from typing import Any, Dict, Optional, Tuple

import numpy as np

from rl.movement_env import RewardConfig, compute_reward_v2, episode_terminal_reward
from rl.observation_builder import ObservationBuilder, ObservationConfig, stacked_observation_size
from rl.replay_recorder import ReplayRecorder, ReplayRecorderConfig


def _action_to_angle(action: np.ndarray) -> Optional[float]:
    if action is None or len(action) < 2:
        return None
    ax, ay = float(action[0]), float(action[1])
    if abs(ax) < 1e-3 and abs(ay) < 1e-3:
        return None
    return math.degrees(math.atan2(ay, ax)) % 360


def _angle_to_wasd(angle_degrees: float) -> str:
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


def _player_box_from_data(data: Optional[Dict[str, Any]]) -> Optional[Tuple[float, float, float, float]]:
    if not data:
        return None
    players = data.get("player") or []
    if not players:
        return None
    box = players[0]
    return (float(box[0]), float(box[1]), float(box[2]), float(box[3]))


def _make_vec_stub(obs_dim: int, act_dim: int = 2):
    import gymnasium as gym
    from gymnasium import spaces
    from stable_baselines3.common.vec_env import DummyVecEnv

    class _StubMovementEnv(gym.Env):
        metadata = {"render_modes": []}

        def __init__(self) -> None:
            super().__init__()
            self.observation_space = spaces.Box(
                low=-1.0,
                high=1.0,
                shape=(obs_dim,),
                dtype=np.float32,
            )
            self.action_space = spaces.Box(
                low=-1.0,
                high=1.0,
                shape=(act_dim,),
                dtype=np.float32,
            )

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            return np.zeros(self.observation_space.shape, dtype=np.float32), {}

        def step(self, action):
            obs = np.zeros(self.observation_space.shape, dtype=np.float32)
            return obs, 0.0, False, False, {}

    return DummyVecEnv([lambda: _StubMovementEnv()])


class RLMovementBridge:
    """SAC inference; records executed transitions when ``record_transitions`` is on."""

    def __init__(
        self,
        *,
        model_path: str,
        is_showdown: bool,
        record_transitions: bool,
        replay_dir: str,
        replay_batch_size: int = 1000,
        replay_flush_seconds: float = 30.0,
        replay_disk_budget_mb: float = 2048.0,
        reward_cfg: Optional[RewardConfig] = None,
        obs_cfg: Optional[ObservationConfig] = None,
    ) -> None:
        try:
            from stable_baselines3 import SAC  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "stable-baselines3 is required for RL movement (SAC). "
                "pip install stable-baselines3 gymnasium"
            ) from exc

        self.model_path = str(model_path)
        self.is_showdown = bool(is_showdown)
        self.reward_cfg = reward_cfg or RewardConfig()

        self.obs_builder = ObservationBuilder(obs_cfg or ObservationConfig())
        self._obs_cfg = obs_cfg or ObservationConfig()
        self.obs_dim = stacked_observation_size(self._obs_cfg)

        self.record_transitions = bool(record_transitions)
        self.recorder: Optional[ReplayRecorder] = None
        if self.record_transitions:
            self.recorder = ReplayRecorder(
                cfg=ReplayRecorderConfig(
                    replay_dir=replay_dir,
                    batch_size_transitions=replay_batch_size,
                    flush_interval_seconds=replay_flush_seconds,
                    disk_budget_mb=replay_disk_budget_mb,
                    compress=True,
                ),
                session_id=self.obs_builder.session_id,
                metadata={"obs_dim": int(self.obs_dim), "algorithm": "sac"},
            )

        self._stub_vec = _make_vec_stub(self.obs_dim, 2)
        self.model = self._load_or_create_sac()

        self._last_obs_full: Optional[np.ndarray] = None
        self._prev_obs_reward: Optional[np.ndarray] = None
        self._last_action_exec: Optional[np.ndarray] = None
        self._last_reward_time = time.time()

        print(
            f"RL SAC bridge (obs_dim={self.obs_dim}, record={self.record_transitions}, "
            f"model={self.model_path})"
        )

    def _load_or_create_sac(self):
        from stable_baselines3 import SAC

        if self.model_path and os.path.exists(self.model_path):
            try:
                model = SAC.load(
                    self.model_path,
                    env=self._stub_vec,
                    device="auto",
                    print_system_info=False,
                )
                print(f"Loaded SAC from {self.model_path}")
                return model
            except Exception as exc:
                print(f"SAC load failed ({exc}); creating new policy.")

        buf = max(100_000, self.obs_dim * 500)
        model = SAC(
            "MlpPolicy",
            self._stub_vec,
            verbose=0,
            learning_rate=3e-4,
            buffer_size=buf,
            batch_size=min(512, max(128, buf // 2000)),
            gamma=0.97,
            tau=0.005,
            train_freq=1,
            gradient_steps=1,
            ent_coef="auto",
            policy_kwargs={"net_arch": [256, 256]},
            device="auto",
        )
        if self.model_path:
            try:
                os.makedirs(os.path.dirname(self.model_path) or ".", exist_ok=True)
                model.save(self.model_path)
                print(f"Saved initial SAC to {self.model_path}")
            except Exception as exc:
                print(f"Could not save initial SAC: {exc}")
        return model

    def on_match_reset(self, result: Optional[str] = None) -> None:
        term_r = float(episode_terminal_reward(result, self.reward_cfg))
        if self.recorder is not None and self._last_obs_full is not None:
            za = np.zeros(2, dtype=np.float32)
            a_exec = (
                za
                if self._last_action_exec is None
                else np.asarray(self._last_action_exec, dtype=np.float32).reshape(-1)[:2]
            )
            self.recorder.append(
                self._last_obs_full.copy(),
                a_exec,
                term_r,
                self._last_obs_full.copy(),
                True,
                {"reason": "match_reset", "result": result},
            )
            self.recorder.flush()
        self.obs_builder.reset_match()
        self._prev_obs_reward = None
        self._last_obs_full = None
        self._last_action_exec = None
        print(f"[RL SAC] episode_end result={result!s} terminal_reward={term_r:+.4f}")

    def predict(self, play: Any, data: Dict[str, Any], current_time: float):
        now_wall = time.time()
        dt = max(1e-4, float(now_wall - self._last_reward_time))
        self._last_reward_time = now_wall

        obs = self.obs_builder.build(
            play,
            data,
            current_time,
            self._last_action_exec,
            track_small_action=True,
            small_mag=self.reward_cfg.stationary_small_action_mag,
            small_needed_seconds=self.reward_cfg.stationary_need_seconds,
        )

        action_vec, _ = self.model.predict(obs, deterministic=True)
        action_vec = np.asarray(action_vec, dtype=np.float32).reshape(-1)[:2]

        player_box = _player_box_from_data(data)
        tracker_hit = False
        if player_box is not None and getattr(play, "projectile_tracker", None) is not None:
            try:
                tracker_hit = bool(
                    play.projectile_tracker.is_player_hit(
                        player_box,
                        now=current_time,
                        padding=getattr(play, "rl_projectile_hit_radius_padding", 18.0),
                        lookahead_seconds=0.15,
                    )
                )
            except Exception:
                tracker_hit = False

        dmg_hit = False
        hm = getattr(play, "health_monitor", None)
        if hm is not None:
            win = float(getattr(play, "damage_confirm_window_seconds", 0.5))
            dmg_hit = hm.recent_damage_event(current_time, win) is not None

        cross = getattr(play, "cross_reference_projectile_hits", True)
        use_intercept = bool(
            cross and getattr(play, "intercept_confirm_enabled", True)
        )
        hc = getattr(play, "hit_confirmer", None)
        if cross and use_intercept and hc is not None:
            win = float(getattr(play, "damage_confirm_window_seconds", 0.5))
            projectile_hit = bool(hc.is_recent_confirmed_hit(current_time, win))
        elif cross:
            projectile_hit = tracker_hit and dmg_hit
        else:
            projectile_hit = tracker_hit

        reward = compute_reward_v2(
            obs,
            self._prev_obs_reward,
            play,
            data,
            current_time,
            dt,
            self.reward_cfg,
            projectile_hit=projectile_hit,
            hp_damage=dmg_hit,
            last_action=self._last_action_exec,
            ob_state=self.obs_builder.state,
        )

        if self.recorder is not None and self._prev_obs_reward is not None and self._last_action_exec is not None:
            self.recorder.append(
                self._prev_obs_reward.copy(),
                self._last_action_exec.copy(),
                float(reward),
                obs.copy(),
                False,
                {"penalty_hit": dmg_hit if self.reward_cfg.use_hp_drop_penalty else projectile_hit},
            )

        self._prev_obs_reward = obs.copy()
        self._last_obs_full = obs.copy()
        self._last_action_exec = action_vec.copy()

        return _action_to_movement(action_vec, self.is_showdown)
