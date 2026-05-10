import unittest

import cv2
import numpy as np

from play import Movement, Play


class FakeWindow:
    width_ratio = 1.0
    height_ratio = 1.0

    def __init__(self):
        self.keys = []

    def press_key(self, key, **kwargs):
        self.keys.append((key, kwargs))


class HalfScaleWindow(FakeWindow):
    width_ratio = 0.5
    height_ratio = 0.5


class SuperUsageTests(unittest.TestCase):
    def test_near_enemy_uses_super_even_when_configured_super_range_is_short(self):
        self.assertTrue(
            Movement.should_use_super_on_enemy(
                "meg",
                "damage",
                enemy_distance=420,
                attack_range=576,
                super_range=277,
                enemy_hittable=True,
            )
        )

    def test_damage_super_waits_when_enemy_is_outside_near_range(self):
        self.assertFalse(
            Movement.should_use_super_on_enemy(
                "meg",
                "damage",
                enemy_distance=500,
                attack_range=576,
                super_range=277,
                enemy_hittable=True,
            )
        )

    def test_damage_super_waits_when_enemy_is_not_hittable(self):
        self.assertFalse(
            Movement.should_use_super_on_enemy(
                "shelly",
                "damage",
                enemy_distance=220,
                attack_range=490,
                super_range=490,
                enemy_hittable=False,
            )
        )

    def test_super_releases_held_attack_before_firing(self):
        play = Play.__new__(Play)
        play.window_controller = FakeWindow()
        play.is_super_ready = True
        play.is_hypercharge_ready = False
        play.time_since_holding_attack = 123.0
        play.super_cooldown = 0.0
        play.last_super_time = 0.0
        play.brawler_ranges = {"shelly": (301, 490, 490)}
        play.get_brawler_range = lambda brawler: play.brawler_ranges[brawler]
        play.is_enemy_hittable = lambda *args, **kwargs: True

        used = play.try_use_super_on_enemy(
            "shelly",
            {"super_type": "damage"},
            player_pos=(100, 100),
            enemy_coords=(250, 100),
            enemy_distance=150,
            walls=[],
        )

        self.assertTrue(used)
        self.assertIsNone(play.time_since_holding_attack)
        self.assertEqual(play.window_controller.keys[0][0], "M")
        self.assertEqual(play.window_controller.keys[0][1], {"touch_up": True, "touch_down": False})
        self.assertEqual(play.window_controller.keys[1][0], "E")

    def test_super_ready_does_not_survive_missed_hud_scan(self):
        play = Play.__new__(Play)
        play.ability_ready_memory_seconds = 1.25
        play._super_ready_seen_at = 10.0
        play._gadget_ready_seen_at = 10.0
        play._hypercharge_ready_seen_at = 10.0

        self.assertFalse(play.remember_ability_ready("super", detected_ready=False, current_time=10.5))
        self.assertFalse(play.remember_ability_ready("gadget", detected_ready=False, current_time=10.5))
        self.assertFalse(play.remember_ability_ready("hypercharge", detected_ready=False, current_time=10.5))
        self.assertFalse(play.remember_ability_ready("super", detected_ready=False, current_time=12.0))

    def test_super_and_gadget_taps_are_long_enough_for_emulators(self):
        movement = Movement.__new__(Movement)
        movement.window_controller = FakeWindow()
        movement.super_cooldown = 0.0
        movement.gadget_cooldown = 0.0
        movement.last_super_time = 0.0
        movement.last_gadget_time = 0.0

        self.assertTrue(movement.use_super())
        self.assertTrue(movement.use_gadget())

        self.assertEqual(movement.window_controller.keys[0], ("E", {"delay": 0.035}))
        self.assertEqual(movement.window_controller.keys[1], ("G", {"delay": 0.035}))

    def test_visible_enemy_fallback_does_not_spam_ready_super_and_gadget(self):
        play = Play.__new__(Play)
        play.window_controller = FakeWindow()
        play.should_use_gadget = True
        play.is_gadget_ready = True
        play.is_hypercharge_ready = False
        play.is_super_ready = True
        play.time_since_holding_attack = None
        play.gadget_cooldown = 0.0
        play.super_cooldown = 0.0
        play.last_gadget_time = 0.0
        play.last_super_time = 0.0
        play._gadget_ready_seen_at = 1.0
        play._super_ready_seen_at = 1.0
        play.time_since_gadget_checked = 0.0
        play.time_since_super_checked = 0.0

        used = play.try_use_ready_abilities_when_enemy_visible([[10, 10, 20, 20]])

        self.assertFalse(used)
        self.assertEqual(play.window_controller.keys, [])
        self.assertTrue(play.is_gadget_ready)
        self.assertTrue(play.is_super_ready)

    def test_gadget_waits_for_near_hittable_enemy(self):
        play = Play.__new__(Play)
        play.should_use_gadget = True
        play.is_gadget_ready = True
        play.time_since_holding_attack = None
        play.get_player_pos = lambda _player_data: (0, 0)
        play.find_closest_enemy = lambda *_args, **_kwargs: ((80, 0), 80)
        play.get_brawler_range = lambda _brawler: (100, 100, 100)
        play.get_enemy_pos = lambda enemy: enemy
        play.get_distance = Play.get_distance
        play.is_enemy_hittable = lambda *_args, **_kwargs: True

        self.assertFalse(play.should_use_gadget_on_enemy("shelly", [0, 0, 10, 10], [(80, 0)], []))

    def test_gadget_uses_on_close_hittable_enemy(self):
        play = Play.__new__(Play)
        play.should_use_gadget = True
        play.is_gadget_ready = True
        play.time_since_holding_attack = None
        play.get_player_pos = lambda _player_data: (0, 0)
        play.find_closest_enemy = lambda *_args, **_kwargs: ((60, 0), 60)
        play.get_brawler_range = lambda _brawler: (100, 100, 100)
        play.get_enemy_pos = lambda enemy: enemy
        play.get_distance = Play.get_distance
        play.is_enemy_hittable = lambda *_args, **_kwargs: True

        self.assertTrue(play.should_use_gadget_on_enemy("shelly", [0, 0, 10, 10], [(60, 0)], []))

    def test_super_ready_detection_rejects_color_outside_button_crop(self):
        play = Play.__new__(Play)
        play.window_controller = FakeWindow()
        play.super_crop_area = [1460, 830, 1560, 930]
        play.super_pixels_minimum = 2400

        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cv2.circle(frame, (1580, 950), 52, (255, 170, 0), -1)

        self.assertFalse(play.check_if_super_ready(frame))

    def test_super_ready_detection_scales_threshold_for_scrcpy_width(self):
        play = Play.__new__(Play)
        play.window_controller = HalfScaleWindow()
        play.super_crop_area = [1460, 830, 1560, 930]
        play.super_pixels_minimum = 1800

        frame = np.zeros((540, 960, 3), dtype=np.uint8)
        frame[425:460, 735:770] = (255, 170, 0)

        self.assertTrue(play.check_if_super_ready(frame))

    def test_super_ready_detection_rejects_yellow_button_edge_only(self):
        play = Play.__new__(Play)
        play.window_controller = HalfScaleWindow()
        play.super_crop_area = [1460, 830, 1560, 930]
        play.super_pixels_minimum = 1800

        frame = np.zeros((540, 960, 3), dtype=np.uint8)
        frame[458:470, 730:780] = (255, 170, 0)

        self.assertFalse(play.check_if_super_ready(frame))

    def test_hypercharge_ready_detection_scales_threshold_for_scrcpy_width(self):
        play = Play.__new__(Play)
        play.window_controller = HalfScaleWindow()
        play.hypercharge_crop_area = [1350, 940, 1450, 1050]
        play.hypercharge_pixels_minimum = 1800

        frame = np.zeros((540, 960, 3), dtype=np.uint8)
        frame[475:505, 685:715] = (190, 0, 255)

        self.assertTrue(play.check_if_hypercharge_ready(frame))

    def test_gadget_ready_detection_matches_op_main_strict_green(self):
        play = Play.__new__(Play)
        play.window_controller = FakeWindow()
        play.gadget_crop_area = [1580, 930, 1700, 1050]
        play.gadget_pixels_minimum = 1100

        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frame[950:1025, 1600:1675] = (0, 255, 0)

        self.assertTrue(play.check_if_gadget_ready(frame))

    def test_gadget_ready_detection_rejects_broad_green_false_positive(self):
        play = Play.__new__(Play)
        play.window_controller = FakeWindow()
        play.gadget_crop_area = [1580, 930, 1700, 1050]
        play.gadget_pixels_minimum = 1100

        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frame[950:1025, 1600:1675] = (65, 210, 70)

        self.assertFalse(play.check_if_gadget_ready(frame))

    def test_visible_enemy_cannot_use_abilities_before_player_validation(self):
        play = Play.__new__(Play)
        play.get_main_data = lambda frame: {"enemy": [[10, 10, 30, 30]], "player": []}
        play.should_detect_walls = False
        play.keep_walls_in_memory = False
        play.validate_game_data = lambda data: None
        play.track_no_detections = lambda data: None
        play.capture_vision_frame = lambda *args, **kwargs: None
        play.refresh_ready_abilities_called = False
        play.used_abilities = False

        def refresh(frame, current_time):
            play.refresh_ready_abilities_called = True

        def use(enemy_data):
            play.used_abilities = bool(enemy_data)
            return play.used_abilities

        play.refresh_ready_abilities = refresh
        play.try_use_ready_abilities_when_enemy_visible = use
        play.time_since_player_last_found = 0
        play.time_since_different_movement = 0
        play.time_since_last_proceeding = 10**12
        play.no_detection_proceed_delay = 6.5
        play.window_controller = FakeWindow()
        play.window_controller.keys_up = lambda keys: None

        main = type("MainState", (), {"state": "match"})()
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        play.main(frame, "shelly", main)

        self.assertFalse(play.refresh_ready_abilities_called)
        self.assertFalse(play.used_abilities)

    def test_enemy_pressure_fallback_moves_when_near_enemy_and_movement_empty(self):
        play = Play.__new__(Play)
        play.enemy_pressure_move_range_multiplier = 1.15
        play._strafe_started_at = 0.0
        play._strafe_side = 1
        play.strafe_interval = 1.0
        play._strafe_current_interval = 0.0
        play.window_controller = FakeWindow()
        play.get_player_pos = lambda player: (100, 100)
        play.get_enemy_pos = lambda enemy: (180, 100)
        play.is_enemy_hittable = lambda *args, **kwargs: True
        play.get_brawler_range = lambda brawler: (120, 240, 240)
        play.find_best_angle = lambda player_pos, desired, walls: desired

        movement = play.enemy_pressure_movement_fallback(
            "",
            {"player": ["player"], "enemy": ["enemy"], "wall": []},
            "shelly",
            current_time=10.0,
        )

        self.assertIsInstance(movement, float)

    def test_enemy_pressure_fallback_leaves_empty_movement_when_enemy_far(self):
        play = Play.__new__(Play)
        play.enemy_pressure_move_range_multiplier = 1.15
        play.window_controller = FakeWindow()
        play.get_player_pos = lambda player: (100, 100)
        play.get_enemy_pos = lambda enemy: (600, 100)
        play.is_enemy_hittable = lambda *args, **kwargs: True
        play.get_brawler_range = lambda brawler: (120, 240, 240)

        movement = play.enemy_pressure_movement_fallback(
            "",
            {"player": ["player"], "enemy": ["enemy"], "wall": []},
            "shelly",
            current_time=10.0,
        )

        self.assertEqual(movement, "")


if __name__ == "__main__":
    unittest.main()
