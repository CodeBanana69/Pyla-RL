"""Lightweight checks that live RL training wiring won't shape-mismatch."""

import unittest

import numpy as np


def _have_gymnasium():
    try:
        import gymnasium  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(_have_gymnasium(), "gymnasium not installed")
class MovementEnvTrainingSmokeTests(unittest.TestCase):
    def test_externally_submitted_step_is_not_empty(self):
        from rl.movement_env import MovementEnv, MovementTransition, observation_size

        k = 6
        env = MovementEnv(max_projectiles=k)
        obs = np.zeros(observation_size(k), dtype=np.float32)
        env.submit_transition(MovementTransition(obs=obs.copy(), reward=0.01, done=False, info={}))
        action = env.action_space.sample()
        obs2, reward, terminated, truncated, info = env.step(action)
        self.assertFalse(info.get("empty", False))
        self.assertEqual(obs2.shape, obs.shape)
        self.assertGreater(float(reward), -1e6)

    def test_max_projectiles_changes_observation_space(self):
        from rl.movement_env import MovementEnv, observation_size

        e4 = MovementEnv(max_projectiles=4)
        e8 = MovementEnv(max_projectiles=8)
        self.assertEqual(e4.observation_space.shape, (observation_size(4),))
        self.assertEqual(e8.observation_space.shape, (observation_size(8),))


def _have_sb3():
    try:
        from stable_baselines3 import SAC  # noqa: F401

        return True
    except Exception:
        return False


@unittest.skipUnless(_have_gymnasium() and _have_sb3(), "sb3/gymnasium not installed")
class SACBridgeShapeTests(unittest.TestCase):
    def test_sac_predict_matches_rich_obs_dim(self):
        from stable_baselines3 import SAC

        from rl.observation_builder import ObservationConfig, stacked_observation_size
        from rl.policy_bridge import _make_vec_stub

        cfg = ObservationConfig(frame_stack=2)
        dim = stacked_observation_size(cfg)
        vec = _make_vec_stub(dim, 2)
        model = SAC("MlpPolicy", vec, verbose=0, learning_starts=1000, train_freq=999_999)
        obs = np.zeros(dim, dtype=np.float32)
        action, _ = model.predict(obs, deterministic=True)
        action = np.asarray(action, dtype=np.float32).reshape(-1)
        self.assertEqual(action.shape, (2,))


if __name__ == "__main__":
    unittest.main()
