import unittest

import numpy as np

from rl.movement_env import (
    PLAYER_FEATURES,
    ENEMY_FEATURES,
    TEAMMATE_FEATURES,
    RewardConfig,
    build_observation,
    compute_reward,
    observation_size,
)
from rl.projectile_tracker import FEATURES_PER_TRACK


def _empty_projectiles(k):
    return np.zeros(k * FEATURES_PER_TRACK, dtype=np.float32)


class BuildObservationTests(unittest.TestCase):
    def test_observation_size_matches_layout(self):
        for k in (0, 1, 6, 12):
            self.assertEqual(
                observation_size(k),
                PLAYER_FEATURES + ENEMY_FEATURES + TEAMMATE_FEATURES + k * FEATURES_PER_TRACK,
            )

    def test_observation_is_zero_when_no_entities(self):
        obs = build_observation(
            player_pos=None,
            nearest_enemy_offset_distance=None,
            nearest_teammate_offset_distance=None,
            projectile_features=_empty_projectiles(6),
            frame_size=(1920, 1080),
            max_projectiles=6,
        )
        self.assertEqual(obs.dtype, np.float32)
        self.assertEqual(obs.shape, (observation_size(6),))
        self.assertEqual(obs[0], 0.0)
        self.assertEqual(obs[1], 0.0)
        self.assertEqual(obs[4], 1.0)
        self.assertEqual(obs[7], 1.0)

    def test_player_position_is_centered_when_at_screen_middle(self):
        obs = build_observation(
            player_pos=(960, 540),
            nearest_enemy_offset_distance=(0, 0, 0),
            nearest_teammate_offset_distance=None,
            projectile_features=_empty_projectiles(6),
            frame_size=(1920, 1080),
            max_projectiles=6,
        )
        self.assertAlmostEqual(obs[0], 0.0, places=4)
        self.assertAlmostEqual(obs[1], 0.0, places=4)

    def test_observation_values_clip_to_unit_range(self):
        obs = build_observation(
            player_pos=(99999, -99999),
            nearest_enemy_offset_distance=(99999, -99999, 99999),
            nearest_teammate_offset_distance=(-99999, 99999, 99999),
            projectile_features=_empty_projectiles(6),
            frame_size=(1920, 1080),
            max_projectiles=6,
        )
        self.assertTrue(np.all(obs[:8] <= 1.0))
        self.assertTrue(np.all(obs[:8] >= -1.0))


class RewardTests(unittest.TestCase):
    def test_reward_penalizes_projectile_hit(self):
        obs = np.zeros(observation_size(6), dtype=np.float32)
        obs[4] = 0.5  # in safe band
        no_hit = compute_reward(obs, projectile_hit=False)
        with_hit = compute_reward(obs, projectile_hit=True)
        self.assertGreater(no_hit, with_hit)
        cfg = RewardConfig()
        self.assertAlmostEqual(no_hit - with_hit, -cfg.projectile_hit_penalty, places=5)

    def test_episode_done_adds_survival_bonus(self):
        cfg = RewardConfig()
        obs = np.zeros(observation_size(6), dtype=np.float32)
        no_done = compute_reward(obs, projectile_hit=False, cfg=cfg, done=False)
        with_done = compute_reward(obs, projectile_hit=False, cfg=cfg, done=True)
        self.assertAlmostEqual(with_done - no_done, cfg.survival_episode_bonus, places=5)


if __name__ == "__main__":
    unittest.main()
