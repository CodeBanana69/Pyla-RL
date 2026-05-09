import math
import unittest

import numpy as np

from rl.projectile_tracker import (
    FEATURES_PER_TRACK,
    ProjectileTracker,
    cluster_bounding_box,
    cluster_tracks_by_distance,
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

    def test_track_born_near_enemy_is_marked_from_enemy(self):
        tracker = ProjectileTracker(velocity_alpha=1.0, enemy_origin_radius=80.0)
        tracker.update(
            [[200, 100, 220, 120]],
            now=0.0,
            enemy_boxes=[[170, 70, 240, 140]],
            friendly_boxes=[[1500, 800, 1560, 860]],
        )
        track = tracker.tracks[0]
        self.assertIs(track.from_enemy, True)

    def test_track_born_away_from_enemy_is_filtered_out(self):
        tracker = ProjectileTracker(
            velocity_alpha=1.0,
            enemy_origin_radius=80.0,
            incoming_min_alignment=-1.0,  # disable direction gate for this test
            min_speed_px_s=0.0,
        )
        # Spawn point is far from the only enemy box.
        tracker.update(
            [[1000, 1000, 1020, 1020]],
            now=0.0,
            enemy_boxes=[[100, 100, 160, 160]],
            friendly_boxes=[[500, 500, 560, 560]],
        )
        # Frame 2: give it any velocity.
        tracker.update(
            [[1020, 1000, 1040, 1020]],
            now=0.1,
            enemy_boxes=[[100, 100, 160, 160]],
            friendly_boxes=[[500, 500, 560, 560]],
        )
        track = tracker.tracks[0]
        self.assertIs(track.from_enemy, False)
        # incoming_tracks must drop it even though it has velocity
        self.assertEqual(tracker.incoming_tracks((1500, 1000)), [])
        # is_player_hit on a player box overlapping its current pos must
        # NOT fire because the projectile is not enemy-spawned.
        self.assertFalse(
            tracker.is_player_hit([1015, 995, 1045, 1025], now=0.1)
        )

    def test_track_born_near_player_is_friendly_fire(self):
        tracker = ProjectileTracker(velocity_alpha=1.0)
        # Spawn point is right next to the player; even though there's
        # also an enemy nearby, the friendly proximity wins.
        tracker.update(
            [[510, 500, 530, 520]],
            now=0.0,
            enemy_boxes=[[400, 400, 460, 460]],
            friendly_boxes=[[490, 480, 540, 530]],
        )
        track = tracker.tracks[0]
        self.assertIs(track.from_enemy, False)

    def test_unknown_origin_is_kept_when_no_entities_visible(self):
        tracker = ProjectileTracker(velocity_alpha=1.0)
        tracker.update([[100, 100, 120, 120]], now=0.0)
        tracker.update([[140, 100, 160, 120]], now=0.1)
        track = tracker.tracks[0]
        self.assertIsNone(track.from_enemy)
        # Direction gate should still let it through because the track
        # is moving toward the (300, 100) player pos and origin is unknown.
        self.assertEqual(len(tracker.incoming_tracks((300, 100))), 1)

    def test_require_enemy_origin_can_be_disabled(self):
        tracker = ProjectileTracker(
            velocity_alpha=1.0,
            require_enemy_origin=False,
            incoming_min_alignment=-1.0,
            min_speed_px_s=0.0,
        )
        tracker.update(
            [[1000, 1000, 1020, 1020]],
            now=0.0,
            enemy_boxes=[[100, 100, 160, 160]],
        )
        tracker.update(
            [[1020, 1000, 1040, 1020]],
            now=0.1,
            enemy_boxes=[[100, 100, 160, 160]],
        )
        # from_enemy is still recorded as False but the gate is off, so
        # the track passes through.
        self.assertIs(tracker.tracks[0].from_enemy, False)
        self.assertEqual(len(tracker.incoming_tracks((1500, 1000))), 1)

    def test_confidence_score_combines_alignment_and_speed(self):
        tracker = ProjectileTracker(velocity_alpha=1.0)
        tracker.update([[0, 100, 20, 120]], now=0.0)
        tracker.update([[40, 100, 60, 120]], now=0.1)  # vx = 400 px/s, +x
        track = tracker.tracks[0]
        toward = track.confidence_score((1000, 100), ref_speed_px_s=400.0)
        away = track.confidence_score((-1000, 100), ref_speed_px_s=400.0)
        self.assertGreater(toward, 0.5)
        self.assertLess(away, 0.1)

    def test_birth_inside_ui_rect_skipped(self):
        tracker = ProjectileTracker(
            velocity_alpha=1.0,
            incoming_min_alignment=-1.0,
            min_speed_px_s=0.0,
        )
        ui = [[0.0, 0.0, 50.0, 50.0]]
        tracker.update([[10, 10, 20, 20]], now=0.0, ui_exclude_boxes=ui)
        self.assertEqual(len(tracker.tracks), 0)

    def test_cluster_tracks_groups_close_and_separates_far(self):
        tracker = ProjectileTracker(
            velocity_alpha=1.0,
            incoming_min_alignment=-1.0,
            min_speed_px_s=0.0,
        )
        tracker.update(
            [
                [100, 100, 110, 110],
                [120, 100, 130, 110],
                [800, 800, 810, 810],
            ],
            now=0.0,
        )
        clusters = cluster_tracks_by_distance(tracker.tracks, max_distance=50.0)
        sizes = sorted(len(c) for c in clusters)
        self.assertEqual(sizes, [1, 2])
        bigger = next(c for c in clusters if len(c) == 2)
        bb = cluster_bounding_box(bigger)
        self.assertIsNotNone(bb)
        self.assertLess(bb[0], 130)
        self.assertGreater(bb[2], 110)

    def test_min_hits_blocks_incoming_until_promoted(self):
        tracker = ProjectileTracker(
            velocity_alpha=1.0,
            min_hits_to_promote=2,
            incoming_min_alignment=-1.0,
            min_speed_px_s=0.0,
        )
        tracker.update([[100, 100, 120, 120]], now=0.0)
        self.assertEqual(len(tracker.incoming_tracks((300, 100))), 0)
        tracker.update([[130, 100, 150, 120]], now=0.1)
        self.assertEqual(len(tracker.incoming_tracks((300, 100))), 1)


if __name__ == "__main__":
    unittest.main()
