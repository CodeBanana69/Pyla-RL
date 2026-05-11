import unittest

import numpy as np

from rl.movement_env import (
    PLAYER_FEATURES,
    ENEMY_FEATURES,
    TEAMMATE_FEATURES,
    RewardConfig,
    build_observation,
    compute_reward,
    episode_terminal_reward,
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

    def test_observation_has_eight_when_no_projectiles_slot(self):
        obs = build_observation(
            player_pos=None,
            nearest_enemy_offset_distance=None,
            nearest_teammate_offset_distance=None,
            projectile_features=np.zeros(0, dtype=np.float32),
            frame_size=(1920, 1080),
            max_projectiles=0,
        )
        self.assertEqual(obs.shape[0], 8)


class RewardTests(unittest.TestCase):
    def test_reward_penalizes_projectile_hit(self):
        obs = np.zeros(observation_size(6), dtype=np.float32)
        obs[4] = 0.5  # in safe band
        no_hit = compute_reward(obs, projectile_hit=False)
        with_hit = compute_reward(obs, projectile_hit=True)
        self.assertGreater(no_hit, with_hit)
        cfg = RewardConfig()
        self.assertAlmostEqual(no_hit - with_hit, -cfg.projectile_hit_penalty, places=5)

    def test_hp_drop_penalty_independent_of_projectile_flag(self):
        obs = np.zeros(observation_size(6), dtype=np.float32)
        obs[4] = 0.5
        cfg = RewardConfig(use_hp_drop_penalty=True)
        base = compute_reward(obs, projectile_hit=True, hp_damage=False, cfg=cfg)
        with_hp = compute_reward(obs, projectile_hit=False, hp_damage=True, cfg=cfg)
        self.assertAlmostEqual(base - with_hp, -cfg.hp_drop_penalty, places=5)

    def test_episode_terminal_reward_showdown_and_fallback(self):
        cfg = RewardConfig(episode_end_fallback_reward=-2.5)
        self.assertAlmostEqual(episode_terminal_reward("1st", cfg), 3.0)
        self.assertAlmostEqual(episode_terminal_reward("4th", cfg), -1.5)
        self.assertAlmostEqual(episode_terminal_reward(None, cfg), -2.5)
        self.assertAlmostEqual(episode_terminal_reward("", cfg), -2.5)


if __name__ == "__main__":
    unittest.main()
