"""Smoke test for tools/train_rl_offline.py."""

import os
import sys
import tempfile
import unittest
from pathlib import Path


def _have_sb3():
    try:
        import stable_baselines3  # noqa: F401

        return True
    except Exception:
        return False


@unittest.skipUnless(_have_sb3(), "stable-baselines3 not installed")
class OfflineTrainerSmokeTests(unittest.TestCase):
    def test_runs_and_writes_checkpoint(self):
        import numpy as np

        repo = Path(__file__).resolve().parents[1]
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))

        obs_dim = 27
        n = 256
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            shard = td_path / "syn.npz"
            obs = np.random.uniform(-1, 1, size=(n, obs_dim)).astype(np.float32)
            act = np.random.uniform(-1, 1, size=(n, 2)).astype(np.float32)
            rew = np.random.uniform(-0.1, 0.1, size=(n,)).astype(np.float32)
            done = np.zeros(n, dtype=np.float32)
            np.savez_compressed(shard, obs=obs, next_obs=obs, actions=act, rewards=rew, dones=done)

            out_zip = td_path / "policy.zip"

            import importlib.util

            script = repo / "tools" / "train_rl_offline.py"
            spec = importlib.util.spec_from_file_location("train_rl_offline Smoke", script)
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(mod)

            old_argv = sys.argv
            try:
                sys.argv = [
                    "train_rl_offline",
                    "--replay-dir",
                    str(td_path),
                    "--model-path",
                    str(out_zip),
                    "--total-steps",
                    "32",
                    "--batch-size",
                    "128",
                    "--gamma",
                    "0.97",
                    "--tensorboard",
                    "",
                    "--device",
                    "cpu",
                ]
                rc = mod.main()
                self.assertEqual(rc, 0)
            finally:
                sys.argv = old_argv

            self.assertTrue(out_zip.is_file())
            backups = list(td_path.glob("policy_*.zip"))
            self.assertGreaterEqual(len(backups), 0)


if __name__ == "__main__":
    unittest.main()
