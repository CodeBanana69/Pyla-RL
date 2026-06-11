import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from main import STUCK_RECOVERY_STATES, run_stuck_recovery


def _worker(**overrides):
    stage_manager = SimpleNamespace(states={"reward_unlock": MagicMock()})
    window_controller = SimpleNamespace(
        emulator_autorestart=True,
        keys_up=MagicMock(),
        press_key=MagicMock(),
        restart_emulator_profile=MagicMock(return_value=True),
        screenshot=MagicMock(return_value=None),
    )
    worker = SimpleNamespace(
        in_cooldown=False,
        lobby_start_retry_interval=8.0,
        lobby_stuck_restart_seconds=120.0,
        stuck_since=time.time() - 130,
        last_stuck_recovery_press=0.0,
        stuck_app_restart_count=0,
        last_stuck_recovery_at=0.0,
        lobby_entered_at=None,
        last_lobby_start_press=0.0,
        ping_when_stuck=False,
        Stage_manager=stage_manager,
        window_controller=window_controller,
        restart_brawl_stars=MagicMock(return_value=True),
    )
    for key, value in overrides.items():
        setattr(worker, key, value)
    return worker


class StuckRecoveryTests(unittest.TestCase):
    def test_stuck_recovery_resets_on_match(self):
        worker = _worker(
            stuck_since=time.time(),
            stuck_app_restart_count=2,
            lobby_entered_at=time.time(),
        )
        self.assertFalse(run_stuck_recovery(worker, "match"))
        self.assertIsNone(worker.stuck_since)
        self.assertEqual(worker.stuck_app_restart_count, 0)

    def test_stuck_recovery_restarts_app_then_emulator(self):
        worker = _worker()
        self.assertTrue(run_stuck_recovery(worker, "reward_unlock"))
        worker.restart_brawl_stars.assert_called_once()

        worker.stuck_since = time.time() - 260
        worker.last_stuck_recovery_at = 0.0
        worker.stuck_app_restart_count = 2
        self.assertTrue(run_stuck_recovery(worker, "reward_unlock"))
        worker.window_controller.restart_emulator_profile.assert_called_once_with()

    def test_stuck_recovery_states_include_reward_unlock(self):
        self.assertIn("reward_unlock", STUCK_RECOVERY_STATES)


if __name__ == "__main__":
    unittest.main()
