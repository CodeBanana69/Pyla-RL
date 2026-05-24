import math
import json
import os
import random
import threading
import time

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
        self.map_object_vision_enabled = str(bot_config.get("map_object_vision_enabled", "yes")).lower() in ("yes", "true", "1")
        self.map_object_wall_color_detection = str(bot_config.get("map_object_wall_color_detection", "yes")).lower() in ("yes", "true", "1")
        self.map_object_water_detection = str(bot_config.get("map_object_water_detection", "no")).lower() in ("yes", "true", "1")
        self.map_object_min_area = float(bot_config.get("map_object_min_area", 900))
        self.last_map_object_data = {}
        self.jump_pad_detection_enabled = str(bot_config.get("jump_pad_detection_enabled", "yes")).lower() in ("yes", "true", "1")
        self.jump_pad_escape_distance = float(bot_config.get("jump_pad_escape_distance", 620))
        self.jump_pad_escape_min_distance = float(bot_config.get("jump_pad_escape_min_distance", 55))
        self.jump_pad_escape_requires_edge = str(bot_config.get("jump_pad_escape_requires_edge", "yes")).lower() in ("yes", "true", "1")
        self.jump_pad_escape_edge_margin = float(bot_config.get("jump_pad_escape_edge_margin", 0.22))
        self.jump_pad_escape_teammate_safe_distance = float(bot_config.get("jump_pad_escape_teammate_safe_distance", 360))
        self.jump_pad_smoke_early_distance = float(bot_config.get("jump_pad_smoke_early_distance", 230))
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
        self.last_jump_pad_data = []
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
        self.player_lost_movement_grace_seconds = float(bot_config.get("player_lost_movement_grace_seconds", 2.5))

        self.last_movement = None
        self.last_movement_time = time.time()
        self.locked_teammate = None
        self.locked_teammate_distance = float('inf')
        self.teammate_hysteresis = 0.75  # Switch only if another teammate is dramatically closer
        self.teammate_lock_max_jump = float(bot_config.get("teammate_lock_max_jump", 320))
        self.teammate_lock_lost_since = 0.0
        self.trio_grouping_enabled = str(bot_config.get("trio_grouping_enabled", "yes")).lower() in ("yes", "true", "1")
        self.showdown_playstyle_mode = str(bot_config.get("showdown_playstyle_mode", "follow")).strip().lower()
        self.teammate_follow_min_distance = float(bot_config.get("teammate_follow_min_distance", 180))
        self.teammate_follow_max_distance = float(bot_config.get("teammate_follow_max_distance", 520))
        self.teammate_follow_step_distance = float(bot_config.get("teammate_follow_step_distance", 8))
        self.teammate_combat_regroup_distance = float(bot_config.get("teammate_combat_regroup_distance", 650))
        self.teammate_combat_bias = float(bot_config.get("teammate_combat_bias", 0.75))
        self.teammate_follow_force_direct = str(bot_config.get("teammate_follow_force_direct", "no")).lower() in ("yes", "true", "1")
        self.teammate_marker_follow_enabled = str(bot_config.get("teammate_marker_follow_enabled", "yes")).lower() in ("yes", "true", "1")
        self.teammate_marker_edge_margin = float(bot_config.get("teammate_marker_edge_margin", 0.28))
        self.teammate_marker_fallback_delay = float(bot_config.get("teammate_marker_fallback_delay", 1.25))
        self.last_teammate_seen_time = 0.0
        self.wall_history = []
        self.wall_history_length = int(bot_config.get("wall_history_length", 3))
        self.scene_data = []
        self.should_detect_walls = bot_config["gamemode"] == "showdown"
        self.is_showdown = bot_config["gamemode"] == "showdown"
        self.minimum_movement_delay = bot_config["minimum_movement_delay"]
        self.no_detection_proceed_delay = time_config["no_detection_proceed"]
        self.no_detection_q_press_interval = float(time_config.get("no_detection_q_press_interval", 15.0))
        self.gadget_pixels_minimum = bot_config["gadget_pixels_minimum"]
        self.hypercharge_pixels_minimum = bot_config["hypercharge_pixels_minimum"]
        self.super_pixels_minimum = bot_config["super_pixels_minimum"]
        self.wall_detection_confidence = bot_config["wall_detection_confidence"]
        self.wall_detection_retry_confidence = float(
            bot_config.get("wall_detection_retry_confidence", max(0.2, self.wall_detection_confidence - 0.55))
        )
        self.wall_detection_retry_min_objects = int(bot_config.get("wall_detection_retry_min_objects", 3))
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
        self.fog_check_every_n_frames = max(1, int(bot_config.get("fog_check_every_n_frames", 1)))
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
            if self.should_use_gadget_on_enemy(brawler, player_data, enemy_data, walls):
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
            "is_path_blocked_angle": self.is_path_blocked_angle,
            "is_enemy_hittable": self.is_enemy_hittable,
            "walls_block_line_of_sight": self.walls_block_line_of_sight,
            "aimed_attack": self.aimed_attack,
            "get_distance": self.get_distance,
            "get_random_movement": lambda: random.choice(["WA", "WD", "SA", "SD", "W", "A", "S", "D"]),
            "TILE_SIZE": self.TILE_SIZE,
            "width": brawl_stars_width,
            "height": brawl_stars_height,
            "math": math,
            "angle_from_direction": self.angle_from_direction,
            "find_best_angle": self.find_best_angle,
            "blend_angles": self.blend_angles,
            "lead_shot_angle": self.lead_shot_angle,
            "track_enemy_velocity": self.track_enemy_velocity,
            "angle_to_keys": lambda angle: [
                "D", "SD", "S", "SA", "A", "WA", "W", "WD"
            ][int((float(angle) % 360 + 22.5) / 45) % 8],
            "detect_wall_stuck": lambda is_moving: self.detect_wall_stuck(
                walls,
                self.get_player_pos(player_data),
                bool(is_moving),
                time.time(),
            ),
            "start_escape": lambda angle: self.start_semicircle_escape(float(angle), time.time()),
            "escape_step": lambda: self.semicircle_escape_step(time.time()),
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

    def find_teammate_alive_marker(self, frame):
        """Find the blue off-screen teammate marker used when an alive mate is far away."""
        if not self.teammate_marker_follow_enabled or frame is None:
            return None

        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
        blue = cv2.inRange(
            hsv,
            np.array((92, 90, 85), dtype=np.uint8),
            np.array((125, 255, 255), dtype=np.uint8),
        )
        blue = cv2.morphologyEx(
            blue,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
        )
        contours, _ = cv2.findContours(blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        edge_x = max(24, int(w * self.teammate_marker_edge_margin))
        edge_y = max(24, int(h * self.teammate_marker_edge_margin))
        scale = max(0.4, min(1.2, w / brawl_stars_width))
        min_area = max(180, int(500 * scale * scale))
        max_area = max(min_area + 1, int(50000 * scale * scale))
        best = None

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area or area > max_area:
                continue
            x, y, bw, bh = cv2.boundingRect(contour)
            if bw < 18 * scale or bh < 18 * scale or bw > 240 * scale or bh > 240 * scale:
                continue
            cx, cy = x + bw * 0.5, y + bh * 0.5
            near_edge = cx <= edge_x or cx >= w - edge_x or cy <= edge_y or cy >= h - edge_y
            if not near_edge:
                continue
            if cx >= w * 0.70 and cy >= h * 0.55:
                continue
            if cx <= w * 0.24 and cy >= h * 0.62:
                continue
            aspect = bw / max(1, bh)
            if aspect < 0.55 or aspect > 1.80:
                continue

            pad = int(max(bw, bh) * 0.45)
            x1, y1 = max(0, x - pad), max(0, y - pad)
            x2, y2 = min(w, x + bw + pad), min(h, y + bh + pad)
            roi = hsv[y1:y2, x1:x2]
            if roi.size == 0:
                continue
            roi_area = max(1, roi.shape[0] * roi.shape[1])
            white_ratio = self._count_mask_pixels(roi, (0, 0, 185), (179, 70, 255)) / roi_area
            blue_ratio = self._count_mask_pixels(roi, (92, 90, 85), (125, 255, 255)) / roi_area
            if white_ratio < 0.055 or blue_ratio < 0.08:
                continue

            edge_score = min(cx, w - cx, cy, h - cy)
            score = (edge_score, -area)
            if best is None or score < best[0]:
                best = (score, (cx, cy), (x1, y1, x2, y2))

        if best is None:
            return None
        _, marker_pos, marker_box = best
        vlog(f"teammate marker detected -> pos={tuple(map(int, marker_pos))} box={tuple(map(int, marker_box))}")
        return marker_pos

    def teammate_marker_follow_angle(self, player_pos):
        marker_pos = self.find_teammate_alive_marker(self.current_frame)
        if marker_pos is None or player_pos is None:
            return None
        dx = marker_pos[0] - player_pos[0]
        dy = marker_pos[1] - player_pos[1]
        if math.hypot(dx, dy) < 8:
            return None
        angle = self.angle_from_direction(dx, dy)
        vlog(f"follow teammate marker -> angle={angle:.1f}°")
        return angle

    def _build_trusted_fog_mask(self, frame, roi_center, roi_radius):
        """Return (mask, (ox, oy)) or None.

        Only processes an ROI of side 2*roi_radius+1 around roi_center —
        we only care about fog that's close to the player.
        Mask contains only fog pixels that belong to a large, morphologically
        clean blob — not stray color noise. (ox, oy) is the ROI's top-left
        offset in frame coordinates so callers can translate back.

        Result is cached per-frame (keyed by id(frame) and ROI tuple).
        """
        if frame is None or not hasattr(frame, "shape"):
            return None

        roi_radius = int(max(1, roi_radius))
        cache_key = (id(frame), int(roi_center[0]), int(roi_center[1]), int(roi_radius))
        if getattr(self, "_fog_mask_cache_frame_id", None) == cache_key:
            return getattr(self, "_fog_mask_cache_value", None)

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

    def _refresh_fog_cache(self, frame, player_position):
        """Build smoke threat state once, then reuse it across movement decisions."""
        if frame is None or player_position is None:
            self._fog_threat_cached = None
            self._fog_direction_escape_cached = None
            return
        self._fog_threat_cached = self.detect_fog_threat(frame, player_position)
        self._fog_direction_escape_cached = self.detect_fog_direction_escape(frame, player_position)

    def _follow_teammate_locked_nearby(self, player_pos, teammate_data, walls=None):
        locked, dist = self.choose_locked_teammate(player_pos, teammate_data or [], walls)
        return locked is not None and dist <= self.teammate_combat_regroup_distance

    def detect_jump_pad_smoke_escape(self, frame, player_position):
        """Return a softer fog escape angle for jump-pad decisions only.

        Normal fog fleeing stays tight to avoid jitter. This detects smoke a
        little earlier, but callers only use it when the bot is alone at the
        map edge and a reachable jump pad exists.
        """
        if frame is None or player_position is None:
            return None
        r = int(max(self.jump_pad_smoke_early_distance, self.fog_flee_distance))
        built = self._build_trusted_fog_mask(frame, roi_center=player_position, roi_radius=r)
        if built is None:
            return None
        mask, (ox, oy) = built

        ys, xs = np.nonzero(mask)
        if xs.size == 0:
            return None

        px, py = int(player_position[0]), int(player_position[1])
        dx_all = (xs + ox) - px
        dy_all = (ys + oy) - py
        dist_sq = dx_all * dx_all + dy_all * dy_all
        inside = dist_sq <= r * r
        count = int(inside.sum())
        min_pixels = max(20, int(self.fog_min_pixels_in_radius * 0.45))
        if count < min_pixels:
            return None

        cx = float(dx_all[inside].mean())
        cy = float(dy_all[inside].mean())
        if math.hypot(cx, cy) < 1:
            return None
        toward_fog = self.angle_from_direction(cx, cy)
        flee = self.angle_opposite(toward_fog)
        vlog(f"jump pad smoke check: {count}px within {r}px -> flee angle={flee:.1f}°")
        return flee

    def angle_points_into_fog(self, frame, player_position, angle_degrees, lookahead=None):
        """Return True when moving at angle_degrees would drive into nearby fog.

        This is intentionally stricter than the generic fog threat check: it
        only rejects the selected movement path, so teammate-following can still
        work beside smoke without blindly walking toward a teammate inside it.
        """
        if frame is None or player_position is None or angle_degrees is None:
            return False
        fog_flee_distance = float(getattr(self, "fog_flee_distance", 130))
        r = int(max(140, lookahead or fog_flee_distance * 1.7))
        built = self._build_trusted_fog_mask(frame, roi_center=player_position, roi_radius=r)
        if built is None:
            return False
        mask, (ox, oy) = built

        import numpy as np
        ys, xs = np.nonzero(mask)
        if xs.size == 0:
            return False

        px, py = player_position
        dx = (xs + ox) - px
        dy = (ys + oy) - py
        ux, uy = self.angle_to_vector(float(angle_degrees))
        forward = dx * ux + dy * uy
        lateral = np.abs(dx * uy - dy * ux)
        corridor_width = max(42, int(r * 0.28))
        min_pixels = max(18, int(self.fog_min_pixels_in_radius * 0.5))
        in_path = (forward > 0) & (forward <= r) & (lateral <= corridor_width)
        count = int(in_path.sum())
        if count >= min_pixels:
            vlog(f"fog path guard: {count}px ahead at angle={float(angle_degrees):.1f}°")
            return True
        return False

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

    def choose_locked_teammate(self, player_pos, teammate_data, walls=None):
        """Keep following the same teammate as long as the detector can track them."""
        closest_teammate, closest_distance = self.find_closest_teammate(teammate_data, player_pos, walls)
        if closest_teammate is None:
            if self.teammate_lock_lost_since <= 0:
                self.teammate_lock_lost_since = time.time()
            if time.time() - self.teammate_lock_lost_since > 1.5:
                self.locked_teammate = None
                self.locked_teammate_distance = float('inf')
            return self.locked_teammate, self.locked_teammate_distance

        self.teammate_lock_lost_since = 0.0
        if self.locked_teammate is None:
            self.locked_teammate = closest_teammate
            self.locked_teammate_distance = closest_distance
            return self.locked_teammate, self.locked_teammate_distance

        candidates = []
        for teammate in teammate_data or []:
            teammate_pos = self.get_enemy_pos(teammate)
            dist_to_lock = self.get_distance(teammate_pos, self.locked_teammate)
            dist_to_player = self.get_distance(teammate_pos, player_pos)
            candidates.append((dist_to_lock, dist_to_player, teammate_pos))
        candidates.sort(key=lambda item: item[0])

        tracked_lock = None
        tracked_distance = float('inf')
        if candidates and candidates[0][0] <= self.teammate_lock_max_jump:
            tracked_lock = candidates[0][2]
            tracked_distance = candidates[0][1]

        if tracked_lock is None:
            self.locked_teammate = closest_teammate
            self.locked_teammate_distance = closest_distance
            return self.locked_teammate, self.locked_teammate_distance

        switch_distance = tracked_distance * (1.0 - self.teammate_hysteresis)
        if closest_distance < switch_distance:
            vlog(
                "follow teammate: switching lock "
                f"tracked={int(tracked_distance)}px closest={int(closest_distance)}px"
            )
            self.locked_teammate = closest_teammate
            self.locked_teammate_distance = closest_distance
        else:
            self.locked_teammate = tracked_lock
            self.locked_teammate_distance = tracked_distance
        return self.locked_teammate, self.locked_teammate_distance

    def showdown_follow_teammate(self, player_data, teammate_data, walls):
        """Official Pyla follower behavior adapted to angle movement.

        The newest Pyla follower does not orbit or keep spacing. When no enemy
        is reachable it simply moves toward the closest teammate, trying the
        direct diagonal vector first, then the horizontal and vertical parts.
        """
        player_pos = self.get_player_pos(player_data)
        closest_teammate, closest_distance = self.choose_locked_teammate(player_pos, teammate_data, walls)
        if teammate_data:
            self.last_teammate_seen_time = time.time()

        if closest_teammate is None:
            self.locked_teammate = None
            self.locked_teammate_distance = float('inf')
            last_seen = float(getattr(self, "last_teammate_seen_time", 0.0) or 0.0)
            marker_delay = float(getattr(self, "teammate_marker_fallback_delay", 1.25))
            no_recent_teammate = (
                    last_seen <= 0
                    or time.time() - last_seen >= marker_delay
            )
            if no_recent_teammate:
                marker_angle = self.teammate_marker_follow_angle(player_pos)
                if marker_angle is not None:
                    return self._wall_aware_follow_angle(player_pos, marker_angle, walls)
            vlog("follow teammate: no teammate detected -> roam")
            return self._wall_aware_follow_angle(player_pos, self.showdown_roam(player_data, walls), walls)

        direction_x = closest_teammate[0] - player_pos[0]
        direction_y = closest_teammate[1] - player_pos[1]
        direct_angle = self.angle_from_direction(direction_x, direction_y)

        if (
                self.teammate_follow_force_direct
                and closest_distance > self.teammate_follow_step_distance
                and not self.is_path_blocked_angle(player_pos, direct_angle, walls)
        ):
            vlog(f"follow teammate: force direct -> angle={direct_angle:.1f}° (dist={int(closest_distance)}px)")
            return self._wall_aware_follow_angle(player_pos, direct_angle, walls)

        movement_vectors = [(direction_x, direction_y), (direction_x, 0), (0, direction_y)]
        fallback_angle = direct_angle

        for dx, dy in movement_vectors:
            if math.hypot(dx, dy) < 1:
                continue
            angle = self.angle_from_direction(dx, dy)
            if fallback_angle is None:
                fallback_angle = angle
            if not self.is_path_blocked_angle(player_pos, angle, walls):
                vlog(f"follow teammate -> angle={angle:.1f}° (dist={int(closest_distance)}px)")
                return self._wall_aware_follow_angle(player_pos, angle, walls)

        for angle in (270.0, 180.0, 90.0, 0.0):
            if not self.is_path_blocked_angle(player_pos, angle, walls):
                vlog(f"follow teammate: preferred blocked -> fallback angle={angle:.1f}°")
                return self._wall_aware_follow_angle(player_pos, angle, walls)

        angle = fallback_angle if fallback_angle is not None else self.showdown_roam(player_data, walls)
        vlog(f"follow teammate: all paths blocked -> forcing angle={float(angle):.1f}°")
        return self._wall_aware_follow_angle(player_pos, angle, walls)

    def _wall_aware_follow_angle(self, player_pos, angle, walls):
        if isinstance(angle, (int, float)):
            if not walls:
                return float(angle) % 360
            return self.find_best_angle(player_pos, float(angle), walls)
        return angle

    def get_showdown_movement(self, player_data, enemy_data, teammate_data, walls, brawler, jump_pads=None):
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

        enemy_coords = None
        enemy_distance = None
        follow_teammates = self.showdown_playstyle_mode in ("follow", "follower", "team", "teammate", "teammates")

        # Smoke override is applied uniformly so it beats teammate-follow,
        # combat strafing, and ordinary roaming. Keep this fast by caching the
        # screen analysis, but default to checking every frame.
        self._fog_check_counter += 1
        if follow_teammates or self._fog_check_counter >= self.fog_check_every_n_frames:
            self._refresh_fog_cache(self.current_frame, player_pos)
            self._fog_check_counter = 0
        fog_threat_angle = self._fog_threat_cached
        fog_direction_escape = self._fog_direction_escape_cached
        active_fog_pressure = (
                fog_direction_escape is not None
                or (
                    fog_threat_angle is not None
                    and not (
                        follow_teammates
                        and self._follow_teammate_locked_nearby(player_pos, teammate_data, walls)
                    )
                )
        )
        if follow_teammates:
            if fog_direction_escape is not None:
                angle = self.find_best_angle(player_pos, fog_direction_escape, walls)
                vlog(f"showdown: teammate follow paused for directional smoke escape -> angle={angle:.1f}°")
                return angle
            if (
                    fog_threat_angle is not None
                    and not self._follow_teammate_locked_nearby(player_pos, teammate_data, walls)
            ):
                angle = self.find_best_angle(player_pos, fog_threat_angle, walls)
                vlog(f"showdown: teammate follow paused for smoke escape -> angle={angle:.1f}°")
                return angle

        # --- No enemy in sight: follow teammate or roam ---
        if not self.is_there_enemy(enemy_data):
            if follow_teammates and (teammate_data or self.current_frame is not None):
                if teammate_data:
                    vlog(f"no enemy → follow teammate ({len(teammate_data)} visible)")
                else:
                    vlog("no enemy -> follow teammate marker if visible")
                angle = self.showdown_follow_teammate(player_data, teammate_data, walls)
            else:
                vlog("no enemy → hide/roam")
                angle = self.showdown_roam(player_data, walls)
        else:
            enemy_coords, enemy_distance = self.find_closest_enemy(enemy_data, player_pos, walls, "attack")
            if enemy_coords is None:
                if follow_teammates and (teammate_data or self.current_frame is not None):
                    if teammate_data:
                        vlog("enemy detected but unreachable → follow teammate")
                    else:
                        vlog("enemy detected but unreachable -> follow teammate marker if visible")
                    angle = self.showdown_follow_teammate(player_data, teammate_data, walls)
                else:
                    vlog("enemy detected but unreachable → hide/roam")
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
                        and not active_fog_pressure
                        and safe_range < enemy_distance <= attack_range
                ):
                    strafe_angle = self.get_strafe_angle(toward_angle, now_t, enemy_distance, safe_range)
                    desired = self.blend_angles(desired, strafe_angle, self.strafe_blend)
                    vlog(f"strafe blend → desired={desired:.1f}°")
                elif (
                        self.strafe_enabled
                        and not active_fog_pressure
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

                if self.strafe_enabled and not active_fog_pressure and enemy_distance <= attack_range:
                    desired = self.apply_combat_dodge(desired, toward_angle, now_t, enemy_distance, safe_range)
                    vlog(f"combat dodge blend -> desired={desired:.1f}°")

                if (follow_teammates and teammate_data and enemy_distance > attack_range):
                    closest_teammate, teammate_distance = self.choose_locked_teammate(
                        player_pos,
                        teammate_data,
                        walls,
                    )
                    if closest_teammate is not None and teammate_distance > self.teammate_follow_step_distance:
                        team_angle = self.angle_from_direction(
                            closest_teammate[0] - player_pos[0],
                            closest_teammate[1] - player_pos[1],
                        )
                        team_weight = self.teammate_combat_bias
                        if self.trio_grouping_enabled and teammate_distance > self.teammate_combat_regroup_distance:
                            team_weight = max(team_weight, 0.85)
                        desired = self.blend_angles(desired, team_angle, team_weight)
                        vlog(f"combat teammate pull -> desired={desired:.1f}° (team dist={int(teammate_distance)}px, weight={team_weight:.2f})")

                angle = self.find_best_angle(player_pos, desired, walls)
                vlog(f"showdown: movement angle={angle:.1f}° (desired={desired:.1f}°)")

        if (
                follow_teammates
                and fog_direction_escape is None
                and self.angle_points_into_fog(self.current_frame, player_pos, angle)
        ):
            path_flee_angle = self.angle_opposite(angle)
            vlog(f"showdown: follow path points into fog -> fallback escape={path_flee_angle:.1f}°")
        else:
            path_flee_angle = None

        # --- Fog proximity override ---
        # If trusted smoke is close, replace movement with a flee angle. Attack
        # block below still fires independently based on enemy_distance.
        if fog_direction_escape is not None:
            angle = self.find_best_angle(player_pos, fog_direction_escape, walls)
            vlog(f"showdown: fog override -> directional escape angle={angle:.1f}°")
        elif path_flee_angle is not None:
            angle = self.find_best_angle(player_pos, path_flee_angle, walls)
            vlog(f"showdown: fog override -> path escape angle={angle:.1f}°")
        elif (
                fog_threat_angle is not None
                and not (
                    follow_teammates
                    and self._follow_teammate_locked_nearby(player_pos, teammate_data, walls)
                )
        ):
            angle = self.find_best_angle(player_pos, fog_threat_angle, walls)
            vlog(f"showdown: fog threat override -> angle={angle:.1f}°")

        jump_pad_flee_angle = None
        if (
                fog_direction_escape is None
                and jump_pads
                and self.jump_pad_detection_enabled
                and (not self.jump_pad_escape_requires_edge or self.is_player_near_map_edge(player_pos))
                and not self.has_close_teammate_for_jump_escape(player_pos, teammate_data)
        ):
            jump_pad_flee_angle = path_flee_angle or fog_threat_angle or self.detect_jump_pad_smoke_escape(self.current_frame, player_pos)

        if jump_pad_flee_angle is not None:
            jump_pad_angle = self.find_jump_pad_escape_angle(
                player_pos,
                jump_pads or [],
                walls,
                jump_pad_flee_angle,
                teammate_data=teammate_data,
            )
            if jump_pad_angle is not None:
                angle = jump_pad_angle
                vlog(f"showdown: fog override -> jump pad angle={angle:.1f}°")

        # --- Skills (only when an attackable enemy was found) ---
        if enemy_coords is None:
            return angle

        self.try_use_super_on_enemy(brawler, brawler_info, player_pos, enemy_coords, enemy_distance, walls)

        vlog(f"showdown movement → angle={angle:.1f}°")

        if enemy_distance <= attack_range:
            enemy_hittable = self.is_enemy_hittable(player_pos, enemy_coords, walls, "attack")
            vlog(f"enemy in attack range (dist={int(enemy_distance)}px, range={attack_range}px), hittable={enemy_hittable}")
            if enemy_hittable:
                if self.should_use_gadget_on_enemy(brawler, player_data, enemy_data, walls):
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
        line_of_sight_walls = getattr(self, "current_line_of_sight_walls", None) or walls
        if self.walls_block_line_of_sight(player_pos, enemy_pos, line_of_sight_walls):
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

        if 'line_of_sight_wall' not in data.keys() or not data['line_of_sight_wall']:
            data['line_of_sight_wall'] = data['wall']

        if 'jump_pad' not in data.keys() or not data['jump_pad']:
            data['jump_pad'] = []

        if 'map_objects' not in data.keys() or not data['map_objects']:
            data['map_objects'] = {}

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
        return safe_range, attack_range, super_range

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

    def loop(self, brawler, data, current_time):
        if self.is_showdown:
            movement = self.get_showdown_movement(
                player_data=data['player'][0],
                enemy_data=data['enemy'],
                teammate_data=data['teammate'],
                walls=data['wall'],
                brawler=brawler,
                jump_pads=data.get('jump_pad') or [],
            )
            strict_following = (
                self.showdown_playstyle_mode in ("follow", "follower", "team", "teammate", "teammates")
                and bool(data.get('teammate'))
            )
            if strict_following:
                self.last_movement = movement
                self.last_movement_time = time.time()
            else:
                # Debounce small angle jitter before sending to joystick.
                movement = self._debounce_angle(movement)
        else:
            movement = self.get_movement(player_data=data['player'][0], enemy_data=data['enemy'], walls=data['wall'], brawler=brawler)

        movement = self.enemy_pressure_movement_fallback(movement, data, brawler, current_time)

        current_time = time.time()
        if isinstance(movement, float):
            # Analog showdown movement must update every frame. Throttling it
            # can leave the bot standing or walking into smoke with a stale
            # joystick angle.
            escape_angle = self.semicircle_escape_step(current_time)
            if escape_angle is not None:
                movement = escape_angle
            else:
                player_pos = self.get_player_pos(data['player'][0]) if data.get('player') else None
                walls = data.get('wall') or []
                if self.detect_wall_stuck(walls, player_pos, True, current_time):
                    self.capture_vision_frame("wall_stuck", self.current_frame, data, brawler)
                    self.start_semicircle_escape(movement, current_time)
                    self._reset_wall_stuck_state(current_time)
                    movement = self.semicircle_escape_step(current_time) or movement
            self.do_movement(movement)
            self.time_since_movement = current_time
        elif current_time - self.time_since_movement > self.minimum_movement_delay:
            movement = self.unstuck_movement_if_needed(movement, current_time)
            self.do_movement(movement)
            self.time_since_movement = current_time
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

    def should_use_gadget_on_enemy(self, brawler, player_data, enemy_data, walls):
        if not self.should_use_gadget or not self.is_gadget_ready or self.time_since_holding_attack is not None:
            return False
        if not enemy_data:
            return False

        player_pos = self.get_player_pos(player_data)
        enemy_coords, enemy_distance = self.find_closest_enemy(enemy_data, player_pos, walls, "attack")
        if enemy_coords is None:
            return False

        _, attack_range, _ = self.get_brawler_range(brawler)
        enemies_in_range = sum(
            1
            for enemy in (enemy_data or [])
            if self.get_distance(self.get_enemy_pos(enemy), player_pos) <= attack_range
        )
        gadget_threshold = attack_range if enemies_in_range >= 2 else attack_range * 0.7
        if enemy_distance > gadget_threshold:
            return False
        return self.is_enemy_hittable(player_pos, enemy_coords, walls, "attack")

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
        primary_count = sum(len(boxes or []) for boxes in (tile_data or {}).values())
        if (
                primary_count < self.wall_detection_retry_min_objects
                and self.wall_detection_retry_confidence < self.wall_detection_confidence
        ):
            retry_data = self.Detect_tile_detector.detect_objects(
                frame,
                conf_tresh=self.wall_detection_retry_confidence,
            )
            retry_count = sum(len(boxes or []) for boxes in (retry_data or {}).values())
            if retry_count > primary_count:
                if visual_debug:
                    counts = {key: len(value) for key, value in retry_data.items()}
                    print(
                        "[DBG] sparse map objects recovered with lower wall threshold "
                        f"{self.wall_detection_retry_confidence:.2f}: {counts}"
                    )
                tile_data = retry_data
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

    def process_tile_data(self, tile_data, frame=None):
        map_objects = self.build_map_object_vision(tile_data, frame)
        walls = []
        for class_name, boxes in map_objects.items():
            if class_name in self.blocking_map_object_classes():
                walls.extend(boxes)
        walls = self.merge_wall_boxes(walls)

        # Add walls to history
        self.wall_history.append(walls)
        if len(self.wall_history) > self.wall_history_length:
            self.wall_history.pop(0)
        # Combine walls from history
        combined_walls = self.combine_walls_from_history()

        return combined_walls, map_objects

    @staticmethod
    def blocking_map_object_classes():
        return {
            "wall",
            "crate",
            "barrel",
            "fence",
            "indestructible",
            "themed",
            "bouncer",
            "gravity_push",
            "gravity_pull",
            "damageable",
            "invisible_indestructible",
        }

    @staticmethod
    def line_of_sight_map_object_classes():
        return {
            "wall",
            "crate",
            "barrel",
            "fence",
            "indestructible",
            "themed",
            "bouncer",
            "gravity_push",
            "gravity_pull",
            "damageable",
            "invisible_indestructible",
        }

    @staticmethod
    def nonblocking_map_object_classes():
        return {"bush", "close_bush", "jump_pad", "fog"}

    def map_object_boxes_for_classes(self, map_objects, class_names):
        boxes = []
        allowed = set(class_names)
        for class_name, class_boxes in (map_objects or {}).items():
            if class_name in allowed:
                boxes.extend(class_boxes or [])
        return self.merge_wall_boxes(boxes)

    def build_map_object_vision(self, tile_data, frame=None):
        objects = {}
        for class_name, boxes in (tile_data or {}).items():
            normalized_name = self.normalize_map_object_class(class_name)
            normalized_boxes = [
                self.normalize_box(box)
                for box in boxes or []
            ]
            if normalized_boxes:
                objects.setdefault(normalized_name, []).extend(normalized_boxes)

        if self.map_object_vision_enabled and self.map_object_water_detection:
            water_boxes = self.detect_water_tiles(frame)
            if water_boxes:
                objects.setdefault("water", []).extend(water_boxes)

        wall_count = len(objects.get("wall") or [])
        if (
                self.map_object_vision_enabled
                and self.map_object_wall_color_detection
                and wall_count < self.wall_detection_retry_min_objects
        ):
            color_wall_boxes = self.detect_wall_tiles_by_color(frame)
            if color_wall_boxes:
                objects.setdefault("wall", []).extend(color_wall_boxes)

        return {
            key: self.merge_wall_boxes(value)
            for key, value in objects.items()
            if value
        }

    @staticmethod
    def normalize_map_object_class(class_name):
        name = str(class_name or "").strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {
            "closebush": "close_bush",
            "forest": "bush",
            "respawningforest": "bush",
            "water_tile": "water",
            "invisiblewater": "invisible_water",
            "wall1": "wall",
            "wall2": "wall",
            "wallywall": "wall",
            "wallyfillerwall": "wall",
            "indestructiblefence": "fence",
            "ropefence": "fence",
            "damageable1": "damageable",
            "damageable2": "damageable",
            "damageable3": "damageable",
            "damageable4": "damageable",
            "gravitypush": "gravity_push",
            "gravitypull": "gravity_pull",
        }
        return aliases.get(name, name)

    def detect_water_tiles(self, frame):
        if frame is None:
            return []

        hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
        # Kept conservative: many Showdown bushes are teal/cyan and otherwise
        # look like water in HSV, so only deep blue water should pass.
        water = cv2.inRange(
            hsv,
            np.array((98, 45, 80), dtype=np.uint8),
            np.array((116, 210, 255), dtype=np.uint8),
        )
        water = cv2.morphologyEx(
            water,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
        )
        water = cv2.morphologyEx(
            water,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (13, 13)),
        )
        contours, _ = cv2.findContours(water, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        h, w = frame.shape[:2]
        scale = max(0.4, min(1.2, w / brawl_stars_width))
        min_area = max(float(self.map_object_min_area), 700 * scale * scale)
        max_area = max(min_area + 1, 70000 * scale * scale)
        boxes = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area or area > max_area:
                continue
            x, y, bw, bh = cv2.boundingRect(contour)
            if bw < 24 * scale or bh < 24 * scale:
                continue
            if y > h * 0.84 or x < w * 0.04 or x > w * 0.96:
                continue
            roi = hsv[y:y + bh, x:x + bw]
            if roi.size == 0:
                continue
            sat_mean = float(roi[:, :, 1].mean())
            val_mean = float(roi[:, :, 2].mean())
            if sat_mean < 80 or val_mean < 85:
                continue
            boxes.append([x, y, x + bw, y + bh])

        return self.merge_wall_boxes(boxes)

    def detect_wall_tiles_by_color(self, frame):
        if frame is None:
            return []

        hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
        wall_mask = cv2.inRange(
            hsv,
            np.array((110, 35, 90), dtype=np.uint8),
            np.array((135, 165, 215), dtype=np.uint8),
        )
        wall_mask = cv2.morphologyEx(
            wall_mask,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        )
        wall_mask = cv2.morphologyEx(
            wall_mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)),
        )
        contours, _ = cv2.findContours(wall_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        h, w = frame.shape[:2]
        scale = max(0.4, min(1.2, w / brawl_stars_width))
        min_area = max(260, int(480 * scale * scale))
        tile = max(24, int(self.TILE_SIZE * scale * 0.85))
        boxes = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue
            x, y, bw, bh = cv2.boundingRect(contour)
            if bw < 16 * scale or bh < 16 * scale:
                continue
            if y < h * 0.08 or y > h * 0.86 or x < w * 0.02 or x > w * 0.98:
                continue
            if bw > w * 0.38 or bh > h * 0.36:
                continue

            roi_mask = wall_mask[y:y + bh, x:x + bw]
            roi_hsv = hsv[y:y + bh, x:x + bw]
            if roi_mask.size == 0:
                continue
            # Teal bushes are high saturation; stone walls sit lower.
            masked = roi_hsv[roi_mask > 0]
            if masked.size == 0 or float(masked[:, 1].mean()) > 150:
                continue
            masked_rgb = frame[y:y + bh, x:x + bw][roi_mask > 0]
            if masked_rgb.size == 0:
                continue
            r_mean = float(masked_rgb[:, 0].mean())
            g_mean = float(masked_rgb[:, 1].mean())
            b_mean = float(masked_rgb[:, 2].mean())
            if b_mean < g_mean + 12 or b_mean < r_mean + 10:
                continue

            step = max(14, int(tile * 0.52))
            min_cell = max(12, int(tile * 0.42))
            for cy in range(y, y + bh, step):
                for cx in range(x, x + bw, step):
                    x2 = min(cx + tile, x + bw)
                    y2 = min(cy + tile, y + bh)
                    if x2 - cx < min_cell or y2 - cy < min_cell:
                        continue
                    cell = wall_mask[cy:y2, cx:x2]
                    if cell.size == 0:
                        continue
                    density = cv2.countNonZero(cell) / float(cell.size)
                    if density < 0.42:
                        continue

                    ys, xs = np.nonzero(cell)
                    if xs.size == 0:
                        continue
                    cell_rgb = frame[cy:y2, cx:x2][cell > 0]
                    if cell_rgb.size == 0:
                        continue
                    r_cell = float(cell_rgb[:, 0].mean())
                    g_cell = float(cell_rgb[:, 1].mean())
                    b_cell = float(cell_rgb[:, 2].mean())
                    if b_cell < g_cell + 12 or b_cell < r_cell + 10:
                        continue
                    bx1 = cx + int(xs.min())
                    by1 = cy + int(ys.min())
                    bx2 = cx + int(xs.max()) + 1
                    by2 = cy + int(ys.max()) + 1
                    if bx2 - bx1 >= min_cell and by2 - by1 >= min_cell:
                        boxes.append([bx1, by1, bx2, by2])

        return self.merge_wall_boxes(boxes)

    @staticmethod
    def box_center(box):
        return (box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5

    def is_player_near_map_edge(self, player_pos):
        frame = getattr(self, "current_frame", None)
        if frame is None or player_pos is None:
            return False
        h, w = frame.shape[:2]
        margin = max(0.05, min(0.45, float(self.jump_pad_escape_edge_margin)))
        edge_x = w * margin
        edge_y = h * margin
        x, y = player_pos
        return x <= edge_x or x >= w - edge_x or y <= edge_y or y >= h - edge_y

    def has_close_teammate_for_jump_escape(self, player_pos, teammate_data):
        if player_pos is None:
            return True
        for teammate in teammate_data or []:
            teammate_pos = self.get_enemy_pos(teammate)
            if self.get_distance(teammate_pos, player_pos) <= self.jump_pad_escape_teammate_safe_distance:
                return True
        return False

    def detect_jump_pads(self, frame):
        """Detect jump pads from their yellow arrow inside a dark gray tile.

        The wall model does not include jump pads, so this uses strict color and
        shape anchors from the game art. It returns pad boxes in frame coords.
        """
        if not self.jump_pad_detection_enabled or frame is None:
            return []

        hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
        yellow = cv2.inRange(
            hsv,
            np.array((18, 90, 120), dtype=np.uint8),
            np.array((38, 255, 255), dtype=np.uint8),
        )
        yellow = cv2.morphologyEx(
            yellow,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
        )
        contours, _ = cv2.findContours(yellow, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        h, w = frame.shape[:2]
        scale = max(0.4, min(1.2, w / brawl_stars_width))
        min_area = max(80, int(450 * scale * scale))
        max_area = max(min_area + 1, int(9000 * scale * scale))
        pads = []

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area or area > max_area:
                continue
            x, y, bw, bh = cv2.boundingRect(contour)
            if bw < 12 * scale or bh < 12 * scale:
                continue
            if bw > 160 * scale or bh > 160 * scale:
                continue

            pad_size = int(max(bw, bh) * 2.4)
            cx, cy = x + bw * 0.5, y + bh * 0.5
            rx1 = max(0, int(cx - pad_size * 0.5))
            ry1 = max(0, int(cy - pad_size * 0.5))
            rx2 = min(w, int(cx + pad_size * 0.5))
            ry2 = min(h, int(cy + pad_size * 0.5))
            roi = hsv[ry1:ry2, rx1:rx2]
            if roi.size == 0:
                continue

            yellow_ratio = self._count_mask_pixels(roi, (18, 90, 120), (38, 255, 255)) / max(1, roi.shape[0] * roi.shape[1])
            gray_ratio = self._count_mask_pixels(roi, (0, 0, 40), (179, 95, 190)) / max(1, roi.shape[0] * roi.shape[1])
            dark_ratio = self._count_mask_pixels(roi, (0, 0, 0), (179, 255, 95)) / max(1, roi.shape[0] * roi.shape[1])
            if not (0.035 <= yellow_ratio <= 0.42 and gray_ratio > 0.16 and dark_ratio > 0.10):
                continue

            pads.append([rx1, ry1, rx2, ry2])

        return self.merge_wall_boxes(pads)

    def find_jump_pad_escape_angle(self, player_pos, jump_pads, walls, fog_flee_angle=None, teammate_data=None):
        if not jump_pads or player_pos is None:
            return None
        if self.jump_pad_escape_requires_edge and not self.is_player_near_map_edge(player_pos):
            vlog("jump pad escape skipped: player is not near map edge")
            return None
        if self.has_close_teammate_for_jump_escape(player_pos, teammate_data):
            vlog("jump pad escape skipped: teammate is close")
            return None

        candidates = []
        for pad in jump_pads:
            pad_pos = self.box_center(self.normalize_box(pad))
            distance = self.get_distance(pad_pos, player_pos)
            if distance < self.jump_pad_escape_min_distance or distance > self.jump_pad_escape_distance:
                continue
            angle = self.angle_from_direction(pad_pos[0] - player_pos[0], pad_pos[1] - player_pos[1])
            if self.is_path_blocked_angle(player_pos, angle, walls, distance=max(40, min(distance, self.TILE_SIZE * 2))):
                continue
            fog_alignment = 0.0
            if fog_flee_angle is not None:
                fog_alignment = abs((angle - fog_flee_angle + 180) % 360 - 180)
            candidates.append((fog_alignment, distance, angle, pad_pos))

        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]))
        _, distance, angle, pad_pos = candidates[0]
        vlog(f"jump pad escape -> angle={angle:.1f}° dist={int(distance)}px pad={tuple(map(int, pad_pos))}")
        return angle

    def combine_walls_from_history(self):
        if not self.wall_history:
            return []
        current_walls = self.wall_history[-1]
        historical_walls = [wall for walls in self.wall_history for wall in walls]
        stable_history = self.merge_wall_boxes(historical_walls, min_hits=max(1, self.wall_history_min_hits))
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
                if self.should_use_gadget_on_enemy(brawler, player_data, enemy_data, walls):
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

    def main(self, frame, brawler, main):
        current_time = time.time()
        raw_data = self.get_main_data(frame)
        data = raw_data
        if self.should_detect_walls and current_time - self.time_since_walls_checked > self.walls_treshold:

            tile_data = self.get_tile_data(frame)

            walls, map_objects = self.process_tile_data(tile_data, frame)
            line_of_sight_walls = self.map_object_boxes_for_classes(
                map_objects,
                self.line_of_sight_map_object_classes(),
            )
            jump_pads = self.detect_jump_pads(frame)
            if jump_pads:
                map_objects.setdefault("jump_pad", []).extend(jump_pads)
                map_objects["jump_pad"] = self.merge_wall_boxes(map_objects["jump_pad"])

            self.time_since_walls_checked = current_time
            self.last_walls_data = walls
            self.last_jump_pad_data = jump_pads
            self.last_map_object_data = map_objects
            data['wall'] = walls
            data['line_of_sight_wall'] = line_of_sight_walls
            data['jump_pad'] = jump_pads
            data['map_objects'] = map_objects
        elif self.keep_walls_in_memory:
            data['wall'] = self.last_walls_data
            data['line_of_sight_wall'] = self.map_object_boxes_for_classes(
                self.last_map_object_data,
                self.line_of_sight_map_object_classes(),
            )
            data['jump_pad'] = self.last_jump_pad_data
            data['map_objects'] = self.last_map_object_data

        data = self.validate_game_data(data)
        self.track_no_detections(data)
        if data:
            self.time_since_player_last_found = time.time()
            if main.state != "match":
                main.state = get_state(frame)
                if main.state != "match":
                    data = None
        if not data:
            player_lost_for = current_time - self.time_since_player_last_found
            if (
                    player_lost_for <= getattr(self, "player_lost_movement_grace_seconds", 2.5)
                    and getattr(self, "last_movement", None) is not None
            ):
                self.do_movement(self.last_movement)
            elif player_lost_for > 1.0:
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
        self.current_line_of_sight_walls = data.get("line_of_sight_wall") or data.get("wall") or []
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
            elif isinstance(value, dict):
                copied[key] = {
                    sub_key: [
                        list(item) if isinstance(item, (list, tuple, np.ndarray)) else item
                        for item in (sub_value or [])
                    ]
                    for sub_key, sub_value in value.items()
                }
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

        # Colors in RGB (frame is kept in RGB; converted to BGR only for imshow).
        colors = {
            "player":   (0, 255, 0),    # green
            "teammate": (0, 0, 255),    # blue
            "enemy":    (255, 0, 0),    # red
            "wall":     (128, 128, 128),  # gray
        }
        object_colors = {
            "wall": (180, 180, 180),
            "water": (0, 190, 255),
            "bush": (0, 180, 60),
            "close_bush": (80, 255, 100),
            "jump_pad": (255, 220, 0),
            "crate": (210, 130, 30),
            "barrel": (210, 110, 50),
            "fence": (210, 210, 210),
            "indestructible": (120, 120, 255),
            "themed": (255, 120, 180),
            "bouncer": (255, 180, 0),
            "damageable": (255, 80, 80),
            "gravity_push": (120, 255, 255),
            "gravity_pull": (170, 120, 255),
            "invisible_water": (80, 160, 255),
            "invisible_indestructible": (160, 160, 220),
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
                if key != "wall":
                    cv2.putText(img, key, sp((x1, max(y1 - 6, 0))),
                                cv2.FONT_HERSHEY_SIMPLEX, max(0.35, 0.5 * scale), color, 1)
                boxes_drawn += 1

        map_objects = data.get("map_objects") or {}
        object_counts = {
            key: len(boxes)
            for key, boxes in map_objects.items()
            if boxes
        }
        if object_counts:
            summary = " ".join(
                f"{key}:{count}"
                for key, count in sorted(object_counts.items())
                if key != "wall"
            )
            wall_count = object_counts.get("wall")
            if wall_count is not None:
                summary = f"wall:{wall_count} {summary}".strip()
            if summary:
                cv2.putText(
                    img,
                    summary[:120],
                    (s(8), s(18)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    max(0.32, 0.45 * scale),
                    (255, 255, 255),
                    1,
                )

        for key, boxes in map_objects.items():
            if not boxes or key == "wall":
                continue
            color = object_colors.get(key, (255, 255, 255))
            label_drawn = False
            for box in boxes:
                if boxes_drawn >= self.visual_debug_max_boxes:
                    break
                x1, y1, x2, y2 = map(int, box)
                cv2.rectangle(img, sp((x1, y1)), sp((x2, y2)), color, max(1, s(1)))
                if not label_drawn and key not in {"bush", "close_bush"}:
                    label = key[:14]
                    cv2.putText(img, label, sp((x1, min(max(y1 + 12, 0), frame.shape[0] - 1))),
                                cv2.FONT_HERSHEY_SIMPLEX, max(0.3, 0.42 * scale), color, 1)
                    label_drawn = True
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
