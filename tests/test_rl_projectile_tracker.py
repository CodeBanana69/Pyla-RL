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
        tracker = ProjectileTracker(velocity_alpha=1.0)
        # Two frames so the track has a velocity heading at the player
        # at (200, 200); otherwise the direction gate would zero it out.
        tracker.update([[100, 100, 120, 120]], now=0.0)
        tracker.update([[130, 130, 150, 150]], now=0.1)
        feats = tracker.observation_features((200, 200), k=4, frame_size=(1920, 1080))
        self.assertEqual(feats.shape, (4 * FEATURES_PER_TRACK,))
        self.assertTrue(np.all(np.isfinite(feats)))
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
        # Zero-velocity tracks fail the incoming gate, so disable it for
        # this purely geometric test.
        nearest = tracker.nearest_tracks((0, 0), k=2, only_incoming=False)
        self.assertEqual(len(nearest), 2)
        self.assertLess(
            math.hypot(nearest[0].cx, nearest[0].cy),
            math.hypot(nearest[1].cx, nearest[1].cy),
        )

    def test_is_incoming_requires_velocity_toward_player(self):
        tracker = ProjectileTracker(velocity_alpha=1.0, min_speed_px_s=25.0)
        # Frame 1: projectile at (10, 100); Frame 2: at (50, 100).
        # Velocity vx=400, vy=0 — heading at +x.
        tracker.update([[0, 90, 20, 110]], now=0.0)
        tracker.update([[40, 90, 60, 110]], now=0.1)
        track = tracker.tracks[0]
        # Player is in front of the projectile -> incoming
        self.assertTrue(track.is_incoming((300, 100), min_alignment=0.5))
        # Player is behind the projectile -> not incoming
        self.assertFalse(track.is_incoming((-300, 100), min_alignment=0.5))
        # Player perpendicular -> alignment ~ 0, fails strict threshold
        self.assertFalse(track.is_incoming((50, 1000), min_alignment=0.5))

    def test_observation_features_zeroes_outgoing_tracks(self):
        tracker = ProjectileTracker(velocity_alpha=1.0, incoming_min_alignment=0.5)
        # Projectile moving away from the player at (0, 0).
        tracker.update([[100, 100, 120, 120]], now=0.0)
        tracker.update([[140, 140, 160, 160]], now=0.1)
        feats = tracker.observation_features((0, 0), k=2, frame_size=(1920, 1080))
        self.assertTrue(np.all(feats == 0.0))

    def test_is_player_hit_ignores_outgoing_projectile(self):
        tracker = ProjectileTracker(velocity_alpha=1.0, incoming_min_alignment=0.5)
        # Tracker is moving in +x but the player is far to the LEFT, so
        # the projectile is heading away from the player. Even with a
        # generous lookahead it must not register as a hit.
        tracker.update([[200, 100, 220, 120]], now=0.0)
        tracker.update([[260, 100, 280, 120]], now=0.1)
        player_box = [0, 100, 20, 120]
        self.assertFalse(
            tracker.is_player_hit(
                player_box, now=0.1, lookahead_seconds=1.0
            )
        )
        # Disabling the gate should restore the old behaviour (which would
        # never hit either since the projectile is moving away, but at
        # least the call shape is supported).
        self.assertFalse(
            tracker.is_player_hit(
                player_box,
                now=0.1,
                lookahead_seconds=1.0,
                require_incoming=False,
            )
        )

    def test_confidence_score_combines_alignment_and_speed(self):
        tracker = ProjectileTracker(velocity_alpha=1.0)
        tracker.update([[0, 100, 20, 120]], now=0.0)
        tracker.update([[40, 100, 60, 120]], now=0.1)  # vx = 400 px/s, +x
        track = tracker.tracks[0]
        toward = track.confidence_score((1000, 100), ref_speed_px_s=400.0)
        away = track.confidence_score((-1000, 100), ref_speed_px_s=400.0)
        self.assertGreater(toward, 0.5)
        self.assertLess(away, 0.1)


if __name__ == "__main__":
    unittest.main()
