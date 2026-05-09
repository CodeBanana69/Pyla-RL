import math
import json
import os
import random
import threading
import time
from typing import Optional

import cv2
import numpy as np
from state_finder import get_state
from detect import Detect
from utils import load_toml_as_dict, count_hsv_pixels, load_brawlers_info

brawl_stars_width, brawl_stars_height = 1920, 1080
debug = load_toml_as_dict("cfg/general_config.toml")['super_debug'] == "yes"
visual_debug = load_toml_as_dict("cfg/general_config.toml").get('visual_debug', 'no') == "yes"

def vlog(*args):
    if visual_debug:
        print("[DBG]", *args)
super_crop_area = load_toml_as_dict("./cfg/lobby_config.toml")['pixel_counter_crop_area']['super']
gadget_crop_area = load_toml_as_dict("./cfg/lobby_config.toml")['pixel_counter_crop_area']['gadget']
hypercharge_crop_area = load_toml_as_dict("./cfg/lobby_config.toml")['pixel_counter_crop_area']['hypercharge']

class Movement:

    def __init__(self, window_controller):
        bot_config = load_toml_as_dict("cfg/bot_config.toml")
        time_config = load_toml_as_dict("cfg/time_tresholds.toml")
        self.fix_movement_keys = {
            "delay_to_trigger": bot_config["unstuck_movement_delay"],
            "duration": bot_config["unstuck_movement_hold_time"],
            "toggled": False,
            "started_at": time.time(),
            "fixed": ""
        }
        self.game_mode = bot_config["gamemode_type"]
        gadget_value = bot_config["bot_uses_gadgets"]
        self.should_use_gadget = str(gadget_value).lower() in ("yes", "true", "1")
        self.gadget_cooldown = float(bot_config.get("gadget_cooldown", 1.0))
        self.last_gadget_time = 0.0
        self.super_cooldown = float(bot_config.get("super_cooldown", 1.0))
        self.last_super_time = 0.0
        self.super_treshold = time_config["super"]
        self.gadget_treshold = time_config["gadget"]
        self.hypercharge_treshold = time_config["hypercharge"]
        self.walls_treshold = time_config["wall_detection"]
        self.keep_walls_in_memory = self.walls_treshold <= 1
        self.last_walls_data = []
        self.keys_hold = []
        self.time_since_different_movement = time.time()
        self.time_since_gadget_checked = time.time()
        self.is_gadget_ready = False
        self.time_since_hypercharge_checked = time.time()
        self.is_hypercharge_ready = False
        self.window_controller = window_controller
        self.attack_cooldown = float(bot_config.get("attack_cooldown", 0.16))
        self.last_attack_time = 0.0
        self.TILE_SIZE = 60
        # Wall-based stuck detector: samples wall bboxes on an interval, ignores
        # walls near the player (they flicker as he overlaps them), and flags
        # "stuck" when walls don't move for wall_stuck_timeout seconds while the
        # bot is trying to move. Triggers a semicircle escape maneuver.
        self.wall_stuck_enabled = str(bot_config.get("wall_stuck_enabled", "yes")).lower() in ("yes", "true", "1")
        general_config = load_toml_as_dict("cfg/general_config.toml")
        self.wall_stuck_debug = str(general_config.get("wall_stuck_debug", "no")).lower() in ("yes", "true", "1")
        self.wall_stuck_ignore_radius = float(bot_config.get("wall_stuck_ignore_radius", 150))
        self.wall_stuck_sample_interval = float(bot_config.get("wall_stuck_sample_interval", 0.2))
        self.wall_stuck_shift_threshold = float(bot_config.get("wall_stuck_shift_threshold", 3.0))
        self.wall_stuck_timeout = float(bot_config.get("wall_stuck_timeout", 3.0))
        self.wall_stuck_min_walls = int(bot_config.get("wall_stuck_min_walls", 3))
        self.wall_path_padding = float(bot_config.get("wall_path_padding", 28))
        self.wall_path_probe_tiles = float(bot_config.get("wall_path_probe_tiles", 1.5))
        self.wall_box_min_size = float(bot_config.get("wall_box_min_size", 20))
        self.wall_box_merge_iou = float(bot_config.get("wall_box_merge_iou", 0.25))
        self.wall_box_merge_center_distance = float(bot_config.get("wall_box_merge_center_distance", 35))
        self.wall_history_min_hits = int(bot_config.get("wall_history_min_hits", 1))
        self.wall_stuck_state = {
            "last_sample_time": 0.0,
            "last_wall_centers": None,   # np.ndarray (N, 2) of filtered wall centers
            "stationary_since": None,    # when walls first went stationary; None = not stationary
        }

        # Semicircle escape state. Alternates side globally between triggers.
        self.escape_retreat_duration = float(bot_config.get("escape_retreat_duration", 0.4))
        self.escape_arc_duration = float(bot_config.get("escape_arc_duration", 1.2))
        self.escape_arc_degrees = float(bot_config.get("escape_arc_degrees", 135.0))
        self.escape_state = {
            "phase": None,            # "retreat" | "arc" | None
            "started_at": 0.0,
            "retreat_angle": 0.0,
            "arc_side": 1,            # +1 = CCW, -1 = CW; flipped each trigger
        }
        self._next_arc_side = 1
        self.adaptive_safe_range_multiplier = 1.0
        self.strafe_enabled = str(bot_config.get("strafe_while_attacking", "yes")).lower() in ("yes", "true", "1")
        self.strafe_interval = float(bot_config.get("strafe_interval", 1.6))
        self.strafe_blend = float(bot_config.get("strafe_blend", 0.35))
        self._strafe_started_at = 0.0
        self._strafe_side = 1
        self.combat_dodge_blend = float(bot_config.get("combat_dodge_blend", 0.45))
        self.combat_dodge_jitter_degrees = float(bot_config.get("combat_dodge_jitter_degrees", 18.0))
        self.enemy_pressure_move_range_multiplier = float(bot_config.get("enemy_pressure_move_range_multiplier", 1.15))
        self.lead_shots_enabled = str(bot_config.get("lead_shots", "yes")).lower() in ("yes", "true", "1")
        self.aimed_attacks_enabled = str(bot_config.get("aimed_attacks", "no")).lower() in ("yes", "true", "1")
        self.projectile_speed_px_s = float(bot_config.get("projectile_speed_px_s", 900.0))
        self._enemy_track = {}
        self.enemy_velocity = (0.0, 0.0)
        self.velocity_ema_alpha = float(bot_config.get("velocity_ema_alpha", 0.40))
        self._enemy_velocity_smooth = {}
        self._enemy_velocity_confidence = {}
        self.enemy_velocity_confidence = 0.0
        self._strafe_current_interval = 0.0
        self.roam_direction_hold_time = float(bot_config.get("roam_direction_hold_time", 1.5))
        self.roam_center_bias = float(bot_config.get("roam_center_bias", 0.25))
        self._roam_angle = random.uniform(0, 360)
        self._roam_last_changed = 0.0
        self.retreat_strafe_fraction = float(bot_config.get("retreat_strafe_fraction", 0.5))
        self.approach_flank_blend = float(bot_config.get("approach_flank_blend", 0.12))
        self.multi_enemy_flee_weight = float(bot_config.get("multi_enemy_flee_weight", 0.45))
        self.angle_smooth_factor = float(bot_config.get("angle_smooth_factor", 0.28))

        self.use_rl_movement = str(bot_config.get("use_rl_movement", "no")).lower() in ("yes", "true", "1")
        self.rl_training_enabled = str(bot_config.get("enable_rl_movement_training", "no")).lower() in ("yes", "true", "1")
        self.rl_movement_model_path = str(bot_config.get("rl_movement_model_path", "models/rl_movement_policy.zip"))
        self.rl_combat_blend_dodge = str(bot_config.get("rl_combat_blend_dodge", "yes")).lower() in ("yes", "true", "1")
        self.rl_max_projectiles = int(bot_config.get("rl_max_projectiles", 6))
        self.rl_projectile_classes = list(bot_config.get("rl_projectile_classes", ["projectile", "super", "bullet", "enemy_shot"]))
        self.rl_projectile_history_seconds = float(bot_config.get("rl_projectile_history_seconds", 0.6))
        self.rl_projectile_min_speed_px_s = float(bot_config.get("rl_projectile_min_speed_px_s", 25.0))
        self.rl_projectile_hit_radius_padding = float(bot_config.get("rl_projectile_hit_radius_padding", 18))
        self.rl_train_steps_per_update = int(bot_config.get("rl_train_steps_per_update", 256))
        self.rl_save_every_seconds = float(bot_config.get("rl_save_every_seconds", 120))
        self.rl_universal_projectiles = str(bot_config.get("rl_universal_projectiles", "yes")).lower() in ("yes", "true", "1")
        self.rl_motion_scale_width = int(bot_config.get("rl_motion_scale_width", 480))
        self.rl_motion_diff_threshold = int(bot_config.get("rl_motion_diff_threshold", 25))
        self.rl_motion_exclude_dilate_px = int(bot_config.get("rl_motion_exclude_dilate_px", 32))
        self.rl_motion_min_area_px = int(bot_config.get("rl_motion_min_area_px", 40))
        self.rl_motion_max_area_px = int(bot_config.get("rl_motion_max_area_px", 6000))
        self.rl_motion_morph_kernel = int(bot_config.get("rl_motion_morph_kernel", 3))
        self.rl_residual_max_box_area_frac = float(bot_config.get("rl_residual_max_box_area_frac", 0.02))
        self.rl_residual_max_side_frac = float(bot_config.get("rl_residual_max_side_frac", 0.25))
        self.rl_residual_iou_exclude = float(bot_config.get("rl_residual_iou_exclude", 0.25))
        self.rl_projectile_merge_nms_iou = float(bot_config.get("rl_projectile_merge_nms_iou", 0.35))
        self.rl_projectile_max_match_distance = float(bot_config.get("rl_projectile_max_match_distance", 120.0))
        # Single 0..1 knob (also exposed in the hub UI) controlling how
        # strictly the projectile pipeline rejects boxes that are not
        # heading toward the player. Higher = fewer false positives.
        self.projectile_detection_confidence = float(
            bot_config.get("projectile_detection_confidence", 0.55)
        )
        # Enemy-origin gate: a candidate is only classified as a real
        # projectile if its first appearance was within
        # ``enemy_origin_radius`` of an enemy hitbox AND not within
        # ``friendly_origin_radius`` of the player / a teammate.
        self.rl_projectile_require_enemy_origin = str(
            bot_config.get("rl_projectile_require_enemy_origin", "yes")
        ).lower() in ("yes", "true", "1")
        self.rl_projectile_enemy_origin_radius = float(
            bot_config.get("rl_projectile_enemy_origin_radius", 140.0)
        )
        self.rl_projectile_friendly_origin_radius = float(
            bot_config.get("rl_projectile_friendly_origin_radius", 100.0)
        )
        self.rl_universal_projectiles_mode = str(
            bot_config.get("rl_universal_projectiles_mode", "motion")
        ).strip().lower()
        self.rl_motion_ego_compensate = str(bot_config.get("rl_motion_ego_compensate", "yes")).lower() in (
            "yes",
            "true",
            "1",
        )
        self.rl_motion_ego_min_response = float(bot_config.get("rl_motion_ego_min_response", 0.08))
        self.rl_motion_skip_on_bad_ego = str(
            bot_config.get("rl_motion_skip_on_bad_ego", "no")
        ).lower() in ("yes", "true", "1")
        self.rl_motion_use_ui_mask = str(bot_config.get("rl_motion_use_ui_mask", "yes")).lower() in (
            "yes",
            "true",
            "1",
        )
        raw_ui = bot_config.get("rl_motion_ui_exclude_rects")
        self.rl_motion_ui_exclude_rects: Optional[list] = (
            raw_ui if isinstance(raw_ui, list) and raw_ui else None
        )
        self.rl_motion_full_frame_fog = str(bot_config.get("rl_motion_full_frame_fog", "yes")).lower() in (
            "yes",
            "true",
            "1",
        )
        self.rl_motion_fog_exclude_dilate_px = int(bot_config.get("rl_motion_fog_exclude_dilate_px", 2))
        raw_terr = bot_config.get("rl_animated_terrain_hsv_ranges")
        self.rl_animated_terrain_hsv_ranges: list = (
            raw_terr if isinstance(raw_terr, list) else []
        )
        self.rl_projectile_min_hits_to_promote = max(
            1, int(bot_config.get("rl_projectile_min_hits_to_promote", 1))
        )
        self.rl_projectile_max_speed_px_s = float(bot_config.get("rl_projectile_max_speed_px_s", 1.0e9))
        self.rl_projectile_max_accel_px_s2 = float(bot_config.get("rl_projectile_max_accel_px_s2", 1.0e9))
        self.rl_projectile_max_line_residual_frac = float(
            bot_config.get("rl_projectile_max_line_residual_frac", 1.0)
        )
        self.rl_projectile_motion_origin_radius = float(
            bot_config.get("rl_projectile_motion_origin_radius", 80.0)
        )
        self.rl_projectile_require_enemy_origin_strict = str(
            bot_config.get("rl_projectile_require_enemy_origin_strict", "no")
        ).lower() in ("yes", "true", "1")
        self.rl_projectile_cluster_distance_px = float(
            bot_config.get("rl_projectile_cluster_distance_px", 200.0)
        )
        # Health bar + damage cross-reference (RL / visual debug)
        self.health_bar_band_offset_px = float(bot_config.get("health_bar_band_offset_px", 8.0))
        self.health_bar_band_height_px = float(bot_config.get("health_bar_band_height_px", 14.0))
        self.health_bar_min_total_pixels = int(bot_config.get("health_bar_min_total_pixels", 40))
        self.health_ocr_enabled = str(bot_config.get("health_ocr_enabled", "yes")).lower() in (
            "yes",
            "true",
            "1",
        )
        self.health_ocr_interval_seconds = float(bot_config.get("health_ocr_interval_seconds", 0.5))
        self.damage_hp_drop_threshold_pct = float(bot_config.get("damage_hp_drop_threshold_pct", 0.015))
        self.damage_confirm_window_seconds = float(bot_config.get("damage_confirm_window_seconds", 0.5))
        self.red_flash_detect_enabled = str(bot_config.get("red_flash_detect_enabled", "yes")).lower() in (
            "yes",
            "true",
            "1",
        )
        self.red_flash_red_dom_threshold = float(bot_config.get("red_flash_red_dom_threshold", 1.40))
        self.red_flash_baseline_alpha = float(bot_config.get("red_flash_baseline_alpha", 0.1))
        self.cross_reference_projectile_hits = str(
            bot_config.get("cross_reference_projectile_hits", "yes")
        ).lower() in ("yes", "true", "1")

    @staticmethod
    def get_enemy_pos(enemy):
        return (enemy[0] + enemy[2]) / 2, (enemy[1] + enemy[3]) / 2

    @staticmethod
    def get_player_pos(player_data):
        return (player_data[0] + player_data[2]) / 2, (player_data[1] + player_data[3]) / 2

    @staticmethod
    def get_distance(enemy_coords, player_coords):
        return math.hypot(enemy_coords[0] - player_coords[0], enemy_coords[1] - player_coords[1])

    @staticmethod
    def is_there_enemy(enemy_data):
        if not enemy_data:
            return False
        return True

    @staticmethod
    def get_horizontal_move_key(direction_x, opposite=False):
        if opposite:
            return "A" if direction_x > 0 else "D"
        return "D" if direction_x > 0 else "A"

    @staticmethod
    def get_vertical_move_key(direction_y, opposite=False):
        if opposite:
            return "W" if direction_y > 0 else "S"
        return "S" if direction_y > 0 else "W"

    def attack(self, touch_up=True, touch_down=True):
        if touch_up and touch_down and self.attack_cooldown > 0:
            current_time = time.time()
            if current_time - self.last_attack_time < self.attack_cooldown:
                return False
            self.last_attack_time = current_time
        self.window_controller.press_key("M", touch_up=touch_up, touch_down=touch_down)
        return True

    def aimed_attack(self, angle_degrees):
        if not self.aimed_attacks_enabled:
            return self.attack()
        if self.attack_cooldown > 0:
            current_time = time.time()
            if current_time - self.last_attack_time < self.attack_cooldown:
                return False
            self.last_attack_time = current_time
        if hasattr(self.window_controller, "aim_attack_angle"):
            self.window_controller.aim_attack_angle(angle_degrees)
            return True
        return self.attack()

    def use_hypercharge(self):
        print("Using hypercharge")
        self.window_controller.press_key("H", delay=0.035)
        return True

    def use_gadget(self):
        if self.gadget_cooldown > 0:
            current_time = time.time()
            if current_time - self.last_gadget_time < self.gadget_cooldown:
                return False
            self.last_gadget_time = current_time
        print("Using gadget")
        self.window_controller.press_key("G", delay=0.035)
        return True

    def use_super(self):
        if self.super_cooldown > 0:
            current_time = time.time()
            if current_time - self.last_super_time < self.super_cooldown:
                return False
            self.last_super_time = current_time
        print("Using super")
        self.window_controller.press_key("E", delay=0.035)
        return True

    @staticmethod
    def should_use_super_on_enemy(brawler, super_type, enemy_distance, attack_range, super_range, enemy_hittable):
        utility_super = super_type in {"spawnable", "other", "other_target"}
        charge_super = super_type == "charge"
        near_range = max(super_range, attack_range * 0.75)
        near_range = min(near_range, attack_range)
        if enemy_hittable and enemy_distance <= min(super_range, near_range):
            return True
        if enemy_hittable and super_type == "damage" and enemy_distance <= near_range:
            return True
        if enemy_hittable and utility_super and enemy_distance <= near_range:
            return True
        if (
                charge_super
                and enemy_distance <= near_range
                and (enemy_hittable or brawler in {"stu", "surge"})
        ):
            return True
        return False

    @staticmethod
    def get_random_attack_key():
        random_movement = random.choice(["A", "W", "S", "D"])
        random_movement += random.choice(["A", "W", "S", "D"])
        return random_movement

    @staticmethod
    def angle_from_direction(dx: float, dy: float) -> float:
        """Return joystick angle in degrees from a direction vector.

        Uses screen coordinates: 0° = right, 90° = down, 180° = left, 270° = up.
        """
        return math.degrees(math.atan2(dy, dx)) % 360

    @staticmethod
    def angle_opposite(angle_degrees: float) -> float:
        """Return the opposite direction angle (retreat)."""
        return (angle_degrees + 180) % 360

    @staticmethod
    def reverse_movement(movement):
        # Create a translation table
        movement = movement.lower()
        translation_table = str.maketrans("wasd", "sdwa")
        return movement.translate(translation_table)

    @staticmethod
    def movement_to_vector(movement):
        dx = 0
        dy = 0
        movement = str(movement or "").lower()
        if "a" in movement:
            dx -= 1
        if "d" in movement:
            dx += 1
        if "w" in movement:
            dy -= 1
        if "s" in movement:
            dy += 1
        return dx, dy

    def unstuck_movement_if_needed(self, movement, current_time=None):
        if current_time is None:
            current_time = time.time()
        movement = movement.lower()
        if self.fix_movement_keys['toggled']:
            if current_time - self.fix_movement_keys['started_at'] > self.fix_movement_keys['duration']:
                self.fix_movement_keys['toggled'] = False
                vlog("unstuck: finished")
            else:
                vlog(f"unstuck: active → {self.fix_movement_keys['fixed']}")

            return self.fix_movement_keys['fixed']

        if "".join(self.keys_hold) != movement and movement[::-1] != "".join(self.keys_hold):
            self.time_since_different_movement = current_time

        # print(f"Last change: {self.time_since_different_movement}", f" self.hold: {self.keys_hold}",f" c movement: {movement}")
        if current_time - self.time_since_different_movement > self.fix_movement_keys["delay_to_trigger"]:
            reversed_movement = self.reverse_movement(movement)

            if reversed_movement == "s":
                reversed_movement = random.choice(['aw', 'dw'])
            elif reversed_movement == "w":
                reversed_movement = random.choice(['as', 'ds'])

            """
            If reverse movement is either "w" or "s" it means the bot is stuck
            going forward or backward. This happens when it doesn't detect a wall in front
            so to go around it it could either go to the left diagonal or right
            """

            self.fix_movement_keys['fixed'] = reversed_movement
            self.fix_movement_keys['toggled'] = True
            self.fix_movement_keys['started_at'] = current_time
            vlog(f"unstuck triggered: {movement} → {reversed_movement}")
            return reversed_movement

        return movement

    def _wslog(self, *args):
        """Dedicated logger for wall-stuck / escape — independent of vlog/visual_debug
        so the new unstuck machinery can be traced without dumping the full debug stream.
        """
        if self.wall_stuck_debug:
            print("[WS]", *args)

    def _wall_centers_filtered(self, walls, player_pos):
        """Return (N, 2) float array of wall centers, excluding walls whose
        center lies within wall_stuck_ignore_radius of the player (those
        flicker as the player overlaps them).
        """
        import numpy as np
        if not walls:
            return np.empty((0, 2), dtype=np.float32)
        centers = []
        px, py = player_pos
        r2 = self.wall_stuck_ignore_radius * self.wall_stuck_ignore_radius
        for box in walls:
            x1, y1, x2, y2 = box[0], box[1], box[2], box[3]
            cx = (x1 + x2) * 0.5
            cy = (y1 + y2) * 0.5
            dx, dy = cx - px, cy - py
            if dx * dx + dy * dy >= r2:
                centers.append((cx, cy))
        return np.asarray(centers, dtype=np.float32) if centers else np.empty((0, 2), dtype=np.float32)

    def _avg_wall_shift(self, prev_centers, curr_centers):
        """Greedy nearest-neighbor match between two sets of wall centers.
        Returns mean pairwise distance (px). Returns None if either set is too
        small (can't form a reliable metric).
        """
        import numpy as np
        if prev_centers is None or len(prev_centers) < self.wall_stuck_min_walls:
            return None
        if len(curr_centers) < self.wall_stuck_min_walls:
            return None
        # For each prev center, find nearest curr center (O(N*M), fine for N~20)
        diffs = prev_centers[:, None, :] - curr_centers[None, :, :]
        d2 = (diffs * diffs).sum(axis=2)
        nearest = np.sqrt(d2.min(axis=1))
        return float(nearest.mean())

    def detect_wall_stuck(self, walls, player_pos, is_trying_to_move, current_time):
        """Wall-based stuck detector. Returns True if the walls around the
        player have been stationary longer than wall_stuck_timeout while the
        bot was issuing movement commands — meaning the bot is pressed against
        something and not actually moving.
        """
        if not self.wall_stuck_enabled or player_pos is None:
            return False
        state = self.wall_stuck_state
        if current_time - state["last_sample_time"] < self.wall_stuck_sample_interval:
            # Between samples: just honor the latest stationary flag
            if state["stationary_since"] is None or not is_trying_to_move:
                return False
            return (current_time - state["stationary_since"]) >= self.wall_stuck_timeout

        curr_centers = self._wall_centers_filtered(walls, player_pos)
        shift = self._avg_wall_shift(state["last_wall_centers"], curr_centers)
        state["last_wall_centers"] = curr_centers
        state["last_sample_time"] = current_time

        if shift is None:
            # Not enough walls to judge — treat as "unknown", don't advance timer
            state["stationary_since"] = None
            return False

        if shift < self.wall_stuck_shift_threshold:
            if state["stationary_since"] is None:
                state["stationary_since"] = current_time
            self._wslog(f"walls shift={shift:.2f}px, stationary for "
                        f"{current_time - state['stationary_since']:.2f}s "
                        f"(trying_to_move={is_trying_to_move})")
        else:
            if state["stationary_since"] is not None:
                self._wslog(f"walls moved again: shift={shift:.2f}px, resetting timer")
            state["stationary_since"] = None

        if state["stationary_since"] is None or not is_trying_to_move:
            return False
        return (current_time - state["stationary_since"]) >= self.wall_stuck_timeout

    def _reset_wall_stuck_state(self, current_time):
        """Clear the wall-stuck timer. Call after triggering an escape to
        avoid retriggering during/just after the maneuver.
        """
        self.wall_stuck_state["stationary_since"] = None
        self.wall_stuck_state["last_wall_centers"] = None
        self.wall_stuck_state["last_sample_time"] = current_time

    def start_semicircle_escape(self, angle, current_time):
        """Begin the retreat+arc escape maneuver. arc_side alternates globally
        between triggers.
        """
        side = self._next_arc_side
        self._next_arc_side = -side
        self.escape_state["phase"] = "retreat"
        self.escape_state["started_at"] = current_time
        self.escape_state["retreat_angle"] = self.angle_opposite(angle)
        self.escape_state["arc_side"] = side
        self._wslog(f"semicircle escape START: angle={angle:.1f}° "
                    f"retreat={self.escape_state['retreat_angle']:.1f}° "
                    f"side={'CCW' if side > 0 else 'CW'}")

    def semicircle_escape_step(self, current_time):
        """Return the current commanded angle for the active escape maneuver,
        or None if no maneuver is active / it just finished.
        """
        state = self.escape_state
        phase = state["phase"]
        if phase is None:
            return None
        elapsed = current_time - state["started_at"]

        if phase == "retreat":
            if elapsed < self.escape_retreat_duration:
                return state["retreat_angle"]
            # Transition: arc starts from retreat angle and sweeps arc_degrees
            state["phase"] = "arc"
            state["started_at"] = current_time
            self._wslog("semicircle escape: retreat done, starting arc")
            elapsed = 0.0
            phase = "arc"

        if phase == "arc":
            if elapsed >= self.escape_arc_duration:
                state["phase"] = None
                self._wslog("semicircle escape: finished")
                return None
            t = elapsed / self.escape_arc_duration  # 0..1
            sweep = self.escape_arc_degrees * t * state["arc_side"]
            return (state["retreat_angle"] + sweep) % 360

        return None


class Play(Movement):

    def __init__(self, main_info_model, tile_detector_model, window_controller):
        super().__init__(window_controller)

        bot_config = load_toml_as_dict("cfg/bot_config.toml")
        time_config = load_toml_as_dict("cfg/time_tresholds.toml")

        self.Detect_main_info = Detect(main_info_model, classes=['enemy', 'teammate', 'player'])
        self.tile_detector_model_classes = bot_config["wall_model_classes"]
        self.Detect_tile_detector = Detect(
            tile_detector_model,
            classes=self.tile_detector_model_classes
        )

        self.time_since_movement = time.time()
        self.time_since_gadget_checked = time.time()
        self.time_since_hypercharge_checked = time.time()
        self.time_since_super_checked = time.time()
        self.time_since_walls_checked = 0
        self.time_since_movement_change = time.time()
        self.time_since_player_last_found = time.time()
        self.current_brawler = None
        self.is_hypercharge_ready = False
        self.is_gadget_ready = False
        self.is_super_ready = False
        self.ability_ready_memory_seconds = float(bot_config.get("ability_ready_memory_seconds", 1.25))
        self._hypercharge_ready_seen_at = 0.0
        self._gadget_ready_seen_at = 0.0
        self._super_ready_seen_at = 0.0
        self.brawlers_info = load_brawlers_info()
        self.brawler_ranges = None
        self.time_since_detections = {
            "player": time.time(),
            "enemy": time.time(),
        }
        self.time_since_last_proceeding = time.time()
        self.time_since_last_no_detection_q = time.time()

        self.last_movement = None
        self.last_movement_time = time.time()
        self.locked_teammate = None
        self.locked_teammate_distance = float('inf')
        self.teammate_hysteresis = 0.20  # Switch only if another teammate is 20% closer
        self.trio_grouping_enabled = str(bot_config.get("trio_grouping_enabled", "yes")).lower() in ("yes", "true", "1")
        self.teammate_follow_min_distance = float(bot_config.get("teammate_follow_min_distance", 180))
        self.teammate_follow_max_distance = float(bot_config.get("teammate_follow_max_distance", 520))
        self.teammate_combat_regroup_distance = float(bot_config.get("teammate_combat_regroup_distance", 650))
        self.teammate_combat_bias = float(bot_config.get("teammate_combat_bias", 0.35))
        self.wall_history = []
        self.wall_history_length = int(bot_config.get("wall_history_length", 3))
        self.scene_data = []
        self.should_detect_walls = bot_config["gamemode"] in ["brawlball", "brawl_ball", "brawll ball", "showdown"]
        self.is_showdown = bot_config["gamemode"] == "showdown"
        self.minimum_movement_delay = bot_config["minimum_movement_delay"]
        self.no_detection_proceed_delay = time_config["no_detection_proceed"]
        self.no_detection_q_press_interval = float(time_config.get("no_detection_q_press_interval", 15.0))
        self.gadget_pixels_minimum = bot_config["gadget_pixels_minimum"]
        self.hypercharge_pixels_minimum = bot_config["hypercharge_pixels_minimum"]
        self.super_pixels_minimum = bot_config["super_pixels_minimum"]
        self.wall_detection_confidence = bot_config["wall_detection_confidence"]
        self.entity_detection_confidence = bot_config["entity_detection_confidence"]
        self.entity_detection_retry_confidence = float(
            bot_config.get("entity_detection_retry_confidence", max(0.35, self.entity_detection_confidence - 0.20))
        )
        self.player_center_bias_radius = float(bot_config.get("player_center_bias_radius", 420))
        self.player_green_pixel_weight = float(bot_config.get("player_green_pixel_weight", 0.03))
        self.player_red_pixel_penalty = float(bot_config.get("player_red_pixel_penalty", 0.05))
        self.time_since_holding_attack = None
        self.seconds_to_hold_attack_after_reaching_max = load_toml_as_dict("cfg/bot_config.toml")["seconds_to_hold_attack_after_reaching_max"]
        self.current_frame = None
        general_config = load_toml_as_dict("cfg/general_config.toml")
        lobby_config = load_toml_as_dict("./cfg/lobby_config.toml")
        self.super_crop_area = lobby_config['pixel_counter_crop_area']['super']
        self.gadget_crop_area = lobby_config['pixel_counter_crop_area']['gadget']
        self.hypercharge_crop_area = lobby_config['pixel_counter_crop_area']['hypercharge']
        global debug, visual_debug
        debug = str(general_config.get("super_debug", "no")).lower() in ("yes", "true", "1")
        visual_debug = str(general_config.get("visual_debug", "no")).lower() in ("yes", "true", "1")
        self.visual_debug_scale = max(0.25, min(1.0, float(general_config.get("visual_debug_scale", 0.6))))
        self.visual_debug_max_fps = max(1.0, float(general_config.get("visual_debug_max_fps", 30)))
        self.visual_debug_max_boxes = max(20, int(general_config.get("visual_debug_max_boxes", 120)))
        self.visual_debug_max_wall_boxes = max(0, int(general_config.get("visual_debug_max_wall_boxes", 250)))
        self.visual_debug_motion_boxes = str(general_config.get("visual_debug_motion_boxes", "no")).lower() in ("yes", "true", "1")
        self._visual_debug_next_frame_at = 0.0
        self._visual_debug_next_enqueue_at = 0.0
        self._visual_debug_lock = threading.Lock()
        self._visual_debug_payload = None
        self._visual_debug_thread = None
        self._visual_debug_stop = False
        self.capture_bad_vision_frames = str(general_config.get("capture_bad_vision_frames", "no")).lower() in ("yes", "true", "1")
        self.bad_vision_capture_dir = general_config.get("bad_vision_capture_dir", "debug_frames/vision")
        self.bad_vision_capture_interval = float(general_config.get("bad_vision_capture_interval", 2.0))
        self.bad_vision_capture_max = int(general_config.get("bad_vision_capture_max", 500))
        self._bad_vision_last_capture = {}
        self._bad_vision_capture_count = 0
        # Fog color (poison gas in showdown) — sampled from images/fog_sample.png.
        # Narrow range because the fog fully overlays whatever is under it.
        self.fog_hsv_low = (50, 95, 215)
        self.fog_hsv_high = (60, 125, 245)
        # Fog proximity override: movement flees fog when a real fog front is
        # within this distance. Attack logic is untouched.
        self.fog_flee_distance = 130
        # Confidence filters to avoid reacting to stray pixels:
        #   - morph opening kernel removes speckle noise
        #   - only connected fog blobs ≥ this many pixels are trusted
        #   - need at least this many trusted fog pixels inside the flee
        #     radius before the override kicks in
        self.fog_min_blob_pixels = 300
        self.fog_min_pixels_in_radius = 50
        # Run the fog-threat check once every N calls to get_showdown_movement.
        # Between checks the previous decision is reused.
        self.fog_check_every_n_frames = 3
        self._fog_check_counter = 0
        self._fog_threat_cached = None
        self._fog_direction_escape_cached = None
        # Per-frame cache of the trusted fog mask, keyed by id(frame).
        # Cache covers one pipeline run so the mask is not rebuilt when both
        # detect_fog_threat and detect_fog_direction are called on the same frame.
        self._fog_mask_cache_frame_id = None
        self._fog_mask_cache_value = None
        self._fog_mask_cache_origin = None
        self.playstyle_name = str(bot_config.get("current_playstyle", "")).strip()
        self.playstyle_meta = {}
        self.playstyle_code = None
        self._playstyle_error_reported = False
        self.load_playstyle()

        try:
            from rl.projectile_tracker import ProjectileTracker
            self.projectile_tracker = ProjectileTracker(
                history_seconds=self.rl_projectile_history_seconds,
                min_speed_px_s=self.rl_projectile_min_speed_px_s,
                max_match_distance=self.rl_projectile_max_match_distance,
                # Map 0..1 confidence to a cosine alignment threshold so the
                # tracker only counts tracks heading at the player.
                # 0.5 -> 0 (±90°), 0.75 -> 0.5 (±60°), 0.9 -> 0.8 (±37°).
                incoming_min_alignment=max(
                    -1.0, min(1.0, 2.0 * self.projectile_detection_confidence - 1.0)
                ),
                enemy_origin_radius=self.rl_projectile_enemy_origin_radius,
                motion_enemy_origin_radius=self.rl_projectile_motion_origin_radius,
                friendly_origin_radius=self.rl_projectile_friendly_origin_radius,
                require_enemy_origin=self.rl_projectile_require_enemy_origin,
                require_enemy_origin_strict=self.rl_projectile_require_enemy_origin_strict,
                min_hits_to_promote=self.rl_projectile_min_hits_to_promote,
                max_speed_px_s=self.rl_projectile_max_speed_px_s,
                max_accel_px_s2=self.rl_projectile_max_accel_px_s2,
                max_line_residual_frac=self.rl_projectile_max_line_residual_frac,
            )
        except Exception as exc:
            print(f"Could not initialise projectile tracker: {exc}")
            self.projectile_tracker = None

        try:
            from rl.health_monitor import HealthMonitor
            from rl.red_flash import RedFlashDetector

            self.health_monitor = HealthMonitor(
                band_offset_px=self.health_bar_band_offset_px,
                band_height_px=self.health_bar_band_height_px,
                min_total_pixels=self.health_bar_min_total_pixels,
                damage_drop_threshold=self.damage_hp_drop_threshold_pct,
                prior_window_seconds=0.4,
                history_seconds=2.0,
                ocr_enabled=self.health_ocr_enabled,
                ocr_interval_seconds=self.health_ocr_interval_seconds,
            )
            self.red_flash_detector = RedFlashDetector(
                threshold=self.red_flash_red_dom_threshold,
                baseline_alpha=self.red_flash_baseline_alpha,
            )
        except Exception as exc:
            print(f"Could not initialise health / red-flash monitors: {exc}")
            self.health_monitor = None
            self.red_flash_detector = None

        self._visual_debug_red_flash = False
        self._rl_motion_prev_gray = None
        self._rl_motion_debug_boxes = []
        # Previous-frame motion/residual centers used to gate candidates
        # by direction-of-travel-toward-player.
        self._rl_prev_motion_centers: list = []
        self._rl_bridge = None
        self._rl_bridge_warned = False

    def load_playstyle(self):
        if not self.playstyle_name:
            return
        safe_name = os.path.basename(self.playstyle_name)
        path = os.path.join("playstyles", safe_name)
        if not os.path.exists(path):
            print(f"Playstyle '{safe_name}' was not found. Falling back to built-in logic.")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                try:
                    self.playstyle_meta = json.loads(first_line) if first_line.startswith("{") else {}
                    source = f.read()
                except json.JSONDecodeError:
                    self.playstyle_meta = {}
                    source = first_line + "\n" + f.read()
            self.playstyle_code = compile(source, path, "exec")
            print(f"Loaded playstyle: {safe_name}")
        except Exception as e:
            print(f"Could not load playstyle '{safe_name}': {e}. Falling back to built-in logic.")
            self.playstyle_code = None

    def run_playstyle(self, player_data, enemy_data, walls, brawler):
        if self.playstyle_code is None:
            return None

        persistent_data = {
            "time_since_holding_attack": self.time_since_holding_attack,
        }

        def use_hypercharge_wrapper():
            if self.use_hypercharge():
                self.time_since_hypercharge_checked = time.time()
                self.clear_ability_ready("hypercharge")

        def use_gadget_wrapper():
            if self.should_use_gadget:
                if self.use_gadget():
                    self.time_since_gadget_checked = time.time()
                    self.clear_ability_ready("gadget")

        def use_super_wrapper():
            if self.use_super():
                self.time_since_super_checked = time.time()
                self.clear_ability_ready("super")

        env = {
            "__builtins__": {
                "abs": abs,
                "bool": bool,
                "float": float,
                "int": int,
                "len": len,
                "max": max,
                "min": min,
                "print": print,
                "range": range,
                "str": str,
                "ValueError": ValueError,
            },
            "time": time,
            "random": random,
            "debug": debug,
            "brawler": brawler,
            "brawlers_info": self.brawlers_info,
            "player_data": player_data,
            "enemy_data": enemy_data,
            "teammate_data": getattr(self, "last_playstyle_teammate_data", None),
            "walls": walls,
            "game_mode": self.game_mode,
            "persistent_data": persistent_data,
            "seconds_to_hold_attack_after_reaching_max": self.seconds_to_hold_attack_after_reaching_max,
            "is_hypercharge_ready": self.is_hypercharge_ready,
            "is_gadget_ready": self.should_use_gadget and self.is_gadget_ready,
            "is_super_ready": self.is_super_ready,
            "movement": None,
            "attack": self.attack,
            "use_hypercharge": use_hypercharge_wrapper,
            "use_gadget": use_gadget_wrapper,
            "use_super": use_super_wrapper,
            "should_use_super_on_enemy": self.should_use_super_on_enemy,
            "must_brawler_hold_attack": self.must_brawler_hold_attack,
            "get_brawler_range": self.get_brawler_range,
            "get_player_pos": self.get_player_pos,
            "get_entity_pos": self.get_entity_pos,
            "is_there_enemy": self.is_there_enemy,
            "is_there_poison_gas": self.is_there_poison_gas,
            "no_enemy_movement": self.no_enemy_movement,
            "find_closest_enemy": self.find_closest_enemy,
            "find_closest_teammate": self.find_closest_teammate,
            "get_horizontal_move_key": self.get_horizontal_move_key,
            "get_vertical_move_key": self.get_vertical_move_key,
            "is_path_blocked": self.is_path_blocked,
            "is_enemy_hittable": self.is_enemy_hittable,
        }

        try:
            exec(self.playstyle_code, env, env)
        except Exception as e:
            if not self._playstyle_error_reported:
                print(f"Playstyle '{self.playstyle_name}' failed: {e}. Falling back to built-in logic.")
                self._playstyle_error_reported = True
            return None

        self.time_since_holding_attack = persistent_data.get("time_since_holding_attack")
        return env.get("movement")

    def capture_vision_frame(self, reason, frame, data=None, brawler=None, extra=None):
        if not self.capture_bad_vision_frames or frame is None:
            return
        if self._bad_vision_capture_count >= self.bad_vision_capture_max:
            return
        now = time.time()
        last = self._bad_vision_last_capture.get(reason, 0.0)
        if now - last < self.bad_vision_capture_interval:
            return

        safe_reason = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(reason))
        folder = os.path.join(self.bad_vision_capture_dir, safe_reason)
        os.makedirs(folder, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{int((now % 1) * 1000):03d}"
        image_path = os.path.join(folder, f"{stamp}.png")
        meta_path = os.path.join(folder, f"{stamp}.json")

        cv2.imwrite(image_path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        metadata = {
            "reason": reason,
            "brawler": brawler or self.current_brawler,
            "time": now,
            "data": data or {},
            "extra": extra or {},
        }
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2)

        self._bad_vision_last_capture[reason] = now
        self._bad_vision_capture_count += 1
        print(f"Captured vision frame: {image_path}")

    def reset_match_control_state(self):
        self.window_controller.keys_up(list("wasd"))
        self.keys_hold = []
        self.last_movement = None
        self.last_movement_time = time.time()
        self.time_since_movement = 0
        self.time_since_different_movement = time.time()
        self.time_since_player_last_found = time.time()
        self.time_since_last_proceeding = time.time()
        self.fix_movement_keys['toggled'] = False
        self.time_since_holding_attack = None
        if getattr(self, "projectile_tracker", None) is not None:
            try:
                self.projectile_tracker.reset()
            except Exception:
                pass
        if getattr(self, "health_monitor", None) is not None:
            try:
                self.health_monitor.reset_match()
            except Exception:
                pass
        if getattr(self, "red_flash_detector", None) is not None:
            try:
                self.red_flash_detector.reset()
            except Exception:
                pass
        self._rl_motion_prev_gray = None
        self._rl_motion_debug_boxes = []
        bridge = getattr(self, "_rl_bridge", None)
        if bridge and bridge is not False and hasattr(bridge, "on_match_reset"):
            try:
                bridge.on_match_reset()
            except Exception as exc:
                print(f"RL bridge match reset failed: {exc}")

    def load_brawler_ranges(self, brawlers_info=None):
        if not brawlers_info:
            brawlers_info = load_brawlers_info()
        screen_size_ratio = self.window_controller.scale_factor
        ranges = {}
        for brawler, info in brawlers_info.items():
            attack_range = info['attack_range']
            safe_range = info['safe_range']
            super_range = info['super_range']
            v = [safe_range, attack_range, super_range]
            ranges[brawler] = [int(v[0] * screen_size_ratio), int(v[1] * screen_size_ratio), int(v[2] * screen_size_ratio)]
        return ranges

    @staticmethod
    def can_attack_through_walls(brawler, skill_type, brawlers_info=None):
        if not brawlers_info: brawlers_info = load_brawlers_info()
        if skill_type == "attack":
            return brawlers_info[brawler]['ignore_walls_for_attacks']
        elif skill_type == "super":
            return brawlers_info[brawler]['ignore_walls_for_supers']
        raise ValueError("skill_type must be either 'attack' or 'super'")

    @staticmethod
    def must_brawler_hold_attack(brawler, brawlers_info=None):
        if not brawlers_info: brawlers_info = load_brawlers_info()
        return brawlers_info[brawler]['hold_attack'] > 0

    @staticmethod
    def walls_block_line_of_sight(p1, p2, walls, padding=0):
        if not walls:
            return False

        p1_t = (int(p1[0]), int(p1[1]))
        p2_t = (int(p2[0]), int(p2[1]))
        min_x, max_x = min(p1_t[0], p2_t[0]), max(p1_t[0], p2_t[0])
        min_y, max_y = min(p1_t[1], p2_t[1]), max(p1_t[1], p2_t[1])
        padding = int(max(0, padding))
        for wall in walls:
            x1, y1, x2, y2 = wall
            x1 -= padding
            y1 -= padding
            x2 += padding
            y2 += padding

            if max_x < x1 or min_x > x2 or max_y < y1 or min_y > y2:
                continue

            rect = (int(x1), int(y1), int(x2 - x1), int(y2 - y1))
            if cv2.clipLine(rect, p1_t, p2_t)[0]:
                return True
        return False

    def no_enemy_movement(self, player_data, walls):
        player_position = self.get_player_pos(player_data)
        preferred_movement = 'W' if self.game_mode == 3 else 'D'  # Adjust based on game mode

        if not self.is_path_blocked(player_position, preferred_movement, walls):
            return preferred_movement
        else:
            # Try alternative movements
            alternative_moves = ['W', 'A', 'S', 'D']
            alternative_moves.remove(preferred_movement)
            random.shuffle(alternative_moves)
            for move in alternative_moves:
                if not self.is_path_blocked(player_position, move, walls):
                    return move
            print("no movement possible ?")
            # If no movement is possible, return empty string
            return preferred_movement

    def get_entity_pos(self, entity):
        return self.get_enemy_pos(entity)

    def find_closest_teammate(self, teammate_data, player_coords, walls=None):
        closest_distance = float('inf')
        closest_teammate = None
        for teammate in teammate_data or []:
            teammate_pos = self.get_enemy_pos(teammate)
            distance = self.get_distance(teammate_pos, player_coords)
            if distance < closest_distance:
                closest_distance = distance
                closest_teammate = teammate_pos
        return closest_teammate, closest_distance

    def _build_trusted_fog_mask(self, frame, roi_center, roi_radius):
        """Return (mask, (ox, oy)) or None.

        Only processes an ROI of side 2*roi_radius+1 around roi_center —
        we only care about fog that's close to the player.
        Mask contains only fog pixels that belong to a large, morphologically
        clean blob — not stray color noise. (ox, oy) is the ROI's top-left
        offset in frame coordinates so callers can translate back.

        Result is cached per-frame (keyed by id(frame) and ROI tuple).
        """
        if frame is None:
            return None

        roi_radius = int(max(1, roi_radius))
        cache_key = (id(frame), int(roi_center[0]), int(roi_center[1]), int(roi_radius))
        if self._fog_mask_cache_frame_id == cache_key:
            return self._fog_mask_cache_value

        import numpy as np
        h, w = frame.shape[:2]
        cx, cy = int(roi_center[0]), int(roi_center[1])
        x0, y0 = max(0, cx - roi_radius), max(0, cy - roi_radius)
        x1, y1 = min(w, cx + roi_radius + 1), min(h, cy + roi_radius + 1)
        if x0 >= x1 or y0 >= y1:
            self._fog_mask_cache_frame_id = cache_key
            self._fog_mask_cache_value = None
            return None
        region = frame[y0:y1, x0:x1]
        origin = (x0, y0)

        hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
        low = np.array(self.fog_hsv_low, dtype=np.uint8)
        high = np.array(self.fog_hsv_high, dtype=np.uint8)
        mask = cv2.inRange(hsv, low, high)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        result = None
        if num_labels > 1:
            trusted = np.zeros_like(mask)
            any_kept = False
            for label in range(1, num_labels):
                if stats[label, cv2.CC_STAT_AREA] >= self.fog_min_blob_pixels:
                    trusted[labels == label] = 255
                    any_kept = True
            if any_kept and cv2.countNonZero(trusted) > 0:
                result = (trusted, origin)

        self._fog_mask_cache_frame_id = cache_key
        self._fog_mask_cache_value = result
        return result

    def detect_fog_threat(self, frame, player_position):
        """Check whether a real fog front is within self.fog_flee_distance of
        the player. Returns the flee angle (away from local fog mass) if so,
        else None.

        Confidence pipeline:
          1. HSV threshold → raw mask.
          2. Morph open + size-filtered connected components → trusted mask.
          3. Count trusted fog pixels inside a disk of radius fog_flee_distance
             around the player. If count ≥ fog_min_pixels_in_radius, it's a
             real incoming front — not a stray artifact.
        The flee direction is the angle opposite to the centroid of the
        trusted fog pixels *inside the radius*, so we run away from the
        closest wall of fog, not from fog on the far side of the map.
        """
        r = self.fog_flee_distance
        built = self._build_trusted_fog_mask(frame, roi_center=player_position, roi_radius=r)
        if built is None:
            return None
        mask, (ox, oy) = built

        import numpy as np
        px, py = int(player_position[0]), int(player_position[1])
        ys, xs = np.nonzero(mask)
        if xs.size == 0:
            return None

        # Translate ROI-local coords to frame coords, then filter to circle
        dx_all = (xs + ox) - px
        dy_all = (ys + oy) - py
        dist_sq = dx_all * dx_all + dy_all * dy_all
        inside = dist_sq <= r * r
        count = int(inside.sum())
        if count < self.fog_min_pixels_in_radius:
            return None

        # Centroid of the nearby fog mass, then flee opposite direction
        cx = float(dx_all[inside].mean())
        cy = float(dy_all[inside].mean())
        if math.hypot(cx, cy) < 1:
            return None
        toward_fog = self.angle_from_direction(cx, cy)
        flee = self.angle_opposite(toward_fog)
        vlog(f"fog threat: {count}px within {r}px → flee angle={flee:.1f}° (fog at {toward_fog:.1f}°)")
        return flee

    def detect_fog_direction_escape(self, frame, player_position):
        """Return an escape angle if poison gas is touching a side of player.

        This mirrors the official v0.8.3 playstyle idea: check up/down/left/right
        close to the player and move in the opposite direction. It complements
        the centroid-based fog detector, which can miss thin gas edges.
        """
        r = int(max(self.fog_flee_distance, 120))
        built = self._build_trusted_fog_mask(frame, roi_center=player_position, roi_radius=r)
        if built is None:
            return None
        mask, (ox, oy) = built

        import numpy as np
        px, py = int(player_position[0]), int(player_position[1])
        ys, xs = np.nonzero(mask)
        if xs.size == 0:
            return None

        dx = (xs + ox) - px
        dy = (ys + oy) - py
        band = max(35, int(r * 0.45))
        min_pixels = max(20, int(self.fog_min_pixels_in_radius * 0.55))

        direction_counts = {
            "up": int(((dy < 0) & (dy >= -r) & (np.abs(dx) <= band)).sum()),
            "down": int(((dy > 0) & (dy <= r) & (np.abs(dx) <= band)).sum()),
            "left": int(((dx < 0) & (dx >= -r) & (np.abs(dy) <= band)).sum()),
            "right": int(((dx > 0) & (dx <= r) & (np.abs(dy) <= band)).sum()),
        }

        escape_x = 0.0
        escape_y = 0.0
        if direction_counts["up"] >= min_pixels and direction_counts["up"] > direction_counts["down"] + min_pixels:
            escape_y += 1.0
        if direction_counts["down"] >= min_pixels and direction_counts["down"] > direction_counts["up"] + min_pixels:
            escape_y -= 1.0
        if direction_counts["left"] >= min_pixels and direction_counts["left"] > direction_counts["right"] + min_pixels:
            escape_x += 1.0
        if direction_counts["right"] >= min_pixels and direction_counts["right"] > direction_counts["left"] + min_pixels:
            escape_x -= 1.0

        if math.hypot(escape_x, escape_y) < 0.01:
            return None

        angle = self.angle_from_direction(escape_x, escape_y)
        vlog(f"directional fog escape: counts={direction_counts} -> angle={angle:.1f} deg")
        return angle

    def is_there_poison_gas(self, direction, player_data):
        if self.current_frame is None or player_data is None:
            return False
        player_pos = self.get_player_pos(player_data)
        r = int(max(80, min(self.fog_flee_distance, 150)))
        built = self._build_trusted_fog_mask(self.current_frame, roi_center=player_pos, roi_radius=r)
        if built is None:
            return False
        mask, (ox, oy) = built
        import numpy as np
        ys, xs = np.nonzero(mask)
        if xs.size == 0:
            return False

        px, py = player_pos
        dx = (xs + ox) - px
        dy = (ys + oy) - py
        band = max(30, int(r * 0.45))
        min_pixels = max(12, int(self.fog_min_pixels_in_radius * 0.45))
        direction = str(direction).lower()
        try:
            player_half_width = max(8, abs(float(player_data[2]) - float(player_data[0])) * 0.55)
            player_half_height = max(8, abs(float(player_data[3]) - float(player_data[1])) * 0.55)
        except (TypeError, ValueError, IndexError):
            player_half_width = player_half_height = max(12, band * 0.35)
        player_area = (np.abs(dx) <= player_half_width) & (np.abs(dy) <= player_half_height)
        if int(player_area.sum()) >= min_pixels:
            return True
        checks = {
            "up": (dy < 0) & (dy >= -r) & (np.abs(dx) <= band),
            "down": (dy > 0) & (dy <= r) & (np.abs(dx) <= band),
            "left": (dx < 0) & (dx >= -r) & (np.abs(dy) <= band),
            "right": (dx > 0) & (dx <= r) & (np.abs(dy) <= band),
        }
        if direction not in checks:
            return False
        return int(checks[direction].sum()) >= min_pixels

    def showdown_roam(self, player_data, walls):
        """Idle roam movement that travels instead of spinning in place.

        Close-fog avoidance is still handled by the uniform fog override in
        get_showdown_movement, but this keeps ordinary no-enemy movement away
        from walls and lightly biased toward screen center.
        """
        now = time.time()
        player_pos = self.get_player_pos(player_data)
        current_blocked = self.is_path_blocked_angle(player_pos, self._roam_angle, walls)
        time_expired = (now - self._roam_last_changed) > self.roam_direction_hold_time

        if current_blocked or time_expired:
            new_angle = None
            for _ in range(16):
                candidate = random.uniform(0, 360)
                if not self.is_path_blocked_angle(player_pos, candidate, walls):
                    new_angle = candidate
                    break
            if new_angle is None:
                new_angle = self.find_best_angle(player_pos, (self._roam_angle + 180) % 360, walls)

            if self.roam_center_bias > 0:
                screen_cx, screen_cy = 960.0, 540.0
                dx = screen_cx - player_pos[0]
                dy = screen_cy - player_pos[1]
                if math.hypot(dx, dy) > 160:
                    toward_center = self.angle_from_direction(dx, dy)
                    blended = self.blend_angles(new_angle, toward_center, self.roam_center_bias)
                    if not self.is_path_blocked_angle(player_pos, blended, walls):
                        new_angle = blended

            self._roam_angle = new_angle % 360
            self._roam_last_changed = now
            vlog(f"roam: new direction -> {self._roam_angle:.1f}°")

        vlog(f"roam: holding -> angle={self._roam_angle:.1f}°")
        return self._roam_angle

    @staticmethod
    def angle_to_vector(angle_degrees):
        angle_rad = math.radians(angle_degrees)
        return math.cos(angle_rad), math.sin(angle_rad)

    def blend_angles(self, primary_angle, secondary_angle, secondary_weight):
        primary_weight = max(0.0, 1.0 - secondary_weight)
        sx = max(0.0, secondary_weight)
        ax, ay = self.angle_to_vector(primary_angle)
        bx, by = self.angle_to_vector(secondary_angle)
        dx = ax * primary_weight + bx * sx
        dy = ay * primary_weight + by * sx
        if math.hypot(dx, dy) < 0.01:
            return primary_angle
        return self.angle_from_direction(dx, dy)

    def get_strafe_angle(self, toward_enemy_angle, current_time, enemy_distance=None, safe_range=None):
        if self._strafe_started_at == 0.0:
            self._strafe_started_at = current_time
            self._strafe_current_interval = self.strafe_interval

        elapsed = current_time - self._strafe_started_at
        if elapsed >= self._strafe_current_interval:
            self._strafe_side *= -1
            self._strafe_started_at = current_time
            jitter = random.uniform(-0.3, 0.3) * self.strafe_interval
            self._strafe_current_interval = max(0.5, self.strafe_interval + jitter)
            elapsed = 0.0

        if enemy_distance is not None and safe_range is not None and enemy_distance < safe_range * 0.6:
            random_kick = random.uniform(65.0, 90.0) * self._strafe_side + random.uniform(-15.0, 15.0)
            return (toward_enemy_angle + random_kick) % 360

        t = elapsed / max(0.001, self._strafe_current_interval)
        sine_factor = math.sin(t * math.pi)
        strafe_offset = 90.0 * self._strafe_side * max(0.55, sine_factor)
        return (toward_enemy_angle + strafe_offset) % 360

    def get_combat_dodge_angle(self, toward_enemy_angle, current_time, enemy_distance=None, safe_range=None):
        """Sideways movement used while shooting so the bot does not become an easy target."""
        strafe_angle = self.get_strafe_angle(toward_enemy_angle, current_time, enemy_distance, safe_range)
        jitter = float(getattr(self, "combat_dodge_jitter_degrees", 0.0))
        if jitter > 0:
            strafe_angle = (strafe_angle + random.uniform(-jitter, jitter)) % 360
        return strafe_angle

    def apply_combat_dodge(self, desired_angle, toward_enemy_angle, current_time, enemy_distance, safe_range):
        if not self.strafe_enabled:
            return desired_angle
        dodge_angle = self.get_combat_dodge_angle(toward_enemy_angle, current_time, enemy_distance, safe_range)
        blend = max(0.0, min(1.0, float(getattr(self, "combat_dodge_blend", 0.0))))
        if enemy_distance is not None and safe_range is not None and enemy_distance <= safe_range:
            blend = max(blend, min(0.85, blend + 0.15))
        return self.blend_angles(desired_angle, dodge_angle, blend)

    def track_enemy_velocity(self, enemy_coords, current_time):
        grid = 25
        rounded_key = (round(enemy_coords[0] / grid) * grid, round(enemy_coords[1] / grid) * grid)
        best_key = None
        best_dist = (grid * 4) ** 2
        for key, item in list(self._enemy_track.items()):
            age = current_time - item["time"]
            if age > 2.5:
                self._enemy_track.pop(key, None)
                self._enemy_velocity_smooth.pop(key, None)
                self._enemy_velocity_confidence.pop(key, None)
                continue
            dist = (key[0] - rounded_key[0]) ** 2 + (key[1] - rounded_key[1]) ** 2
            if dist < best_dist:
                best_dist = dist
                best_key = key
        if best_key is None:
            self._enemy_track[rounded_key] = {"pos": enemy_coords, "time": current_time}
            self._enemy_velocity_confidence[rounded_key] = 0
            self.enemy_velocity_confidence = 0.0
            return 0.0, 0.0

        previous = self._enemy_track.pop(best_key)
        previous_smooth = self._enemy_velocity_smooth.pop(best_key, None)
        previous_confidence = self._enemy_velocity_confidence.pop(best_key, 0)
        dt = max(0.001, current_time - previous["time"])
        raw_vx = max(-1200.0, min(1200.0, (enemy_coords[0] - previous["pos"][0]) / dt))
        raw_vy = max(-1200.0, min(1200.0, (enemy_coords[1] - previous["pos"][1]) / dt))
        alpha = self.velocity_ema_alpha
        if previous_smooth is None:
            smooth_vx, smooth_vy = raw_vx, raw_vy
        else:
            smooth_vx = alpha * raw_vx + (1.0 - alpha) * previous_smooth[0]
            smooth_vy = alpha * raw_vy + (1.0 - alpha) * previous_smooth[1]

        new_confidence = min(previous_confidence + 1, 8)
        self.enemy_velocity_confidence = min(1.0, new_confidence / 4.0)
        self._enemy_track[rounded_key] = {"pos": enemy_coords, "time": current_time}
        self._enemy_velocity_smooth[rounded_key] = (smooth_vx, smooth_vy)
        self._enemy_velocity_confidence[rounded_key] = new_confidence
        return smooth_vx, smooth_vy

    def lead_shot_angle(self, player_pos, enemy_coords, enemy_velocity, projectile_speed_px_s=None, confidence=1.0):
        projectile_speed = projectile_speed_px_s or self.projectile_speed_px_s
        dx = enemy_coords[0] - player_pos[0]
        dy = enemy_coords[1] - player_pos[1]
        direct_angle = self.angle_from_direction(dx, dy)
        if math.hypot(dx, dy) < 1 or projectile_speed <= 1:
            return direct_angle

        vx, vy = enemy_velocity
        if math.hypot(vx, vy) < 15:
            return direct_angle

        a = vx * vx + vy * vy - projectile_speed * projectile_speed
        b = 2 * (dx * vx + dy * vy)
        c = dx * dx + dy * dy
        if abs(a) < 1e-6:
            if abs(b) < 1e-6:
                return direct_angle
            t = -c / b
        else:
            discriminant = b * b - 4 * a * c
            if discriminant < 0:
                return direct_angle
            root = math.sqrt(discriminant)
            candidates = [(-b - root) / (2 * a), (-b + root) / (2 * a)]
            positive = [value for value in candidates if value > 0]
            if not positive:
                return direct_angle
            t = min(positive)
        if t <= 0 or t > 1.5:
            return direct_angle

        led_angle = self.angle_from_direction(dx + vx * t, dy + vy * t)
        if confidence < 1.0:
            led_angle = self.blend_angles(direct_angle, led_angle, confidence)
        return led_angle

    def get_closest_teammate(self, player_data, teammate_data):
        player_pos = self.get_player_pos(player_data)
        closest_teammate = None
        closest_distance = float('inf')
        for tm in teammate_data or []:
            tm_pos = self.get_enemy_pos(tm)
            dist = self.get_distance(tm_pos, player_pos)
            if dist < closest_distance:
                closest_distance = dist
                closest_teammate = tm_pos
        return closest_teammate, closest_distance

    def showdown_follow_teammate(self, player_data, teammate_data, walls):
        """Keep a useful Trio Showdown spacing around the closest teammate."""
        player_pos = self.get_player_pos(player_data)
        closest_teammate, closest_distance = self.get_closest_teammate(player_data, teammate_data)

        if closest_teammate is None:
            self.locked_teammate = None
            self.locked_teammate_distance = float('inf')
            return self.showdown_roam(player_data, walls)

        # Hysteresis only applies when there are multiple teammates to choose from.
        # If we already have a locked target, check whether to switch to a closer one.
        # Either way, always update the locked target's position to this frame's value.
        if self.locked_teammate is not None:
            locked_dist = self.get_distance(self.locked_teammate, player_pos)
            if closest_distance < locked_dist * (1 - self.teammate_hysteresis):
                vlog(f"follow teammate: switched target ({int(locked_dist)}px → {int(closest_distance)}px)")
                self.locked_teammate = closest_teammate
                self.locked_teammate_distance = closest_distance
            else:
                # Same target (or similar) — update its position to the current frame
                self.locked_teammate = closest_teammate
                self.locked_teammate_distance = closest_distance
        else:
            self.locked_teammate = closest_teammate
            self.locked_teammate_distance = closest_distance

        direction_x = self.locked_teammate[0] - player_pos[0]
        direction_y = self.locked_teammate[1] - player_pos[1]
        teammate_angle = self.angle_from_direction(direction_x, direction_y)
        if self.trio_grouping_enabled and closest_distance < self.teammate_follow_min_distance:
            angle = self.angle_opposite(teammate_angle)
            action = "space"
        elif self.trio_grouping_enabled and closest_distance <= self.teammate_follow_max_distance:
            orbit_side = 1 if (int(time.time() / 2) % 2 == 0) else -1
            angle = (teammate_angle + 90 * orbit_side) % 360
            action = "orbit"
        else:
            angle = teammate_angle
            action = "follow"
        best = self.find_best_angle(player_pos, angle, walls)
        vlog(f"{action} teammate → angle={best:.1f}° (desired={angle:.1f}°, dist={int(closest_distance)}px, "
             f"player={int(player_pos[0])},{int(player_pos[1])} tm={int(self.locked_teammate[0])},{int(self.locked_teammate[1])})")
        return best

    def get_showdown_movement(self, player_data, enemy_data, teammate_data, walls, brawler):
        """Showdown movement using analog joystick angles.

        Always returns a float angle in degrees (0–360).
        0° = right, 90° = down, 180° = left, 270° = up.
        """
        brawler_info = self.brawlers_info.get(brawler)
        if not brawler_info:
            raise ValueError(f"Brawler '{brawler}' not found in brawlers info.")

        must_brawler_hold_attack = self.must_brawler_hold_attack(brawler, self.brawlers_info)
        if must_brawler_hold_attack and self.time_since_holding_attack is not None and \
                time.time() - self.time_since_holding_attack >= brawler_info['hold_attack'] + self.seconds_to_hold_attack_after_reaching_max:
            self.attack(touch_up=True, touch_down=False)
            self.time_since_holding_attack = None

        safe_range, attack_range, super_range = self.get_brawler_range(brawler)
        player_pos = self.get_player_pos(player_data)

        # Fog override is applied uniformly at the end so it works for all
        # three movement sources (chase/retreat enemy, follow teammate, roam).
        # Throttled: only actually run the detector once every N calls and
        # reuse the last decision in between — the fog advances slowly enough
        # that a few frames of staleness don't matter.
        self._fog_check_counter += 1
        if self._fog_check_counter >= self.fog_check_every_n_frames:
            self._fog_threat_cached = self.detect_fog_threat(self.current_frame, player_pos)
            self._fog_direction_escape_cached = self.detect_fog_direction_escape(self.current_frame, player_pos)
            self._fog_check_counter = 0
        fog_flee_angle = self._fog_direction_escape_cached or self._fog_threat_cached

        enemy_coords = None
        enemy_distance = None

        # --- No enemy in sight: follow teammate or roam ---
        if not self.is_there_enemy(enemy_data):
            if teammate_data:
                vlog(f"no enemy → follow teammate ({len(teammate_data)} visible)")
                angle = self.showdown_follow_teammate(player_data, teammate_data, walls)
            else:
                vlog("no enemy, no teammate → roam")
                angle = self.showdown_roam(player_data, walls)
        else:
            enemy_coords, enemy_distance = self.find_closest_enemy(enemy_data, player_pos, walls, "attack")
            if enemy_coords is None:
                if teammate_data:
                    vlog("enemy detected but unreachable → follow teammate")
                    angle = self.showdown_follow_teammate(player_data, teammate_data, walls)
                else:
                    vlog("enemy detected but unreachable, no teammate → roam")
                    angle = self.showdown_roam(player_data, walls)
            else:
                # --- Compute exact angle toward/away from enemy, then wall-avoid ---
                direction_x = enemy_coords[0] - player_pos[0]
                direction_y = enemy_coords[1] - player_pos[1]
                toward_angle = self.angle_from_direction(direction_x, direction_y)
                now_t = time.time()
                if self.lead_shots_enabled:
                    self.enemy_velocity = self.track_enemy_velocity(enemy_coords, now_t)
                else:
                    self.enemy_velocity = (0.0, 0.0)
                    self.enemy_velocity_confidence = 0.0

                if enemy_distance > safe_range:
                    desired = toward_angle
                    vlog(f"enemy detected → approach desired={desired:.1f}° (dist={int(enemy_distance)}px, safe={safe_range}px)")
                    if self.approach_flank_blend > 0 and enemy_distance > safe_range * 1.2:
                        flank_angle = (toward_angle + 90 * self._strafe_side) % 360
                        desired = self.blend_angles(desired, flank_angle, self.approach_flank_blend)
                        vlog(f"approach flank blend -> desired={desired:.1f}°")
                else:
                    desired = self.angle_opposite(toward_angle)
                    vlog(f"enemy too close → retreat desired={desired:.1f}° (dist={int(enemy_distance)}px, safe={safe_range}px)")
                    if self.multi_enemy_flee_weight > 0 and enemy_data and len(enemy_data) > 1:
                        mass_x = sum(self.get_enemy_pos(enemy)[0] for enemy in enemy_data) / len(enemy_data)
                        mass_y = sum(self.get_enemy_pos(enemy)[1] for enemy in enemy_data) / len(enemy_data)
                        mass_dx = mass_x - player_pos[0]
                        mass_dy = mass_y - player_pos[1]
                        if math.hypot(mass_dx, mass_dy) > 10:
                            mass_flee = self.angle_opposite(self.angle_from_direction(mass_dx, mass_dy))
                            desired = self.blend_angles(desired, mass_flee, self.multi_enemy_flee_weight)
                            vlog(f"multi-enemy flee blend -> desired={desired:.1f}°")

                if (
                        self.strafe_enabled
                        and fog_flee_angle is None
                        and safe_range < enemy_distance <= attack_range
                ):
                    strafe_angle = self.get_strafe_angle(toward_angle, now_t, enemy_distance, safe_range)
                    desired = self.blend_angles(desired, strafe_angle, self.strafe_blend)
                    vlog(f"strafe blend → desired={desired:.1f}°")
                elif (
                        self.strafe_enabled
                        and fog_flee_angle is None
                        and enemy_distance <= safe_range
                        and self.retreat_strafe_fraction > 0
                ):
                    strafe_angle = self.get_strafe_angle(toward_angle, now_t, enemy_distance, safe_range)
                    desired = self.blend_angles(
                        desired,
                        strafe_angle,
                        self.strafe_blend * self.retreat_strafe_fraction,
                    )
                    vlog(f"retreat strafe blend -> desired={desired:.1f}°")

                if self.strafe_enabled and fog_flee_angle is None and enemy_distance <= attack_range:
                    desired = self.apply_combat_dodge(desired, toward_angle, now_t, enemy_distance, safe_range)
                    vlog(f"combat dodge blend -> desired={desired:.1f}°")

                if (self.trio_grouping_enabled and teammate_data and enemy_distance > attack_range):
                    closest_teammate, teammate_distance = self.get_closest_teammate(player_data, teammate_data)
                    if closest_teammate is not None and teammate_distance > self.teammate_combat_regroup_distance:
                        team_angle = self.angle_from_direction(
                            closest_teammate[0] - player_pos[0],
                            closest_teammate[1] - player_pos[1],
                        )
                        desired = self.blend_angles(desired, team_angle, self.teammate_combat_bias)
                        vlog(f"combat regroup bias → desired={desired:.1f}° (team dist={int(teammate_distance)}px)")

                angle = self.find_best_angle(player_pos, desired, walls)
                vlog(f"showdown: movement angle={angle:.1f}° (desired={desired:.1f}°)")

        # --- Fog proximity override ---
        # If trusted fog is close, replace movement with a flee angle. Attack
        # block below still fires independently based on enemy_distance.
        if fog_flee_angle is not None:
            angle = self.find_best_angle(player_pos, fog_flee_angle, walls)
            vlog(f"showdown: fog override → angle={angle:.1f}°")

        # --- Skills (only when an attackable enemy was found) ---
        if enemy_coords is None:
            return angle

        self.try_use_super_on_enemy(brawler, brawler_info, player_pos, enemy_coords, enemy_distance, walls)

        vlog(f"showdown movement → angle={angle:.1f}°")

        if enemy_distance <= attack_range:
            enemy_hittable = self.is_enemy_hittable(player_pos, enemy_coords, walls, "attack")
            vlog(f"enemy in attack range (dist={int(enemy_distance)}px, range={attack_range}px), hittable={enemy_hittable}")
            if enemy_hittable:
                if self.should_use_gadget and self.is_gadget_ready and self.time_since_holding_attack is None:
                    enemies_in_range = sum(
                        1 for enemy in (enemy_data or [])
                        if self.get_distance(self.get_enemy_pos(enemy), player_pos) <= attack_range
                    )
                    gadget_threshold = attack_range if enemies_in_range >= 2 else attack_range * 0.7
                    if enemy_distance <= gadget_threshold:
                        if self.use_gadget():
                            self.time_since_gadget_checked = time.time()
                            self.clear_ability_ready("gadget")

                if not must_brawler_hold_attack:
                    attack_angle = toward_angle
                    if self.lead_shots_enabled and self.enemy_velocity != (0.0, 0.0):
                        attack_angle = self.lead_shot_angle(
                            player_pos,
                            enemy_coords,
                            self.enemy_velocity,
                            confidence=getattr(self, "enemy_velocity_confidence", 1.0),
                        )
                    self.aimed_attack(attack_angle)
                else:
                    if self.time_since_holding_attack is None:
                        self.time_since_holding_attack = time.time()
                        self.attack(touch_up=False, touch_down=True)
                    elif time.time() - self.time_since_holding_attack >= self.brawlers_info[brawler]['hold_attack']:
                        self.attack(touch_up=True, touch_down=False)
                        self.time_since_holding_attack = None
        else:
            vlog(f"enemy out of attack range (dist={int(enemy_distance)}px, range={attack_range}px)")

        return angle

    def is_enemy_hittable(self, player_pos, enemy_pos, walls, skill_type):
        if self.can_attack_through_walls(self.current_brawler, skill_type, self.brawlers_info):
            return True
        if self.walls_block_line_of_sight(player_pos, enemy_pos, walls):
            return False
        return True

    def find_closest_enemy(self, enemy_data, player_coords, walls, skill_type):
        player_pos_x, player_pos_y = player_coords
        closest_hittable_distance = float('inf')
        closest_unhittable_distance = float('inf')
        closest_hittable = None
        closest_unhittable = None
        for enemy in enemy_data:
            enemy_pos = self.get_enemy_pos(enemy)
            distance = self.get_distance(enemy_pos, player_coords)
            if self.is_enemy_hittable((player_pos_x, player_pos_y), enemy_pos, walls, skill_type):
                if distance < closest_hittable_distance:
                    closest_hittable_distance = distance
                    closest_hittable = [enemy_pos, distance]
            else:
                if distance < closest_unhittable_distance:
                    closest_unhittable_distance = distance
                    closest_unhittable = [enemy_pos, distance]
        if closest_hittable:
            return closest_hittable
        elif closest_unhittable:
            return closest_unhittable

        return None, None

    @staticmethod
    def _count_mask_pixels(hsv_roi, lower, upper):
        if hsv_roi.size == 0:
            return 0
        mask = cv2.inRange(hsv_roi, np.array(lower, dtype=np.uint8), np.array(upper, dtype=np.uint8))
        return int(cv2.countNonZero(mask))

    def _entity_team_color_scores(self, frame, box):
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = map(int, self.normalize_box(box))
        pad_x = max(18, int((x2 - x1) * 0.45))
        pad_y = max(24, int((y2 - y1) * 0.75))
        rx1 = max(0, x1 - pad_x)
        ry1 = max(0, y1 - pad_y)
        rx2 = min(w, x2 + pad_x)
        ry2 = min(h, y2 + pad_y)
        roi = frame[ry1:ry2, rx1:rx2]
        if roi.size == 0:
            return 0, 0
        hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
        # Friendly self/teammate overlays are bright green; enemy HP/name UI is red/orange.
        green = self._count_mask_pixels(hsv, (35, 80, 80), (85, 255, 255))
        red = (
            self._count_mask_pixels(hsv, (0, 80, 80), (14, 255, 255))
            + self._count_mask_pixels(hsv, (170, 80, 80), (179, 255, 255))
        )
        return green, red

    def select_own_player_box(self, frame, player_boxes):
        if not player_boxes:
            return None, []
        h, w = frame.shape[:2]
        screen_center = (w * 0.5, h * 0.54)
        radius = max(1.0, self.player_center_bias_radius * self.window_controller.scale_factor)
        scored = []
        for box in player_boxes:
            cx, cy = self.get_player_pos(box)
            center_dist = math.hypot(cx - screen_center[0], cy - screen_center[1])
            center_score = max(0.0, 1.0 - center_dist / radius)
            green, red = self._entity_team_color_scores(frame, box)
            color_score = green * self.player_green_pixel_weight - red * self.player_red_pixel_penalty
            scored.append((center_score + color_score, center_dist, box))
        scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        own_box = scored[0][2]
        rejected = [item[2] for item in scored[1:]]
        if visual_debug and rejected:
            print(f"[DBG] own player selected: {own_box}; reclassified {len(rejected)} player boxes as enemy")
        return own_box, rejected

    def stabilize_entity_roles(self, frame, data):
        players = data.get("player") or []
        own_box, rejected_players = self.select_own_player_box(frame, players)
        if own_box is not None:
            data["player"] = [own_box]
        if rejected_players:
            data.setdefault("enemy", [])
            data["enemy"].extend(rejected_players)
        return data

    def get_main_data(self, frame):
        data = self.Detect_main_info.detect_objects(frame, conf_tresh=self.entity_detection_confidence)
        if not data.get("player") and self.entity_detection_retry_confidence < self.entity_detection_confidence:
            retry_data = self.Detect_main_info.detect_objects(frame, conf_tresh=self.entity_detection_retry_confidence)
            if retry_data.get("player"):
                if visual_debug:
                    print(
                        "[DBG] player recovered with lower entity threshold "
                        f"{self.entity_detection_retry_confidence:.2f}"
                    )
                data = retry_data
        return self.stabilize_entity_roles(frame, data)

    def is_path_blocked(self, player_pos, move_direction, walls, distance=None):  # Increased distance
        if distance is None:
            distance = self.TILE_SIZE*self.window_controller.scale_factor
        dx, dy = 0, 0
        if 'w' in move_direction.lower():
            dy -= distance
        if 's' in move_direction.lower():
            dy += distance
        if 'a' in move_direction.lower():
            dx -= distance
        if 'd' in move_direction.lower():
            dx += distance
        new_pos = (player_pos[0] + dx, player_pos[1] + dy)
        return self.walls_block_line_of_sight(player_pos, new_pos, walls, padding=self.wall_path_padding)

    def is_path_blocked_angle(self, player_pos, angle_degrees, walls, distance=None):
        """Check if the path in the given angle direction is blocked by walls.

        Uses two probe distances (half-tile and full-tile) so that walls that
        start very close to the player are also detected.
        """
        if distance is None:
            distance = self.TILE_SIZE * self.window_controller.scale_factor
        angle_rad = math.radians(angle_degrees)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        max_probe = max(1.0, self.wall_path_probe_tiles)
        probes = (distance * 0.5, distance, distance * max_probe)
        for d in probes:
            new_pos = (player_pos[0] + cos_a * d, player_pos[1] + sin_a * d)
            if self.walls_block_line_of_sight(player_pos, new_pos, walls, padding=self.wall_path_padding):
                return True
        return False

    def find_best_angle(self, player_pos, desired_angle, walls, sweep_range=160, step=10):
        """Find the closest unblocked angle to desired_angle within ±sweep_range degrees.

        Sweeps outward from the desired angle in alternating left/right steps so
        the first hit is always the least deviation from the goal direction.
        Returns desired_angle unchanged if no walls (or no clear path found).
        """
        if not self.is_path_blocked_angle(player_pos, desired_angle, walls):
            return desired_angle

        for offset in range(step, sweep_range + 1, step):
            for sign in (1, -1):
                candidate = (desired_angle + sign * offset) % 360
                if not self.is_path_blocked_angle(player_pos, candidate, walls):
                    return candidate

        # Nothing clear found — return desired anyway (better than stopping)
        return desired_angle

    @staticmethod
    def validate_game_data(data):
        incomplete = False
        if not data.get("player"):
            incomplete = True  # This is required so track_no_detections can also keep track if enemy is missing

        if "enemy" not in data.keys():
            data['enemy'] = None

        if "teammate" not in data.keys():
            data['teammate'] = None

        if 'wall' not in data.keys() or not data['wall']:
            data['wall'] = []

        return False if incomplete else data

    def track_no_detections(self, data):
        if not data:
            data = {
                "enemy": None,
                "player": None,
                "teammate": None,
            }
        for key in self.time_since_detections:
            if key in data and data[key]:
                self.time_since_detections[key] = time.time()

    def do_movement(self, movement):
        if isinstance(movement, float):
            # Analog joystick path: movement is an angle in degrees
            self.window_controller.move_joystick_angle(movement)
            self.keys_hold = []
        else:
            # Legacy WASD path
            movement = movement.lower()
            keys_to_keyDown = []
            keys_to_keyUp = []
            for key in ['w', 'a', 's', 'd']:
                if key in movement:
                    keys_to_keyDown.append(key)
                else:
                    keys_to_keyUp.append(key)

            if keys_to_keyDown:
                self.window_controller.keys_down(keys_to_keyDown)

            self.window_controller.keys_up(keys_to_keyUp)

            self.keys_hold = keys_to_keyDown

    def get_brawler_range(self, brawler):
        if self.brawler_ranges is None:
            self.brawler_ranges = self.load_brawler_ranges(self.brawlers_info)
        safe_range, attack_range, super_range = self.brawler_ranges[brawler]
        multiplier = max(0.75, min(1.35, float(getattr(self, "adaptive_safe_range_multiplier", 1.0))))
        return int(safe_range * multiplier), attack_range, super_range

    def _debounce_angle(self, angle: float, threshold_deg: float = 10.0) -> float:
        """Suppress small angle changes and smooth accepted turns.

        Only adopts the new angle if it differs by more than threshold_deg
        from the last committed angle, OR if no angle was committed yet.
        """
        if self.last_movement is None or not isinstance(self.last_movement, float):
            self.last_movement = angle
            self.last_movement_time = time.time()
            return angle

        diff = abs((angle - self.last_movement + 180) % 360 - 180)
        if diff > threshold_deg:
            if self.angle_smooth_factor > 0:
                self.last_movement = self.blend_angles(angle, self.last_movement, self.angle_smooth_factor)
            else:
                self.last_movement = angle
            self.last_movement_time = time.time()

        return self.last_movement

    def run_combat(self, brawler, data, movement, current_time):
        """Heuristic combat layer: attacks, supers, gadgets, hold-attack release.

        This is split out from get_movement / get_showdown_movement so that
        when the RL movement policy is driving movement we still get the
        same per-brawler attack behaviour.

        Returns a possibly-modified movement (combat dodge/strafe may blend
        on top of the movement angle when the bot is in attack range and
        rl_combat_blend_dodge is enabled).
        """
        if not data or not data.get("player"):
            return movement

        brawler_info = self.brawlers_info.get(brawler)
        if not brawler_info:
            return movement

        must_brawler_hold_attack = self.must_brawler_hold_attack(brawler, self.brawlers_info)
        if (
            must_brawler_hold_attack
            and self.time_since_holding_attack is not None
            and current_time - self.time_since_holding_attack
            >= brawler_info['hold_attack'] + self.seconds_to_hold_attack_after_reaching_max
        ):
            self.attack(touch_up=True, touch_down=False)
            self.time_since_holding_attack = None

        enemy_data = data.get("enemy") or []
        walls = data.get("wall") or []
        if not self.is_there_enemy(enemy_data):
            return movement

        player_pos = self.get_player_pos(data['player'][0])
        enemy_coords, enemy_distance = self.find_closest_enemy(enemy_data, player_pos, walls, "attack")
        if enemy_coords is None or enemy_distance is None:
            return movement

        safe_range, attack_range, _super_range = self.get_brawler_range(brawler)
        direction_x = enemy_coords[0] - player_pos[0]
        direction_y = enemy_coords[1] - player_pos[1]
        toward_angle = self.angle_from_direction(direction_x, direction_y)

        if self.lead_shots_enabled:
            self.enemy_velocity = self.track_enemy_velocity(enemy_coords, current_time)
        else:
            self.enemy_velocity = (0.0, 0.0)
            self.enemy_velocity_confidence = 0.0

        self.try_use_super_on_enemy(brawler, brawler_info, player_pos, enemy_coords, enemy_distance, walls)

        if enemy_distance > attack_range:
            return movement

        enemy_hittable = self.is_enemy_hittable(player_pos, enemy_coords, walls, "attack")
        if not enemy_hittable:
            return movement

        if (
            self.rl_combat_blend_dodge
            and self.strafe_enabled
            and isinstance(movement, float)
        ):
            desired = self.apply_combat_dodge(movement, toward_angle, current_time, enemy_distance, safe_range)
            movement = self.find_best_angle(player_pos, desired, walls)
        elif (
            self.rl_combat_blend_dodge
            and self.strafe_enabled
            and isinstance(movement, str)
            and movement
        ):
            base_angle = self.angle_from_direction(*self.movement_to_vector(movement))
            desired = self.apply_combat_dodge(base_angle, toward_angle, current_time, enemy_distance, safe_range)
            movement = self.find_best_angle(player_pos, desired, walls)

        if (
            self.should_use_gadget
            and self.is_gadget_ready
            and self.time_since_holding_attack is None
        ):
            enemies_in_range = sum(
                1 for enemy in enemy_data
                if self.get_distance(self.get_enemy_pos(enemy), player_pos) <= attack_range
            )
            gadget_threshold = attack_range if enemies_in_range >= 2 else attack_range * 0.7
            if enemy_distance <= gadget_threshold:
                if self.use_gadget():
                    self.time_since_gadget_checked = time.time()
                    self.clear_ability_ready("gadget")

        if not must_brawler_hold_attack:
            attack_angle = toward_angle
            if self.lead_shots_enabled and self.enemy_velocity != (0.0, 0.0):
                attack_angle = self.lead_shot_angle(
                    player_pos,
                    enemy_coords,
                    self.enemy_velocity,
                    confidence=getattr(self, "enemy_velocity_confidence", 1.0),
                )
            if self.aimed_attacks_enabled:
                self.aimed_attack(attack_angle)
            else:
                self.attack()
        else:
            if self.time_since_holding_attack is None:
                self.time_since_holding_attack = time.time()
                self.attack(touch_up=False, touch_down=True)
            elif time.time() - self.time_since_holding_attack >= brawler_info['hold_attack']:
                self.attack(touch_up=True, touch_down=False)
                self.time_since_holding_attack = None

        return movement

    def compute_rl_movement(self, brawler, data, current_time):
        """Hook used by loop() when use_rl_movement is enabled.

        Returns a movement value (float angle in showdown, WASD string in 3v3)
        produced by the RL policy bridge, or None to fall back to the
        heuristic movement path. The actual policy lives in
        rl/policy_bridge.py and is loaded lazily on first use.
        """
        bridge = getattr(self, "_rl_bridge", None)
        if bridge is None:
            try:
                from rl.policy_bridge import RLMovementBridge
                bridge = RLMovementBridge(
                    model_path=self.rl_movement_model_path,
                    is_showdown=self.is_showdown,
                    train=self.rl_training_enabled,
                    train_steps_per_update=self.rl_train_steps_per_update,
                    save_every_seconds=self.rl_save_every_seconds,
                    max_projectiles=self.rl_max_projectiles,
                )
            except Exception as exc:
                if not getattr(self, "_rl_bridge_warned", False):
                    print(f"RL movement bridge unavailable, falling back to heuristic: {exc}")
                    self._rl_bridge_warned = True
                self._rl_bridge = False
                return None
            self._rl_bridge = bridge

        if bridge is False:
            return None

        try:
            movement = bridge.predict(self, data, current_time)
        except Exception as exc:
            if not getattr(self, "_rl_bridge_warned", False):
                print(f"RL movement predict failed, falling back to heuristic: {exc}")
                self._rl_bridge_warned = True
            return None
        return movement

    def loop(self, brawler, data, current_time):
        rl_movement = None
        if self.use_rl_movement:
            rl_movement = self.compute_rl_movement(brawler, data, current_time)

        rl_active = rl_movement is not None
        if rl_active:
            movement = rl_movement
            if self.is_showdown and isinstance(movement, float):
                movement = self._debounce_angle(movement)
            movement = self.run_combat(brawler, data, movement, current_time)
        elif self.is_showdown:
            movement = self.get_showdown_movement(
                player_data=data['player'][0],
                enemy_data=data['enemy'],
                teammate_data=data['teammate'],
                walls=data['wall'],
                brawler=brawler,
            )
            # Debounce small angle jitter before sending to joystick
            movement = self._debounce_angle(movement)
        else:
            movement = self.get_movement(player_data=data['player'][0], enemy_data=data['enemy'], walls=data['wall'], brawler=brawler)

        if not rl_active:
            # The pressure fallback is a heuristic movement adjustment; with the
            # RL policy driving movement we trust the policy and only keep
            # safety mechanisms (wall-stuck escape, unstuck) below.
            movement = self.enemy_pressure_movement_fallback(movement, data, brawler, current_time)

        current_time = time.time()
        if current_time - self.time_since_movement > self.minimum_movement_delay:
            if isinstance(movement, float):
                # 1. If a semicircle escape is already running, just advance it.
                escape_angle = self.semicircle_escape_step(current_time)
                if escape_angle is not None:
                    movement = escape_angle
                else:
                    # 2. Wall-based stuck detector triggers the semicircle escape.
                    player_pos = self.get_player_pos(data['player'][0]) if data.get('player') else None
                    walls = data.get('wall') or []
                    is_trying = isinstance(movement, float)
                    if self.detect_wall_stuck(walls, player_pos, is_trying, current_time):
                        self.capture_vision_frame("wall_stuck", self.current_frame, data, brawler)
                        self.start_semicircle_escape(movement, current_time)
                        self._reset_wall_stuck_state(current_time)
                        movement = self.semicircle_escape_step(current_time) or movement
            else:
                movement = self.unstuck_movement_if_needed(movement, current_time)
            self.do_movement(movement)
            self.time_since_movement = time.time()
        return movement

    def enemy_pressure_movement_fallback(self, movement, data, brawler, current_time):
        if isinstance(movement, float):
            return movement
        if isinstance(movement, str) and movement.strip():
            return movement
        if not data or not data.get("player") or not data.get("enemy"):
            return movement

        player_pos = self.get_player_pos(data["player"][0])
        walls = data.get("wall") or []
        enemy_coords, enemy_distance = self.find_closest_enemy(data["enemy"], player_pos, walls, "attack")
        if enemy_coords is None or enemy_distance is None:
            return movement

        safe_range, attack_range, _ = self.get_brawler_range(brawler)
        pressure_range = max(safe_range, attack_range) * self.enemy_pressure_move_range_multiplier
        if enemy_distance > pressure_range:
            return movement

        toward_angle = self.angle_from_direction(
            enemy_coords[0] - player_pos[0],
            enemy_coords[1] - player_pos[1],
        )
        if enemy_distance <= safe_range:
            desired = self.blend_angles(
                self.angle_opposite(toward_angle),
                self.get_strafe_angle(toward_angle, current_time, enemy_distance, safe_range),
                0.35,
            )
        else:
            desired = self.get_strafe_angle(toward_angle, current_time, enemy_distance, safe_range)

        return self.find_best_angle(player_pos, desired, walls)

    def release_held_attack_for_super(self):
        if self.time_since_holding_attack is None:
            return
        try:
            self.window_controller.press_key("M", touch_up=True, touch_down=False)
        except Exception as exc:
            print(f"Could not release held attack before super: {exc}")
        self.time_since_holding_attack = None

    def try_use_super_on_enemy(self, brawler, brawler_info, player_pos, enemy_coords, enemy_distance, walls):
        if not self.is_super_ready:
            return False
        super_type = brawler_info['super_type']
        _, attack_range, super_range = self.get_brawler_range(brawler)
        enemy_hittable = self.is_enemy_hittable(player_pos, enemy_coords, walls, "super")
        if not self.should_use_super_on_enemy(
                brawler, super_type, enemy_distance, attack_range, super_range, enemy_hittable
        ):
            return False

        self.release_held_attack_for_super()
        if self.is_hypercharge_ready:
            self.use_hypercharge()
            self.time_since_hypercharge_checked = time.time()
            self.clear_ability_ready("hypercharge")
        if self.use_super():
            self.time_since_super_checked = time.time()
            self.clear_ability_ready("super")
            return True
        return False

    def remember_ability_ready(self, ability_name, detected_ready, current_time):
        seen_attr = f"_{ability_name}_ready_seen_at"
        if detected_ready:
            setattr(self, seen_attr, current_time)
            return True
        return False

    def clear_ability_ready(self, ability_name):
        setattr(self, f"_{ability_name}_ready_seen_at", 0.0)
        setattr(self, f"is_{ability_name}_ready", False)

    def try_use_ready_abilities_when_enemy_visible(self, enemy_data):
        return False

    def refresh_ready_abilities(self, frame, current_time):
        if current_time - self.time_since_hypercharge_checked > self.hypercharge_treshold:
            detected = self.check_if_hypercharge_ready(frame)
            self.is_hypercharge_ready = bool(detected)
            self.time_since_hypercharge_checked = current_time
        if current_time - self.time_since_gadget_checked > self.gadget_treshold:
            detected = self.check_if_gadget_ready(frame)
            self.is_gadget_ready = bool(detected)
            self.time_since_gadget_checked = current_time
        if current_time - self.time_since_super_checked > self.super_treshold:
            detected = self.check_if_super_ready(frame)
            self.is_super_ready = self.remember_ability_ready("super", detected, current_time)
            self.time_since_super_checked = current_time

    @staticmethod
    def _scaled_pixel_threshold(base_threshold, screenshot, crop_area):
        reference_area = max(1, abs(crop_area[2] - crop_area[0]) * abs(crop_area[3] - crop_area[1]))
        actual_area = max(1, screenshot.shape[0] * screenshot.shape[1])
        return max(1.0, float(base_threshold) * (actual_area / reference_area))

    def check_if_hypercharge_ready(self, frame):
        wr, hr = self.window_controller.width_ratio, self.window_controller.height_ratio
        x1, y1 = int(self.hypercharge_crop_area[0] * wr), int(self.hypercharge_crop_area[1] * hr)
        x2, y2 = int(self.hypercharge_crop_area[2] * wr), int(self.hypercharge_crop_area[3] * hr)
        screenshot = frame[y1:y2, x1:x2]
        purple_pixels = count_hsv_pixels(screenshot, (137, 158, 159), (179, 255, 255))
        threshold = self._scaled_pixel_threshold(self.hypercharge_pixels_minimum, screenshot, self.hypercharge_crop_area)
        if debug:
            print("hypercharge purple pixels:", purple_pixels, "(if > ", threshold, " then hypercharge is ready)")
            cv2.imwrite(f"debug_frames/hypercharge_debug_{int(time.time())}.png", cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR))
        if purple_pixels > threshold:
            return True
        return False

    def check_if_gadget_ready(self, frame):
        wr, hr = self.window_controller.width_ratio, self.window_controller.height_ratio
        x1, y1 = int(self.gadget_crop_area[0] * wr), int(self.gadget_crop_area[1] * hr)
        x2, y2 = int(self.gadget_crop_area[2] * wr), int(self.gadget_crop_area[3] * hr)
        screenshot = frame[y1:y2, x1:x2]
        green_pixels = count_hsv_pixels(screenshot, (57, 219, 165), (62, 255, 255))
        threshold = self._scaled_pixel_threshold(self.gadget_pixels_minimum, screenshot, self.gadget_crop_area)
        if debug:
            print(
                "gadget green pixels:",
                green_pixels,
                "(if > ",
                threshold,
                " then gadget is ready)"
            )
            cv2.imwrite(f"debug_frames/gadget_debug_{int(time.time())}.png", cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR))
        if green_pixels > threshold:
            return True
        return False

    def check_if_super_ready(self, frame):
        wr, hr = self.window_controller.width_ratio, self.window_controller.height_ratio
        x1, y1 = int(self.super_crop_area[0] * wr), int(self.super_crop_area[1] * hr)
        x2, y2 = int(self.super_crop_area[2] * wr), int(self.super_crop_area[3] * hr)
        screenshot = frame[y1:y2, x1:x2]
        yellow_pixels = count_hsv_pixels(screenshot, (17, 170, 200), (27, 255, 255))
        orange_pixels = count_hsv_pixels(screenshot, (8, 120, 150), (38, 255, 255))
        threshold = self._scaled_pixel_threshold(self.super_pixels_minimum, screenshot, self.super_crop_area) * 2.0
        if debug:
            print(
                "super pixels:",
                f"yellow={yellow_pixels}",
                f"orange={orange_pixels}",
                f"threshold={threshold}",
                "(if above threshold, super is ready)",
            )
            cv2.imwrite(f"debug_frames/super_debug_{int(time.time())}.png", cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR))

        if yellow_pixels > threshold:
            return True
        if orange_pixels > threshold * 1.25:
            return True
        return False

    def get_tile_data(self, frame):
        tile_data = self.Detect_tile_detector.detect_objects(frame, conf_tresh=self.wall_detection_confidence)
        return tile_data

    @staticmethod
    def normalize_box(box):
        x1, y1, x2, y2 = box[:4]
        return [int(min(x1, x2)), int(min(y1, y2)), int(max(x1, x2)), int(max(y1, y2))]

    @staticmethod
    def box_iou(a, b):
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        intersection = iw * ih
        if intersection <= 0:
            return 0.0
        area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
        union = area_a + area_b - intersection
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def box_center_distance(a, b):
        acx, acy = (a[0] + a[2]) * 0.5, (a[1] + a[3]) * 0.5
        bcx, bcy = (b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5
        return math.hypot(acx - bcx, acy - bcy)

    def merge_wall_boxes(self, boxes, min_hits=1):
        clusters = []
        for raw_box in boxes:
            box = self.normalize_box(raw_box)
            width = box[2] - box[0]
            height = box[3] - box[1]
            if width < self.wall_box_min_size or height < self.wall_box_min_size:
                continue

            matched = None
            for cluster in clusters:
                if (
                        self.box_iou(cluster["box"], box) >= self.wall_box_merge_iou
                        or self.box_center_distance(cluster["box"], box) <= self.wall_box_merge_center_distance
                ):
                    matched = cluster
                    break

            if matched is None:
                clusters.append({"box": box, "hits": 1})
                continue

            old = matched["box"]
            hits = matched["hits"]
            matched["box"] = [
                int((old[0] * hits + box[0]) / (hits + 1)),
                int((old[1] * hits + box[1]) / (hits + 1)),
                int((old[2] * hits + box[2]) / (hits + 1)),
                int((old[3] * hits + box[3]) / (hits + 1)),
            ]
            matched["hits"] = hits + 1

        return [cluster["box"] for cluster in clusters if cluster["hits"] >= min_hits]

    def process_tile_data(self, tile_data):
        walls = []
        for class_name, boxes in tile_data.items():
            if class_name != 'bush':
                walls.extend(boxes)
        walls = self.merge_wall_boxes(walls)

        # Add walls to history
        self.wall_history.append(walls)
        if len(self.wall_history) > self.wall_history_length:
            self.wall_history.pop(0)
        # Combine walls from history
        combined_walls = self.combine_walls_from_history()

        return combined_walls

    def combine_walls_from_history(self):
        if not self.wall_history:
            return []
        current_walls = self.wall_history[-1]
        historical_walls = [wall for walls in self.wall_history for wall in walls]
        stable_history = self.merge_wall_boxes(historical_walls, min_hits=max(2, self.wall_history_min_hits))
        return self.merge_wall_boxes(current_walls + stable_history)

    def get_movement(self, player_data, enemy_data, walls, brawler):
        brawler_info = self.brawlers_info.get(brawler)
        if not brawler_info:
            raise ValueError(f"Brawler '{brawler}' not found in brawlers info.")
        playstyle_movement = self.run_playstyle(player_data, enemy_data, walls, brawler)
        if playstyle_movement is not None:
            return playstyle_movement
        must_brawler_hold_attack = self.must_brawler_hold_attack(brawler, self.brawlers_info)
        # if a brawler has been holding an attack for its max duration + the bot setting, then we release
        if must_brawler_hold_attack and self.time_since_holding_attack is not None and time.time() - self.time_since_holding_attack >= brawler_info['hold_attack'] + self.seconds_to_hold_attack_after_reaching_max:
            self.attack(touch_up=True, touch_down=False)
            self.time_since_holding_attack = None

        safe_range, attack_range, super_range = self.get_brawler_range(brawler)
        player_pos = self.get_player_pos(player_data)
        if debug: print("found player pos:", player_pos)
        if not self.is_there_enemy(enemy_data):
            return self.no_enemy_movement(player_data, walls)
        enemy_coords, enemy_distance = self.find_closest_enemy(enemy_data, player_pos, walls, "attack")
        if enemy_coords is None:
            return self.no_enemy_movement(player_data, walls)
        if debug: print("found enemy pos:", enemy_coords)
        direction_x = enemy_coords[0] - player_pos[0]
        direction_y = enemy_coords[1] - player_pos[1]

        # Determine initial movement direction
        if enemy_distance > safe_range:  # Move towards the enemy
            move_horizontal = self.get_horizontal_move_key(direction_x)
            move_vertical = self.get_vertical_move_key(direction_y)
        else:  # Move away from the enemy
            move_horizontal = self.get_horizontal_move_key(direction_x, opposite=True)
            move_vertical = self.get_vertical_move_key(direction_y, opposite=True)

        movement_options = [move_horizontal + move_vertical]
        if self.game_mode == 3:
            movement_options += [move_vertical, move_horizontal]
        elif self.game_mode == 5:
            movement_options += [move_horizontal, move_vertical]
        else:
            raise ValueError("Gamemode type is invalid")

        # Check for walls and adjust movement
        for move in movement_options:
            if not self.is_path_blocked(player_pos, move, walls):
                movement = move
                break
        else:
            print("default paths are blocked")
            # If all preferred directions are blocked, try other directions
            alternative_moves = ['W', 'A', 'S', 'D']
            random.shuffle(alternative_moves)
            for move in alternative_moves:
                if not self.is_path_blocked(player_pos, move, walls):
                    movement = move
                    break
            else:
                # if no movement is available, we still try to go in the best direction
                # because it's better than doing nothing
                movement = move_horizontal + move_vertical

        current_time = time.time()
        if movement != self.last_movement:
            if current_time - self.last_movement_time >= self.minimum_movement_delay:
                self.last_movement = movement
                self.last_movement_time = current_time
            else:
                movement = self.last_movement  # Continue previous movement
        else:
            self.last_movement_time = current_time  # Reset timer if movement didn't change

        self.try_use_super_on_enemy(brawler, brawler_info, player_pos, enemy_coords, enemy_distance, walls)

        # Attack if enemy is within attack range and hittable
        if enemy_distance <= attack_range:
            enemy_hittable = self.is_enemy_hittable(player_pos, enemy_coords, walls, "attack")
            if enemy_hittable:
                if self.strafe_enabled:
                    toward_angle = self.angle_from_direction(direction_x, direction_y)
                    desired = self.apply_combat_dodge(
                        self.angle_from_direction(*self.movement_to_vector(movement)),
                        toward_angle,
                        current_time,
                        enemy_distance,
                        safe_range,
                    )
                    movement = self.find_best_angle(player_pos, desired, walls)
                if self.should_use_gadget == True and self.is_gadget_ready and self.time_since_holding_attack is None:
                    if self.use_gadget():
                        self.time_since_gadget_checked = time.time()
                        self.clear_ability_ready("gadget")

                if not must_brawler_hold_attack:
                    self.attack()
                else:
                    if self.time_since_holding_attack is None:
                        self.time_since_holding_attack = time.time()
                        self.attack(touch_up=False, touch_down=True)
                    elif time.time() - self.time_since_holding_attack >= self.brawlers_info[brawler]['hold_attack']:
                        self.attack(touch_up=True, touch_down=False)
                        self.time_since_holding_attack = None


        return movement

    def is_respawning_overlay(self, frame):
        """Return True when the 'Back in:' / lightning-bolt respawn HUD is showing.

        We don't run projectile detection while the player is dead — the
        camera follows a teammate / spectator perspective and YOLO can
        still emit detections that aren't meaningful to dodge.

        Detection is purely color-based and cheap:
          * crop a top-center band of the frame
          * count bright-yellow pixels (lightning bolt) AND large near-white
            pixel cluster (the "Back in:" outlined text)
          * both must clear independent thresholds for a positive
        """
        if frame is None:
            return False
        try:
            h, w = frame.shape[:2]
        except Exception:
            return False
        if h < 80 or w < 80:
            return False

        # Reference 1920×1080 region centered horizontally near the top.
        # The respawn overlay floats in roughly the upper third of screen.
        ref_w, ref_h = 1920.0, 1080.0
        x = int(w * (560.0 / ref_w))
        y = int(h * (60.0 / ref_h))
        cw = int(w * (800.0 / ref_w))
        ch = int(h * (320.0 / ref_h))
        x = max(0, min(w - 8, x))
        y = max(0, min(h - 8, y))
        cw = max(8, min(w - x, cw))
        ch = max(8, min(h - y, ch))

        crop = frame[y:y + ch, x:x + cw]
        if crop.size == 0:
            return False

        try:
            hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
        except cv2.error:
            return False

        yellow_low = np.array((22, 180, 200), dtype=np.uint8)
        yellow_high = np.array((36, 255, 255), dtype=np.uint8)
        yellow = cv2.inRange(hsv, yellow_low, yellow_high)
        yellow_count = int(cv2.countNonZero(yellow))

        white_low = np.array((0, 0, 220), dtype=np.uint8)
        white_high = np.array((179, 60, 255), dtype=np.uint8)
        white = cv2.inRange(hsv, white_low, white_high)
        white_count = int(cv2.countNonZero(white))

        # Thresholds scale with crop area (resolution independent).
        area = float(crop.shape[0] * crop.shape[1])
        yellow_ratio = yellow_count / max(1.0, area)
        white_ratio = white_count / max(1.0, area)
        return yellow_ratio >= 0.0035 and white_ratio >= 0.020

    def update_projectile_tracker(self, data, current_time):
        """Aggregate labeled, residual-detector, and motion-diff boxes into
        ``data['projectile']`` and advance ``ProjectileTracker``.

        With ``rl_universal_projectiles`` enabled, small moving regions
        masked away from entities (and trusted fog) augment YOLO projectile
        classes so RL dodge features work without a retrained main model.
        """
        if not data:
            return []

        self._preserve_rl_motion_prev_gray = False
        scale = self.window_controller.scale_factor
        hm_early = getattr(self, "health_monitor", None)
        frame_early = self.current_frame
        if hm_early is not None and frame_early is not None and data.get("player"):
            try:
                hm_early.update(
                    current_time,
                    frame_early,
                    data["player"][0],
                    scale,
                    lambda: self.is_respawning_overlay(frame_early),
                )
            except Exception:
                pass

        flashing = False
        if (
            getattr(self, "red_flash_detect_enabled", True)
            and getattr(self, "red_flash_detector", None) is not None
            and frame_early is not None
        ):
            try:
                flashing = bool(self.red_flash_detector.update(frame_early))
            except Exception:
                flashing = False
        self._visual_debug_red_flash = flashing

        if self.projectile_tracker is None:
            data["projectile"] = []
            return []

        # Skip detection entirely while the death/respawn overlay is up.
        # No player to dodge for, and the spectator camera produces noise.
        if self.is_respawning_overlay(self.current_frame):
            data["projectile"] = []
            self._rl_motion_prev_gray = None
            self._rl_motion_debug_boxes = []
            try:
                self.projectile_tracker.reset()
            except Exception:
                pass
            return []

        from rl.projectile_tracker import extract_projectile_boxes
        from rl.universal_projectiles import (
            animated_terrain_mask_small,
            collect_entity_wall_boxes,
            extract_residual_projectile_boxes,
            grayscale_small,
            merge_projectile_candidates_with_sources,
            motion_blob_boxes,
            parse_animated_terrain_hsv_ranges,
            raster_fog_roi_to_small_mask,
            scale_ui_reference_rects,
            trusted_fog_mask_small,
        )

        labeled = extract_projectile_boxes(data, self.rl_projectile_classes)
        residual: list = []
        motion_boxes: list = []
        ui_boxes_fullres: list = []
        motion_ran = False

        univ_mode = getattr(self, "rl_universal_projectiles_mode", "motion")
        run_residual = self.rl_universal_projectiles and univ_mode in ("motion", "residual_only")
        run_motion = self.rl_universal_projectiles and univ_mode == "motion"

        if flashing:
            run_residual = False
            run_motion = False
            self._preserve_rl_motion_prev_gray = True

        if self.rl_universal_projectiles:
            exclude_keys = {"player", "teammate", "enemy", "wall"}
            for cls_name in self.rl_projectile_classes:
                exclude_keys.add(str(cls_name))
            for wcls in self.tile_detector_model_classes:
                exclude_keys.add(str(wcls))

            ref_boxes = collect_entity_wall_boxes(data)
            frame = self.current_frame
            fw, fh = brawl_stars_width, brawl_stars_height
            if frame is not None:
                fh, fw = frame.shape[:2]
            frame_wh = (fw, fh)

            if getattr(self, "rl_motion_use_ui_mask", True):
                ui_boxes_fullres = scale_ui_reference_rects(
                    fw,
                    fh,
                    definitions=self.rl_motion_ui_exclude_rects,
                )

            ref_motion = list(ref_boxes) + ui_boxes_fullres

            if run_residual:
                residual = extract_residual_projectile_boxes(
                    data,
                    exclude_keys,
                    ref_boxes,
                    frame_wh,
                    max_box_area_frac=self.rl_residual_max_box_area_frac,
                    max_side_frac=self.rl_residual_max_side_frac,
                    iou_exclude_thresh=self.rl_residual_iou_exclude,
                    ui_exclude_boxes=ui_boxes_fullres or None,
                )

            if run_motion and frame is not None:
                curr_small = grayscale_small(frame, self.rl_motion_scale_width)
                sh, sw = curr_small.shape[:2]
                fog_small = None
                if data.get("player"):
                    px, py = self.get_player_pos(data["player"][0])
                    built = self._build_trusted_fog_mask(
                        frame, roi_center=(px, py), roi_radius=self.fog_flee_distance
                    )
                    if built is not None:
                        fog_mask_roi, origin = built
                        fog_small = raster_fog_roi_to_small_mask(
                            fog_mask_roi, origin, (fh, fw), (sh, sw)
                        )
                if getattr(self, "rl_motion_full_frame_fog", True):
                    ff_area = max(1, fh * fw)
                    full_fog = trusted_fog_mask_small(
                        frame,
                        fog_hsv_low=tuple(self.fog_hsv_low),
                        fog_hsv_high=tuple(self.fog_hsv_high),
                        scale_width=self.rl_motion_scale_width,
                        full_frame_area=ff_area,
                        full_min_blob_pixels=int(self.fog_min_blob_pixels),
                        dilate_px=int(getattr(self, "rl_motion_fog_exclude_dilate_px", 2)),
                    )
                    if fog_small is not None:
                        fog_small = cv2.bitwise_or(fog_small, full_fog)
                    else:
                        fog_small = full_fog

                terr_ranges = parse_animated_terrain_hsv_ranges(
                    getattr(self, "rl_animated_terrain_hsv_ranges", [])
                )
                terrain_mask = animated_terrain_mask_small(
                    frame,
                    scale_width=self.rl_motion_scale_width,
                    hsv_ranges=terr_ranges,
                    dilate_px=2,
                )
                if terrain_mask is not None and cv2.countNonZero(terrain_mask) > 0:
                    if fog_small is not None:
                        fog_small = cv2.bitwise_or(fog_small, terrain_mask)
                    else:
                        fog_small = terrain_mask

                dil_small = max(
                    1, int(round(self.rl_motion_exclude_dilate_px * sw / max(1, fw)))
                )
                motion_boxes = motion_blob_boxes(
                    self._rl_motion_prev_gray,
                    curr_small,
                    ref_motion,
                    frame_wh,
                    diff_threshold=self.rl_motion_diff_threshold,
                    exclude_dilate_px=dil_small,
                    min_area_px=self.rl_motion_min_area_px,
                    max_area_px=self.rl_motion_max_area_px,
                    morph_kernel=self.rl_motion_morph_kernel,
                    fog_exclude_small=fog_small,
                    ego_compensate=getattr(self, "rl_motion_ego_compensate", False),
                    ego_min_response=float(getattr(self, "rl_motion_ego_min_response", 0.08)),
                    skip_motion_on_low_ego_response=getattr(
                        self, "rl_motion_skip_on_bad_ego", False
                    ),
                )
                self._rl_motion_prev_gray = curr_small.copy()
                motion_ran = True

        if not motion_ran and not getattr(self, "_preserve_rl_motion_prev_gray", False):
            self._rl_motion_prev_gray = None

        # Direction gate: drop residual/motion candidates whose movement
        # since the previous frame is clearly heading away from the player.
        # YOLO-labeled projectiles bypass this — the tracker's own
        # alignment check will filter those once they have a velocity.
        player_pos = None
        if data.get("player"):
            player_pos = self.get_player_pos(data["player"][0])

        residual, motion_boxes = self._filter_candidates_toward_player(
            residual_boxes=residual,
            motion_boxes=motion_boxes,
            player_pos=player_pos,
        )

        boxes, box_sources = merge_projectile_candidates_with_sources(
            labeled,
            residual,
            motion_boxes,
            self.rl_projectile_merge_nms_iou,
        )
        self._rl_motion_debug_boxes = motion_boxes

        # Origin gate inputs: classify newly-born tracks as enemy-spawned
        # only when they appear near an enemy hitbox (and not near a
        # friendly one). Pass None when nothing is visible so the tracker
        # treats classification as "unknown" instead of "not enemy".
        enemy_boxes = list(data.get("enemy") or []) or None
        friendly_boxes_raw = list(data.get("player") or []) + list(
            data.get("teammate") or []
        )
        friendly_boxes = friendly_boxes_raw if friendly_boxes_raw else None

        data["projectile"] = boxes
        try:
            tracks = self.projectile_tracker.update(
                boxes,
                now=current_time,
                enemy_boxes=enemy_boxes,
                friendly_boxes=friendly_boxes,
                box_sources=box_sources,
                ui_exclude_boxes=ui_boxes_fullres or None,
            )
        except Exception as exc:
            print(f"Projectile tracker update failed: {exc}")
            tracks = []

        pt = self.projectile_tracker
        win = float(getattr(self, "damage_confirm_window_seconds", 0.5))
        hm = getattr(self, "health_monitor", None)
        if pt is not None and data.get("player"):
            player_box = data["player"][0]
            try:
                if hm is not None and not flashing:
                    if hm.recent_damage_event(current_time, win) is not None:
                        pt.confirm_tracks_touching_player(
                            player_box,
                            now=current_time,
                            padding=self.rl_projectile_hit_radius_padding,
                            lookahead_seconds=0.15,
                        )
                pt.purge_unconfirmed_recent_tracks(current_time, win)
            except Exception as exc:
                print(f"Projectile tracker HP cross-reference failed: {exc}")

        return tracks

    def _filter_candidates_toward_player(
        self,
        residual_boxes,
        motion_boxes,
        player_pos,
    ):
        """Drop residual/motion candidates that visibly move away from player.

        For each new candidate, find the nearest previous-frame center
        within ``rl_projectile_max_match_distance``. If the displacement
        vector exceeds a small minimum and points away from the player
        (cosine < threshold), reject it. Candidates without a nearby
        previous match are kept — there is no evidence yet, and the
        tracker's own gate filters them once they have velocity.
        """
        prev_centers = list(getattr(self, "_rl_prev_motion_centers", []) or [])
        kept_residual: list = []
        kept_motion: list = []
        new_centers: list = []

        # Same 0..1 -> cosine mapping used for the tracker, so the UI
        # confidence affects motion/residual gating identically.
        align_thresh = max(
            -1.0,
            min(1.0, 2.0 * float(self.projectile_detection_confidence) - 1.0),
        )
        # Movement smaller than this is treated as "no evidence yet".
        min_displacement_px = 6.0

        def _keep(box):
            if player_pos is None or not prev_centers:
                return True
            cx = (float(box[0]) + float(box[2])) * 0.5
            cy = (float(box[1]) + float(box[3])) * 0.5
            best_idx = -1
            best_d = float(self.rl_projectile_max_match_distance)
            for i, (pcx, pcy) in enumerate(prev_centers):
                d = math.hypot(cx - pcx, cy - pcy)
                if d < best_d:
                    best_d = d
                    best_idx = i
            if best_idx < 0:
                return True
            pcx, pcy = prev_centers[best_idx]
            dvx, dvy = cx - pcx, cy - pcy
            disp = math.hypot(dvx, dvy)
            if disp < min_displacement_px:
                return True
            tx, ty = player_pos[0] - cx, player_pos[1] - cy
            tnorm = math.hypot(tx, ty)
            if tnorm < 1e-3:
                return True
            cos = (dvx * tx + dvy * ty) / (disp * tnorm)
            return cos >= align_thresh

        for box in residual_boxes or []:
            if len(box) < 4:
                continue
            cx = (float(box[0]) + float(box[2])) * 0.5
            cy = (float(box[1]) + float(box[3])) * 0.5
            new_centers.append((cx, cy))
            if _keep(box):
                kept_residual.append(box)

        for box in motion_boxes or []:
            if len(box) < 4:
                continue
            cx = (float(box[0]) + float(box[2])) * 0.5
            cy = (float(box[1]) + float(box[3])) * 0.5
            new_centers.append((cx, cy))
            if _keep(box):
                kept_motion.append(box)

        self._rl_prev_motion_centers = new_centers
        return kept_residual, kept_motion

    def main(self, frame, brawler, main):
        current_time = time.time()
        raw_data = self.get_main_data(frame)
        data = raw_data
        # Always attach cached walls when this gamemode runs the tile detector; otherwise
        # data['wall'] is missing between refreshes if wall_detection interval > 1s
        # (keep_walls_in_memory is false) and debug/movement see an empty list.
        if self.should_detect_walls:
            if current_time - self.time_since_walls_checked > self.walls_treshold:
                tile_data = self.get_tile_data(frame)
                walls = self.process_tile_data(tile_data)
                self.time_since_walls_checked = current_time
                self.last_walls_data = walls
            data["wall"] = self.last_walls_data
        elif self.keep_walls_in_memory:
            data["wall"] = self.last_walls_data

        data = self.validate_game_data(data)
        self.track_no_detections(data)
        if data:
            self.time_since_player_last_found = time.time()
            if main.state != "match":
                main.state = get_state(frame)
                if main.state != "match":
                    data = None
        if not data:
            if current_time - self.time_since_player_last_found > 1.0:
                self.capture_vision_frame(
                    "player_lost",
                    frame,
                    {"raw_detection": raw_data},
                    brawler,
                    {"state": getattr(main, "state", None)},
                )
                self.window_controller.keys_up(list("wasd"))
            self.time_since_different_movement = time.time()
            if current_time - self.time_since_last_proceeding > self.no_detection_proceed_delay:
                current_state = get_state(frame)
                if current_state != "match":
                    self.time_since_last_proceeding = current_time
                else:
                    if current_time - self.time_since_last_no_detection_q >= self.no_detection_q_press_interval:
                        print("No detection fallback: pressing Q.")
                        self.window_controller.press_key("Q")
                        self.time_since_last_no_detection_q = current_time
                    self.time_since_last_proceeding = time.time()
            return
        self.time_since_last_proceeding = time.time()
        self.refresh_ready_abilities(frame, current_time)

        self.current_frame = frame
        self.last_playstyle_teammate_data = data.get("teammate")
        self.update_projectile_tracker(data, current_time)
        movement = self.loop(brawler, data, current_time)

        if visual_debug:
            self.queue_visual_debug(frame, data, brawler)

        # if data:
        #     # Record scene data
        #     self.scene_data.append({
        #         'frame_number': len(self.scene_data),
        #         'player': data.get('player', []),
        #         'enemy': data.get('enemy', []),
        #         'wall': data.get('wall', []),
        #         'movement': movement,
        #     })

    def _copy_visual_debug_data(self, data):
        copied = {}
        for key, value in (data or {}).items():
            if isinstance(value, list):
                copied[key] = [
                    list(item) if isinstance(item, (list, tuple, np.ndarray)) else item
                    for item in value
                ]
            else:
                copied[key] = value
        return copied

    def _ensure_visual_debug_thread(self):
        if self._visual_debug_thread and self._visual_debug_thread.is_alive():
            return
        self._visual_debug_stop = False
        self._visual_debug_thread = threading.Thread(
            target=self._visual_debug_loop,
            name="PylaVisualDebug",
            daemon=True,
        )
        self._visual_debug_thread.start()

    def queue_visual_debug(self, frame, data, brawler=None):
        now = time.time()
        frame_delay = 1.0 / self.visual_debug_max_fps
        if now < self._visual_debug_next_enqueue_at:
            return
        self._visual_debug_next_enqueue_at = now + frame_delay
        self._ensure_visual_debug_thread()
        payload = (
            frame.copy() if isinstance(frame, np.ndarray) else np.array(frame),
            self._copy_visual_debug_data(data),
            brawler,
        )
        with self._visual_debug_lock:
            self._visual_debug_payload = payload

    def _visual_debug_loop(self):
        frame_delay = 1.0 / self.visual_debug_max_fps
        while not self._visual_debug_stop:
            loop_started = time.time()
            with self._visual_debug_lock:
                payload = self._visual_debug_payload
                self._visual_debug_payload = None
            if payload is not None:
                try:
                    self.show_visual_debug(*payload, respect_throttle=False)
                except Exception as exc:
                    print(f"Visual debug renderer error: {exc}")
            sleep_for = frame_delay - (time.time() - loop_started)
            if sleep_for > 0:
                time.sleep(min(sleep_for, frame_delay))

    def show_visual_debug(self, frame, data, brawler=None, respect_throttle=True):
        import numpy as np
        now = time.time()
        if respect_throttle and now < self._visual_debug_next_frame_at:
            return
        if respect_throttle:
            self._visual_debug_next_frame_at = now + (1.0 / self.visual_debug_max_fps)

        scale = self.visual_debug_scale
        if scale < 0.999:
            img = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        else:
            img = frame.copy() if isinstance(frame, np.ndarray) else np.array(frame)

        def s(value):
            return int(value * scale)

        def sp(point):
            return s(point[0]), s(point[1])

        if getattr(self, "_visual_debug_red_flash", False):
            bar_h = max(4, s(26))
            cv2.rectangle(img, (0, 0), (img.shape[1], bar_h), (220, 40, 40), -1)
            cv2.putText(
                img,
                "RED FLASH",
                (s(8), max(s(18), bar_h - s(6))),
                cv2.FONT_HERSHEY_SIMPLEX,
                max(0.45, 0.65 * scale),
                (255, 255, 255),
                max(1, s(2)),
            )

        hm_dbg = getattr(self, "health_monitor", None)
        if hm_dbg is not None and data.get("player"):
            pb = data["player"][0]
            if len(pb) >= 4:
                x1, y1, x2, y2 = map(float, pb[:4])
                sf = float(self.window_controller.scale_factor)
                off = max(2.0, getattr(self, "health_bar_band_offset_px", 8.0) * sf)
                bh = max(4.0, getattr(self, "health_bar_band_height_px", 14.0) * sf)
                bar_w = max(8, int(abs(x2 - x1)))
                bar_left = int(min(x1, x2))
                bar_top = int(min(y1, y2) - off - bh)
                hp_pct = hm_dbg.last_hp_pct if hm_dbg.last_hp_ok else None
                if hp_pct is not None:
                    fill_w = max(0, int(bar_w * hp_pct))
                    cv2.rectangle(
                        img,
                        sp((bar_left, bar_top)),
                        sp((bar_left + bar_w, bar_top + int(bh))),
                        (90, 90, 90),
                        max(1, s(1)),
                    )
                    cv2.rectangle(
                        img,
                        sp((bar_left, bar_top)),
                        sp((bar_left + fill_w, bar_top + int(bh))),
                        (40, 200, 80),
                        -1,
                    )
                hp_label = ""
                if hm_dbg.hp_value is not None and hm_dbg.observed_max_hp > 0:
                    hp_label = f"HP {hm_dbg.hp_value}/{hm_dbg.observed_max_hp}"
                elif hp_pct is not None:
                    hp_label = f"HP {hp_pct * 100:.0f}%"
                if hp_label:
                    cv2.putText(
                        img,
                        hp_label,
                        sp((bar_left, bar_top - s(6))),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        max(0.35, 0.5 * scale),
                        (255, 255, 255),
                        max(1, s(1)),
                    )

        # --- Fog overlay ---
        # Only draw the fog tint + centroid arrow when a fog threat is strong
        # enough to trigger evasion (same thresholds as detect_fog_threat):
        # trusted mask inside flee-radius must contain >= fog_min_pixels_in_radius.
        if data.get("player"):
            px, py = self.get_player_pos(data["player"][0])
            r = self.fog_flee_distance
            built = self._build_trusted_fog_mask(frame, roi_center=(px, py), roi_radius=r)
            if built is not None:
                mask, (ox, oy) = built
                ys, xs = np.nonzero(mask)
                if xs.size > 0:
                    dx_all = (xs + ox) - px
                    dy_all = (ys + oy) - py
                    dist_sq = dx_all * dx_all + dy_all * dy_all
                    inside = dist_sq <= r * r
                    if int(inside.sum()) >= self.fog_min_pixels_in_radius:
                        # Paint only the fog ROI instead of allocating a full-frame mask/tint.
                        roi_mask = np.zeros_like(mask)
                        roi_mask[ys[inside], xs[inside]] = 255
                        if scale < 0.999:
                            roi_mask = cv2.resize(roi_mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
                        x0, y0 = s(ox), s(oy)
                        x1 = min(img.shape[1], x0 + roi_mask.shape[1])
                        y1 = min(img.shape[0], y0 + roi_mask.shape[0])
                        roi_mask = roi_mask[:max(0, y1 - y0), :max(0, x1 - x0)]
                        if roi_mask.size:
                            roi = img[y0:y1, x0:x1]
                            magenta = np.empty_like(roi)
                            magenta[:, :] = (255, 0, 255)
                            blended = cv2.addWeighted(roi, 0.55, magenta, 0.45, 0)
                            roi[roi_mask > 0] = blended[roi_mask > 0]
                        fog_cx = int(dx_all[inside].mean() + px)
                        fog_cy = int(dy_all[inside].mean() + py)
                        cv2.circle(img, sp((fog_cx, fog_cy)), max(3, s(8)), (255, 0, 255), -1)
                        cv2.putText(img, "fog", sp((fog_cx + 10, fog_cy)),
                                    cv2.FONT_HERSHEY_SIMPLEX, max(0.35, 0.6 * scale), (255, 0, 255), 2)
                        cv2.arrowedLine(img, sp((px, py)), sp((fog_cx, fog_cy)),
                                        (255, 0, 255), 2, tipLength=0.15)

        # Walls first with their own cap so they are not starved when
        # visual_debug_max_boxes is exhausted by player/enemy/teammate.
        wall_col = (128, 128, 128)
        max_walls_dbg = int(getattr(self, "visual_debug_max_wall_boxes", 250))
        for box in (data.get("wall") or [])[: max(0, max_walls_dbg)]:
            if len(box) < 4:
                continue
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(img, sp((x1, y1)), sp((x2, y2)), wall_col, max(1, s(2)))

        # Colors in RGB (frame is kept in RGB; converted to BGR only for imshow).
        colors = {
            "player": (0, 255, 0),
            "teammate": (0, 0, 255),
            "enemy": (255, 0, 0),
        }
        boxes_drawn = 0
        for key, color in colors.items():
            boxes = data.get(key)
            if not boxes:
                continue
            for box in boxes:
                if boxes_drawn >= self.visual_debug_max_boxes:
                    break
                x1, y1, x2, y2 = map(int, box)
                cv2.rectangle(img, sp((x1, y1)), sp((x2, y2)), color, max(1, s(2)))
                cv2.putText(
                    img,
                    key,
                    sp((x1, max(y1 - 6, 0))),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    max(0.35, 0.5 * scale),
                    color,
                    1,
                )
                boxes_drawn += 1

        projectile_tracker = getattr(self, "projectile_tracker", None)
        if projectile_tracker is not None:
            from rl.projectile_tracker import (
                cluster_bounding_box,
                cluster_tracks_by_distance,
            )

            track_col = (255, 165, 0)
            cluster_col = (255, 215, 0)  # gold for cluster bounds
            arrow_dt = 0.1
            promoted_tracks = [
                tr
                for tr in projectile_tracker.tracks
                if tr.match_streak >= projectile_tracker.min_hits_to_promote
            ]

            for tr in promoted_tracks:
                x1, y1, x2, y2 = tr.expanded_box()
                xa1, ya1, xa2, ya2 = int(x1), int(y1), int(x2), int(y2)
                cv2.rectangle(
                    img,
                    sp((xa1, ya1)),
                    sp((xa2, ya2)),
                    track_col,
                    max(1, s(2)),
                )
                suffix = "*" if getattr(tr, "confidence_confirmed", False) else ""
                cv2.putText(
                    img,
                    f"proj{tr.track_id}{suffix}",
                    sp((xa1, max(ya1 - 6, 0))),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    max(0.35, 0.5 * scale),
                    track_col,
                    1,
                )
                tip_x = tr.cx + tr.vx * arrow_dt
                tip_y = tr.cy + tr.vy * arrow_dt
                cv2.arrowedLine(
                    img,
                    sp((tr.cx, tr.cy)),
                    sp((tip_x, tip_y)),
                    track_col,
                    max(1, s(2)),
                    tipLength=0.25,
                )

            # Cluster bounding rectangle for dense volleys (>= 2 tracks).
            # Only drawn for clusters of 2+; isolated projectiles keep
            # their individual box only, so dodging stays precise.
            if len(promoted_tracks) >= 2:
                cluster_dist = float(
                    getattr(self, "rl_projectile_cluster_distance_px", 200.0)
                )
                clusters = cluster_tracks_by_distance(promoted_tracks, cluster_dist)
                for cluster in clusters:
                    if len(cluster) < 2:
                        continue
                    bb = cluster_bounding_box(cluster, padding=4.0)
                    if bb is None:
                        continue
                    bx1, by1, bx2, by2 = (int(v) for v in bb)
                    cv2.rectangle(
                        img,
                        sp((bx1, by1)),
                        sp((bx2, by2)),
                        cluster_col,
                        max(2, s(3)),
                    )
                    cv2.putText(
                        img,
                        f"x{len(cluster)}",
                        sp((bx1, max(by1 - 8, 0))),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        max(0.4, 0.6 * scale),
                        cluster_col,
                        2,
                    )

        if getattr(self, "visual_debug_motion_boxes", False):
            motion_col = (0, 255, 255)
            for box in getattr(self, "_rl_motion_debug_boxes", []) or []:
                if boxes_drawn >= self.visual_debug_max_boxes:
                    break
                if len(box) < 4:
                    continue
                x1, y1, x2, y2 = map(int, box[:4])
                cv2.rectangle(img, sp((x1, y1)), sp((x2, y2)), motion_col, 1)
                cv2.putText(
                    img,
                    "motion",
                    sp((x1, max(y1 - 6, 0))),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    max(0.35, 0.45 * scale),
                    motion_col,
                    1,
                )
                boxes_drawn += 1

        # Draw attack/super ranges around the player based on brawlers_info.json.
        if brawler and data.get("player"):
            info = self.brawlers_info.get(brawler)
            if info:
                px, py = self.get_player_pos(data["player"][0])
                center = sp((px, py))
                attack_range = s(int(info.get("attack_range", 0)))
                super_range = s(int(info.get("super_range", 0)))
                if attack_range > 0:
                    cv2.circle(img, center, attack_range, (160, 32, 240), 2)  # purple
                if super_range > 0:
                    cv2.circle(img, center, super_range, (255, 255, 0), 2)  # yellow

        cv2.imshow("PylaAi-XXZ Visual Debug", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        cv2.waitKey(1)

    @staticmethod
    def movement_to_direction(movement):
        mapping = {
            'w': 'up',
            'a': 'left',
            's': 'down',
            'd': 'right',
            'wa': 'up-left',
            'aw': 'up-left',
            'wd': 'up-right',
            'dw': 'up-right',
            'sa': 'down-left',
            'as': 'down-left',
            'sd': 'down-right',
            'ds': 'down-right',
        }
        movement = movement.lower()
        movement = ''.join(sorted(movement))
        return mapping.get(movement, 'idle' if movement == '' else movement)
