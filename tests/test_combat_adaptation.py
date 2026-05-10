import math
import unittest

from play import Play


class CombatAdaptationTests(unittest.TestCase):
    def setUp(self):
        self.movement = object.__new__(Play)
        self.movement._strafe_started_at = 0.0
        self.movement._strafe_side = 1
        self.movement._strafe_current_interval = 0.0
        self.movement.strafe_interval = 1.0
        self.movement.strafe_enabled = True
        self.movement.combat_dodge_blend = 0.65
        self.movement.combat_dodge_jitter_degrees = 0.0
        self.movement.projectile_speed_px_s = 900.0

    def test_strafe_angle_smoothly_flips_after_interval(self):
        first = self.movement.get_strafe_angle(0, 10.0)
        second = self.movement.get_strafe_angle(0, 11.2)
        self.assertAlmostEqual(first, 49.5)
        self.assertGreater(second, 180)
        self.assertLess(second, 360)

    def test_lead_shot_falls_back_to_direct_when_unsolvable(self):
        angle = self.movement.lead_shot_angle((0, 0), (100, 0), (3000, 0), projectile_speed_px_s=100)
        self.assertAlmostEqual(angle, 0.0)

    def test_lead_shot_aims_ahead_of_moving_target(self):
        angle = self.movement.lead_shot_angle((0, 0), (900, 0), (0, 300), projectile_speed_px_s=900)
        self.assertGreater(angle, 0.0)
        self.assertLess(angle, 45.0)
        self.assertFalse(math.isnan(angle))

    def test_combat_dodge_biases_shooting_movement_sideways(self):
        desired = self.movement.apply_combat_dodge(
            desired_angle=0,
            toward_enemy_angle=0,
            current_time=10.0,
            enemy_distance=180,
            safe_range=120,
        )

        self.assertGreater(desired, 25)
        self.assertLess(desired, 90)

    def test_movement_to_vector_converts_legacy_keys(self):
        self.assertEqual(self.movement.movement_to_vector("wd"), (1, -1))
        self.assertEqual(self.movement.movement_to_vector("as"), (-1, 1))

    def test_playstyle_env_exposes_biomistik_helpers(self):
        play = object.__new__(Play)
        play.playstyle_code = compile(
            "movement = 270.0 if angle_to_keys(270) == 'W' and get_distance((0, 0), (3, 4)) == 5.0 else None",
            "<test_playstyle>",
            "exec",
        )
        play.time_since_holding_attack = None
        play.TILE_SIZE = 60
        play.brawlers_info = {}
        play.game_mode = 3
        play.seconds_to_hold_attack_after_reaching_max = 1.5
        play.is_hypercharge_ready = False
        play.should_use_gadget = False
        play.is_gadget_ready = False
        play.is_super_ready = False
        play.attack = lambda *args, **kwargs: True
        play.use_hypercharge = lambda: True
        play.use_gadget = lambda: True
        play.use_super = lambda: True
        play.clear_ability_ready = lambda _ability: None
        play.should_use_super_on_enemy = lambda *args, **kwargs: False
        play.must_brawler_hold_attack = lambda *args, **kwargs: False
        play.get_brawler_range = lambda _brawler: (100, 200, 300)
        play.get_player_pos = lambda _player: (50, 50)
        play.get_entity_pos = lambda _entity: (50, 50)
        play.is_there_enemy = lambda _enemy: False
        play.is_there_poison_gas = lambda *_args, **_kwargs: False
        play.no_enemy_movement = lambda *_args, **_kwargs: "W"
        play.find_closest_enemy = lambda *_args, **_kwargs: (None, None)
        play.find_closest_teammate = lambda *_args, **_kwargs: (None, None)
        play.get_horizontal_move_key = lambda *_args, **_kwargs: "D"
        play.get_vertical_move_key = lambda *_args, **_kwargs: "W"
        play.is_path_blocked = lambda *_args, **_kwargs: False
        play.is_path_blocked_angle = lambda *_args, **_kwargs: False
        play.is_enemy_hittable = lambda *_args, **_kwargs: False
        play.walls_block_line_of_sight = lambda *_args, **_kwargs: False
        play.aimed_attack = lambda *_args, **_kwargs: True
        play.get_distance = Play.get_distance
        play.angle_from_direction = lambda *_args, **_kwargs: 0.0
        play.find_best_angle = lambda _player, angle, _walls: angle
        play.blend_angles = lambda primary, *_args, **_kwargs: primary
        play.lead_shot_angle = lambda *_args, **_kwargs: 0.0
        play.track_enemy_velocity = lambda *_args, **_kwargs: (0.0, 0.0)
        play.detect_wall_stuck = lambda *_args, **_kwargs: False
        play.start_semicircle_escape = lambda *_args, **_kwargs: None
        play.semicircle_escape_step = lambda *_args, **_kwargs: None
        play._playstyle_error_reported = False

        movement = play.run_playstyle([0, 0, 100, 100], [], [], "shelly")

        self.assertEqual(movement, 270.0)

    def test_showdown_hide_mode_roams_when_no_enemy_and_teammate_visible(self):
        play = object.__new__(Play)
        play.brawlers_info = {"shelly": {"hold_attack": 0, "super_type": "damage"}}
        play.must_brawler_hold_attack = lambda *_args, **_kwargs: False
        play.time_since_holding_attack = None
        play.seconds_to_hold_attack_after_reaching_max = 1.5
        play.get_brawler_range = lambda _brawler: (100, 200, 300)
        play.get_player_pos = lambda _player: (50, 50)
        play._fog_check_counter = 0
        play.fog_check_every_n_frames = 999
        play._fog_direction_escape_cached = None
        play._fog_threat_cached = None
        play.detect_fog_threat = lambda *_args, **_kwargs: None
        play.detect_fog_direction_escape = lambda *_args, **_kwargs: None
        play.current_frame = None
        play.is_there_enemy = lambda _enemy: False
        play.showdown_follow_teammate = lambda *_args, **_kwargs: 45.0
        play.showdown_roam = lambda *_args, **_kwargs: 270.0
        play.showdown_playstyle_mode = "hide"

        movement = play.get_showdown_movement([0, 0, 100, 100], [], [[100, 100, 120, 120]], [], "shelly")

        self.assertEqual(movement, 270.0)

    def test_showdown_follow_mode_follows_teammate_when_no_enemy_visible(self):
        play = object.__new__(Play)
        play.brawlers_info = {"shelly": {"hold_attack": 0, "super_type": "damage"}}
        play.must_brawler_hold_attack = lambda *_args, **_kwargs: False
        play.time_since_holding_attack = None
        play.seconds_to_hold_attack_after_reaching_max = 1.5
        play.get_brawler_range = lambda _brawler: (100, 200, 300)
        play.get_player_pos = lambda _player: (50, 50)
        play._fog_check_counter = 0
        play.fog_check_every_n_frames = 999
        play._fog_direction_escape_cached = None
        play._fog_threat_cached = None
        play.detect_fog_threat = lambda *_args, **_kwargs: None
        play.detect_fog_direction_escape = lambda *_args, **_kwargs: None
        play.current_frame = None
        play.is_there_enemy = lambda _enemy: False
        play.showdown_follow_teammate = lambda *_args, **_kwargs: 45.0
        play.showdown_roam = lambda *_args, **_kwargs: 270.0
        play.showdown_playstyle_mode = "follow"

        movement = play.get_showdown_movement([0, 0, 100, 100], [], [[100, 100, 120, 120]], [], "shelly")

        self.assertEqual(movement, 45.0)

    def test_showdown_follow_mode_does_not_follow_into_fog(self):
        play = object.__new__(Play)
        play.brawlers_info = {"shelly": {"hold_attack": 0, "super_type": "damage"}}
        play.must_brawler_hold_attack = lambda *_args, **_kwargs: False
        play.time_since_holding_attack = None
        play.seconds_to_hold_attack_after_reaching_max = 1.5
        play.get_brawler_range = lambda _brawler: (100, 200, 300)
        play.get_player_pos = lambda _player: (50, 50)
        play._fog_check_counter = 0
        play.fog_check_every_n_frames = 999
        play._fog_direction_escape_cached = None
        play._fog_threat_cached = None
        play.detect_fog_threat = lambda *_args, **_kwargs: None
        play.detect_fog_direction_escape = lambda *_args, **_kwargs: None
        play.current_frame = object()
        play.is_there_enemy = lambda _enemy: False
        play.showdown_follow_teammate = lambda *_args, **_kwargs: 0.0
        play.showdown_roam = lambda *_args, **_kwargs: 270.0
        play.angle_points_into_fog = lambda *_args, **_kwargs: True
        play.angle_opposite = Play.angle_opposite
        play.find_best_angle = lambda _player, angle, _walls: angle
        play.showdown_playstyle_mode = "follow"

        movement = play.get_showdown_movement([0, 0, 100, 100], [], [[100, 100, 120, 120]], [], "shelly")

        self.assertEqual(movement, 180.0)

    def test_showdown_follow_teammate_moves_directly_toward_closest_teammate(self):
        play = object.__new__(Play)
        play.get_player_pos = lambda _player: (100, 100)
        play.get_enemy_pos = lambda entity: entity
        play.get_distance = Play.get_distance
        play.angle_from_direction = Play.angle_from_direction
        play.is_path_blocked_angle = lambda *_args, **_kwargs: False

        movement = play.showdown_follow_teammate(
            [90, 90, 110, 110],
            [(200, 100), (120, 220)],
            [],
        )

        self.assertEqual(movement, 0.0)

    def test_showdown_follow_teammate_uses_axis_option_when_diagonal_blocked(self):
        play = object.__new__(Play)
        play.get_player_pos = lambda _player: (100, 100)
        play.get_enemy_pos = lambda entity: entity
        play.get_distance = Play.get_distance
        play.angle_from_direction = Play.angle_from_direction
        blocked = {45.0}
        play.is_path_blocked_angle = lambda _player, angle, _walls: round(angle, 1) in blocked

        movement = play.showdown_follow_teammate(
            [90, 90, 110, 110],
            [(200, 200)],
            [],
        )

        self.assertEqual(movement, 0.0)


if __name__ == "__main__":
    unittest.main()
