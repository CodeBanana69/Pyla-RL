import math
import unittest

from play import Movement, Play
from rl.projectile_tracker import ProjectileTracker


class HeuristicProjectileDodgeTests(unittest.TestCase):
    def make_play(self):
        play = object.__new__(Play)
        play.heuristic_dodge_enabled = True
        play.heuristic_dodge_scope = "all"
        play.heuristic_dodge_max_tracks = 6
        play.heuristic_dodge_horizon_seconds = 0.5
        play.heuristic_dodge_min_alignment = 0.35
        play.heuristic_dodge_min_speed_px_s = 90.0
        play.heuristic_dodge_blend = 0.8
        play.use_rl_movement = False
        play.rl_projectile_hit_radius_padding = 18.0
        play.angle_from_direction = Play.angle_from_direction
        play.blend_angles = Play.blend_angles.__get__(play, Play)
        play.is_path_blocked_angle = lambda *_args, **_kwargs: False
        play._pick_perpendicular_dodge_angle = Play._pick_perpendicular_dodge_angle.__get__(
            play, Play
        )
        play._heuristic_dodge_candidate_tracks = Play._heuristic_dodge_candidate_tracks.__get__(
            play, Play
        )
        play.compute_projectile_dodge_angle = Play.compute_projectile_dodge_angle.__get__(
            play, Play
        )
        return play

    def feed_incoming_track(self, tracker, enemy_box, start, end, t0=0.0, dt=0.1):
        tracker.update([start], now=t0, enemy_boxes=[enemy_box])
        tracker.update([end], now=t0 + dt, enemy_boxes=[enemy_box])

    def test_incoming_shot_produces_dodge(self):
        play = self.make_play()
        tracker = ProjectileTracker(
            velocity_alpha=1.0,
            require_enemy_origin=False,
            min_hits_to_promote=1,
        )
        play.projectile_tracker = tracker
        enemy = [500.0, 180.0, 540.0, 220.0]
        self.feed_incoming_track(
            tracker,
            enemy,
            [100.0, 190.0, 120.0, 210.0],
            [160.0, 190.0, 180.0, 210.0],
        )
        player_box = [180.0, 180.0, 220.0, 220.0]
        player_pos = (200.0, 200.0)
        dodge = play.compute_projectile_dodge_angle(
            player_pos,
            0.0,
            [],
            0.1,
            player_box=player_box,
        )
        self.assertIsNotNone(dodge)
        track = tracker.tracks[0]
        perp = play._pick_perpendicular_dodge_angle(player_pos, track, [])
        self.assertIsNotNone(perp)
        self.assertLess(abs((dodge - perp + 180) % 360 - 180), 25.0)

    def test_all_scope_includes_non_incoming_track(self):
        play = self.make_play()
        play.heuristic_dodge_scope = "all"
        tracker = ProjectileTracker(
            velocity_alpha=1.0,
            require_enemy_origin=False,
            min_hits_to_promote=1,
            incoming_min_alignment=0.35,
        )
        play.projectile_tracker = tracker
        enemy = [500.0, 180.0, 540.0, 220.0]
        self.feed_incoming_track(
            tracker,
            enemy,
            [100.0, 40.0, 120.0, 60.0],
            [160.0, 40.0, 180.0, 60.0],
        )
        player_pos = (200.0, 200.0)
        all_candidates = play._heuristic_dodge_candidate_tracks(player_pos)
        play.heuristic_dodge_scope = "incoming"
        incoming_candidates = play._heuristic_dodge_candidate_tracks(player_pos)
        self.assertGreaterEqual(len(all_candidates), 1)
        self.assertEqual(len(incoming_candidates), 0)

    def test_slow_track_is_ignored(self):
        play = self.make_play()
        play.heuristic_dodge_min_speed_px_s = 200.0
        tracker = ProjectileTracker(
            velocity_alpha=1.0,
            require_enemy_origin=False,
            min_hits_to_promote=1,
        )
        play.projectile_tracker = tracker
        enemy = [500.0, 180.0, 540.0, 220.0]
        self.feed_incoming_track(
            tracker,
            enemy,
            [100.0, 190.0, 120.0, 210.0],
            [110.0, 190.0, 130.0, 210.0],
            dt=0.5,
        )
        player_box = [180.0, 180.0, 220.0, 220.0]
        dodge = play.compute_projectile_dodge_angle(
            (200.0, 200.0),
            0.0,
            [],
            0.5,
            player_box=player_box,
        )
        self.assertIsNone(dodge)

    def test_disabled_dodge_returns_none(self):
        play = self.make_play()
        play.heuristic_dodge_enabled = False
        tracker = ProjectileTracker(velocity_alpha=1.0, min_hits_to_promote=1)
        play.projectile_tracker = tracker
        tracker.update([[100.0, 100.0, 120.0, 120.0]], now=0.0)
        tracker.update([[160.0, 100.0, 180.0, 120.0]], now=0.1)
        dodge = play.compute_projectile_dodge_angle(
            (200.0, 200.0),
            0.0,
            [],
            0.1,
            player_box=[180.0, 180.0, 220.0, 220.0],
        )
        self.assertIsNone(dodge)


if __name__ == "__main__":
    unittest.main()
