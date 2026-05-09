import math
import unittest

import numpy as np

from rl.projectile_tracker import (
    FEATURES_PER_TRACK,
    ProjectileTracker,
    extract_projectile_boxes,
)


class ProjectileTrackerTests(unittest.TestCase):
    def test_extract_projectile_boxes_filters_by_class(self):
        data = {
            "player": [[0, 0, 10, 10]],
            "enemy": [[100, 100, 120, 120]],
            "projectile": [[200, 200, 220, 220]],
            "super": [[300, 300, 340, 340]],
        }
        boxes = extract_projectile_boxes(data, ["projectile", "super", "missing"])
        self.assertEqual(len(boxes), 2)
        self.assertEqual(boxes[0], [200.0, 200.0, 220.0, 220.0])
        self.assertEqual(boxes[1], [300.0, 300.0, 340.0, 340.0])

    def test_velocity_is_estimated_from_consecutive_frames(self):
        tracker = ProjectileTracker(velocity_alpha=1.0)
        tracker.update([[100, 100, 120, 120]], now=0.0)
        tracker.update([[120, 100, 140, 120]], now=0.1)
        tracks = tracker.tracks
        self.assertEqual(len(tracks), 1)
        self.assertAlmostEqual(tracks[0].vx, 200.0, places=2)
        self.assertAlmostEqual(tracks[0].vy, 0.0, places=2)

    def test_track_dies_after_history_seconds(self):
        tracker = ProjectileTracker(history_seconds=0.2)
        tracker.update([[100, 100, 120, 120]], now=0.0)
        tracker.update([], now=0.5)
        self.assertEqual(len(tracker.tracks), 0)

    def test_is_player_hit_uses_lookahead(self):
        tracker = ProjectileTracker(velocity_alpha=1.0)
        tracker.update([[0, 100, 20, 120]], now=0.0)
        tracker.update([[40, 100, 60, 120]], now=0.1)  # vx ~= 400 px/s
        # player box is 100 px ahead and tracker hasn't reached yet
        player_box = [180, 100, 200, 120]
        self.assertFalse(
            tracker.is_player_hit(player_box, now=0.1, lookahead_seconds=0.0)
        )
        self.assertTrue(
            tracker.is_player_hit(player_box, now=0.1, lookahead_seconds=0.5)
        )

    def test_observation_features_shape_and_padding(self):
        tracker = ProjectileTracker()
        tracker.update([[100, 100, 120, 120]], now=0.0)
        feats = tracker.observation_features((200, 200), k=4, frame_size=(1920, 1080))
        self.assertEqual(feats.shape, (4 * FEATURES_PER_TRACK,))
        self.assertTrue(np.all(np.isfinite(feats)))
        # First slot has the only track; remaining slots are zero-padded
        self.assertTrue(np.any(feats[:FEATURES_PER_TRACK] != 0.0))
        self.assertTrue(np.all(feats[FEATURES_PER_TRACK:] == 0.0))

    def test_nearest_tracks_are_sorted_by_distance(self):
        tracker = ProjectileTracker()
        tracker.update(
            [
                [0, 0, 10, 10],          # close
                [500, 0, 510, 10],       # mid
                [1000, 1000, 1010, 1010] # far
            ],
            now=0.0,
        )
        nearest = tracker.nearest_tracks((0, 0), k=2)
        self.assertEqual(len(nearest), 2)
        self.assertLess(
            math.hypot(nearest[0].cx, nearest[0].cy),
            math.hypot(nearest[1].cx, nearest[1].cy),
        )


if __name__ == "__main__":
    unittest.main()
