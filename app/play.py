import math
import os
import queue
import random
import threading
import time

import cv2
import numpy as np

from detect import Detect
try:
    from early_access.early_access import add_advanced_visuals
    early_access = True
except ImportError:
    early_access = False
    def add_advanced_visuals(a, b):
        return None
from core.integration import migrate_bot_config
from state_finder import get_state
from utils import load_toml_as_dict, count_hsv_pixels, load_brawlers_info, resolve_brawler_info_key, interpret_pyla_code, \
    count_mask_pixels, JOYSTICK_RADIUS, clamp, debug_beep, config_bool, resolve_project_path
from visual_debug_window import (
    log_visual_debug_startup,
    opencv_highgui_available,
    show_visual_debug_frame,
)

brawl_stars_width, brawl_stars_height = 1920, 1080
CLOSE_TILE_CROP_SIZE = 640
CLOSE_TILE_MODEL_PATH = "models/closeTileDetector.onnx"
DEBUG_FRAMES_DIR = resolve_project_path("debug_frames")
visual_debug = str(load_toml_as_dict("cfg/general_config.toml").get("visual_debug", "no")).lower() in (
    "yes",
    "true",
    "1",
)
super_crop_area = load_toml_as_dict("./cfg/lobby_config.toml")['pixel_counter_crop_area']['super']
gadget_crop_area = load_toml_as_dict("./cfg/lobby_config.toml")['pixel_counter_crop_area']['gadget']
hypercharge_crop_area = load_toml_as_dict("./cfg/lobby_config.toml")['pixel_counter_crop_area']['hypercharge']
POISON_LOW_HSV = np.array((30, 90, 221), dtype=np.uint8)
POISON_HIGH_HSV = np.array((57, 114, 235), dtype=np.uint8)
PLAYER_HIT_CIRCLE_RADIUS = 53

class Play:

    def __init__(self, main_info_model, tile_detector_model, close_tile_detector_model, window_controller, pyla_code):
        bot_config = migrate_bot_config(load_toml_as_dict("cfg/bot_config.toml"))
        time_config = load_toml_as_dict("cfg/time_tresholds.toml")
        self.fix_movement_keys = {
            "delay_to_trigger": bot_config["unstuck_movement_delay"],
            "duration": bot_config["unstuck_movement_hold_time"],
            "toggled": False,
            "started_at": time.time(),
            "fixed": (0, 0),
            "last_direction_key": None,
            "rotation_sign": 1,
            "rotation_angle_step": 1,
            "max_rotation_angle_step": 4,
        }
        self.super_treshold = time_config["super"]
        self.gadget_treshold = time_config["gadget"]
        self.hypercharge_treshold = time_config["hypercharge"]
        self.walls_treshold = time_config["wall_detection"]
        self.last_walls_data = []
        self.last_bushes_data = []
        self.keys_hold = []
        self.time_since_different_movement = time.time()
        self.should_use_gadget = str(bot_config.get("bot_uses_gadgets", "yes")).lower() in ("yes", "true", "1")
        self.gadget_cooldown = float(bot_config.get("gadget_cooldown", 8.0))
        self.last_gadget_time = 0.0
        self.super_cooldown = float(bot_config.get("super_cooldown", 1.0))
        self.last_super_time = 0.0
        self.ability_ready_memory_seconds = float(bot_config.get("ability_ready_memory_seconds", 1.25))
        self._hypercharge_ready_seen_at = 0.0
        self._gadget_ready_seen_at = 0.0
        self._super_ready_seen_at = 0.0
        self.super_crop_area = list(super_crop_area)
        self.gadget_crop_area = list(gadget_crop_area)
        self.hypercharge_crop_area = list(hypercharge_crop_area)
        self.time_since_gadget_checked = time.time()
        self.is_gadget_ready = False
        self.time_since_hypercharge_checked = time.time()
        self.is_hypercharge_ready = False
        self.time_since_super_checked = time.time()
        self.is_super_ready = False
        self.window_controller = window_controller
        self.TILE_SIZE = bot_config.get("perceived_tile_size", 32)
        self.close_tile_detector_enabled = (
            config_bool(bot_config.get("close_tile_detector_enabled"), False)
            or config_bool(bot_config.get("centered_wall_detection"), False)
        )
        self.centered_wall_detection = self.close_tile_detector_enabled
        self.centered_wall_crop_size = CLOSE_TILE_CROP_SIZE
        self.verbose_debug = config_bool(load_toml_as_dict("cfg/debug_settings.toml").get('verbose_debug'), False)
        if self.verbose_debug:
            os.makedirs(DEBUG_FRAMES_DIR, exist_ok=True)
        self.Detect_main_info = Detect(main_info_model, classes=['enemy', 'teammate', 'player'])
        self.tile_detector_model_classes = bot_config["wall_model_classes"]
        self.Detect_tile_detector = Detect(
            tile_detector_model,
            classes=self.tile_detector_model_classes,
        )
        close_model_path = resolve_project_path(close_tile_detector_model)
        if self.close_tile_detector_enabled and not os.path.exists(close_model_path):
            close_model_path = resolve_project_path(CLOSE_TILE_MODEL_PATH)
        self.Detect_close_tile_detector = None
        if self.close_tile_detector_enabled:
            if os.path.exists(close_model_path):
                self.Detect_close_tile_detector = Detect(
                    close_model_path,
                    classes=self.tile_detector_model_classes,
                )
                self._log_tile_detection_mode(
                    f"Close tile wall detector enabled ({close_model_path}, {CLOSE_TILE_CROP_SIZE}x{CLOSE_TILE_CROP_SIZE} crop).",
                )
            else:
                print(
                    f"WARNING: {close_model_path} not found; close tile detector disabled, using full-frame walls."
                )
                self.close_tile_detector_enabled = False
                self.centered_wall_detection = False
        self.Detect_centered_tile_detector = self.Detect_close_tile_detector
        self.last_tile_detection_debug = None

        self.time_since_walls_checked = 0
        self.time_since_player_last_found = time.time()
        self.current_brawler = None
        self.brawlers_info = load_brawlers_info()
        self.brawler_ranges = None
        self.time_since_detections = {
            "player": time.time(),
            "enemy": time.time(),
        }
        self.time_since_last_proceeding = time.time()

        self.last_movement = ''
        self.last_movement_change_time = time.time()
        self.minimum_movement_delay = bot_config["minimum_movement_delay"]
        self.no_detection_proceed_delay = time_config["no_detection_proceed"]
        self.gadget_pixels_minimum = bot_config["gadget_pixels_minimum"]
        self.hypercharge_pixels_minimum = bot_config["hypercharge_pixels_minimum"]
        self.super_pixels_minimum = bot_config["super_pixels_minimum"]
        self.wall_detection_confidence = bot_config["wall_detection_confidence"]
        self.wall_detection_retry_confidence = float(
            bot_config.get("wall_detection_retry_confidence", max(0.2, self.wall_detection_confidence - 0.55))
        )
        self.wall_detection_retry_min_objects = int(bot_config.get("wall_detection_retry_min_objects", 3))
        self.last_wall_primary_count = 0
        self.wall_box_min_size = float(bot_config.get("wall_box_min_size", 20))
        self.wall_box_merge_iou = float(bot_config.get("wall_box_merge_iou", 0.25))
        self.wall_box_merge_center_distance = float(bot_config.get("wall_box_merge_center_distance", 35))
        self.wall_history_min_hits = int(bot_config.get("wall_history_min_hits", 1))
        self.wall_history = []
        self.wall_history_length = int(bot_config.get("wall_history_length", 3))
        self.map_object_vision_enabled = config_bool(bot_config.get("map_object_vision_enabled"), True)
        self.map_object_wall_color_detection = config_bool(bot_config.get("map_object_wall_color_detection"), True)
        self.map_object_water_detection = config_bool(bot_config.get("map_object_water_detection"), False)
        self.map_object_min_area = float(bot_config.get("map_object_min_area", 900))
        self.last_map_object_data = {}
        self.entity_detection_confidence = bot_config["entity_detection_confidence"]
        self.seconds_to_hold_attack_after_reaching_max = load_toml_as_dict("cfg/bot_config.toml")["seconds_to_hold_attack_after_reaching_max"]
        self.persistent_data = {"time_since_holding_attack": None}
        self.pyla_code = pyla_code
        self.context = None
        self.frame = None
        self._spacing_strafe_side = 1
        self._spacing_strafe_last_flip_at = 0.0
        self._spacing_action = None
        self._evasion_active = False
        self._dodge_side = 1
        self._dodge_committed_until = 0.0
        self._dodge_vector = None
        self._dodge_jitter_rad = 0.0
        self._enemy_track = {"pos": None, "ts": 0.0, "velocity": (0.0, 0.0)}
        self._combat_target = None
        self._last_attack_tap_at = 0.0
        self.match_intent_summary = ""
        gamemode = str(bot_config.get("gamemode", "showdown")).strip().lower()
        self.is_showdown = gamemode == "showdown"
        self.wall_stuck_enabled = config_bool(bot_config.get("wall_stuck_enabled"), True)
        self.wall_stuck_ignore_radius = float(bot_config.get("wall_stuck_ignore_radius", 150))
        self.wall_stuck_sample_interval = float(bot_config.get("wall_stuck_sample_interval", 0.2))
        self.wall_stuck_shift_threshold = float(bot_config.get("wall_stuck_shift_threshold", 3.0))
        self.wall_stuck_timeout = float(bot_config.get("wall_stuck_timeout", 3.0))
        self.wall_stuck_min_walls = int(bot_config.get("wall_stuck_min_walls", 3))
        self.escape_retreat_duration = float(bot_config.get("escape_retreat_duration", 0.4))
        self.escape_arc_duration = float(bot_config.get("escape_arc_duration", 1.2))
        self.escape_arc_degrees = float(bot_config.get("escape_arc_degrees", 135.0))
        self.wall_stuck_state = {
            "last_sample_time": 0.0,
            "last_wall_centers": None,
            "stationary_since": None,
        }
        self.escape_state = {
            "phase": None,
            "started_at": 0.0,
            "retreat_angle": 0.0,
            "arc_side": 1,
        }
        self._next_arc_side = 1
        fog_low = bot_config.get("fog_hsv_low", (50, 95, 215))
        fog_high = bot_config.get("fog_hsv_high", (60, 125, 245))
        self.fog_hsv_low = tuple(fog_low) if isinstance(fog_low, (list, tuple)) else (50, 95, 215)
        self.fog_hsv_high = tuple(fog_high) if isinstance(fog_high, (list, tuple)) else (60, 125, 245)
        self.fog_flee_distance = float(bot_config.get("fog_flee_distance", 130))
        self.fog_min_blob_pixels = int(bot_config.get("fog_min_blob_pixels", 20))
        self.fog_min_pixels_in_radius = int(bot_config.get("fog_min_pixels_in_radius", 20))
        self.fog_check_every_n_frames = max(1, int(bot_config.get("fog_check_every_n_frames", 3)))
        self._fog_check_counter = 0
        self._fog_threat_cached = None
        self._fog_direction_escape_cached = None
        self._fog_mask_cache_frame_id = None
        self._fog_mask_cache_value = None
        self.refresh_enemy_spacing_config()
        general_config = load_toml_as_dict("cfg/general_config.toml")
        self.wall_stuck_debug = config_bool(general_config.get("wall_stuck_debug"), False)
        global visual_debug
        visual_debug = str(general_config.get("visual_debug", "no")).lower() in ("yes", "true", "1")
        self.advanced_visuals = str(general_config.get("advanced_visuals", "no")).lower() in ("yes", "true", "1")
        self.visual_debug_scale = max(0.25, min(1.0, float(general_config.get("visual_debug_scale", 0.6))))
        self.visual_debug_max_fps = max(1.0, float(general_config.get("visual_debug_max_fps", 30)))
        self.visual_debug_max_boxes = max(20, int(general_config.get("visual_debug_max_boxes", 120)))
        self._visual_debug_next_frame_at = 0.0
        self._visual_debug_next_enqueue_at = 0.0
        self._visual_debug_lock = threading.Lock()
        self._visual_debug_payload = None
        self._visual_debug_display_queue = queue.Queue(maxsize=1)
        self._visual_debug_thread = None
        self._visual_debug_stop = False
        if visual_debug:
            opencv_highgui_available()
            log_visual_debug_startup()

    @staticmethod
    def get_entity_pos(entity):
        return (entity[0] + entity[2]) / 2, (entity[1] + entity[3]) / 2

    @staticmethod
    def get_player_foot_circle(player_data):
        x1, y1, x2, y2 = player_data[:4]
        width = abs(float(x2) - float(x1))
        height = abs(float(y2) - float(y1))
        radius = max(width / 2.0, 4.0)
        foot_x = (float(x1) + float(x2)) / 2.0
        foot_y = float(y2) - radius
        return foot_x, foot_y, radius

    @staticmethod
    def get_player_pos(player_data):
        foot_x, foot_y, _ = Play.get_player_foot_circle(player_data)
        return foot_x, foot_y

    def _get_active_frame(self):
        frame = getattr(self, "current_frame", None)
        if frame is not None:
            return frame
        return getattr(self, "frame", None)

    @staticmethod
    def angle_from_direction(dx: float, dy: float) -> float:
        return math.degrees(math.atan2(dy, dx)) % 360

    @staticmethod
    def angle_opposite(angle_degrees: float) -> float:
        return (angle_degrees + 180) % 360

    @staticmethod
    def angle_to_vector(angle_degrees):
        angle_rad = math.radians(angle_degrees)
        return math.cos(angle_rad), math.sin(angle_rad)

    @staticmethod
    def vector_from_angle(angle_degrees, radius=JOYSTICK_RADIUS):
        ux, uy = Play.angle_to_vector(angle_degrees)
        return ux * radius, uy * radius

    @staticmethod
    def get_distance(enemy_coords, player_coords):
        return math.hypot(enemy_coords[0] - player_coords[0], enemy_coords[1] - player_coords[1])

    @staticmethod
    def is_there_enemy(enemy_data):
        if not enemy_data:
            return False
        return True

    def _log_combat_action(self, action: str) -> None:
        try:
            import runtime_log
        except ImportError:
            return
        brawler = getattr(self, "current_brawler", None) or "brawler"
        runtime_log.log_once(
            f"combat:{action}:{brawler}",
            1.5,
            runtime_log.LEVEL_INFO,
            "combat",
            f"{action.capitalize()} with {brawler}",
        )

    def attack(self, touch_up=True, touch_down=True):
        full_tap = bool(touch_down and touch_up)
        if full_tap and not self._holding_attack():
            now = time.time()
            interval = float(getattr(self, "attack_min_interval", 0.35) or 0.35)
            if now - float(getattr(self, "_last_attack_tap_at", 0) or 0) < interval:
                return
            if self._try_lead_aim_attack():
                self._last_attack_tap_at = now
                return
            self._last_attack_tap_at = now
        if full_tap:
            self._log_combat_action("attack")
        self.window_controller.press("attack", touch_up=touch_up, touch_down=touch_down)

    @staticmethod
    def lead_shot_angle(player_pos, enemy_pos, enemy_velocity, *, projectile_speed_px_s=1200.0):
        px, py = player_pos
        ex, ey = enemy_pos
        vx, vy = enemy_velocity
        dx = ex - px
        dy = ey - py
        distance = math.hypot(dx, dy)
        if distance < 1:
            return math.degrees(math.atan2(dy, dx))
        speed = max(float(projectile_speed_px_s or 1200.0), 1.0)
        travel_s = distance / speed
        lead_x = ex + vx * travel_s
        lead_y = ey + vy * travel_s
        return math.degrees(math.atan2(lead_y - py, lead_x - px))

    def get_tracked_enemy_velocity(self):
        track = getattr(self, "_enemy_track", None) or {}
        velocity = track.get("velocity", (0.0, 0.0))
        if not isinstance(velocity, (tuple, list)) or len(velocity) != 2:
            return (0.0, 0.0)
        return float(velocity[0]), float(velocity[1])

    def track_enemy(self, data, brawler=None):
        track = getattr(self, "_enemy_track", None)
        if track is None:
            track = {"pos": None, "ts": 0.0, "velocity": (0.0, 0.0)}
            self._enemy_track = track

        self._combat_target = None
        if not data or not data.get("player"):
            return
        enemies = data.get("enemy") or []
        if not self.is_there_enemy(enemies):
            return

        player_pos = self.get_player_pos(data["player"][0])
        walls = data.get("wall") or []
        enemy_result = self.find_closest_enemy(enemies, player_pos, walls, "attack")
        if not enemy_result:
            return

        enemy_pos, enemy_distance = enemy_result
        now = time.time()
        if track["pos"] is not None:
            dt = max(now - float(track["ts"] or now), 0.001)
            jump = math.hypot(enemy_pos[0] - track["pos"][0], enemy_pos[1] - track["pos"][1])
            if jump > 150.0:
                track["velocity"] = (0.0, 0.0)
            else:
                inst_vx = (enemy_pos[0] - track["pos"][0]) / dt
                inst_vy = (enemy_pos[1] - track["pos"][1]) / dt
                alpha = 0.35
                old_vx, old_vy = track["velocity"]
                track["velocity"] = (
                    old_vx * (1.0 - alpha) + inst_vx * alpha,
                    old_vy * (1.0 - alpha) + inst_vy * alpha,
                )

        track["pos"] = enemy_pos
        track["ts"] = now
        self._combat_target = {
            "pos": enemy_pos,
            "distance": float(enemy_distance),
            "player_pos": player_pos,
            "brawler": brawler,
        }

    def _try_lead_aim_attack(self) -> bool:
        if not config_bool(getattr(self, "smart_aim_enabled", "yes"), True):
            return False
        if self._holding_attack():
            return False
        target = getattr(self, "_combat_target", None) or {}
        player_pos = target.get("player_pos")
        enemy_pos = target.get("pos")
        if not player_pos or not enemy_pos:
            return False

        vx, vy = self.get_tracked_enemy_velocity()
        speed = math.hypot(vx, vy)
        if speed < 80.0:
            return False

        brawler = str(target.get("brawler") or self.current_brawler or "")
        _, attack_range, _ = self.get_brawler_range(brawler) if brawler else (0, 0, 0)
        if attack_range and float(target.get("distance", 0) or 0) > attack_range * 1.1:
            return False

        projectile_speed = float(getattr(self, "projectile_speed_px_s", 1200.0) or 1200.0)
        scale = float(getattr(self.window_controller, "scale_factor", 1.0) or 1.0)
        angle = self.lead_shot_angle(
            player_pos,
            enemy_pos,
            (vx, vy),
            projectile_speed_px_s=projectile_speed * scale,
        )
        if not hasattr(self.window_controller, "aim_attack_angle"):
            return False
        self.window_controller.aim_attack_angle(angle, radius=170.0, duration=0.04)
        return True

    def use_hypercharge(self):
        self._log_combat_action("hypercharge")
        self.window_controller.press("hypercharge")
        self.time_since_hypercharge_checked = time.time()
        self.is_hypercharge_ready = False

    def use_gadget(self):
        if self.gadget_cooldown > 0:
            current_time = time.time()
            if current_time - self.last_gadget_time < self.gadget_cooldown:
                return False
            self.last_gadget_time = current_time
        self._log_combat_action("gadget")
        if hasattr(self.window_controller, "press"):
            self.window_controller.press("gadget", delay=0.035)
        else:
            self.window_controller.press_key("G", delay=0.035)
        self.time_since_gadget_checked = time.time()
        self.is_gadget_ready = False
        self._gadget_ready_seen_at = 0.0
        return True

    def use_super(self):
        if self.super_cooldown > 0:
            current_time = time.time()
            if current_time - self.last_super_time < self.super_cooldown:
                return False
            self.last_super_time = current_time
        self._log_combat_action("super")
        if hasattr(self.window_controller, "press"):
            self.window_controller.press("super", delay=0.035)
        else:
            self.window_controller.press_key("E", delay=0.035)
        self.time_since_super_checked = time.time()
        self.is_super_ready = False
        self._super_ready_seen_at = 0.0
        return True

    @staticmethod
    def get_random_movement():
        random_movement = random.randint(-75, 75), random.randint(-75, 75)
        return random_movement

    @staticmethod
    def movement_to_vector(movement):
        if not isinstance(movement, (tuple, list)) or len(movement) != 2:
            return None

        x, y = movement
        if x is None or y is None:
            return None

        try:
            return float(x), float(y)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def rotate_movement(movement, angle_radians):
        x, y = movement
        cos_angle = math.cos(angle_radians)
        sin_angle = math.sin(angle_radians)
        return (
            x * cos_angle - y * sin_angle,
            x * sin_angle + y * cos_angle,
        )

    @staticmethod
    def movement_direction_key(movement):
        x, y = movement
        magnitude = math.hypot(x, y)
        if magnitude < 1:
            return None

        angle = math.atan2(y, x)
        return round(angle / (math.pi / 8)) % 16

    def _wslog(self, *args):
        if not self.wall_stuck_debug:
            return
        try:
            import runtime_log
            runtime_log.log_debug("movement", " ".join(str(arg) for arg in args))
        except Exception:
            print("[WS]", *args)

    def _wall_centers_filtered(self, walls, player_pos):
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
        if prev_centers is None or len(prev_centers) < self.wall_stuck_min_walls:
            return None
        if len(curr_centers) < self.wall_stuck_min_walls:
            return None
        diffs = prev_centers[:, None, :] - curr_centers[None, :, :]
        d2 = (diffs * diffs).sum(axis=2)
        nearest = np.sqrt(d2.min(axis=1))
        return float(nearest.mean())

    def detect_wall_stuck(self, walls, player_pos, is_trying_to_move, current_time):
        if not self.wall_stuck_enabled or player_pos is None:
            return False
        state = self.wall_stuck_state
        if current_time - state["last_sample_time"] < self.wall_stuck_sample_interval:
            if state["stationary_since"] is None or not is_trying_to_move:
                return False
            return (current_time - state["stationary_since"]) >= self.wall_stuck_timeout

        curr_centers = self._wall_centers_filtered(walls, player_pos)
        shift = self._avg_wall_shift(state["last_wall_centers"], curr_centers)
        state["last_wall_centers"] = curr_centers
        state["last_sample_time"] = current_time

        if shift is None:
            state["stationary_since"] = None
            return False

        if shift < self.wall_stuck_shift_threshold:
            if state["stationary_since"] is None:
                state["stationary_since"] = current_time
            self._wslog(
                f"walls shift={shift:.2f}px, stationary for "
                f"{current_time - state['stationary_since']:.2f}s "
                f"(trying_to_move={is_trying_to_move})"
            )
        elif state["stationary_since"] is not None:
            self._wslog(f"walls moved again: shift={shift:.2f}px, resetting timer")
            state["stationary_since"] = None

        if state["stationary_since"] is None or not is_trying_to_move:
            return False
        return (current_time - state["stationary_since"]) >= self.wall_stuck_timeout

    def _reset_wall_stuck_state(self, current_time):
        self.wall_stuck_state["stationary_since"] = None
        self.wall_stuck_state["last_wall_centers"] = None
        self.wall_stuck_state["last_sample_time"] = current_time

    def start_semicircle_escape(self, angle, current_time):
        side = self._next_arc_side
        self._next_arc_side = -side
        self.escape_state["phase"] = "retreat"
        self.escape_state["started_at"] = current_time
        self.escape_state["retreat_angle"] = self.angle_opposite(angle)
        self.escape_state["arc_side"] = side
        self._wslog(
            f"semicircle escape START: angle={angle:.1f}° "
            f"retreat={self.escape_state['retreat_angle']:.1f}° "
            f"side={'CCW' if side > 0 else 'CW'}"
        )

    def semicircle_escape_step(self, current_time):
        state = self.escape_state
        phase = state["phase"]
        if phase is None:
            return None
        elapsed = current_time - state["started_at"]

        if phase == "retreat":
            if elapsed < self.escape_retreat_duration:
                return state["retreat_angle"]
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
            t = elapsed / self.escape_arc_duration
            sweep = self.escape_arc_degrees * t * state["arc_side"]
            return (state["retreat_angle"] + sweep) % 360

        return None

    def _build_trusted_fog_mask(self, frame, roi_center, roi_radius):
        if frame is None or not hasattr(frame, "shape"):
            return None

        roi_radius = int(max(1, roi_radius))
        cache_key = (id(frame), int(roi_center[0]), int(roi_center[1]), int(roi_radius))
        if getattr(self, "_fog_mask_cache_frame_id", None) == cache_key:
            return getattr(self, "_fog_mask_cache_value", None)

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
        r = self.fog_flee_distance
        built = self._build_trusted_fog_mask(frame, roi_center=player_position, roi_radius=r)
        if built is None:
            return None
        mask, (ox, oy) = built

        px, py = int(player_position[0]), int(player_position[1])
        ys, xs = np.nonzero(mask)
        if xs.size == 0:
            return None

        dx_all = (xs + ox) - px
        dy_all = (ys + oy) - py
        dist_sq = dx_all * dx_all + dy_all * dy_all
        inside = dist_sq <= r * r
        count = int(inside.sum())
        if count < self.fog_min_pixels_in_radius:
            return None

        cx = float(dx_all[inside].mean())
        cy = float(dy_all[inside].mean())
        if math.hypot(cx, cy) < 1:
            return None
        toward_fog = self.angle_from_direction(cx, cy)
        return self.angle_opposite(toward_fog)

    def detect_fog_direction_escape(self, frame, player_position):
        r = int(max(self.fog_flee_distance, 120))
        built = self._build_trusted_fog_mask(frame, roi_center=player_position, roi_radius=r)
        if built is None:
            return None
        mask, (ox, oy) = built

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

        return self.angle_from_direction(escape_x, escape_y)

    def _refresh_fog_cache(self, frame, player_position):
        if frame is None or player_position is None:
            self._fog_threat_cached = None
            self._fog_direction_escape_cached = None
            return
        self._fog_threat_cached = self.detect_fog_threat(frame, player_position)
        self._fog_direction_escape_cached = self.detect_fog_direction_escape(frame, player_position)

    def angle_points_into_fog(self, frame, player_position, angle_degrees, lookahead=None):
        if frame is None or player_position is None or angle_degrees is None:
            return False
        fog_flee_distance = float(getattr(self, "fog_flee_distance", 130))
        r = int(max(140, lookahead or fog_flee_distance * 1.7))
        built = self._build_trusted_fog_mask(frame, roi_center=player_position, roi_radius=r)
        if built is None:
            return False
        mask, (ox, oy) = built

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
        return count >= min_pixels

    def _poison_gas_in_direction(self, direction, player_data):
        frame = self._get_active_frame()
        if frame is None or player_data is None:
            return False
        player_pos = self.get_player_pos(player_data)
        r = int(max(80, min(self.fog_flee_distance, 150)))
        built = self._build_trusted_fog_mask(frame, roi_center=player_pos, roi_radius=r)
        if built is None:
            return False
        mask, (ox, oy) = built
        ys, xs = np.nonzero(mask)
        if xs.size == 0:
            return False

        px, py = player_pos
        dx = (xs + ox) - px
        dy = (ys + oy) - py
        band = max(30, int(r * 0.45))
        min_pixels = max(12, int(self.fog_min_pixels_in_radius * 0.45))
        direction = str(direction).lower()
        _, _, foot_radius = self.get_player_foot_circle(player_data)
        dist_sq = dx * dx + dy * dy
        player_area = dist_sq <= (foot_radius * foot_radius)
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

    def unstuck_movement_if_needed(self, movement, current_time=None):
        if current_time is None:
            current_time = time.time()

        movement_vector = self.movement_to_vector(movement)
        if movement_vector is None:
            self.fix_movement_keys["toggled"] = False
            self.fix_movement_keys["last_direction_key"] = None
            self.fix_movement_keys["rotation_sign"] = 1
            self.fix_movement_keys["rotation_angle_step"] = 1
            self.time_since_different_movement = current_time
            return movement

        direction_key = self.movement_direction_key(movement_vector)
        if direction_key is None:
            self.fix_movement_keys["toggled"] = False
            self.fix_movement_keys["last_direction_key"] = None
            self.fix_movement_keys["rotation_sign"] = 1
            self.fix_movement_keys["rotation_angle_step"] = 1
            self.time_since_different_movement = current_time
            return movement_vector

        if self.fix_movement_keys['toggled']:
            if current_time - self.fix_movement_keys['started_at'] > self.fix_movement_keys['duration']:
                self.fix_movement_keys['toggled'] = False
                self.fix_movement_keys["last_direction_key"] = direction_key
                self.time_since_different_movement = current_time
                return movement_vector

            return self.fix_movement_keys['fixed']

        if self.fix_movement_keys["last_direction_key"] != direction_key:
            self.fix_movement_keys["last_direction_key"] = direction_key
            self.fix_movement_keys["rotation_sign"] = 1
            self.fix_movement_keys["rotation_angle_step"] = 1
            self.time_since_different_movement = current_time

        if current_time - self.time_since_different_movement > self.fix_movement_keys["delay_to_trigger"]:
            self.fix_movement_keys["rotation_sign"] *= -1
            angle_step = self.fix_movement_keys["rotation_angle_step"]
            rotated_movement = self.rotate_movement(
                movement_vector,
                self.fix_movement_keys["rotation_sign"] * angle_step * math.pi / 4
            )
            if self.fix_movement_keys["rotation_sign"] > 0:
                self.fix_movement_keys["rotation_angle_step"] += 1
                if self.fix_movement_keys["rotation_angle_step"] > self.fix_movement_keys["max_rotation_angle_step"]:
                    self.fix_movement_keys["rotation_angle_step"] = 1

            self.fix_movement_keys['fixed'] = rotated_movement
            self.fix_movement_keys['toggled'] = True
            self.fix_movement_keys['started_at'] = current_time
            return rotated_movement

        return movement_vector

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
        brawler = resolve_brawler_info_key(brawler, brawlers_info)
        if skill_type == "attack":
            return brawlers_info[brawler]['ignore_walls_for_attacks']
        elif skill_type == "super":
            return brawlers_info[brawler]['ignore_walls_for_supers']
        raise ValueError("skill_type must be either 'attack' or 'super'")

    @staticmethod
    def must_brawler_hold_attack(brawler, brawlers_info=None):
        if not brawlers_info: brawlers_info = load_brawlers_info()
        brawler = resolve_brawler_info_key(brawler, brawlers_info)
        return brawlers_info[brawler]['hold_attack'] > 0

    @staticmethod
    def walls_block_line_of_sight(p1, p2, walls):
        if not walls:
            return False

        p1_t = (int(p1[0]), int(p1[1]))
        p2_t = (int(p2[0]), int(p2[1]))
        min_x, max_x = min(p1_t[0], p2_t[0]), max(p1_t[0], p2_t[0])
        min_y, max_y = min(p1_t[1], p2_t[1]), max(p1_t[1], p2_t[1])
        for wall in walls:
            x1, y1, x2, y2 = wall

            if max_x < x1 or min_x > x2 or max_y < y1 or min_y > y2:
                continue

            rect = (int(x1), int(y1), int(x2 - x1), int(y2 - y1))
            if cv2.clipLine(rect, p1_t, p2_t)[0]:
                return True
        return False

    def get_player_hit_circle(self, player_box):
        radius = PLAYER_HIT_CIRCLE_RADIUS * (self.window_controller.scale_factor or 1)
        if player_box and len(player_box) >= 4:
            x1, y1, x2, y2 = player_box[:4]
            return ((x1 + x2) / 2, y2 - radius), radius

        return None, radius

    def get_actual_player_box(self, player_box):
        center, radius = self.get_player_hit_circle(player_box)
        if center is None:
            return None
        return [
            center[0] - radius,
            center[1] - radius,
            center[0] + radius,
            center[1] + radius,
        ]

    @staticmethod
    def point_rect_distance_sq(point, rect):
        x, y = point
        x1, y1, x2, y2 = rect
        dx = max(x1 - x, 0, x - x2)
        dy = max(y1 - y, 0, y - y2)
        return dx * dx + dy * dy

    @staticmethod
    def walls_block_swept_circle(p1, p2, radius, walls):
        if not walls:
            return False

        p1_t = (int(p1[0]), int(p1[1]))
        p2_t = (int(p2[0]), int(p2[1]))
        min_x, max_x = min(p1_t[0], p2_t[0]), max(p1_t[0], p2_t[0])
        min_y, max_y = min(p1_t[1], p2_t[1]), max(p1_t[1], p2_t[1])
        radius = int(math.ceil(radius))

        for wall in walls:
            x1, y1, x2, y2 = wall[:4]
            wall_rect = (x1, y1, x2, y2)
            expanded_x1 = int(x1 - radius)
            expanded_y1 = int(y1 - radius)
            expanded_x2 = int(x2 + radius)
            expanded_y2 = int(y2 + radius)

            if max_x < expanded_x1 or min_x > expanded_x2 or max_y < expanded_y1 or min_y > expanded_y2:
                continue

            rect = (
                expanded_x1,
                expanded_y1,
                max(1, expanded_x2 - expanded_x1),
                max(1, expanded_y2 - expanded_y1),
            )
            if cv2.clipLine(rect, p1_t, p2_t)[0]:
                radius_sq = radius * radius
                start_distance_sq = Play.point_rect_distance_sq(p1, wall_rect)
                end_distance_sq = Play.point_rect_distance_sq(p2, wall_rect)
                if start_distance_sq <= radius_sq and end_distance_sq > start_distance_sq:
                    continue
                return True

        return False

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
            enemy_pos = self.get_entity_pos(enemy)
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

    def find_closest_teammate(self, teammate_data, player_coords, walls):
        closest_distance = float('inf')
        closest_teammate = None
        for teammate in teammate_data:
            teammate_pos = self.get_entity_pos(teammate)
            distance = self.get_distance(teammate_pos, player_coords)
            if distance < closest_distance:
                closest_distance = distance
                closest_teammate = teammate_pos
        return closest_teammate, closest_distance

    def is_there_poison_gas(self, arg1, arg2=10000):
        if isinstance(arg1, str):
            return self._poison_gas_in_direction(arg1, arg2)
        player_data = arg1
        threshold = arg2 if isinstance(arg2, (int, float)) else 10000
        frame = self._get_active_frame()
        if frame is None:
            return {"up": 0, "down": 0, "left": 0, "right": 0}
        actual_player_box = self.get_actual_player_box(player_data) or player_data
        px1, py1, px2, py2 = actual_player_box
        player_width = max(px2 - px1, 1)
        player_height = max(py2 - py1, 1)
        min_x = int(max(px1 - player_width, 0))
        max_x = int(min(px2 + player_width, self.window_controller.width))
        min_y = int(max(py1 - player_height, 0))
        max_y = int(min(py2 + player_height, self.window_controller.height))

        if min_x >= max_x or min_y >= max_y:
            return {
                "up": 0,
                "down": 0,
                "left": 0,
                "right": 0,
            }

        roi = frame[min_y:max_y, min_x:max_x]
        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)

        mask = cv2.inRange(hsv_roi, POISON_LOW_HSV, POISON_HIGH_HSV)
        x, y = self.get_player_pos(player_data)
        roi_w = int(max_x - min_x)
        roi_h = int(max_y - min_y)
        local_px = int(clamp(x - min_x, 0, roi_w))
        local_py = int(clamp(y - min_y, 0, roi_h))

        counts = {
            "up": count_mask_pixels(mask, 0, 0, roi_w, local_py),
            "down": count_mask_pixels(mask, 0, local_py, roi_w, roi_h),
            "left": count_mask_pixels(mask, 0, 0, local_px, roi_h),
            "right": count_mask_pixels(mask, local_px, 0, roi_w, roi_h),
        }

        result = {
            direction: count if count > threshold else 0
            for direction, count in counts.items()
        }

        if self.verbose_debug:
            print("Poison gas pixels:", counts)

            ts = int(time.time())

            debug_regions = {
                "up": roi[0:local_py, 0:roi_w],
                "down": roi[local_py:roi_h, 0:roi_w],
                "left": roi[0:roi_h, 0:local_px],
                "right": roi[0:roi_h, local_px:roi_w],
            }

            for direction, img in debug_regions.items():
                if img.size > 0:
                    cv2.imwrite(
                        os.path.join(DEBUG_FRAMES_DIR, f"poison_gas_{direction}_debug_{ts}.png"),
                        cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                    )

        return result

    def get_main_data(self, frame):
        data = self.Detect_main_info.detect_objects(frame, conf_tresh=self.entity_detection_confidence)
        return data

    def is_path_blocked(self, player_box, move_direction, walls, distance=None):
        if distance is None:
            distance = self.TILE_SIZE*self.window_controller.scale_factor
        movement = self.movement_to_vector(move_direction)
        if movement is None:
            return False

        magnitude = math.hypot(movement[0], movement[1])
        if magnitude < 1:
            return False

        dx = movement[0] / magnitude * distance
        dy = movement[1] / magnitude * distance
        foot_x, foot_y, foot_radius = self.get_player_foot_circle(player_box)
        foot_center = (foot_x, foot_y)
        padding = float(load_toml_as_dict("cfg/bot_config.toml").get("wall_path_padding", 0) or 0)
        radius = foot_radius + padding
        probe_tiles = float(load_toml_as_dict("cfg/bot_config.toml").get("wall_path_probe_tiles", 1.0) or 1.0)
        probes = (distance * 0.5, distance, distance * max(1.0, probe_tiles))
        for probe_distance in probes:
            scale = probe_distance / max(distance, 1e-6)
            probe_pos = (
                foot_center[0] + dx * scale,
                foot_center[1] + dy * scale,
            )
            if self.walls_block_swept_circle(foot_center, probe_pos, radius, walls):
                return True
        return False

    def find_best_angle(self, player_box, desired_vector, walls, sweep_steps=16):
        movement = self.movement_to_vector(desired_vector)
        if movement is None:
            return desired_vector
        if not self.is_path_blocked(player_box, desired_vector, walls):
            return desired_vector
        base_angle = math.atan2(movement[1], movement[0])
        for step in range(1, sweep_steps + 1):
            for sign in (1, -1):
                angle = base_angle + sign * step * (math.pi / sweep_steps)
                candidate = (math.cos(angle) * JOYSTICK_RADIUS, math.sin(angle) * JOYSTICK_RADIUS)
                if not self.is_path_blocked(player_box, candidate, walls):
                    return candidate
        return desired_vector

    def is_path_blocked_angle(self, player_arg, angle_degrees, walls, distance=None):
        if (
            isinstance(player_arg, (list, tuple))
            and len(player_arg) >= 4
            and not isinstance(player_arg[0], (list, tuple, np.ndarray))
        ):
            return self.is_path_blocked(
                player_arg,
                self.vector_from_angle(angle_degrees),
                walls,
                distance=distance,
            )
        if distance is None:
            distance = self.TILE_SIZE * self.window_controller.scale_factor
        foot_x, foot_y = float(player_arg[0]), float(player_arg[1])
        foot_radius = 4.0
        foot_center = (foot_x, foot_y)
        padding = float(load_toml_as_dict("cfg/bot_config.toml").get("wall_path_padding", 0) or 0)
        radius = foot_radius + padding
        angle_rad = math.radians(angle_degrees)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        probe_tiles = float(load_toml_as_dict("cfg/bot_config.toml").get("wall_path_probe_tiles", 1.0) or 1.0)
        probes = (distance * 0.5, distance, distance * max(1.0, probe_tiles))
        for probe_distance in probes:
            probe_pos = (
                foot_center[0] + cos_a * probe_distance,
                foot_center[1] + sin_a * probe_distance,
            )
            if self.walls_block_swept_circle(foot_center, probe_pos, radius, walls):
                return True
        return False

    @staticmethod
    def validate_game_data(data):
        incomplete = False
        if "player" not in data.keys():
            incomplete = True  # This is required so track_no_detections can also keep track if enemy is missing

        if "enemy" not in data.keys():
            data['enemy'] = []

        if "teammate" not in data.keys():
            data['teammate'] = []

        if 'wall' not in data.keys() or not data['wall']:
            data['wall'] = []

        if 'bushes' not in data.keys() or not data['bushes']:
            data['bushes'] = []

        return False if incomplete else data

    def track_no_detections(self, data):
        if not data:
            data = {
                "enemy": None,
                "player": None
            }
        for key in self.time_since_detections:
            if key in data and data[key]:
                self.time_since_detections[key] = time.time()

    def do_movement(self, movement):
        movement_vector = self.movement_to_vector(movement)
        if movement_vector is None:
            self.window_controller.release_movement()
            return
        self.window_controller.move(*movement_vector)

    def get_brawler_range(self, brawler):
        if self.brawler_ranges is None:
            self.brawler_ranges = self.load_brawler_ranges(self.brawlers_info)
        if brawler in self.brawler_ranges:
            return self.brawler_ranges[brawler]
        resolved = resolve_brawler_info_key(brawler, self.brawlers_info)
        if resolved in self.brawler_ranges:
            return self.brawler_ranges[resolved]
        return self.brawler_ranges[brawler]

    def refresh_enemy_spacing_config(self):
        bot_config = load_toml_as_dict("cfg/bot_config.toml")
        self.enemy_spacing_enabled = config_bool(bot_config.get("enemy_spacing_enabled"), True)
        self.enemy_spacing_blend = float(bot_config.get("enemy_spacing_blend", 0.35))
        self.enemy_spacing_tolerance = float(bot_config.get("enemy_spacing_tolerance", 40))
        hold_strafe = bot_config.get("enemy_spacing_hold_strafe")
        if hold_strafe is None:
            hold_strafe = bot_config.get("strafe_while_attacking", "yes")
        self.enemy_spacing_hold_strafe = config_bool(hold_strafe, True)
        self.combat_los_dodge_enabled = config_bool(bot_config.get("combat_los_dodge_enabled"), True)
        self.combat_dodge_blend = float(bot_config.get("combat_dodge_blend", 0.45))
        self.combat_dodge_jitter_degrees = float(bot_config.get("combat_dodge_jitter_degrees", 18.0))
        self.combat_dodge_commit_seconds = float(bot_config.get("combat_dodge_commit_seconds", 0.6))
        self.strafe_interval = float(bot_config.get("strafe_interval", 1.5))
        self.attack_min_interval = float(bot_config.get("attack_min_interval", 0.35))
        smart_aim = bot_config.get("smart_aim_enabled")
        if smart_aim is None:
            smart_aim = bot_config.get("lead_shots", "yes")
        self.smart_aim_enabled = smart_aim
        projectile_speed = bot_config.get("projectile_speed_px_s")
        self.projectile_speed_px_s = float(projectile_speed if projectile_speed is not None else 1200.0)

    def _clear_dodge_commitment(self, *, flip_side: bool = False) -> None:
        if flip_side:
            self._dodge_side = -int(getattr(self, "_dodge_side", 1) or 1)
        self._dodge_committed_until = 0.0
        self._dodge_vector = None
        self._dodge_jitter_rad = 0.0

    def _dodge_is_committed(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return bool(self._dodge_vector) and float(getattr(self, "_dodge_committed_until", 0) or 0) > now

    def _scale_movement_vector(self, vector):
        magnitude = math.hypot(vector[0], vector[1])
        if magnitude < 1:
            return None
        scale = min(JOYSTICK_RADIUS, magnitude) / magnitude
        return (vector[0] * scale, vector[1] * scale)

    def _compute_dodge_vector(self, player_pos, enemy_coords, side: int):
        direction_x = enemy_coords[0] - player_pos[0]
        direction_y = enemy_coords[1] - player_pos[1]
        toward_angle = math.atan2(direction_y, direction_x)
        dodge_angle = toward_angle + int(side) * (math.pi / 2) + float(getattr(self, "_dodge_jitter_rad", 0.0) or 0.0)
        return self._scale_movement_vector((
            math.cos(dodge_angle) * JOYSTICK_RADIUS,
            math.sin(dodge_angle) * JOYSTICK_RADIUS,
        ))

    def _start_dodge_commitment(self, player_data, player_pos, enemy_coords, walls, *, flip_side: bool = True):
        now = time.time()
        if flip_side:
            self._dodge_side = -int(getattr(self, "_dodge_side", 1) or 1)
        jitter_degrees = float(getattr(self, "combat_dodge_jitter_degrees", 18.0))
        self._dodge_jitter_rad = math.radians(random.uniform(-jitter_degrees, jitter_degrees))

        for side in (self._dodge_side, -self._dodge_side):
            dodge_vector = self._compute_dodge_vector(player_pos, enemy_coords, side)
            if dodge_vector and not self.is_path_blocked(player_data, dodge_vector, walls):
                self._dodge_side = side
                self._dodge_vector = dodge_vector
                self._dodge_committed_until = now + float(getattr(self, "combat_dodge_commit_seconds", 0.6) or 0.6)
                self._evasion_active = True
                self._spacing_action = "dodge"
                return dodge_vector
        self._clear_dodge_commitment()
        return None

    def apply_los_evasion_movement(self, brawler, data, movement):
        self._evasion_active = False
        if not getattr(self, "combat_los_dodge_enabled", True):
            self._clear_dodge_commitment()
            return movement
        if not data or not data.get("player"):
            self._clear_dodge_commitment()
            return movement

        base = self.movement_to_vector(movement)
        if base is None:
            self._clear_dodge_commitment()
            return movement

        player_data = data["player"][0]
        player_pos = self.get_player_pos(player_data)
        walls = data.get("wall") or []
        enemies = data.get("enemy") or []
        if not self.is_there_enemy(enemies):
            self._clear_dodge_commitment()
            return movement

        enemy_result = self.find_closest_enemy(enemies, player_pos, walls, "attack")
        if not enemy_result:
            self._clear_dodge_commitment()
            return movement
        enemy_coords, _enemy_distance = enemy_result
        if not self.is_enemy_hittable(player_pos, enemy_coords, walls, "attack"):
            self._clear_dodge_commitment(flip_side=True)
            return movement

        blend = clamp(float(getattr(self, "combat_dodge_blend", 0.45)), 0.0, 1.0)
        if blend <= 0:
            self._clear_dodge_commitment()
            return movement

        now = time.time()
        if self._dodge_is_committed(now):
            committed = self._dodge_vector
            if committed and not self.is_path_blocked(player_data, committed, walls):
                self._evasion_active = True
                self._spacing_action = "dodge"
                return committed
            recommitted = self._start_dodge_commitment(
                player_data,
                player_pos,
                enemy_coords,
                walls,
                flip_side=True,
            )
            if recommitted:
                return recommitted
            return movement

        dodge_vector = self._start_dodge_commitment(
            player_data,
            player_pos,
            enemy_coords,
            walls,
            flip_side=True,
        )
        if dodge_vector:
            return dodge_vector
        return movement

    def get_effective_enemy_range(self, brawler):
        safe_range, attack_range, _ = self.get_brawler_range(brawler)
        if not getattr(self, "enemy_spacing_enabled", True):
            return safe_range
        blend = clamp(float(getattr(self, "enemy_spacing_blend", 0.35)), 0.0, 1.0)
        return int(safe_range + (attack_range - safe_range) * blend)

    @staticmethod
    def get_enemy_spacing_action(enemy_distance, target, tolerance):
        if enemy_distance > target + tolerance:
            return "approach"
        if enemy_distance < target - tolerance:
            return "retreat"
        return "hold"

    def _maybe_flip_strafe_side(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        interval = float(getattr(self, "strafe_interval", 1.5) or 1.5)
        last_flip = float(getattr(self, "_spacing_strafe_last_flip_at", 0.0) or 0.0)
        if now - last_flip >= interval:
            self._spacing_strafe_side = -int(getattr(self, "_spacing_strafe_side", 1) or 1)
            self._spacing_strafe_last_flip_at = now

    def _hold_strafe_vector(self, norm_x, norm_y):
        strafe_side = int(getattr(self, "_spacing_strafe_side", 1) or 1)
        return (-norm_y * JOYSTICK_RADIUS * strafe_side, norm_x * JOYSTICK_RADIUS * strafe_side)

    def get_enemy_spacing_movement(self, player_data, player_pos, enemy_coords, enemy_distance, brawler, walls):
        safe_range, _, _ = self.get_brawler_range(brawler)
        if getattr(self, "enemy_spacing_enabled", True):
            target = self.get_effective_enemy_range(brawler)
            tolerance = float(getattr(self, "enemy_spacing_tolerance", 40))
            action = self.get_enemy_spacing_action(enemy_distance, target, tolerance)
        else:
            action = "approach" if enemy_distance > safe_range else "retreat"
        self._spacing_action = action

        toward_x = enemy_coords[0] - player_pos[0]
        toward_y = enemy_coords[1] - player_pos[1]
        vx, vy = self.get_tracked_enemy_velocity()

        if action == "approach":
            direction_x = toward_x
            direction_y = toward_y
        elif action == "retreat":
            direction_x = -toward_x
            direction_y = -toward_y
            if math.hypot(vx, vy) > 1.0:
                direction_x -= vx * 0.35
                direction_y -= vy * 0.35
        else:
            direction_x = toward_x
            direction_y = toward_y

        magnitude = math.hypot(direction_x, direction_y)
        if magnitude < 1:
            magnitude = 1.0
        norm_x = direction_x / magnitude
        norm_y = direction_y / magnitude

        if action == "approach":
            move_diagonal = (direction_x, direction_y)
            move_horizontal = (direction_x, 0)
            move_vertical = (0, direction_y)
        elif action == "retreat":
            move_diagonal = (direction_x, direction_y)
            move_horizontal = (direction_x, 0)
            move_vertical = (0, direction_y)
        else:
            self._maybe_flip_strafe_side()
            if getattr(self, "enemy_spacing_hold_strafe", True):
                strafe_side = getattr(self, "_spacing_strafe_side", 1)
                strafe = self._hold_strafe_vector(norm_x, norm_y)
                if not self.is_path_blocked(player_data, strafe, walls):
                    self._spacing_action = "hold_strafe"
                    return strafe
                flipped = (-strafe[0], -strafe[1])
                if not self.is_path_blocked(player_data, flipped, walls):
                    self._spacing_strafe_side = -strafe_side
                    self._spacing_action = "hold_strafe"
                    return flipped
            self._spacing_action = "hold"
            return self._hold_strafe_vector(norm_x, norm_y)

        movement_options = [move_diagonal, move_vertical, move_horizontal]
        for move in movement_options:
            if not self.is_path_blocked(player_data, move, walls):
                return move

        alternative_moves = [
            (0, -JOYSTICK_RADIUS),
            (-JOYSTICK_RADIUS, 0),
            (0, JOYSTICK_RADIUS),
            (JOYSTICK_RADIUS, 0),
        ]
        random.shuffle(alternative_moves)
        for move in alternative_moves:
            if not self.is_path_blocked(player_data, move, walls):
                return move
        return move_diagonal

    def release_held_attack_for_super(self):
        persistent = getattr(self, "persistent_data", None)
        if not isinstance(persistent, dict) or persistent.get("time_since_holding_attack") is None:
            return
        self.attack(touch_up=True, touch_down=False)
        persistent["time_since_holding_attack"] = None

    def _holding_attack(self):
        persistent = getattr(self, "persistent_data", None) or {}
        return persistent.get("time_since_holding_attack") is not None

    def try_use_super_on_enemy(self, brawler, brawler_info, player_pos, enemy_coords, enemy_distance, walls):
        if not self.is_super_ready:
            return False
        super_type = brawler_info["super_type"]
        _, attack_range, super_range = self.get_brawler_range(brawler)
        enemy_hittable = self.is_enemy_hittable(player_pos, enemy_coords, walls, "super")
        should_fire = self.should_use_super_on_enemy(
            brawler, super_type, enemy_distance, attack_range, super_range, enemy_hittable
        )
        if not should_fire:
            try:
                import runtime_log
                runtime_log.log_once(
                    f"combat:super-skip:{brawler}",
                    2.0,
                    runtime_log.LEVEL_INFO,
                    "combat",
                    f"Super ready but waiting ({int(enemy_distance)}px, hittable={enemy_hittable})",
                )
            except ImportError:
                pass
            return False
        self.release_held_attack_for_super()
        if self.is_hypercharge_ready:
            self.use_hypercharge()
            self.time_since_hypercharge_checked = time.time()
            self.is_hypercharge_ready = False
        return self.use_super()

    def should_use_gadget_on_enemy(self, brawler, player_data, enemy_data, walls):
        if not self.should_use_gadget or not self.is_gadget_ready:
            return False
        if self._holding_attack():
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
            for enemy in enemy_data
            if self.get_distance(self.get_entity_pos(enemy), player_pos) <= attack_range
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

    def try_use_ready_abilities_when_enemy_visible(self, enemy_data):
        return False

    def refresh_ready_abilities(self, frame, current_time):
        if current_time - self.time_since_hypercharge_checked > self.hypercharge_treshold:
            self.is_hypercharge_ready = self.check_if_hypercharge_ready(frame)
            self.time_since_hypercharge_checked = current_time
        if current_time - self.time_since_gadget_checked > self.gadget_treshold:
            self.is_gadget_ready = self.check_if_gadget_ready(frame)
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

    @staticmethod
    def should_use_super_on_enemy(brawler, super_type, enemy_distance, attack_range, super_range, enemy_hittable):
        if not enemy_hittable:
            return False
        if super_type in ("spawnable", "other"):
            return True
        if brawler in ("stu", "surge") and super_type == "charge":
            return enemy_distance <= super_range + attack_range
        if enemy_distance <= super_range:
            return True
        if super_type == "damage":
            return enemy_distance <= attack_range * 0.75
        return enemy_distance <= super_range

    def _update_match_intent(self, brawler, data) -> None:
        try:
            import runtime_log
        except ImportError:
            return

        if not data or not data.get("player"):
            self.match_intent_summary = ""
            return

        player_pos = self.get_player_pos(data["player"][0])
        enemies = data.get("enemy") or []
        teammates = data.get("teammate") or []
        walls = data.get("wall") or []

        if not self.is_there_enemy(enemies):
            teammate_pos, teammate_dist = self.find_closest_teammate(teammates, player_pos, walls)
            if teammate_pos:
                intent = f"No enemies visible — following teammate ({int(teammate_dist)}px away)"
                key = "match:follow"
                self.match_intent_summary = "Following teammate"
            else:
                intent = "No enemies visible — roaming and scanning"
                key = "match:roam"
                self.match_intent_summary = "Roaming"
        else:
            enemy_coords, enemy_distance = self.find_closest_enemy(
                enemies, player_pos, walls, "attack"
            )
            if enemy_coords is None:
                intent = "Enemy detected but unreachable — repositioning"
                key = "match:reposition"
                self.match_intent_summary = "Repositioning"
            else:
                _, attack_range, _ = self.get_brawler_range(brawler)
                target = self.get_effective_enemy_range(brawler)
                action = self._spacing_action or "approach"
                action_labels = {
                    "approach": "Closing in on enemy",
                    "retreat": "Kiting back from enemy",
                    "hold": "Holding spacing",
                    "hold_strafe": "Holding spacing and strafing",
                    "dodge": "Dodging under fire",
                }
                label = action_labels.get(action, "Engaging enemy")
                in_range = enemy_distance <= attack_range
                hittable = self.is_enemy_hittable(player_pos, enemy_coords, walls, "attack")
                dist = int(enemy_distance)
                if getattr(self, "_evasion_active", False) and hittable:
                    intent = f"{label} — enemy has line of sight at {dist}px"
                    self.match_intent_summary = "Dodging"
                    key = "match:dodge"
                elif in_range and hittable:
                    intent = f"{label} — shooting at {dist}px (target {target}px)"
                    self.match_intent_summary = "Shooting"
                elif in_range:
                    intent = f"{label} — in range at {dist}px but line of sight blocked"
                    self.match_intent_summary = "Blocked shot"
                else:
                    intent = f"{label} — {dist}px from enemy (target {target}px)"
                    self.match_intent_summary = label
                if not getattr(self, "_evasion_active", False):
                    key = f"match:{action}:{dist // 40}"

        runtime_log.log_once(key, 2.5, runtime_log.LEVEL_INFO, "match", intent)

    def clamp_movement(self, movement):
        x, y = movement
        target_x = clamp(x, -JOYSTICK_RADIUS*self.window_controller.width_ratio, JOYSTICK_RADIUS*self.window_controller.width_ratio)
        target_y = clamp(y, -JOYSTICK_RADIUS*self.window_controller.height_ratio, JOYSTICK_RADIUS*self.window_controller.height_ratio)
        return target_x, target_y

    def loop(self, brawler, data, current_time):
        self.refresh_enemy_spacing_config()
        self.track_enemy(data, brawler=brawler)
        self.context = {
                'player_data': data['player'][0],
                'enemy_data': data['enemy'],
                'teammate_data': data['teammate'],
                'brawler': brawler,
                'walls': data['wall'],
                'bushes': data['bushes'],
                'brawlers_info': self.brawlers_info,
                'must_brawler_hold_attack': self.must_brawler_hold_attack,
                'is_gadget_ready': self.should_use_gadget and self.is_gadget_ready,
                'is_hypercharge_ready': self.is_hypercharge_ready,
                'is_super_ready': self.is_super_ready,
                'should_use_gadget': self.should_use_gadget,
                'TILE_SIZE': self.TILE_SIZE*self.window_controller.scale_factor,
                'get_entity_pos': self.get_entity_pos,
                'get_distance': self.get_distance,
                'get_actual_player_box': self.get_actual_player_box,
                'get_brawler_range': self.get_brawler_range,
                'get_effective_enemy_range': self.get_effective_enemy_range,
                'get_enemy_spacing_movement': self.get_enemy_spacing_movement,
                'get_player_pos': self.get_player_pos,
                'get_player_foot_circle': self.get_player_foot_circle,
                'should_use_super_on_enemy': self.should_use_super_on_enemy,
                'try_use_super_on_enemy': self.try_use_super_on_enemy,
                'should_use_gadget_on_enemy': self.should_use_gadget_on_enemy,
                'is_there_enemy': self.is_there_enemy,
                'attack': self.attack,
                'use_hypercharge': self.use_hypercharge,
                'use_super': self.use_super,
                'use_gadget': self.use_gadget,
                'get_random_movement': self.get_random_movement,
                'get_tracked_enemy_velocity': self.get_tracked_enemy_velocity,
                'current_brawler': self.current_brawler,
                'last_movement': self.last_movement,
                'last_movement_change_time': self.last_movement_change_time,
                'seconds_to_hold_attack_after_reaching_max': self.seconds_to_hold_attack_after_reaching_max,
                "width": brawl_stars_width,
                "height": brawl_stars_height,
                'find_closest_enemy': self.find_closest_enemy,
                'find_closest_teammate': self.find_closest_teammate,
                'is_there_poison_gas': self.is_there_poison_gas,
                'is_path_blocked': self.is_path_blocked,
                'is_path_blocked_angle': self.is_path_blocked_angle,
                'is_enemy_hittable': self.is_enemy_hittable,
                'time': time,
                'random': random,
                "persistent_data": self.persistent_data,
                'debug': self.verbose_debug,
                'JOYSTICK_RADIUS': JOYSTICK_RADIUS,
                'rotate_movement': self.rotate_movement
            }
        movement = self.get_movement()
        movement = self.apply_los_evasion_movement(brawler, data, movement)
        self._update_match_intent(brawler, data)
        self.current_frame = self.frame
        escape_override = False
        escape_angle = self.semicircle_escape_step(current_time)
        if escape_angle is not None:
            movement = self.vector_from_angle(escape_angle)
            escape_override = True
        elif self.movement_to_vector(movement) is not None:
            if self.is_showdown and data.get("player") and self.frame is not None:
                player_pos = self.get_player_pos(data["player"][0])
                self._fog_check_counter += 1
                if self._fog_check_counter >= self.fog_check_every_n_frames:
                    self._refresh_fog_cache(self.frame, player_pos)
                    self._fog_check_counter = 0
                flee_angle = self._fog_direction_escape_cached
                if flee_angle is None:
                    flee_angle = self._fog_threat_cached
                if flee_angle is not None:
                    movement = self.vector_from_angle(flee_angle)

            if self.escape_state.get("phase") is None and data.get("player"):
                player_pos = self.get_player_pos(data["player"][0])
                walls = data.get("wall") or []
                if self.detect_wall_stuck(walls, player_pos, True, current_time):
                    mv = self.movement_to_vector(movement)
                    angle = self.angle_from_direction(mv[0], mv[1]) if mv else 0.0
                    self.start_semicircle_escape(angle, current_time)
                    self._reset_wall_stuck_state(current_time)
                    esc = self.semicircle_escape_step(current_time)
                    if esc is not None:
                        movement = self.vector_from_angle(esc)
                        escape_override = True

        if self.movement_to_vector(movement) is None:
            self.window_controller.release_movement()
            self.last_movement = ''
            return None
        movement = self.clamp_movement(movement)
        current_time = time.time()
        if not escape_override:
            if movement != self.last_movement:
                if current_time - self.last_movement_change_time >= self.minimum_movement_delay:
                    self.last_movement = movement
                    self.last_movement_change_time = current_time
                else:
                    movement = self.last_movement
            else:
                self.last_movement_change_time = current_time
            movement = self.unstuck_movement_if_needed(movement, current_time)
        else:
            self.last_movement = movement
            self.last_movement_change_time = current_time
        return movement

    def check_if_hypercharge_ready(self, frame):
        wr, hr = self.window_controller.width_ratio, self.window_controller.height_ratio
        x1, y1 = int(hypercharge_crop_area[0] * wr), int(hypercharge_crop_area[1] * hr)
        x2, y2 = int(hypercharge_crop_area[2] * wr), int(hypercharge_crop_area[3] * hr)
        screenshot = frame[y1:y2, x1:x2]
        purple_pixels = count_hsv_pixels(screenshot, (137, 158, 159), (179, 255, 255))
        threshold = self._scaled_pixel_threshold(self.hypercharge_pixels_minimum, screenshot, self.hypercharge_crop_area)
        if getattr(self, "verbose_debug", False):
            print("hypercharge purple pixels:", purple_pixels, "(if > ", threshold, " then hypercharge is ready)")
            cv2.imwrite(os.path.join(DEBUG_FRAMES_DIR, f"hypercharge_debug_{purple_pixels}_{int(time.time())}.png"), cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR))

        return purple_pixels > threshold

    def check_if_gadget_ready(self, frame):
        wr, hr = self.window_controller.width_ratio, self.window_controller.height_ratio
        x1, y1 = int(self.gadget_crop_area[0] * wr), int(self.gadget_crop_area[1] * hr)
        x2, y2 = int(self.gadget_crop_area[2] * wr), int(self.gadget_crop_area[3] * hr)
        screenshot = frame[y1:y2, x1:x2]
        green_pixels = count_hsv_pixels(screenshot, (57, 219, 165), (62, 255, 255))
        threshold = self._scaled_pixel_threshold(self.gadget_pixels_minimum, screenshot, self.gadget_crop_area)
        if getattr(self, "verbose_debug", False):
            print("gadget green pixels:", green_pixels, "(if > ", threshold, " then gadget is ready)")
            cv2.imwrite(os.path.join(DEBUG_FRAMES_DIR, f"gadget_debug_{green_pixels}_{int(time.time())}.png"), cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR))

        return green_pixels > threshold

    def check_if_super_ready(self, frame):
        wr, hr = self.window_controller.width_ratio, self.window_controller.height_ratio
        x1, y1 = int(self.super_crop_area[0] * wr), int(self.super_crop_area[1] * hr)
        x2, y2 = int(self.super_crop_area[2] * wr), int(self.super_crop_area[3] * hr)
        screenshot = frame[y1:y2, x1:x2]
        yellow_pixels = count_hsv_pixels(screenshot, (17, 170, 200), (27, 255, 255))
        orange_pixels = count_hsv_pixels(screenshot, (8, 120, 150), (38, 255, 255))
        threshold = self._scaled_pixel_threshold(self.super_pixels_minimum, screenshot, self.super_crop_area) * 2.0
        if getattr(self, "verbose_debug", False):
            print(
                "super pixels yellow:", yellow_pixels, "orange:", orange_pixels,
                "(if > ", threshold, " then super is ready)",
            )
            cv2.imwrite(os.path.join(DEBUG_FRAMES_DIR, f"super_debug_{yellow_pixels}_{int(time.time())}.png"), cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR))

        if yellow_pixels > threshold:
            return True
        return orange_pixels > threshold * 1.25

    @staticmethod
    def _log_tile_detection_mode(message: str) -> None:
        try:
            import runtime_log
            runtime_log.log_info("startup", message)
        except Exception:
            print(message)

    def _log_tile_detection_event(self, message: str, key: str) -> None:
        try:
            import runtime_log
            runtime_log.log_once(key, 8.0, runtime_log.LEVEL_INFO, "perf", message)
        except Exception:
            print(message)

    def _set_tile_detection_debug(self, source, crop=None, fallback=None):
        self.last_tile_detection_debug = {
            "enabled": bool(self.close_tile_detector_enabled),
            "source": source,
            "crop": list(crop) if crop else None,
            "fallback": fallback,
        }

    @staticmethod
    def crop_close_tile_region(frame, player_pos, crop_size=CLOSE_TILE_CROP_SIZE):
        if frame is None or player_pos is None:
            return None, 0, 0
        height, width = frame.shape[:2]
        if width < crop_size or height < crop_size:
            return None, 0, 0
        center_x, center_y = int(player_pos[0]), int(player_pos[1])
        half = crop_size // 2
        crop_x1 = max(0, min(center_x - half, width - crop_size))
        crop_y1 = max(0, min(center_y - half, height - crop_size))
        crop_x2 = crop_x1 + crop_size
        crop_y2 = crop_y1 + crop_size
        return frame[crop_y1:crop_y2, crop_x1:crop_x2], crop_x1, crop_y1

    def get_centered_wall_crop(self, frame, player_data=None):
        player_pos = self._resolve_player_pos(player_data)
        if player_pos is None:
            frame_height, frame_width = frame.shape[:2]
            player_pos = (frame_width / 2, frame_height / 2)
        crop, crop_x1, crop_y1 = self.crop_close_tile_region(frame, player_pos, self.centered_wall_crop_size)
        if crop is None:
            return frame, 0, 0
        return crop, crop_x1, crop_y1

    @staticmethod
    def _resolve_player_pos(player_data):
        if player_data is None:
            return None
        if (
            isinstance(player_data, (list, tuple))
            and len(player_data) == 2
            and not isinstance(player_data[0], (list, tuple, np.ndarray))
        ):
            return int(player_data[0]), int(player_data[1])
        if isinstance(player_data, (list, tuple)) and player_data:
            first = player_data[0]
            if isinstance(first, (list, tuple, np.ndarray)) and len(first) >= 4:
                return Play.get_player_pos(first)
        return None

    @staticmethod
    def offset_tile_data(tile_data, offset_x, offset_y):
        if not offset_x and not offset_y:
            return tile_data

        offset_data = {}
        for class_name, boxes in tile_data.items():
            offset_data[class_name] = [
                [box[0] + offset_x, box[1] + offset_y, box[2] + offset_x, box[3] + offset_y]
                for box in boxes
            ]
        return offset_data

    offset_tile_boxes = offset_tile_data

    def _detect_tile_data(self, detector, frame, conf_tresh):
        tile_data = detector.detect_objects(frame, conf_tresh=conf_tresh)
        primary_count = sum(len(boxes or []) for boxes in (tile_data or {}).values())
        previous_primary_count = self.last_wall_primary_count
        self.last_wall_primary_count = primary_count
        if (
            primary_count < self.wall_detection_retry_min_objects
            and previous_primary_count < self.wall_detection_retry_min_objects
            and self.wall_detection_retry_confidence < conf_tresh
        ):
            retry_data = detector.detect_objects(
                frame,
                conf_tresh=self.wall_detection_retry_confidence,
            )
            retry_count = sum(len(boxes or []) for boxes in (retry_data or {}).values())
            if retry_count > primary_count:
                tile_data = retry_data
        return tile_data

    def get_tile_data(self, frame, player_data=None):
        player_pos = self._resolve_player_pos(player_data)
        if (
            self.close_tile_detector_enabled
            and self.Detect_close_tile_detector is not None
            and player_pos is not None
        ):
            crop, crop_x, crop_y = self.crop_close_tile_region(frame, player_pos)
            if crop is not None:
                crop_box = [crop_x, crop_y, crop_x + CLOSE_TILE_CROP_SIZE, crop_y + CLOSE_TILE_CROP_SIZE]
                tile_data = self._detect_tile_data(
                    self.Detect_close_tile_detector,
                    crop,
                    self.wall_detection_confidence,
                )
                self._set_tile_detection_debug("close", crop=crop_box)
                self._log_tile_detection_event(
                    f"Wall detection using close tile model ({CLOSE_TILE_MODEL_PATH}).",
                    "wall-detection:close",
                )
                return self.offset_tile_data(tile_data, crop_x, crop_y)
            self._set_tile_detection_debug("full", fallback="crop_failed")
            self._log_tile_detection_event(
                "Close tile crop failed; falling back to full-frame wall detector.",
                "wall-detection:fallback-crop",
            )
        elif self.close_tile_detector_enabled:
            if player_pos is None:
                self._set_tile_detection_debug("full", fallback="no_player")
                self._log_tile_detection_event(
                    "No player position for close tile crop; using full-frame wall detector.",
                    "wall-detection:fallback-no-player",
                )
            else:
                self._set_tile_detection_debug("full", fallback="model_unavailable")
        else:
            self._set_tile_detection_debug("full")

        tile_data = self._detect_tile_data(
            self.Detect_tile_detector,
            frame,
            self.wall_detection_confidence,
        )
        if self.close_tile_detector_enabled:
            self._log_tile_detection_event(
                "Wall detection using full-frame tileDetector.onnx.",
                "wall-detection:full",
            )
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

        self.wall_history.append(walls)
        if len(self.wall_history) > self.wall_history_length:
            self.wall_history.pop(0)
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
        return {"bush", "close_bush", "fog"}

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
            normalized_boxes = [self.normalize_box(box) for box in boxes or []]
            if normalized_boxes:
                objects.setdefault(normalized_name, []).extend(normalized_boxes)

        if self.map_object_vision_enabled and self.map_object_water_detection:
            water_boxes = self.detect_water_tiles(frame)
            if water_boxes:
                objects.setdefault("water", []).extend(water_boxes)

        wall_count = len(objects.get("wall") or [])
        skip_color_fallback = self.last_wall_primary_count >= self.wall_detection_retry_min_objects
        if (
            self.map_object_vision_enabled
            and self.map_object_wall_color_detection
            and wall_count < self.wall_detection_retry_min_objects
            and not skip_color_fallback
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

    def combine_walls_from_history(self):
        if not self.wall_history:
            return []
        current_walls = self.wall_history[-1]
        historical_walls = [wall for walls in self.wall_history for wall in walls]
        stable_history = self.merge_wall_boxes(historical_walls, min_hits=max(1, self.wall_history_min_hits))
        return self.merge_wall_boxes(current_walls + stable_history)

    def get_movement(self):
        movement, updated_globals = interpret_pyla_code(self.pyla_code, self.context)
        return movement

    def _copy_visual_debug_data(self, data):
        copied = {}
        for key, value in (data or {}).items():
            if isinstance(value, list):
                copied[key] = [
                    list(item) if isinstance(item, (list, tuple, np.ndarray)) else item
                    for item in value
                ]
            elif isinstance(value, dict):
                if key == "close_tile_debug":
                    copied[key] = dict(value)
                else:
                    copied[key] = dict(value)
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

    def _enqueue_visual_debug_display(self, img):
        while True:
            try:
                self._visual_debug_display_queue.get_nowait()
            except queue.Empty:
                break
        try:
            self._visual_debug_display_queue.put_nowait(img)
        except queue.Full:
            pass

    def pump_visual_debug_display(self):
        if not visual_debug:
            return
        try:
            img = self._visual_debug_display_queue.get_nowait()
        except queue.Empty:
            return
        show_visual_debug_frame(img)

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

    def _draw_player_foot_circle_debug(self, img, box, sp, s):
        foot_x, foot_y, foot_r = self.get_player_foot_circle(box)
        center = sp((foot_x, foot_y))
        radius = max(3, s(int(round(foot_r))))
        green = (0, 255, 0)
        overlay = img.copy()
        cv2.circle(overlay, center, radius, green, -1, cv2.LINE_AA)
        cv2.addWeighted(overlay, 0.24, img, 0.76, 0, img)
        cv2.circle(img, center, radius, green, max(2, s(2)), cv2.LINE_AA)
        cv2.circle(img, center, max(2, s(2)), (255, 255, 255), -1, cv2.LINE_AA)

    def show_visual_debug(self, frame, data, brawler=None, respect_throttle=True):
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

        status = data.get("status") or data.get("state")
        if status:
            cv2.putText(
                img,
                str(status),
                (8, max(24, s(24))),
                cv2.FONT_HERSHEY_SIMPLEX,
                max(0.5, 0.7 * scale),
                (255, 255, 0),
                2,
                cv2.LINE_AA,
            )

        colors = {
            "player": (0, 255, 0),
            "teammate": (0, 0, 255),
            "enemy": (255, 0, 0),
            "wall": (128, 128, 128),
            "bush": (0, 180, 60),
        }
        boxes_drawn = 0
        for key, color in colors.items():
            boxes = data.get(key)
            if not boxes:
                continue
            for box in boxes:
                if boxes_drawn >= self.visual_debug_max_boxes:
                    break
                if len(box) < 4:
                    continue
                x1, y1, x2, y2 = map(int, box[:4])
                cv2.rectangle(img, sp((x1, y1)), sp((x2, y2)), color, max(1, s(2)))
                if key != "wall":
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

        players = data.get("player") or []
        if players:
            px, py = self.get_player_pos(players[0])
            center = sp((px, py))
            spacing_range = s(int(data.get("effective_enemy_range") or data.get("attack_range") or 0))
            attack_range = s(int(data.get("attack_range") or 0))
            super_range = s(int(data.get("super_range") or 0))
            if spacing_range > 0:
                cv2.circle(img, center, spacing_range, (160, 32, 240), 2)
            elif attack_range > 0:
                cv2.circle(img, center, attack_range, (160, 32, 240), 2)
            if super_range > 0:
                cv2.circle(img, center, super_range, (255, 255, 0), 2)

        movement = data.get("movement")
        if movement and players:
            px, py = self.get_player_pos(players[0])
            mx, my = float(movement[0]), float(movement[1])
            cv2.arrowedLine(
                img,
                sp((px, py)),
                sp((px + mx * 80, py + my * 80)),
                (0, 255, 255),
                2,
                tipLength=0.2,
            )

        joystick = data.get("joystick")
        if joystick and len(joystick) >= 2:
            jx, jy = int(joystick[0]), int(joystick[1])
            radius = s(int(data.get("joystick_radius") or 50))
            cv2.circle(img, sp((jx, jy)), radius, (255, 255, 255), 1)

        close_tile_debug = data.get("close_tile_debug")
        if close_tile_debug:
            crop = close_tile_debug.get("crop")
            if crop and len(crop) >= 4:
                x1, y1, x2, y2 = map(int, crop[:4])
                cv2.rectangle(img, sp((x1, y1)), sp((x2, y2)), (0, 220, 255), max(2, s(2)))
            source = close_tile_debug.get("source", "full")
            fallback = close_tile_debug.get("fallback")
            if source == "close":
                label = "Tile: close 640x640"
                label_color = (0, 220, 255)
            elif fallback:
                label = f"Tile: full ({str(fallback).replace('_', ' ')})"
                label_color = (255, 200, 80)
            else:
                label = "Tile: full"
                label_color = (200, 200, 200)
            cv2.putText(
                img,
                label,
                (s(8), s(36)),
                cv2.FONT_HERSHEY_SIMPLEX,
                max(0.35, 0.5 * scale),
                label_color,
                max(1, s(1)),
                cv2.LINE_AA,
            )

        intent = getattr(self, "match_intent_summary", "")
        if intent:
            cv2.putText(
                img,
                intent[:96],
                (8, img.shape[0] - 12),
                cv2.FONT_HERSHEY_SIMPLEX,
                max(0.4, 0.55 * scale),
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        for box in data.get("player") or []:
            if len(box) >= 4:
                self._draw_player_foot_circle_debug(img, box, sp, s)

        show_visual_debug_frame(img)

    def publish_debug_view(self, frame, data, state, movement=None):
        self.frame = frame
        advanced_visuals = self.advanced_visuals
        debug_view = getattr(self.window_controller, "debug_view", None)
        if debug_view is not None:
            advanced_visuals = bool(getattr(debug_view, "advanced_visuals", advanced_visuals))
        debug_data = {
            "state": state,
            "player": [],
            "enemy": [],
            "teammate": [],
            "wall": [],
            "attack_range": 0,
            "super_range": 0,
            "effective_enemy_range": 0,
            "poison_gas": {},
            "movement": None,
            "joystick": [self.window_controller.joystick_x, self.window_controller.joystick_y],
            "advanced_visuals": advanced_visuals,
            "joystick_radius": int(JOYSTICK_RADIUS * (self.window_controller.scale_factor or 1)),
            "joystick_directions": [],
            "enemy_los_lines": [],
            "teammate_los_lines": [],
            "player_hit_circle": None,
        }

        if data:
            for key in ["player", "enemy", "teammate", "wall"]:
                debug_data[key] = [[int(v) for v in box[:4]] for box in (data.get(key) or []) if len(box) >= 4]
            try:
                _, attack_range, super_range = self.get_brawler_range(self.current_brawler)
                debug_data["attack_range"] = int(attack_range)
                debug_data["super_range"] = int(super_range)
                debug_data["effective_enemy_range"] = int(self.get_effective_enemy_range(self.current_brawler))
            except Exception:
                pass
            if debug_data["player"]:
                try:
                    debug_data["poison_gas"] = self.is_there_poison_gas(debug_data["player"][0])
                except Exception:
                    pass
                if advanced_visuals and early_access:
                    add_advanced_visuals(self, debug_data)

        if movement is not None:
            debug_data["movement"] = [float(movement[0]), float(movement[1])]
        if self.last_tile_detection_debug:
            debug_data["close_tile_debug"] = dict(self.last_tile_detection_debug)

        if visual_debug:
            if not data:
                debug_data["status"] = f"No detections ({state})"
            else:
                debug_data["state"] = state
            self.queue_visual_debug(frame, debug_data, self.current_brawler)
            return

        if debug_view is None:
            return
        debug_view.publish(frame, debug_data)

    def main(self, frame, brawler, main):
        current_time = time.time()
        state = main.get_latest_state()
        data = self.get_main_data(frame)
        if current_time - self.time_since_walls_checked > self.walls_treshold:
            tile_data = self.get_tile_data(frame, data.get("player"))
            walls, map_objects = self.process_tile_data(tile_data, frame)
            line_of_sight_walls = self.map_object_boxes_for_classes(
                map_objects,
                self.line_of_sight_map_object_classes(),
            )
            bushes = self.map_object_boxes_for_classes(
                map_objects,
                {"bush", "close_bush"},
            )
            self.time_since_walls_checked = current_time
            self.last_walls_data = walls
            self.last_map_object_data = map_objects
            self.last_bushes_data = bushes
            data['wall'] = walls
            data['line_of_sight_wall'] = line_of_sight_walls
            data['map_objects'] = map_objects
            data['bushes'] = bushes
        else:
            data['wall'] = self.last_walls_data
            data['bushes'] = self.last_bushes_data
            data['map_objects'] = self.last_map_object_data
            data['line_of_sight_wall'] = self.map_object_boxes_for_classes(
                self.last_map_object_data,
                self.line_of_sight_map_object_classes(),
            )

        data = self.validate_game_data(data)
        self.track_no_detections(data)
        if data:
            self.time_since_player_last_found = time.time()
            if state != "match":
                data = None

        if not data:
            if current_time - self.time_since_player_last_found > 1.0:
                self.window_controller.release_movement()
            if current_time - self.time_since_last_proceeding > self.no_detection_proceed_delay:
                current_state = get_state(frame)
                if current_state != "match":
                    main.handle_detected_state(current_state)
                    state = current_state
                    self.time_since_last_proceeding = current_time
                else:
                    try:
                        import runtime_log
                        runtime_log.log_warn("match", "Player not detected — pressing proceed")
                    except ImportError:
                        pass
                    self.window_controller.press("proceed")
                    self.time_since_last_proceeding = time.time()
            self.publish_debug_view(frame, data, state)
            return
        self.time_since_last_proceeding = time.time()
        self.refresh_ready_abilities(frame, current_time)
        self.frame = frame
        movement = self.loop(brawler, data, current_time)
        self.publish_debug_view(frame, data, state, movement)
        if movement is not None:
            self.do_movement(movement)


Movement = Play
