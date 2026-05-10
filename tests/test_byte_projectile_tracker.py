"""Optional ByteTrack wrapper tests (requires supervision)."""

from __future__ import annotations

import unittest

from rl.byte_projectile_tracker import BYTE_TRACK_AVAILABLE, ByteProjectileTracker


@unittest.skipUnless(BYTE_TRACK_AVAILABLE, "supervision ByteTrack not installed")
class ByteProjectileTrackerTests(unittest.TestCase):
    def test_two_frame_track_has_id(self) -> None:
        t = ByteProjectileTracker(
            minimum_matching_threshold=0.3,
            track_activation_threshold=0.5,
            lost_track_buffer_frames=45,
            frame_rate=30.0,
            min_hits_to_promote=1,
            incoming_min_alignment=-1.0,
            min_speed_px_s=0.0,
        )
        enemy = [[300.0, 300.0, 360.0, 360.0]]
        t.update(
            [[100.0, 100.0, 120.0, 120.0]],
            now=0.0,
            enemy_boxes=enemy,
            box_sources=["labeled"],
        )
        tr1 = t.update(
            [[105.0, 100.0, 125.0, 120.0]],
            now=0.033,
            enemy_boxes=enemy,
            box_sources=["labeled"],
        )
        self.assertTrue(len(tr1) >= 1)
        self.assertEqual(tr1[0].track_id, 1)


if __name__ == "__main__":
    unittest.main()
