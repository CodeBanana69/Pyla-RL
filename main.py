import asyncio
import gc
import os
import platform
import sys
import time
import traceback
from pathlib import Path

import cv2

from logger_setup import setup_logging_if_enabled

setup_logging_if_enabled()

import window_controller
from discord_control import DiscordControlServer
from gui.hub import Hub
from gui.login import login
from gui.main import App
from gui.select_brawler import SelectBrawler
from lobby_automation import LobbyAutomation
from play import Play
from runtime_control import RuntimeControlWindow
from stage_manager import StageManager
from state_finder import (
    get_state,
    get_starr_nova_got_it_button_center,
    get_starr_nova_hub_back_button_center,
    is_starr_nova_hub_screen,
    is_starr_nova_info_screen,
)
from telegram_control import TelegramControlServer
from time_management import TimeManagement
from utils import (
    api_base_url,
    async_notify_user,
    check_version,
    cprint,
    current_wall_model_is_latest,
    extract_text_strings,
    get_brawler_list,
    get_latest_version,
    get_latest_wall_model_file,
    load_toml_as_dict,
    update_missing_brawlers_info,
    update_wall_model_classes,
)
from window_controller import WindowController

if platform.architecture()[0] != "64bit":
    print("\nWARNING: PylaAi-XXZ is running on 32-bit Python.")
    print("If IPS is very low, run python tools/performance_check.py to verify ONNX and emulator frame speed.")
    print(f"Current Python: {sys.executable}")

pyla_version = load_toml_as_dict("./cfg/general_config.toml")['pyla_version']


def parse_max_ips(value):
    try:
        max_ips = int(value)
    except (TypeError, ValueError):
        return None
    if max_ips <= 0:
        return None
    return max_ips


OUT_OF_MATCH_REWARD_STATES = {"prestige_reward", "trophy_reward"}
TROPHY_REWARD_FOLLOWUP_STATES = {"reward_unlock"}
STAR_DROP_STATES = {"star_drop", "daily_star_drop", "nova_star_drop"}
SLOW_FEED_FPS_THRESHOLD = 5.0
SLOW_FEED_PLAY_AVG_LIMIT = 0.35
MATCH_RESULT_STATES = {
    "end_victory",
    "end_defeat",
    "end_draw",
    "end_1st",
    "end_2nd",
    "end_3rd",
    "end_4th",
}


def config_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def normalize_detected_state(
        detected_state,
        previous_state=None,
        lobby_seen_since_match=False,
        match_launch_pending=False,
        match_result_seen=False,
        trophy_result_recorded=False,
        recent_trophy_change=False,
        prestige_reward_allowed=True,
        exact_star_drop_after_match=False,
):
    if detected_state == "match_making":
        if previous_state in {"lobby", "match_making"} or match_launch_pending:
            return detected_state
        return previous_state or "match"
    if detected_state in STAR_DROP_STATES:
        allowed_context = (
                previous_state in MATCH_RESULT_STATES
                or previous_state in OUT_OF_MATCH_REWARD_STATES
                or previous_state in TROPHY_REWARD_FOLLOWUP_STATES
                or previous_state in STAR_DROP_STATES
                or (detected_state == "nova_star_drop" and previous_state == "match" and match_result_seen)
                or (exact_star_drop_after_match and previous_state == "match")
                or (trophy_result_recorded and match_result_seen)
        )
        if allowed_context and not match_launch_pending:
            return detected_state
        return previous_state or "match"
    if detected_state in TROPHY_REWARD_FOLLOWUP_STATES:
        if (
                previous_state in {"trophy_reward", "reward_unlock"}
                or (previous_state != "lobby" and match_result_seen)
        ):
            return detected_state
        return previous_state or "match"
    if detected_state in OUT_OF_MATCH_REWARD_STATES:
        if detected_state == "prestige_reward" and not prestige_reward_allowed:
            return previous_state or "match"
        allowed_context = (
                previous_state in MATCH_RESULT_STATES
                or previous_state in OUT_OF_MATCH_REWARD_STATES
                or previous_state in TROPHY_REWARD_FOLLOWUP_STATES
                or (previous_state == "lobby" and lobby_seen_since_match)
                or (trophy_result_recorded and match_result_seen)
                or (previous_state == "match" and recent_trophy_change)
        )
        if not allowed_context:
            return previous_state or "match"
        if match_launch_pending and previous_state not in MATCH_RESULT_STATES:
            return "match"
    return detected_state


def should_accept_lobby_after_match(pending_for, confirm_seconds):
    return pending_for >= confirm_seconds


def pyla_main(data):

    class Main:

        def __init__(self):
            self.window_controller = WindowController()
            self.Play = Play(*self.load_models(), self.window_controller)
            self.Time_management = TimeManagement()
            self.lobby_automator = LobbyAutomation(self.window_controller)
            self.Stage_manager = StageManager(data, self.lobby_automator, self.window_controller)
            self.states_requiring_data = ["lobby"]
            if data[0]['automatically_pick']:
                print("Picking brawler automatically")
                if not self.lobby_automator.select_brawler(data[0]['brawler']):
                    print("Automatic brawler pick failed; continuing without crashing.")
            self.Play.current_brawler = data[0]['brawler']
            self.no_detections_action_threshold = 60 * 8
            self.initialize_stage_manager()
            self.state = None
            self.lobby_seen_since_match = False
            self.match_launch_pending = False
            self.pending_lobby_since = None
            self.pending_lobby_notice = 0.0
            self.post_match_reward_until = 0.0
            self.reward_chain_seen = False
            self.last_ignored_prestige_state_time = 0.0
            self.last_ignored_star_drop_state_time = 0.0
            general_config = load_toml_as_dict("cfg/general_config.toml")
            self.max_ips = parse_max_ips(general_config.get('max_ips', 0))
            self.duplicate_frame_replay_enabled = config_bool(
                general_config.get("duplicate_frame_replay_enabled", "yes"),
                True,
            )
            self.duplicate_frame_replay_max_ips = parse_max_ips(
                general_config.get("duplicate_frame_replay_max_ips", 15)
            ) or 15
            if self.max_ips:
                self.duplicate_frame_replay_max_ips = min(self.duplicate_frame_replay_max_ips, self.max_ips)
            self.duplicate_frame_replay_max_age = float(
                general_config.get("duplicate_frame_replay_max_age_seconds", 0.35)
            )
            self.duplicate_frame_replay_play_avg_limit = float(
                general_config.get("duplicate_frame_replay_play_avg_limit", 0.18)
            )
            self.last_duplicate_frame_replay = 0.0
            self.perf_duplicate_frame_replays = 0
            print(
                "Performance config:",
                f"max_ips={self.max_ips if self.max_ips is not None else 'unlimited'}",
                f"scrcpy_max_fps={general_config.get('scrcpy_max_fps', 'default')}",
                f"scrcpy_max_width={general_config.get('scrcpy_max_width', 'default')}",
                f"onnx_cpu_threads={general_config.get('onnx_cpu_threads', 'auto')}",
            )
            self.visual_debug = load_toml_as_dict("cfg/general_config.toml").get('visual_debug', 'no') == "yes"
            self.run_for_minutes = int(load_toml_as_dict("cfg/general_config.toml")['run_for_minutes'])
            self.start_time = time.time()
            self.time_to_stop = False
            self.in_cooldown = False
            self.cooldown_start_time = 0
            self.cooldown_duration = 3 * 60
            self.match_ready_at = 0.0
            self.match_warmup_seconds = float(load_toml_as_dict("cfg/bot_config.toml").get("match_warmup_seconds", 4.0))
            time_thresholds = load_toml_as_dict("cfg/time_tresholds.toml")
            self.started_at = time.time()
            self.low_ips_startup_grace_seconds = float(time_thresholds.get("low_ips_startup_grace_seconds", 120))
            self.low_ips_match_grace_seconds = float(time_thresholds.get("low_ips_match_grace_seconds", 20))
            self.visual_freeze_check_interval = float(time_thresholds.get("visual_freeze_check_interval", 1.0))
            self.visual_freeze_restart_seconds = float(time_thresholds.get("visual_freeze_restart", 45.0))
            self.visual_freeze_diff_threshold = float(time_thresholds.get("visual_freeze_diff_threshold", 0.35))
            self.last_visual_freeze_check = 0.0
            self.last_visual_change_time = time.time()
            self.last_visual_sample = None
            self.global_freeze_health_interval = float(time_thresholds.get("global_freeze_health_interval", 60.0))
            self.global_freeze_diff_threshold = float(time_thresholds.get("global_freeze_diff_threshold", 0.20))
            self.global_freeze_emulator_restart_after = int(
                time_thresholds.get("global_freeze_emulator_restart_after", 2)
            )
            self.stale_feed_emulator_restart_after = int(
                time_thresholds.get("stale_feed_emulator_restart_after", 3)
            )
            self.last_global_freeze_check = 0.0
            self.last_global_freeze_sample = None
            self.global_freeze_recovery_attempts = 0
            self.host_freeze_enabled = str(
                time_thresholds.get("host_emulator_freeze_enabled", "no")
            ).strip().lower() in ("1", "true", "yes", "on")
            self.host_freeze_health_interval = float(
                time_thresholds.get("host_emulator_freeze_health_interval", 60.0)
            )
            self.host_freeze_diff_threshold = float(
                time_thresholds.get("host_emulator_freeze_diff_threshold", 0.15)
            )
            self.last_host_freeze_check = 0.0
            self.last_host_freeze_sample = None
            self.starr_nova_info_check_interval = float(
                time_thresholds.get("starr_nova_info_check_interval", 60.0)
            )
            self.last_starr_nova_info_check = 0.0
            self.match_start_fast_check_interval = float(
                time_thresholds.get("match_start_fast_check_interval", 0.20)
            )
            self.last_match_start_fast_check = 0.0
            self.lobby_start_retry_interval = float(time_thresholds.get("lobby_start_retry", 8.0))
            self.lobby_stuck_restart_seconds = float(time_thresholds.get("lobby_stuck_restart", 120.0))
            self.lobby_after_match_confirm_seconds = float(
                time_thresholds.get("lobby_after_match_confirm_seconds", 3.0)
            )
            self.lobby_after_match_detection_quiet_seconds = float(
                time_thresholds.get("lobby_after_match_detection_quiet_seconds", 3.0)
            )
            self.post_match_reward_window_seconds = float(
                time_thresholds.get("post_match_reward_window_seconds", 120.0)
            )
            self.lobby_entered_at = None
            self.last_lobby_start_press = 0.0
            self.last_stale_feed_recovery = 0.0
            self.stale_feed_recovery_attempts = 0
            self.last_stale_feed_message = 0.0
            self.low_ips_threshold = float(time_thresholds.get("low_ips_recovery_threshold", 4.0))
            self.low_ips_recovery_seconds = float(time_thresholds.get("low_ips_recovery_seconds", 35.0))
            self.low_ips_recovery_cooldown = float(time_thresholds.get("low_ips_recovery_cooldown", 20.0))
            self.low_ips_app_restart_after = int(time_thresholds.get("low_ips_app_restart_after", 2))
            self.low_ips_emulator_restart_after = int(time_thresholds.get("low_ips_emulator_restart_after", 4))
            self.low_ips_feed_restart_seconds = min(
                float(time_thresholds.get("low_ips_feed_restart_seconds", 8.0)),
                8.0,
            )
            self.low_ips_since = None
            self.last_low_ips_recovery = 0.0
            self.low_ips_recovery_attempts = 0
            self.last_disconnect_check = 0.0
            self.disconnect_reload_attempts = 0
            self.last_processed_frame_id = -1
            self.ips_ema = None
            self.low_frame_fps_warning_time = 0.0
            self.low_feed_since = None
            self.low_feed_last_recovery = 0.0
            self.slow_feed_recovery_attempts = 0
            self.last_offline_emulator_message = 0.0
            self.perf_last_frame_id = -1
            self.perf_last_frame_time = time.time()
            self.perf_frame_count = 0
            self.perf_duplicate_waits = 0
            self.perf_screenshot_ema = None
            self.perf_state_ema = None
            self.perf_play_ema = None
            self.perf_feed_fps = 0.0
            self.disconnect_ocr_interval = 6.0
            self.control_window = RuntimeControlWindow()
            self.control_window.start()
            self.discord_control = DiscordControlServer(self.control_window.state_path)
            self.discord_control.start()
            self.telegram_control = TelegramControlServer(
                self.control_window.state_path,
                screenshot_provider=self.window_controller.screenshot,
                restart_game_callback=self.restart_brawl_stars,
                status_provider=self.telegram_status,
            )
            self.telegram_control.start()
            self.was_paused = False
            self.pause_started_at = None

        def initialize_stage_manager(self):
            self.Stage_manager.Trophy_observer.win_streak = data[0]['win_streak']
            self.Stage_manager.Trophy_observer.current_trophies = data[0]['trophies']
            self.Stage_manager.Trophy_observer.current_wins = data[0]['wins'] if data[0]['wins'] != "" else 0

        def telegram_status(self):
            current = self.Stage_manager.brawlers_pick_data[0] if self.Stage_manager.brawlers_pick_data else {}
            return {
                "state": self.state or "unknown",
                "ips": f"{self.ips_ema:.2f}" if self.ips_ema is not None else "",
                "feed_fps": f"{self.perf_feed_fps:.2f}",
                "emulator": getattr(self.window_controller, "selected_emulator", ""),
                "adb_device": getattr(getattr(self.window_controller, "device", None), "serial", ""),
                "brawler": current.get("brawler", ""),
                "target": current.get("push_until", ""),
            }

        @staticmethod
        def load_models():
            folder_path = "./models/"
            model_names = ['mainInGameModel.onnx', 'tileDetector.onnx']
            loaded_models = []

            for name in model_names:
                loaded_models.append(folder_path + name)
            return loaded_models

        def restart_brawl_stars(self):
            if not self.window_controller.restart_brawl_stars():
                return False
            if not self.window_controller.restart_scrcpy_client():
                print("Brawl Stars restarted, but scrcpy did not recover yet.")
                self.handle_offline_emulator()
                return False
            self.reset_visual_freeze_watchdog()
            self.reset_low_ips_watchdog(recovered=False)
            gc.collect()
            self.lobby_entered_at = None
            self.last_lobby_start_press = 0.0
            self.last_processed_frame_id = -1
            self.Play.time_since_detections["player"] = time.time()
            self.Play.time_since_detections["enemy"] = time.time()
            opened_package = self.window_controller.foreground_package(timeout=4)
            if opened_package and opened_package != window_controller.BRAWL_STARS_PACKAGE:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    screenshot = self.window_controller.screenshot()
                    loop.run_until_complete(async_notify_user(
                        "bot_is_stuck",
                        screenshot,
                        details={
                            "reason": "Brawl Stars did not stay in the foreground after recovery.",
                            "state": self.state or "unknown",
                            "emulator": getattr(self.window_controller, "selected_emulator", "unknown"),
                            "adb_device": getattr(getattr(self.window_controller, "device", None), "serial", ""),
                        },
                    ))
                finally:
                    loop.run_until_complete(asyncio.sleep(0.25))
                    loop.run_until_complete(loop.shutdown_asyncgens())
                    asyncio.set_event_loop(None)
                    loop.close()
                print("Bot got stuck. User notified. Shutting down.")
                self.window_controller.keys_up(list("wasd"))
                self.window_controller.close()
                import sys
                sys.exit(1)
            return True

        def reset_visual_freeze_watchdog(self):
            self.last_visual_sample = None
            self.last_visual_freeze_check = 0.0
            self.last_visual_change_time = time.time()
            self.last_global_freeze_sample = None
            self.global_freeze_recovery_attempts = 0
            self.last_host_freeze_sample = None

        def reset_low_ips_watchdog(self, recovered=True):
            self.low_ips_since = None
            self.low_feed_since = None
            self.slow_feed_recovery_attempts = 0
            self.ips_ema = None
            if recovered:
                self.low_ips_recovery_attempts = 0

        @staticmethod
        def update_ema(current, sample, weight=0.25):
            if current is None:
                return sample
            return (current * (1 - weight)) + (sample * weight)

        def record_new_frame_for_perf(self, frame_id):
            now = time.time()
            if frame_id != self.perf_last_frame_id:
                self.perf_frame_count += 1
                self.perf_last_frame_id = frame_id
            elapsed = now - self.perf_last_frame_time
            if elapsed >= 1:
                self.perf_feed_fps = self.perf_frame_count / elapsed
                self.perf_frame_count = 0
                self.perf_last_frame_time = now

        def print_low_ips_detail(self, current_ips):
            _, last_frame_time = self.window_controller.get_latest_frame()
            frame_age = time.time() - last_frame_time if last_frame_time else 0
            duplicate_waits = self.perf_duplicate_waits
            duplicate_replays = self.perf_duplicate_frame_replays
            self.perf_duplicate_waits = 0
            self.perf_duplicate_frame_replays = 0
            print(
                "Low IPS detail:",
                f"bot_ips={current_ips:.2f}",
                f"feed_fps={self.perf_feed_fps:.2f}",
                f"duplicate_waits={duplicate_waits}",
                f"duplicate_replays={duplicate_replays}",
                f"frame_age={frame_age:.1f}s",
                f"screenshot_avg={self.perf_screenshot_ema or 0:.3f}s",
                f"state_avg={self.perf_state_ema or 0:.3f}s",
                f"play_avg={self.perf_play_ema or 0:.3f}s",
            )
            if (
                    self.state == "match"
                    and self.perf_feed_fps < SLOW_FEED_FPS_THRESHOLD
                    and (self.perf_play_ema or 0) < SLOW_FEED_PLAY_AVG_LIMIT
            ):
                print(
                    "Diagnosis: emulator/scrcpy is only delivering a few usable frames. "
                    "This is not an AI/GPU compute limit; check emulator FPS/performance mode and local ADB."
                )
            elif (self.perf_play_ema or 0) > 0.75:
                print(
                    "Diagnosis: vision/play loop is slow. Run python tools/performance_check.py "
                    "and make sure ONNX uses DmlExecutionProvider or CUDAExecutionProvider."
                )

        def recover_slow_feed(self):
            now = time.time()
            if self.state != "match":
                self.low_feed_since = None
                return False
            if now - self.started_at < self.low_ips_startup_grace_seconds:
                return False
            if now - self.match_ready_at < self.low_ips_match_grace_seconds:
                return False
            if (
                    self.perf_feed_fps >= SLOW_FEED_FPS_THRESHOLD
                    or (self.perf_play_ema or 0) >= SLOW_FEED_PLAY_AVG_LIMIT
            ):
                self.low_feed_since = None
                return False
            if self.low_feed_since is None:
                self.low_feed_since = now
                return False
            if now - self.low_feed_since < self.low_ips_feed_restart_seconds:
                return False
            if now - self.low_feed_last_recovery < self.low_ips_recovery_cooldown:
                return False

            self.low_feed_last_recovery = now
            self.slow_feed_recovery_attempts += 1
            print(
                f"Frame feed stayed under 3 FPS for {now - self.low_feed_since:.1f}s "
                f"(feed_fps={self.perf_feed_fps:.2f}); recovery attempt {self.slow_feed_recovery_attempts}."
            )
            self.window_controller.keys_up(list("wasd"))
            if not self.window_controller.restart_scrcpy_client():
                self.handle_offline_emulator()
                return False
            self.last_processed_frame_id = -1
            self.perf_duplicate_waits = 0
            self.low_feed_since = now
            return True

        def should_replay_duplicate_frame(self, frame_time):
            if not self.duplicate_frame_replay_enabled:
                return False
            if self.state != "match":
                return False
            if self.was_paused:
                return False
            if not frame_time:
                return False
            if time.time() - frame_time > self.duplicate_frame_replay_max_age:
                return False
            if (self.perf_play_ema or 0) > self.duplicate_frame_replay_play_avg_limit:
                return False
            follow_mode_active = (
                getattr(self.Play, "showdown_playstyle_mode", "").strip().lower()
                in ("follow", "follower", "team", "teammate", "teammates")
            )
            if time.time() < self.match_ready_at and not follow_mode_active:
                return False
            min_interval = 1 / max(1, self.duplicate_frame_replay_max_ips)
            return time.time() - self.last_duplicate_frame_replay >= min_interval

        def replay_duplicate_match_frame(self, frame):
            self.last_duplicate_frame_replay = time.time()
            brawler = self.Stage_manager.brawlers_pick_data[0]['brawler']
            play_start = time.perf_counter()
            self.Play.main(frame, brawler, self)
            self.perf_play_ema = self.update_ema(
                self.perf_play_ema,
                time.perf_counter() - play_start,
            )
            self.perf_duplicate_frame_replays += 1

        def recover_low_ips(self, current_ips):
            now = time.time()
            if now - self.started_at < self.low_ips_startup_grace_seconds:
                return False
            if self.state == "match" and now - self.match_ready_at < self.low_ips_match_grace_seconds:
                return False
            if current_ips >= self.low_ips_threshold:
                if self.low_ips_since is not None:
                    print(f"IPS recovered to {current_ips:.2f}; clearing low-IPS watchdog.")
                self.reset_low_ips_watchdog(recovered=True)
                return False

            _, last_frame_time = self.window_controller.get_latest_frame()
            frame_age = now - last_frame_time if last_frame_time else 999.0
            if self.low_ips_since is None:
                self.low_ips_since = now
                return False

            low_for = now - self.low_ips_since
            if low_for < self.low_ips_recovery_seconds:
                return False
            if now - self.last_low_ips_recovery < self.low_ips_recovery_cooldown:
                return False

            self.last_low_ips_recovery = now
            self.low_ips_recovery_attempts += 1
            self.window_controller.keys_up(list("wasd"))
            print(
                f"IPS stayed low ({current_ips:.2f}, frame age {frame_age:.1f}s) "
                f"for {low_for:.1f}s; recovery attempt {self.low_ips_recovery_attempts}."
            )

            if self.low_ips_recovery_attempts >= self.low_ips_emulator_restart_after:
                if frame_age <= 5:
                    print(
                        "Low IPS is still happening but scrcpy frames are fresh; "
                        "skipping emulator restart and restarting Brawl Stars/scrcpy instead."
                    )
                    self.restart_brawl_stars()
                    self.low_ips_recovery_attempts = max(
                        self.low_ips_app_restart_after,
                        self.low_ips_emulator_restart_after - 1,
                    )
                else:
                    print("Low IPS did not recover after app/scrcpy restarts; restarting emulator profile.")
                    if self.window_controller.restart_emulator_profile():
                        self.low_ips_recovery_attempts = 0
                    else:
                        print("Emulator restart was not available; keeping bot alive and retrying scrcpy recovery.")
                        if not self.window_controller.restart_scrcpy_client():
                            self.handle_offline_emulator()
                        self.low_ips_recovery_attempts = max(
                            self.low_ips_app_restart_after,
                            self.low_ips_emulator_restart_after - 1,
                        )
            elif self.low_ips_recovery_attempts >= self.low_ips_app_restart_after:
                print("Low IPS persisted; restarting Brawl Stars and scrcpy.")
                self.restart_brawl_stars()
            else:
                print("Low IPS detected; restarting scrcpy feed.")
                if not self.window_controller.restart_scrcpy_client():
                    self.handle_offline_emulator()

            self.last_processed_frame_id = -1
            self.low_ips_since = now
            self.ips_ema = None
            gc.collect()
            return True

        def handle_visual_freeze(self, frame):
            if self.state != "match":
                self.reset_visual_freeze_watchdog()
                return False

            now = time.time()
            if now < self.match_ready_at or now - self.last_visual_freeze_check < self.visual_freeze_check_interval:
                return False
            self.last_visual_freeze_check = now

            sample = cv2.resize(frame, (96, 54), interpolation=cv2.INTER_AREA)
            sample = cv2.cvtColor(sample, cv2.COLOR_RGB2GRAY)
            if self.last_visual_sample is None:
                self.last_visual_sample = sample
                self.last_visual_change_time = now
                return False

            diff = float(cv2.absdiff(sample, self.last_visual_sample).mean())
            self.last_visual_sample = sample
            if diff >= self.visual_freeze_diff_threshold:
                self.last_visual_change_time = now
                return False

            frozen_for = now - self.last_visual_change_time
            if frozen_for < self.visual_freeze_restart_seconds:
                return False

            print(
                f"Match image did not change for {frozen_for:.1f}s "
                f"(diff {diff:.3f}); restarting Brawl Stars and scrcpy."
            )
            self.window_controller.keys_up(list("wasd"))
            self.restart_brawl_stars()
            return True

        def handle_global_screen_freeze(self, frame):
            now = time.time()
            if now - self.last_global_freeze_check < self.global_freeze_health_interval:
                return False
            self.last_global_freeze_check = now

            sample = cv2.resize(frame, (96, 54), interpolation=cv2.INTER_AREA)
            sample = cv2.cvtColor(sample, cv2.COLOR_RGB2GRAY)
            if self.last_global_freeze_sample is None:
                self.last_global_freeze_sample = sample
                return False

            diff = float(cv2.absdiff(sample, self.last_global_freeze_sample).mean())
            self.last_global_freeze_sample = sample
            if diff >= self.global_freeze_diff_threshold:
                self.global_freeze_recovery_attempts = 0
                return False

            self.global_freeze_recovery_attempts += 1
            print(
                "Screen health check found no visible change for "
                f"{self.global_freeze_health_interval:.0f}s (diff {diff:.3f}); "
                f"recovery attempt {self.global_freeze_recovery_attempts}."
            )
            self.window_controller.keys_up(list("wasd"))
            if self.global_freeze_recovery_attempts >= self.global_freeze_emulator_restart_after:
                print("Screen is still frozen after app recovery; restarting emulator profile.")
                if self.window_controller.restart_emulator_profile():
                    self.reset_visual_freeze_watchdog()
                    self.reset_low_ips_watchdog(recovered=False)
                    self.last_processed_frame_id = -1
                else:
                    print("Emulator restart was not available yet; restarting Brawl Stars and scrcpy instead.")
                    self.restart_brawl_stars()
            else:
                print("Restarting Brawl Stars and scrcpy first.")
                self.restart_brawl_stars()
            return True

        def handle_host_emulator_freeze(self):
            if not self.host_freeze_enabled:
                return False
            now = time.time()
            if now - self.last_host_freeze_check < self.host_freeze_health_interval:
                return False
            self.last_host_freeze_check = now

            frame = self.window_controller.host_emulator_screenshot()
            if frame is None or frame.size == 0:
                return False

            sample = cv2.resize(frame, (96, 54), interpolation=cv2.INTER_AREA)
            sample = cv2.cvtColor(sample, cv2.COLOR_RGB2GRAY)
            if self.last_host_freeze_sample is None:
                self.last_host_freeze_sample = sample
                return False

            diff = float(cv2.absdiff(sample, self.last_host_freeze_sample).mean())
            self.last_host_freeze_sample = sample
            if diff >= self.host_freeze_diff_threshold:
                return False

            print(
                "PC emulator-window screenshot did not visibly change for "
                f"{self.host_freeze_health_interval:.0f}s (diff {diff:.3f}); "
                "skipping emulator restart because this check can false-trigger on static screens."
            )
            return False

        def handle_starr_nova_info_screen(self, frame):
            now = time.time()
            if now - self.last_starr_nova_info_check < self.starr_nova_info_check_interval:
                return False
            self.last_starr_nova_info_check = now

            screenshot_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            if not is_starr_nova_info_screen(screenshot_bgr):
                return False
            button_center = get_starr_nova_got_it_button_center(screenshot_bgr)
            if button_center is None:
                return False
            print("Starr Nova info screen detected; clicking GOT IT.")
            self.window_controller.keys_up(list("wasd"))
            self.window_controller.click(*button_center, delay=0.08)
            return True

        def handle_starr_nova_hub_screen(self, frame):
            if self.state not in (None, "lobby", "shop"):
                return False

            screenshot_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            if not is_starr_nova_hub_screen(screenshot_bgr):
                return False
            back_center = get_starr_nova_hub_back_button_center(screenshot_bgr)
            if back_center is None:
                return False
            print("Starr Nova hub screen detected; clicking back.")
            self.window_controller.keys_up(list("wasd"))
            self.window_controller.click(*back_center, delay=0.08)
            self.lobby_entered_at = None
            self.last_lobby_start_press = time.time()
            return True

        def handle_lobby_watchdog(self, state):
            now = time.time()
            if state != "lobby" or self.in_cooldown:
                if state != "lobby":
                    self.lobby_entered_at = None
                return False

            if self.lobby_entered_at is None:
                self.lobby_entered_at = now

            if now - self.last_lobby_start_press >= self.lobby_start_retry_interval:
                print("Lobby watchdog: pressing start again.")
                self.window_controller.keys_up(list("wasd"))
                self.window_controller.press_key("Q")
                self.last_lobby_start_press = now

            lobby_age = now - self.lobby_entered_at
            if lobby_age < self.lobby_stuck_restart_seconds:
                return False

            print(f"Lobby did not enter a match for {lobby_age:.1f}s; restarting Brawl Stars.")
            self.restart_brawl_stars()
            return True

        def apply_state_context_guard(self, detected_state, previous_state):
            now = time.time()
            if detected_state in MATCH_RESULT_STATES:
                self.post_match_reward_until = now + self.post_match_reward_window_seconds

            trophy_result_recorded = (
                    0 < now - getattr(self.Stage_manager, "last_recorded_result_time", 0.0)
                    <= self.post_match_reward_window_seconds
            )
            recent_trophy_change = self.Stage_manager.had_recent_trophy_change(seconds=30.0)
            reward_chain_active = (
                    self.reward_chain_seen
                    or previous_state is None
                    or previous_state in OUT_OF_MATCH_REWARD_STATES
            )
            post_match_context_active = (
                    trophy_result_recorded
                    or now <= self.post_match_reward_until
                    or reward_chain_active
            )
            state = normalize_detected_state(
                detected_state,
                previous_state=previous_state,
                lobby_seen_since_match=self.lobby_seen_since_match,
                match_launch_pending=self.match_launch_pending,
                match_result_seen=post_match_context_active,
                trophy_result_recorded=trophy_result_recorded,
                recent_trophy_change=recent_trophy_change,
                prestige_reward_allowed=self.Stage_manager.can_handle_prestige_reward_screen(),
                exact_star_drop_after_match=detected_state in STAR_DROP_STATES,
            )
            if detected_state != "lobby":
                self.pending_lobby_since = None

            if state == "lobby" and previous_state == "match":
                if self.pending_lobby_since is None:
                    self.pending_lobby_since = now
                    self.pending_lobby_notice = 0.0
                pending_for = now - self.pending_lobby_since
                if not should_accept_lobby_after_match(
                        pending_for,
                        self.lobby_after_match_confirm_seconds,
                ):
                    if now - self.pending_lobby_notice >= 5.0:
                        print(
                            "Ignoring lobby detection until it is stable after match "
                            f"({pending_for:.1f}/{self.lobby_after_match_confirm_seconds:.1f}s)."
                        )
                        self.pending_lobby_notice = now
                    return "match"
                self.pending_lobby_since = None

            if detected_state in OUT_OF_MATCH_REWARD_STATES and state != detected_state:
                if now - self.last_ignored_prestige_state_time >= 5.0:
                    print(f"Ignoring {detected_state} detection until a match result or lobby is confirmed.")
                    self.last_ignored_prestige_state_time = now
            if detected_state in STAR_DROP_STATES and state != detected_state:
                if now - self.last_ignored_star_drop_state_time >= 5.0:
                    print("Ignoring star_drop detection because no post-match reward chain is active.")
                    self.last_ignored_star_drop_state_time = now

            if state == "match":
                self.lobby_seen_since_match = False
                self.match_launch_pending = False
                if previous_state == "lobby":
                    self.post_match_reward_until = 0.0
                    self.reward_chain_seen = False
            elif state == "lobby":
                self.lobby_seen_since_match = True
                self.match_launch_pending = False
                self.reward_chain_seen = False
            elif state == "match_making":
                self.match_launch_pending = True
            elif (
                    state in OUT_OF_MATCH_REWARD_STATES
                    or state in STAR_DROP_STATES
                    or state in TROPHY_REWARD_FOLLOWUP_STATES
            ):
                self.reward_chain_seen = True
            return state

        def manage_time_tasks(self, frame):
            if self.handle_starr_nova_hub_screen(frame):
                return

            if self.handle_starr_nova_info_screen(frame):
                return

            if self.handle_disconnect_screen(frame):
                return

            if self.Time_management.state_check():
                detected_state = get_state(frame)
                previous_state = self.state
                state = self.apply_state_context_guard(detected_state, previous_state)
                self.state = state
                if state != "match":
                    self.Play.time_since_last_proceeding = time.time()
                if previous_state == "match" and state != "match":
                    self.Play.reset_match_control_state()
                elif previous_state != "match" and state == "match":
                    self.Play.reset_match_control_state()
                    self.match_ready_at = time.time() + self.match_warmup_seconds
                    if previous_state in {"lobby", "match_making"}:
                        self.Stage_manager.reset_prestige_reward_gate()
                frame_data = None
                self.Stage_manager.do_state(state, frame_data)
                if state == "lobby":
                    self.match_launch_pending = True
                self.handle_lobby_watchdog(state)

            if self.Time_management.no_detections_check():
                frame_data = self.Play.time_since_detections
                for key, value in frame_data.items():
                    if time.time() - value > self.no_detections_action_threshold:
                        self.restart_brawl_stars()

            if self.Time_management.idle_check():
                #print("check for idle!")
                self.lobby_automator.check_for_idle(frame)

        def try_promote_match_start(self, frame):
            if self.state not in {"match_making", "lobby"}:
                return False
            now = time.time()
            if now - self.last_match_start_fast_check < self.match_start_fast_check_interval:
                return False
            self.last_match_start_fast_check = now
            detected_state = get_state(frame)
            state = self.apply_state_context_guard(detected_state, self.state)
            if state != "match":
                return False
            previous_state = self.state
            self.state = "match"
            self.match_launch_pending = False
            self.Play.reset_match_control_state()
            self.match_ready_at = time.time() + self.match_warmup_seconds
            if previous_state in {"lobby", "match_making"}:
                self.Stage_manager.reset_prestige_reward_gate()
            print("Fast match start detected; movement loop active.")
            return True

        def handle_disconnect_screen(self, frame):
            if time.time() - self.last_disconnect_check < self.disconnect_ocr_interval:
                return False
            self.last_disconnect_check = time.time()

            h, w = frame.shape[:2]
            dialog_crop = frame[int(h * 0.32):int(h * 0.62), int(w * 0.24):int(w * 0.76)]
            dialog_mean = float(dialog_crop.mean())
            dialog_std = float(dialog_crop.std())
            dialog_hsv = cv2.cvtColor(dialog_crop, cv2.COLOR_RGB2HSV)
            dialog_saturation = float(dialog_hsv[:, :, 1].mean())
            if dialog_mean > 90 or dialog_std > 75 or dialog_saturation > 85:
                return False

            center_crop = frame[int(h * 0.22):int(h * 0.55), int(w * 0.15):int(w * 0.70)]
            try:
                text = " ".join(extract_text_strings(center_crop))
            except Exception as e:
                print(f"Could not OCR disconnect screen: {e}")
                return False

            lowered_text = text.lower()
            if (
                    "reload" not in lowered_text
                    and "disconnect" not in lowered_text
                    and "disconnected" not in lowered_text
                    and "connection" not in lowered_text
                    and "lost" not in lowered_text
                    and "retry" not in lowered_text
                    and "logging" not in lowered_text
                    and "login" not in lowered_text
                    and "idle" not in lowered_text
            ):
                return False

            self.disconnect_reload_attempts += 1
            self.window_controller.keys_up(list("wasd"))
            print(f"Disconnect/login screen detected, recovery attempt {self.disconnect_reload_attempts}.")
            if self.disconnect_reload_attempts >= 3:
                print("Retry did not clear disconnect screen; restarting Brawl Stars.")
                self.restart_brawl_stars()
                self.disconnect_reload_attempts = 0
            else:
                self.window_controller.click(650, 610, delay=0.08, already_include_ratio=False)
                time.sleep(3)
            return True

        def handle_offline_emulator(self):
            now = time.time()
            if now - self.last_offline_emulator_message > 10:
                if self.window_controller.emulator_autorestart:
                    remaining = max(
                        0,
                        self.window_controller.emulator_restart_cooldown
                        - (now - self.window_controller.last_emulator_restart_time),
                    )
                    if remaining > 0:
                        print(f"Emulator ADB is offline; waiting {remaining:.0f}s before the next profile restart attempt.")
                    else:
                        print("Emulator ADB is offline; trying to restart the saved emulator profile.")
                else:
                    print("Emulator ADB is offline and auto-restart is disabled; waiting for the emulator to come back online.")
                self.last_offline_emulator_message = now

            if self.window_controller.emulator_autorestart:
                remaining = (
                    self.window_controller.emulator_restart_cooldown
                    - (now - self.window_controller.last_emulator_restart_time)
                )
                if remaining <= 0:
                    if self.window_controller.restart_emulator_profile():
                        self.reset_visual_freeze_watchdog()
                        self.reset_low_ips_watchdog(recovered=False)
                        self.last_processed_frame_id = -1
                        self.Play.time_since_detections["player"] = time.time()
                        self.Play.time_since_detections["enemy"] = time.time()
                        self.Play.time_since_player_last_found = time.time()
            time.sleep(2)

        def handle_stale_scrcpy_feed(self, frame_time=None):
            now = time.time()
            stale_age = now - frame_time if frame_time else 0
            age_text = f"{stale_age:.1f}s old" if frame_time else "missing"
            self.Play.window_controller.keys_up(list("wasd"))

            if not self.window_controller.is_emulator_online():
                self.handle_offline_emulator()
                self.stale_feed_recovery_attempts = 0
                self.last_stale_feed_recovery = now
                return

            if now - self.last_stale_feed_recovery < 5:
                if now - self.last_stale_feed_message > 2:
                    remaining = 5 - (now - self.last_stale_feed_recovery)
                    print(f"Scrcpy frame is still {age_text}; retrying recovery in {remaining:.1f}s.")
                    self.last_stale_feed_message = now
                return

            self.last_stale_feed_recovery = now
            self.stale_feed_recovery_attempts += 1

            if self.stale_feed_recovery_attempts >= self.stale_feed_emulator_restart_after or stale_age > 60:
                print("Scrcpy feed is still frozen after recovery attempts; restarting emulator profile.")
                if self.window_controller.restart_emulator_profile():
                    self.stale_feed_recovery_attempts = 0
                    self.reset_visual_freeze_watchdog()
                    self.reset_low_ips_watchdog(recovered=False)
                    self.last_processed_frame_id = -1
                else:
                    print("Emulator restart was not available yet; restarting Brawl Stars and scrcpy.")
                    self.restart_brawl_stars()
            elif self.stale_feed_recovery_attempts >= 2 or stale_age > 30:
                print("Scrcpy feed is still frozen; restarting Brawl Stars and scrcpy.")
                if self.restart_brawl_stars():
                    self.stale_feed_recovery_attempts = max(1, self.stale_feed_recovery_attempts - 1)
            else:
                print(f"Scrcpy frame is {age_text}; restarting scrcpy feed.")
                if not self.window_controller.restart_scrcpy_client():
                    self.handle_offline_emulator()

        def handle_pause_control(self):
            if not self.control_window.is_paused():
                if self.was_paused:
                    paused_for = time.time() - self.pause_started_at if self.pause_started_at else 0
                    self.start_time += paused_for
                    self.Play.time_since_detections["player"] = time.time()
                    self.Play.time_since_detections["enemy"] = time.time()
                    self.Play.time_since_player_last_found = time.time()
                    self.Play.time_since_last_proceeding = time.time()
                    self.last_processed_frame_id = -1
                    self.was_paused = False
                    self.pause_started_at = None
                    print("Bot resumed.")
                return False

            if not self.was_paused:
                self.window_controller.keys_up(list("wasd"))
                self.Play.reset_match_control_state()
                self.was_paused = True
                self.pause_started_at = time.time()
                print("Bot paused.")
            time.sleep(0.1)
            return True

        def main(self): #this is for timer to stop after time
            s_time = time.time()
            c = 0
            while True:
                if self.handle_pause_control():
                    s_time = time.time()
                    c = 0
                    continue
                if self.max_ips:
                    frame_start = time.perf_counter()
                if self.run_for_minutes > 0 and not self.in_cooldown:
                    elapsed_time = (time.time() - self.start_time) / 60
                    if elapsed_time >= self.run_for_minutes:
                        if self.state != "match":
                            cprint(f"timer is done, {self.run_for_minutes} minutes are over and bot is not in game. stopping bot fully", "#AAE5A4")
                            break
                        cprint(f"timer is done, {self.run_for_minutes} is over. continuing for 3 minutes if in game", "#AAE5A4")
                        self.in_cooldown = True # tries to finish game if in game
                        self.cooldown_start_time = time.time()
                        self.Stage_manager.states['lobby'] = lambda: 0

                if self.in_cooldown:
                    if time.time() - self.cooldown_start_time >= self.cooldown_duration:
                        cprint("stopping bot fully", "#AAE5A4")
                        break

                if abs(s_time - time.time()) > 1:
                    elapsed = time.time() - s_time
                    if elapsed > 0 and not self.visual_debug:
                        current_ips = c / elapsed
                        self.ips_ema = current_ips if self.ips_ema is None else (self.ips_ema * 0.75 + current_ips * 0.25)
                        print(f"{self.ips_ema:.2f} IPS")
                        if self.recover_low_ips(self.ips_ema):
                            s_time = time.time()
                            c = 0
                            continue
                        if self.ips_ema is not None and self.ips_ema < 3 and time.time() - self.low_frame_fps_warning_time > 20:
                            self.print_low_ips_detail(self.ips_ema)
                            self.low_frame_fps_warning_time = time.time()
                    s_time = time.time()
                    c = 0

                try:
                    screenshot_start = time.perf_counter()
                    frame = self.window_controller.screenshot()
                    self.perf_screenshot_ema = self.update_ema(
                        self.perf_screenshot_ema,
                        time.perf_counter() - screenshot_start,
                    )
                except ConnectionError as e:
                    if self.window_controller.is_emulator_online():
                        print(f"{e} Recovering scrcpy feed.")
                    self.handle_stale_scrcpy_feed()
                    continue

                _, last_ft = self.window_controller.get_latest_frame()
                if last_ft > 0 and (time.time() - last_ft) > self.window_controller.FRAME_STALE_TIMEOUT:
                    self.handle_stale_scrcpy_feed(last_ft)
                    continue

                self.stale_feed_recovery_attempts = 0

                if self.handle_host_emulator_freeze():
                    continue

                if self.handle_global_screen_freeze(frame):
                    continue

                frame_id = self.window_controller.get_latest_frame_id()
                self.record_new_frame_for_perf(frame_id)
                if frame_id == self.last_processed_frame_id:
                    self.perf_duplicate_waits += 1
                    if self.should_replay_duplicate_frame(last_ft):
                        self.replay_duplicate_match_frame(frame)
                        c += 1
                        self.recover_slow_feed()
                        continue
                    self.recover_slow_feed()
                    time.sleep(0.01)
                    continue
                self.last_processed_frame_id = frame_id

                state_start = time.perf_counter()
                self.manage_time_tasks(frame)
                self.perf_state_ema = self.update_ema(
                    self.perf_state_ema,
                    time.perf_counter() - state_start,
                )

                if self.handle_visual_freeze(frame):
                    continue

                if self.state != "match":
                    if self.try_promote_match_start(frame):
                        pass
                    else:
                        self.window_controller.keys_up(list("wasd"))
                        time.sleep(0.02)
                        continue

                if self.state != "match":
                    self.window_controller.keys_up(list("wasd"))
                    time.sleep(0.02)
                    continue

                follow_mode_active = (
                    getattr(self.Play, "showdown_playstyle_mode", "").strip().lower()
                    in ("follow", "follower", "team", "teammate", "teammates")
                )
                if self.state == "match" and time.time() < self.match_ready_at and not follow_mode_active:
                    self.window_controller.keys_up(list("wasd"))
                    time.sleep(0.05)
                    continue

                brawler = self.Stage_manager.brawlers_pick_data[0]['brawler']
                play_start = time.perf_counter()
                self.Play.main(frame, brawler, self)
                self.perf_play_ema = self.update_ema(
                    self.perf_play_ema,
                    time.perf_counter() - play_start,
                )
                c += 1
                self.recover_slow_feed()

                if self.max_ips:
                    target_period = 1 / self.max_ips
                    work_time = time.perf_counter() - frame_start
                    if work_time < target_period:
                        time.sleep(target_period - work_time)

            self.discord_control.close()
            self.telegram_control.close()
            self.control_window.close()

    main = Main()
    main.main()


def run_app():
    all_brawlers = get_brawler_list()
    if api_base_url != "localhost":
        update_missing_brawlers_info(all_brawlers)
        check_version()
        update_wall_model_classes()
        if not current_wall_model_is_latest():
            print("New Wall detection model found, downloading... (this might take a few minutes depending on your internet speed)")
            get_latest_wall_model_file()

    app = App(login, SelectBrawler, pyla_main, all_brawlers, Hub)
    app.start(pyla_version, get_latest_version)


def write_crash_log(error):
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    crash_path = log_dir / "startup_crash.log"
    crash_path.write_text(
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        encoding="utf-8",
    )
    print(f"Pyla crashed during startup. Crash log saved to: {crash_path.resolve()}")
    print(traceback.format_exc())


if __name__ == "__main__":
    try:
        run_app()
    except Exception as e:
        write_crash_log(e)
        try:
            input("Press Enter to close...")
        except EOFError:
            pass
        raise
