"""Tests for rl/replay_recorder.py."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from rl.replay_recorder import ReplayRecorder, ReplayRecorderConfig, load_replay_npzs


class ReplayRecorderTests(unittest.TestCase):
    def test_roundtrip_npz(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = ReplayRecorderConfig(
                replay_dir=td,
                batch_size_transitions=10_000,
                flush_interval_seconds=9999.0,
            )
            rec = ReplayRecorder(cfg=cfg, session_id="utest", metadata={"k": "v"})
            obs = np.random.randn(27).astype(np.float32)
            nxt = np.random.randn(27).astype(np.float32)
            act = np.array([0.2, -0.3], dtype=np.float32)
            rec.append(obs, act, 0.25, nxt, False, {"t": 1})
            rec.flush()
            files = list(Path(td).glob("*.npz"))
            self.assertEqual(len(files), 1)
            pack = load_replay_npzs(td)
            self.assertEqual(int(pack["num_transitions"][0]), 1)
            self.assertTrue(np.allclose(pack["obs"][0], obs))
            self.assertTrue(np.allclose(pack["next_obs"][0], nxt))
            self.assertTrue(np.allclose(pack["actions"][0], act))
            self.assertAlmostEqual(float(pack["rewards"][0]), 0.25)
            self.assertEqual(float(pack["dones"][0]), 0.0)

    def test_load_replay_num_transitions_matches_rows(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.npz"
            n = 5
            obs = np.zeros((n, 12), dtype=np.float32)
            np.savez_compressed(
                p,
                obs=obs,
                next_obs=obs,
                actions=np.zeros((n, 2), dtype=np.float32),
                rewards=np.zeros(n, dtype=np.float32),
                dones=np.zeros(n, dtype=np.float32),
            )
            pack = load_replay_npzs(td)
            self.assertEqual(pack["obs"].shape[0], n)
            self.assertEqual(int(pack["num_transitions"][0]), n)


if __name__ == "__main__":
    unittest.main()
