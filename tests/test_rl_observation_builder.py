"""Tests for rl/observation_builder.py (rich SAC observations)."""

import unittest
from unittest.mock import MagicMock

import numpy as np

from rl.observation_builder import (
    OB_ENEMY1_DIST,
    OB_LAST_AX,
    OB_LAST_AY,
    OB_PLAYER_CX,
    OB_VX,
    OB_VY,
    ObservationBuilder,
    ObservationConfig,
    SINGLE_OBS_DIM,
    stacked_observation_size,
    stationary_seconds,
    wall_quadrant_counts,
)


class _StubHM:
    last_hp_ok = True
    last_hp_pct = 0.72
    _damage_events = []


class _StubPlay:
    current_frame = None
    is_super_ready = True
    should_use_gadget = False
    is_gadget_ready = True
    health_monitor = _StubHM()

    def _build_trusted_fog_mask(self, frame, roi_center=None, roi_radius=0):
        return None


class ObservationBuilderTests(unittest.TestCase):
    def test_stacked_size(self):
        c1 = ObservationConfig(frame_stack=1)
        c4 = ObservationConfig(frame_stack=4)
        self.assertEqual(stacked_observation_size(c1), SINGLE_OBS_DIM)
        self.assertEqual(stacked_observation_size(c4), SINGLE_OBS_DIM * 4)

    def test_velocity_finite_diff_and_none_prev(self):
        play = _StubPlay()
        b = ObservationBuilder(ObservationConfig(frame_stack=1))
        data1 = {"player": [[100.0, 200.0, 120.0, 220.0]], "enemy": [], "teammate": [], "wall": []}
        o1 = b.build(play, data1, 0.0, None)
        self.assertEqual(o1.shape, (SINGLE_OBS_DIM,))
        self.assertEqual(float(o1[OB_VX]), 0.0)
        self.assertEqual(float(o1[OB_VY]), 0.0)
        data2 = {"player": [[112.0, 200.0, 132.0, 220.0]], "enemy": [], "teammate": [], "wall": []}
        o2 = b.build(play, data2, 0.1, np.array([0.5, 0.0], dtype=np.float32))
        self.assertNotEqual(float(o2[OB_VX]), 0.0)

    def test_frame_stack_pads_zeros(self):
        play = _StubPlay()
        cfg = ObservationConfig(frame_stack=3, use_fog=False, use_walls=False)
        b = ObservationBuilder(cfg)
        data = {"player": [[400.0, 300.0, 420.0, 320.0]], "enemy": [], "teammate": [], "wall": []}
        stacked = b.build(play, data, 0.0, None)
        self.assertEqual(stacked.shape, (SINGLE_OBS_DIM * 3,))
        self.assertTrue(np.all(stacked[: SINGLE_OBS_DIM * 2] == 0.0))
        self.assertNotEqual(float(stacked[-SINGLE_OBS_DIM + OB_PLAYER_CX]), 0.0)

    def test_fog_ablated_sets_clear(self):
        play = _StubPlay()
        cfg = ObservationConfig(use_fog=False, frame_stack=1)
        b = ObservationBuilder(cfg)
        data = {"player": [[400.0, 300.0, 420.0, 320.0]], "enemy": [], "teammate": [], "wall": []}
        o = b.build(play, data, 0.0, None)
        fog = o[17:21]
        self.assertTrue(np.all(fog >= 0.99))

    def test_last_action_written(self):
        play = _StubPlay()
        b = ObservationBuilder(ObservationConfig(frame_stack=1))
        data = {"player": [[400.0, 300.0, 420.0, 320.0]], "enemy": [], "teammate": [], "wall": []}
        la = np.array([-0.25, 0.75], dtype=np.float32)
        o = b.build(play, data, 0.0, la)
        self.assertAlmostEqual(float(o[OB_LAST_AX]), -0.25, places=5)
        self.assertAlmostEqual(float(o[OB_LAST_AY]), 0.75, places=5)

    def test_wall_quadrant_counts_bins(self):
        px, py = 100.0, 100.0
        walls = [
            [110.0, 90.0, 120.0, 100.0],  # NE quadrant from (100,100) -> cx>= px, cy < py ??? 
            # For (110,95): cx>=100, cy<100 -> q0
        ]
        qs = wall_quadrant_counts(walls, (px, py))
        self.assertGreaterEqual(sum(qs), 1)


class StationarySecondsTests(unittest.TestCase):
    def test_tracks_under_threshold(self):
        from rl.observation_builder import ObservationBuilderState

        st = ObservationBuilderState()
        st.small_action_since = 10.0
        la = np.array([0.01, 0.0], dtype=np.float32)
        self.assertGreaterEqual(stationary_seconds(st, 12.5, 0.1, la), 2.4)


class RewardSizedObsTests(unittest.TestCase):
    def test_gaussian_peak_at_band_mid_for_enemy(self):
        from rl.movement_env import RewardConfig, compute_reward_v2

        cfg = RewardConfig(
            safe_distance_band_min=0.35,
            safe_distance_band_max=0.75,
            fog_proximity_penalty=0.0,
            wall_hug_penalty=0.0,
            stationary_penalty=0.0,
        )
        tail = np.zeros(SINGLE_OBS_DIM, dtype=np.float32)
        mid = (cfg.safe_distance_band_min + cfg.safe_distance_band_max) * 0.5
        tail[int(OB_ENEMY1_DIST)] = mid
        tail[17:21] = 1.0  # fog clear
        obs = tail.copy()

        mp = MagicMock()
        mp.health_monitor = None
        mp.damage_confirm_window_seconds = 0.5
        data = {"player": [[0, 0, 10, 10]], "wall": [], "enemy": []}

        reward_mid = compute_reward_v2(obs, obs, mp, data, 0.0, 1.0 / 30.0, cfg)

        tail2 = tail.copy()
        tail2[int(OB_ENEMY1_DIST)] = 0.01
        tail2[17:21] = 1.0
        obs2 = tail2.copy()
        reward_edge = compute_reward_v2(obs2, obs2, mp, data, 0.0, 1.0 / 30.0, cfg)
        self.assertGreater(reward_mid, reward_edge)

    def test_hp_potential_sign(self):
        from rl.observation_builder import OB_HP_FRAC
        from rl.movement_env import RewardConfig, compute_reward_v2

        cfg = RewardConfig(
            hp_potential_coef=1.0,
            fog_proximity_penalty=0.0,
            wall_hug_penalty=0.0,
            stationary_penalty=0.0,
            safe_distance_bonus=0.0,
            teammate_proximity_bonus=0.0,
        )
        prev = np.zeros(SINGLE_OBS_DIM, dtype=np.float32)
        prev[OB_HP_FRAC] = 0.9
        prev[17:21] = 1.0
        cur = prev.copy()
        cur[OB_HP_FRAC] = 0.4
        cur[17:21] = 1.0
        mp = MagicMock()
        mp.health_monitor = None
        mp.damage_confirm_window_seconds = 0.5
        data = {"player": [[0, 0, 10, 10]], "wall": [], "enemy": []}
        r = compute_reward_v2(cur, prev, mp, data, 0.0, 1.0 / 30.0, cfg)
        base = cfg.survival_per_step
        self.assertLess(r - base, 0.0)


if __name__ == "__main__":
    unittest.main()
