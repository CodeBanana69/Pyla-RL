"""Unit tests for rl.hit_confirmer.HitConfirmer."""

from __future__ import annotations

import unittest

from rl.health_monitor import DamageEvent
from rl.hit_confirmer import HitConfirmer
from rl.projectile_tracker import ProjectileTracker


class HitConfirmerTests(unittest.TestCase):
    def test_confirms_when_damage_near_expected_hit(self) -> None:
        hc = HitConfirmer(history_seconds=2.0)
        tr = ProjectileTracker(velocity_alpha=1.0, min_hits_to_promote=1, incoming_min_alignment=-1.0)
        tr._tracks.clear()
        hc.record_pending_intercepts([(1, 0.05)], now=1.0)
        hc.record_damage(DamageEvent(time=1.04, drop_pct=0.05))
        out = hc.confirm(tr, now=1.05, tolerance_seconds=0.3)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out.track_id, 1)
        self.assertTrue(hc.is_recent_confirmed_hit(1.1, 0.5))

    def test_no_confirm_outside_tolerance(self) -> None:
        hc = HitConfirmer(history_seconds=2.0)
        tr = ProjectileTracker(min_hits_to_promote=1)
        hc.record_pending_intercepts([(1, 0.05)], now=0.0)
        hc.record_damage(DamageEvent(time=1.0, drop_pct=0.05))
        out = hc.confirm(tr, now=1.0, tolerance_seconds=0.01)
        self.assertIsNone(out)
        self.assertFalse(hc.is_recent_confirmed_hit(1.0, 0.2))


if __name__ == "__main__":
    unittest.main()
