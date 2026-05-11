#!/usr/bin/env python3
"""Offline SAC training from replay .npz batches (see rl/replay_recorder.py)."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def _stub_vec(obs_dim: int, act_dim: int = 2):
    import gymnasium as gym
    from gymnasium import spaces
    import numpy as np
    from stable_baselines3.common.vec_env import DummyVecEnv

    class _E(gym.Env):
        def __init__(self):
            super().__init__()
            self.observation_space = spaces.Box(
                low=-1.0, high=1.0, shape=(obs_dim,), dtype=np.float32
            )
            self.action_space = spaces.Box(
                low=-1.0, high=1.0, shape=(act_dim,), dtype=np.float32
            )

        def reset(self, *, seed=None, options=None):
            return np.zeros(self.observation_space.shape, dtype=np.float32), {}

        def step(self, action):
            z = np.zeros(self.observation_space.shape, dtype=np.float32)
            return z, 0.0, False, False, {}

    return DummyVecEnv([lambda: _E()])


def main() -> int:
    ap = argparse.ArgumentParser(description="Train SAC offline from ReplayRecorder .npz files.")
    ap.add_argument("--replay-dir", default="data/rl_replay")
    ap.add_argument("--model-path", default="models/rl_movement_policy.zip")
    ap.add_argument("--total-steps", type=int, default=200_000)
    ap.add_argument("--batch-size", type=int, default=512)
    ap.add_argument("--gamma", type=float, default=0.97)
    ap.add_argument("--tensorboard", default="runs/rl_sac")
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    replay_dir = Path(args.replay_dir)

    try:
        from rl.replay_recorder import load_replay_npzs
    except ImportError:
        repo_root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(repo_root))
        from rl.replay_recorder import load_replay_npzs

    try:
        pack = load_replay_npzs(str(replay_dir))
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    import numpy as np
    from stable_baselines3 import SAC
    from stable_baselines3.common.buffers import ReplayBuffer

    obs = pack["obs"].astype(np.float32, copy=False)
    next_obs = pack["next_obs"].astype(np.float32, copy=False)
    actions = pack["actions"].astype(np.float32, copy=False)
    rewards = pack["rewards"].astype(np.float32, copy=False)
    dones = pack["dones"].astype(np.float32, copy=False)

    n = int(obs.shape[0])
    obs_dim = int(obs.shape[1])
    act_dim = int(actions.shape[1])
    nreport = pack.get("num_transitions")
    n_rep = int(nreport.flatten()[0]) if nreport is not None else -1
    print(f"Loaded {n} transitions (num_transitions field={n_rep}); obs_dim={obs_dim}; action_dim={act_dim}")

    vec = _stub_vec(obs_dim, act_dim)
    obs_space = vec.observation_space
    act_space = vec.action_space

    buf_size = max(int(n) + 512, 500_000)
    batch_eff = max(8, min(int(args.batch_size), int(n), buf_size))

    model = SAC(
        "MlpPolicy",
        vec,
        verbose=1,
        learning_rate=3e-4,
        buffer_size=buf_size,
        batch_size=batch_eff,
        gamma=float(args.gamma),
        tau=0.005,
        train_freq=1,
        gradient_steps=1,
        ent_coef="auto",
        tensorboard_log=args.tensorboard if args.tensorboard else None,
        policy_kwargs={"net_arch": [256, 256]},
        device=args.device,
    )
    model.learning_starts = 0

    ckpt_ok = False
    if os.path.isfile(args.model_path):
        try:
            model = SAC.load(
                args.model_path,
                env=vec,
                device=args.device,
                print_system_info=False,
            )
            ckpt_loaded_dim = None
            try:
                ckpt_loaded_dim = int(model.observation_space.shape[0])  # type: ignore[union-attr]
            except Exception:
                pass
            if ckpt_loaded_dim is not None and ckpt_loaded_dim != obs_dim:
                print(
                    f"Checkpoint observation dim ({ckpt_loaded_dim}) != replay ({obs_dim}); "
                    "rebuilding SAC from replay.",
                    file=sys.stderr,
                )
                model = SAC(
                    "MlpPolicy",
                    vec,
                    verbose=1,
                    learning_rate=3e-4,
                    buffer_size=buf_size,
                    batch_size=batch_eff,
                    gamma=float(args.gamma),
                    tau=0.005,
                    train_freq=1,
                    gradient_steps=1,
                    ent_coef="auto",
                    tensorboard_log=args.tensorboard if args.tensorboard else None,
                    policy_kwargs={"net_arch": [256, 256]},
                    device=args.device,
                )
                model.learning_starts = 0
            else:
                model.learning_starts = 0
                ckpt_ok = True
                print(f"Loaded checkpoint from {args.model_path}")
        except Exception as exc:
            print(f"Checkpoint load failed ({exc}); training from freshly built SAC.", file=sys.stderr)
            model = SAC(
                "MlpPolicy",
                vec,
                verbose=1,
                learning_rate=3e-4,
                buffer_size=buf_size,
                batch_size=batch_eff,
                gamma=float(args.gamma),
                tau=0.005,
                train_freq=1,
                gradient_steps=1,
                ent_coef="auto",
                tensorboard_log=args.tensorboard if args.tensorboard else None,
                policy_kwargs={"net_arch": [256, 256]},
                device=args.device,
            )
            model.learning_starts = 0

    # Keep batch aligned with reconstructed model vs loaded (loaded may overwrite batch_size)
    if ckpt_ok and hasattr(model, "batch_size"):
        model.batch_size = max(8, min(int(model.batch_size), int(n)))

    device = model.device
    rb = ReplayBuffer(
        buffer_size=max(int(model.buffer_size), int(n) + 128),
        observation_space=obs_space,
        action_space=act_space,
        device=device,
        n_envs=1,
    )
    for i in range(n):
        rb.add(obs[i], next_obs[i], actions[i], rewards[i], dones[i], [{}])
    model.replay_buffer = rb
    print(f"Injected ReplayBuffer size={rb.size()} batch_size={model.batch_size}")

    t0 = time.time()
    model.learn(
        total_timesteps=int(args.total_steps),
        log_interval=10,
        progress_bar=False,
        reset_num_timesteps=False,
    )
    print(f"learn() done in {time.time() - t0:.1f}s")

    mp = Path(args.model_path)
    mp.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(mp))
    backup = mp.with_name(mp.stem + f"_{int(time.time())}" + mp.suffix)
    model.save(str(backup))
    print(f"Saved {mp} (backup {backup})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
