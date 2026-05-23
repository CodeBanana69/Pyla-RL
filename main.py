import asyncio
import gc
import os
import platform
import subprocess
import sys
import time
import traceback
from collections import deque
from pathlib import Path


def repair_numpy_before_cv2_import():
    try:
        import numpy
    except Exception:
        return

    try:
        major = int(str(numpy.__version__).split(".", 1)[0])
    except (TypeError, ValueError):
        return
    if major < 2:
        return

    if os.environ.get("PYLAAI_NUMPY_REPAIR") == "1":
        print(
            "NumPy is still 2.x after repair. Run: "
            f'"{sys.executable}" -m pip install --force-reinstall --no-deps "numpy<2.0.0"'
        )
        return

    print(
        f"Detected NumPy {numpy.__version__}; repairing to numpy<2.0.0 before loading OpenCV..."
    )
    os.environ["PYLAAI_NUMPY_REPAIR"] = "1"
    subprocess.check_call([
        sys.executable,
        "-m",
        "pip",
        "install",
        "--force-reinstall",
        "--no-deps",
        "numpy<2.0.0",
    ])


repair_numpy_before_cv2_import()

try:
    import cv2
except ModuleNotFoundError:
    print("\n" + "=" * 50)
    print("  OpenCV (cv2) is not installed for this Python.")
    print("  Run setup.exe in the Pyla-RL folder first.")
    print("  Or run: py -3.11-64 setup.py --pyla-install")
    print("=" * 50 + "\n")
    raise SystemExit(1) from None

from logger_setup import setup_logging_if_enabled

setup_logging_if_enabled()

import runtime_log

runtime_log.configure()

import window_controller
from discord_control import DiscordControlServer
from gui.qml_hub import QmlHub
from gui.login import login
from gui.main import App
from gui.select_brawler import SelectBrawler
from lobby_automation import LobbyAutomation
from play import Play
from runtime_control import RUNNING, RuntimeControlWindow, is_stop_requested, write_state
from runtime_metrics import metrics_path_for_pid, write_metrics
from stage_manager import StageManager
from state_finder import (
    get_state,
    get_starr_nova_got_it_button_center,
    get_starr_nova_hub_back_button_center,
    is_in_brawl_pass,
    is_in_star_road,
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
    normalize_brawler_name,
    update_missing_brawlers_info,
    update_wall_model_classes,
)
from window_controller import WindowController

if platform.architecture()[0] != "64bit":
    print("\nWARNING: PylaAi-XXZ is running on 32-bit Python.")
    print("If IPS is very low, run python tools/performance_check.py to verify ONNX and emulator frame speed.")
    print(f"Current Python: {sys.executable}")

pyla_version = load_toml_as_dict("./cfg/general_config.toml")['pyla_version']


def HubMenu(*args, **kwargs):
    return QmlHub(*args, **kwargs)


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


def apply_in_match_overlay_guard(
        state,
        detected_state,
        previous_state,
        *,
        allow_panel_escape=False,
):
    if (
        previous_state == "match"
        and detected_state in {"brawler_selection", "shop"}
        and state == detected_state
    ):
        if allow_panel_escape and detected_state == "shop":
            return "shop"
        return "match"
    return state


def pyla_main(data):
    from gui.instance_config import get_active_instance_id, instance_context_for_notifications

    class Main:

        def __init__(self):
            self.instance_id = get_active_instance_id()
            self.last_manifest_heartbeat = 0.0
            self.window_controller = WindowController()
            self.window_controller.recovery_logger = self.log_runtime_recovery
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
                general_config.get("duplicate_frame_replay_max_ips", 25)
            ) or 15
            if self.max_ips:
                self.duplicate_frame_replay_max_ips = min(self.duplicate_frame_replay_max_ips, self.max_ips)
            self.duplicate_frame_replay_max_age = float(
                general_config.get("duplicate_frame_replay_max_age_seconds", 0.35)
            )
            self.duplicate_frame_replay_play_avg_limit = float(
                general_config.get("duplicate_frame_replay_play_avg_limit", 0.22)
            )
            self.last_duplicate_frame_replay = 0.0
            self.perf_duplicate_frame_replays = 0
            runtime_log.log_info(
                "startup",
                (
                    "Performance config: "
                    f"max_ips={self.max_ips if self.max_ips is not None else 'unlimited'} "
                    f"scrcpy_max_fps={general_config.get('scrcpy_max_fps', 'default')} "
                    f"scrcpy_max_width={general_config.get('scrcpy_max_width', 'default')} "
                    f"onnx_cpu_threads={general_config.get('onnx_cpu_threads', 'auto')}"
                ),
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
            if getattr(self.window_controller, "selected_emulator", "") == "MuMu":
                self.stale_feed_emulator_restart_after = max(
                    4,
                    self.stale_feed_emulator_restart_after,
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
            self.pause_menu_ips_graph = str(
                general_config.get("pause_menu_ips_graph", "no")
            ).strip().lower() in ("yes", "true", "1", "on")
            self.pause_menu_session_strip = str(
                general_config.get("pause_menu_session_strip", "yes")
            ).strip().lower() in ("yes", "true", "1", "on")
            self.pause_menu_graph_samples = max(
                30,
                min(120, int(general_config.get("pause_menu_graph_samples", 45))),
            )
            self.console_ips = str(
                general_config.get("console_ips", "yes")
            ).strip().lower() in ("yes", "true", "1", "on")
            self.terminal_summary_seconds = max(
                1.0,
                float(general_config.get("terminal_summary_seconds", 5)),
            )
            self.last_terminal_summary_at = 0.0
            self.pause_menu_auto_reopen = str(
                general_config.get("pause_menu_auto_reopen", "yes")
            ).strip().lower() in ("yes", "true", "1", "on")
            self.ips_history = deque(maxlen=self.pause_menu_graph_samples)
            self.metrics_path = metrics_path_for_pid(os.getpid())
            self.disconnect_ocr_interval = 6.0
            self.control_window = RuntimeControlWindow(metrics_path=self.metrics_path)
            self.control_window.start()
            self.last_pause_menu_check = 0.0
            runtime_log.log_info(
                "startup",
                "Pause menu ready: F8 pause/resume, - minimize, x compact, expand full panel.",
            )
            self.remote_control_enabled = not self.instance_id
            # Single-instance remote control wiring (Discord slash + Telegram commands).
            # See docs/tutorials/discord-remote-control.md and docs/tutorials/telegram.md.
            if self.remote_control_enabled:
                self.discord_control = DiscordControlServer(
                    self.control_window.state_path,
                    screenshot_provider=self.window_controller.screenshot,
                    restart_game_callback=self.restart_brawl_stars,
                    restart_scrcpy_callback=self.window_controller.restart_scrcpy_client,
                    restart_emulator_callback=self.window_controller.restart_emulator_profile,
                    press_key_callback=self.discord_press_key,
                    back_callback=self.window_controller.android_back,
                    status_provider=self.telegram_status,
                    stats_provider=self.remote_session_stats,
                    start_push_callback=self.discord_start_push,
                    skip_brawler_callback=self.remote_skip_brawler,
                    remove_brawler_callback=self.remote_remove_brawler,
                    set_target_callback=self.remote_set_target,
                    stop_all_callback=self.discord_stop_all,
                    pause_menu_callback=self.control_window.show,
                )
                self.discord_control.start()
                self.telegram_control = TelegramControlServer(
                    self.control_window.state_path,
                    screenshot_provider=self.window_controller.screenshot,
                    restart_game_callback=self.restart_brawl_stars,
                    restart_scrcpy_callback=self.window_controller.restart_scrcpy_client,
                    restart_emulator_callback=self.window_controller.restart_emulator_profile,
                    press_key_callback=self.discord_press_key,
                    back_callback=self.window_controller.android_back,
                    status_provider=self.telegram_status,
                    stats_provider=self.remote_session_stats,
                    start_push_callback=self.discord_start_push,
                    skip_brawler_callback=self.remote_skip_brawler,
                    remove_brawler_callback=self.remote_remove_brawler,
                    set_target_callback=self.remote_set_target,
                    stop_all_callback=self.discord_stop_all,
                    pause_menu_callback=self.control_window.show,
                )
                self.telegram_control.start()
            else:
                self.discord_control = None
                self.telegram_control = None
            if self.instance_id:
                from gui.instance_registry import build_manifest, write_manifest

                write_manifest(
                    self.instance_id,
                    build_manifest(
                        self.instance_id,
                        pid=os.getpid(),
                        state_path=self.control_window.state_path,
                        metrics_path=self.metrics_path,
                        snapshot=self.build_runtime_snapshot(),
                    ),
                )
            self.was_paused = False
            self.pause_started_at = None
            self.runtime_notice = "Running"
            self.last_recovery = None
            self.recovery_count_session = 0

        def log_runtime_recovery(self, event_type, detail=""):
            from recovery_events import count_session_events, log_recovery, should_send_recovery_alert
            from utils import load_toml_as_dict

            record = log_recovery(
                event_type,
                detail,
                getattr(self, "runtime_notice", "Running"),
                session_id=str(os.getpid()),
            )
            self.last_recovery = record
            self.recovery_count_session = count_session_events(str(os.getpid()))
            discord_config = load_toml_as_dict("cfg/discord_config.toml")
            telegram_config = load_toml_as_dict("cfg/telegram_config.local.toml") or load_toml_as_dict("cfg/telegram_config.toml")
            threshold = int(discord_config.get("recovery_alert_threshold", 3) or 3)
            notify_enabled = bool(
                discord_config.get("notify_on_recovery", False)
                or telegram_config.get("notify_on_recovery", False)
            )
            if notify_enabled and should_send_recovery_alert(event_type, threshold=threshold):
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(async_notify_user(
                            "recovery_alert",
                            self.window_controller.screenshot(),
                            details={
                                "state": self.state or "unknown",
                                "notice": record.get("notice", ""),
                                "event_type": event_type,
                                "detail": detail,
                                "emulator": getattr(self.window_controller, "selected_emulator", ""),
                                "queue_preview": self.build_runtime_snapshot().get("queue_preview", ""),
                                **instance_context_for_notifications(self.instance_id),
                            },
                        ))
                    finally:
                        loop.close()
                        asyncio.set_event_loop(None)
                except Exception:
                    pass
            return record

        def initialize_stage_manager(self):
            row = data[0] if data else {}
            self.Stage_manager.Trophy_observer.win_streak = int(row.get("win_streak", 0) or 0)
            self.Stage_manager.Trophy_observer.current_trophies = int(row.get("trophies", 0) or 0)
            wins = row.get("wins", 0)
            self.Stage_manager.Trophy_observer.current_wins = int(wins) if wins not in ("", None) else 0
            total = self.Stage_manager.Trophy_observer.match_history.get("total", {})
            self.session_totals_start = {
                "victory": int(total.get("victory", 0) or 0),
                "defeat": int(total.get("defeat", 0) or 0),
                "draw": int(total.get("draw", 0) or 0),
            }

        def write_runtime_metrics(self):
            if not (self.pause_menu_ips_graph or self.pause_menu_session_strip):
                return
            write_metrics(
                self.metrics_path,
                self.ips_ema or 0.0,
                self.perf_feed_fps,
                self.ips_history,
                max_samples=self.pause_menu_graph_samples,
                session=self.build_runtime_snapshot() if self.pause_menu_session_strip else None,
            )

        def graceful_shutdown(self, notice="Stopping", notify_reason=None):
            self.runtime_notice = notice
            try:
                self.write_runtime_metrics()
            except Exception:
                pass
            self.window_controller.keys_up(list("wasd"))
            if notify_reason:
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(async_notify_user(
                            notify_reason,
                            self.window_controller.screenshot(),
                            details={"state": self.state or "unknown", "notice": notice},
                        ))
                    finally:
                        loop.close()
                        asyncio.set_event_loop(None)
                except Exception:
                    pass

        def build_runtime_snapshot(self):
            from match_journal import read_recent_matches

            current = self.Stage_manager.brawlers_pick_data[0] if self.Stage_manager.brawlers_pick_data else {}
            total = self.Stage_manager.Trophy_observer.match_history.get("total", {})
            start = getattr(self, "session_totals_start", {})
            trophies = self.Stage_manager.Trophy_observer.current_trophies
            recent = read_recent_matches(limit=1)
            last_match = ""
            if recent:
                item = recent[0]
                last_match = f"{item.get('brawler', '')} {item.get('result', '')} ({item.get('delta', '')})"
            queue_preview = ""
            try:
                from gui.remote_formatting import format_queue_preview_names

                queue = self.Stage_manager.brawlers_pick_data or []
                queue_preview = format_queue_preview_names(queue)
            except Exception:
                queue_preview = ""
            snapshot = {
                "uptime_s": time.time() - self.started_at,
                "state": self.state or "unknown",
                "brawler": current.get("brawler", ""),
                "target": current.get("push_until", ""),
                "trophies": trophies,
                "session_wins": int(total.get("victory", 0) or 0) - int(start.get("victory", 0) or 0),
                "session_losses": int(total.get("defeat", 0) or 0) - int(start.get("defeat", 0) or 0),
                "session_draws": int(total.get("draw", 0) or 0) - int(start.get("draw", 0) or 0),
                "notice": getattr(self, "runtime_notice", "Running"),
                "last_match": last_match,
                "queue_preview": queue_preview,
                "last_recovery": (getattr(self, "last_recovery", None) or {}).get("event_type", ""),
                "recovery_count_session": int(getattr(self, "recovery_count_session", 0) or 0),
                "scrcpy_restarts": int(getattr(self.window_controller, "scrcpy_restart_count", 0) or 0),
                "display_repairs": int(getattr(self.window_controller, "display_repair_count", 0) or 0),
                "app_restarts": int(getattr(self.window_controller, "app_restart_count", 0) or 0),
                "emulator_restarts": int(getattr(self.window_controller, "emulator_restart_count", 0) or 0),
            }
            return snapshot

        def telegram_status(self):
            snapshot = self.build_runtime_snapshot()
            current = self.Stage_manager.brawlers_pick_data[0] if self.Stage_manager.brawlers_pick_data else {}
            status = {
                "state": self.state or "unknown",
                "ips": f"{self.ips_ema:.2f}" if self.ips_ema is not None else "",
                "feed_fps": f"{self.perf_feed_fps:.2f}",
                "emulator": getattr(self.window_controller, "selected_emulator", ""),
                "adb_device": getattr(getattr(self.window_controller, "device", None), "serial", ""),
                "brawler": current.get("brawler", ""),
                "target": current.get("push_until", ""),
                "last_match": snapshot.get("last_match", ""),
                "queue_preview": snapshot.get("queue_preview", ""),
                "last_recovery": snapshot.get("last_recovery", ""),
            }
            return status

        def remote_session_stats(self):
            snapshot = self.build_runtime_snapshot()
            from gui.remote_formatting import build_session_stats

            stats = build_session_stats(snapshot)
            if self.instance_id:
                profile = instance_context_for_notifications(self.instance_id)
                stats["instance_id"] = profile.get("instance_id", "")
                stats["instance_name"] = profile.get("instance_name", "")
            return stats

        def handle_remote_command(self, command):
            from gui.remote_command_router import encode_screenshot_reply
            from runtime_control import write_remote_reply

            action = str(command.get("action") or "").strip()
            args = dict(command.get("args") or {})
            reply_path = command.get("reply_path")
            try:
                if action == "screenshot":
                    payload = encode_screenshot_reply(self.window_controller.screenshot())
                elif action == "push":
                    payload = {"ok": True, "result": self.discord_start_push(args.get("brawler", ""), args.get("target"))}
                elif action == "skip":
                    payload = {"ok": True, "result": self.remote_skip_brawler()}
                elif action == "remove":
                    payload = {"ok": True, "result": self.remote_remove_brawler(args.get("brawler", ""))}
                elif action == "target":
                    payload = {"ok": True, "result": self.remote_set_target(int(args.get("target", 0)))}
                elif action == "restart_game":
                    payload = {"ok": bool(self.restart_brawl_stars()), "result": "Brawl Stars restart finished."}
                elif action == "restart_scrcpy":
                    payload = {"ok": bool(self.window_controller.restart_scrcpy_client()), "result": "Scrcpy restart finished."}
                elif action == "restart_emulator":
                    payload = {"ok": bool(self.window_controller.restart_emulator_profile()), "result": "Emulator restart finished."}
                elif action == "press":
                    payload = {"ok": True, "result": self.discord_press_key(args.get("key", ""))}
                elif action == "back":
                    payload = {"ok": True, "result": self.window_controller.android_back()}
                elif action == "stats":
                    payload = {"ok": True, "result": self.remote_session_stats()}
                elif action == "status":
                    payload = {"ok": True, "result": self.telegram_status()}
                elif action == "queue":
                    from gui.brawler_queue import load_queue
                    from gui.remote_formatting import format_queue_lines

                    payload = {"ok": True, "result": format_queue_lines(load_queue())}
                else:
                    payload = {"ok": False, "error": f"Unknown remote action '{action}'."}
                if payload.get("ok") is False:
                    write_remote_reply(reply_path, payload)
                else:
                    write_remote_reply(reply_path, {"ok": True, "result": payload.get("result", payload)})
            except Exception as exc:
                write_remote_reply(reply_path, {"ok": False, "error": str(exc)})

        def pump_instance_manifest(self):
            if not self.instance_id:
                return
            now = time.time()
            if now - self.last_manifest_heartbeat < 5.0:
                return
            self.last_manifest_heartbeat = now
            from gui.instance_registry import update_manifest_heartbeat

            update_manifest_heartbeat(
                self.instance_id,
                self.build_runtime_snapshot(),
                state_path=self.control_window.state_path,
                metrics_path=self.metrics_path,
            )

        def pump_remote_commands(self):
            if self.instance_id:
                from runtime_control import drain_remote_commands

                drain_remote_commands(self.control_window.state_path, self.handle_remote_command)

        def discord_press_key(self, key):
            normalized = str(key or "").strip().upper()
            self.window_controller.press_key(normalized)
            return True

        def discord_stop_all(self):
            self.graceful_shutdown("Stopping")
            return "PylaAi-XXZ is stopping. The bot process will exit shortly."

        def _apply_remote_queue_change(self, new_queue, message: str):
            from gui.remote_formatting import format_command_result, format_queue_lines

            active = new_queue[0].get("brawler", "") if new_queue else ""
            staged = self.Stage_manager.stage_queue_update(new_queue, reason="remote", reselect_brawler=active)
            write_state(self.control_window.state_path, RUNNING)

            reselect_note = ""
            if staged and active:
                reselect_note = f" Will reselect {active} after returning to lobby."
            elif active:
                reselect_note = " Farm plan unchanged."

            payload = format_command_result("Farm Plan Updated", message + reselect_note, new_queue)
            payload["queue_text"] = format_queue_lines(new_queue)
            return payload

        def discord_start_push(self, brawler: str, target: int | None = None):
            from discord_control import resolve_brawler_choice
            from gui.brawler_queue import load_queue
            from gui.remote_queue_commands import prioritize_brawler_in_queue

            resolved = resolve_brawler_choice(brawler)
            if not resolved:
                return False

            queue = self.Stage_manager.brawlers_pick_data or load_queue()
            new_queue, message = prioritize_brawler_in_queue(queue, resolved, target)
            return self._apply_remote_queue_change(new_queue, message)

        def remote_skip_brawler(self):
            from gui.brawler_queue import load_queue, normalize_queue
            from gui.remote_queue_commands import skip_current_brawler

            queue = self.Stage_manager.brawlers_pick_data or load_queue()
            new_queue, message = skip_current_brawler(queue)
            if normalize_queue(new_queue) == normalize_queue(queue):
                return message
            return self._apply_remote_queue_change(new_queue, message)

        def remote_remove_brawler(self, brawler: str):
            from discord_control import resolve_brawler_choice
            from gui.brawler_queue import load_queue, normalize_queue
            from gui.remote_queue_commands import remove_brawler_from_queue

            resolved = resolve_brawler_choice(brawler)
            if not resolved:
                return False
            queue = self.Stage_manager.brawlers_pick_data or load_queue()
            new_queue, message = remove_brawler_from_queue(queue, resolved)
            if normalize_queue(new_queue) == normalize_queue(queue):
                return message
            return self._apply_remote_queue_change(new_queue, message)

        def remote_set_target(self, target: int):
            from gui.brawler_queue import load_queue, normalize_queue
            from gui.remote_queue_commands import set_active_target

            queue = self.Stage_manager.brawlers_pick_data or load_queue()
            new_queue, message = set_active_target(queue, int(target))
            if normalize_queue(new_queue) == normalize_queue(queue):
                return message
            return self._apply_remote_queue_change(new_queue, message)

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
                print("Bot got stuck. User notified. Shutting down.")
                self.graceful_shutdown("Bot stuck", notify_reason="bot_is_stuck")
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
            self.runtime_notice = "Slow feed recovery"
            self.log_runtime_recovery("slow_feed", f"attempt {self.slow_feed_recovery_attempts}")
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

        def update_terminal_status(self):
            if not self.console_ips or self.ips_ema is None:
                return
            now = time.time()
            if now - self.last_terminal_summary_at >= self.terminal_summary_seconds:
                self.last_terminal_summary_at = now
                brawler = ""
                if self.Stage_manager.brawlers_pick_data:
                    brawler = self.Stage_manager.brawlers_pick_data[0].get("brawler", "")
                pending = ""
                pending_queue = getattr(self.Stage_manager, "pending_queue", None)
                if pending_queue:
                    pending = pending_queue[0].get("brawler", "")
                front = pending or brawler or "-"
                runtime_log.log_status_line(
                    f"IPS {self.ips_ema:.1f} | state {self.state or '?'} | brawler {front}"
                )
            else:
                runtime_log.log_status_line(f"IPS {self.ips_ema:.1f}")

        def recover_low_ips(self, current_ips):
            now = time.time()
            if now - self.started_at < self.low_ips_startup_grace_seconds:
                return False
            if self.state == "match" and now - self.match_ready_at < self.low_ips_match_grace_seconds:
                return False
            if current_ips >= self.low_ips_threshold:
                if self.low_ips_since is not None:
                    runtime_log.log_info("recovery", f"IPS recovered to {current_ips:.2f}; clearing low-IPS watchdog.")
                self.reset_low_ips_watchdog(recovered=True)
                self.runtime_notice = "Running"
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
            self.runtime_notice = "Low IPS recovery"
            self.log_runtime_recovery("low_ips", f"ips={current_ips:.2f}")
            self.window_controller.keys_up(list("wasd"))
            runtime_log.log_warn(
                "recovery",
                (
                    f"IPS stayed low ({current_ips:.2f}, frame age {frame_age:.1f}s) "
                    f"for {low_for:.1f}s; recovery attempt {self.low_ips_recovery_attempts}."
                ),
            )

            if self.low_ips_recovery_attempts >= self.low_ips_emulator_restart_after:
                if frame_age <= 5:
                    runtime_log.log_warn(
                        "recovery",
                        "Low IPS is still happening but scrcpy frames are fresh; restarting Brawl Stars/scrcpy instead.",
                    )
                    self.restart_brawl_stars()
                    self.low_ips_recovery_attempts = max(
                        self.low_ips_app_restart_after,
                        self.low_ips_emulator_restart_after - 1,
                    )
                else:
                    runtime_log.log_warn("recovery", "Low IPS did not recover after app/scrcpy restarts; restarting emulator profile.")
                    if self.window_controller.restart_emulator_profile():
                        self.low_ips_recovery_attempts = 0
                    else:
                        runtime_log.log_warn("recovery", "Emulator restart was not available; keeping bot alive and retrying scrcpy recovery.")
                        if not self.window_controller.restart_scrcpy_client():
                            self.handle_offline_emulator()
                        self.low_ips_recovery_attempts = max(
                            self.low_ips_app_restart_after,
                            self.low_ips_emulator_restart_after - 1,
                        )
            elif self.low_ips_recovery_attempts >= self.low_ips_app_restart_after:
                runtime_log.log_warn("recovery", "Low IPS persisted; restarting Brawl Stars and scrcpy.")
                self.restart_brawl_stars()
            else:
                runtime_log.log_warn("recovery", "Low IPS detected; restarting scrcpy feed.")
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

            feed_fps = getattr(self, "perf_feed_fps", 0.0) or 0.0
            if feed_fps >= 3.0:
                print(
                    f"Match image unchanged for {frozen_for:.1f}s but feed FPS is healthy "
                    f"({feed_fps:.1f}); skipping app restart."
                )
                self.last_visual_change_time = now
                return False

            print(
                f"Match image did not change for {frozen_for:.1f}s "
                f"(diff {diff:.3f}); restarting Brawl Stars and scrcpy."
            )
            self.runtime_notice = "Visual freeze recovery"
            self.log_runtime_recovery("visual_freeze", "debug overlay unchanged")
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
            self.runtime_notice = "Screen freeze recovery"
            self.log_runtime_recovery("global_freeze", "screen hash unchanged")
            runtime_log.log_warn(
                "recovery",
                (
                    "Screen health check found no visible change for "
                    f"{self.global_freeze_health_interval:.0f}s (diff {diff:.3f}); "
                    f"recovery attempt {self.global_freeze_recovery_attempts}."
                ),
            )
            self.window_controller.keys_up(list("wasd"))
            if self.global_freeze_recovery_attempts >= self.global_freeze_emulator_restart_after:
                runtime_log.log_warn("recovery", "Screen is still frozen after app recovery; restarting emulator profile.")
                if self.window_controller.restart_emulator_profile():
                    self.reset_visual_freeze_watchdog()
                    self.reset_low_ips_watchdog(recovered=False)
                    self.last_processed_frame_id = -1
                else:
                    runtime_log.log_warn(
                        "recovery",
                        "Emulator restart was not available yet; restarting Brawl Stars and scrcpy instead.",
                    )
                    self.restart_brawl_stars()
            else:
                runtime_log.log_warn("recovery", "Restarting Brawl Stars and scrcpy first.")
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

        def handle_brawl_pass_screen(self, frame):
            screenshot_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            if not (is_in_brawl_pass(screenshot_bgr) or is_in_star_road(screenshot_bgr)):
                return False
            print("Brawl Pass panel detected; backing out.")
            self.window_controller.keys_up(list("wasd"))
            self.Stage_manager.quit_shop()
            self.lobby_entered_at = None
            self.last_lobby_start_press = time.time()
            return True

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
            if self.state == "match":
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

            if (
                getattr(self.Stage_manager, "pending_queue", None)
                or getattr(self.Stage_manager, "pending_brawler_reselection", False)
            ):
                return False

            if now - self.last_lobby_start_press >= self.lobby_start_retry_interval:
                runtime_log.log_debug("match", "Lobby watchdog: pressing start again.")
                self.window_controller.keys_up(list("wasd"))
                self.window_controller.press_key("Q")
                self.last_lobby_start_press = now

            lobby_age = now - self.lobby_entered_at
            if lobby_age < self.lobby_stuck_restart_seconds:
                return False

            runtime_log.log_warn(
                "recovery",
                f"Lobby did not enter a match for {lobby_age:.1f}s; restarting Brawl Stars.",
            )
            self.runtime_notice = "Lobby stuck recovery"
            self.log_runtime_recovery("lobby_stuck", f"state={state}")
            self.restart_brawl_stars()
            return True

        def apply_state_context_guard(self, detected_state, previous_state, *, allow_panel_escape=False):
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
            if (
                previous_state == "match"
                and detected_state in {"brawler_selection", "shop"}
                and state == detected_state
            ):
                return apply_in_match_overlay_guard(
                    state,
                    detected_state,
                    previous_state,
                    allow_panel_escape=allow_panel_escape,
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

            if self.handle_brawl_pass_screen(frame):
                return

            if self.handle_disconnect_screen(frame):
                return

            if self.Time_management.state_check():
                screenshot_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                allow_panel_escape = (
                    is_in_brawl_pass(screenshot_bgr) or is_in_star_road(screenshot_bgr)
                )
                detected_state = get_state(frame)
                previous_state = self.state
                state = self.apply_state_context_guard(
                    detected_state,
                    previous_state,
                    allow_panel_escape=allow_panel_escape,
                )
                self.state = state
                if state != "match":
                    self.Play.time_since_last_proceeding = time.time()
                if previous_state == "match" and state != "match":
                    self.Play.reset_match_control_state()
                    try:
                        self.window_controller.repair_display_after_match()
                    except Exception as exc:
                        print(f"Post-match display repair failed: {exc}")
                elif previous_state != "match" and state == "match":
                    self.Play.reset_match_control_state()
                    self.match_ready_at = time.time() + self.match_warmup_seconds
                    self.Stage_manager.active_match_brawler = self.Play.current_brawler or (
                        self.Stage_manager.brawlers_pick_data[0].get("brawler", "")
                        if self.Stage_manager.brawlers_pick_data else ""
                    )
                    if previous_state in {"lobby", "match_making"}:
                        self.Stage_manager.reset_prestige_reward_gate()
                frame_data = None
                self.Stage_manager.do_state(state, frame_data)
                if state == "lobby":
                    self.match_launch_pending = True
                    if (
                        not self.Stage_manager.pending_queue
                        and self.Stage_manager.brawlers_pick_data
                    ):
                        active = self.Stage_manager.brawlers_pick_data[0].get("brawler", "")
                        if active:
                            self.Play.current_brawler = active
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
            if self.state not in {None, "match_making", "lobby", "shop", "brawler_selection"}:
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
            self.Stage_manager.active_match_brawler = self.Play.current_brawler or (
                self.Stage_manager.brawlers_pick_data[0].get("brawler", "")
                if self.Stage_manager.brawlers_pick_data else ""
            )
            if previous_state in {"lobby", "match_making"}:
                self.Stage_manager.reset_prestige_reward_gate()
            runtime_log.log_debug("match", "Fast match start detected; movement loop active.")
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
            self.runtime_notice = "Disconnect recovery"
            self.log_runtime_recovery("disconnect_reload", "idle disconnect dialog")
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
            self.runtime_notice = "Emulator offline"
            self.log_runtime_recovery("emulator_offline", "adb device missing")
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
            self.runtime_notice = "Recovering scrcpy"
            self.log_runtime_recovery("stale_scrcpy", "restarting video feed")

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
                    self.runtime_notice = "Running"
                    print("Bot resumed.")
                return False

            if not self.was_paused:
                self.window_controller.keys_up(list("wasd"))
                self.Play.reset_match_control_state()
                self.was_paused = True
                self.pause_started_at = time.time()
                self.runtime_notice = "Paused"
                print("Bot paused.")
            self.write_runtime_metrics()
            time.sleep(0.1)
            return True

        def ensure_pause_menu_window(self):
            if not self.pause_menu_auto_reopen:
                return
            now = time.time()
            if now - self.last_pause_menu_check < 2.0:
                return
            self.last_pause_menu_check = now
            if self.control_window.is_running():
                return
            print("Pause menu closed — reopening compact control bar.")
            self.control_window.start()
            self.control_window.show_compact()

        def main(self): #this is for timer to stop after time
            s_time = time.time()
            c = 0
            while True:
                if is_stop_requested(self.control_window.state_path):
                    print("Remote stop requested; shutting down bot.")
                    self.graceful_shutdown("Stopping")
                    break

                self.pump_remote_commands()
                self.pump_instance_manifest()
                self.ensure_pause_menu_window()

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
                    if elapsed > 0:
                        current_ips = c / elapsed
                        self.ips_ema = current_ips if self.ips_ema is None else (self.ips_ema * 0.75 + current_ips * 0.25)
                        if self.ips_ema is not None:
                            if self.pause_menu_ips_graph:
                                self.ips_history.append(self.ips_ema)
                            if self.pause_menu_ips_graph or self.pause_menu_session_strip:
                                self.write_runtime_metrics()
                        if self.console_ips:
                            self.update_terminal_status()
                            if self.recover_low_ips(self.ips_ema):
                                s_time = time.time()
                                c = 0
                                continue
                            if self.ips_ema is not None and self.ips_ema < 3 and time.time() - self.low_frame_fps_warning_time > 20:
                                self.print_low_ips_detail(self.ips_ema)
                                self.low_frame_fps_warning_time = time.time()
                        elif not self.visual_debug:
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
                        runtime_log.log_warn("recovery", f"{e} Recovering scrcpy feed.")
                    self.handle_stale_scrcpy_feed()
                    continue

                _, last_ft = self.window_controller.get_latest_frame()
                if last_ft > 0 and (time.time() - last_ft) > self.window_controller.FRAME_STALE_TIMEOUT:
                    self.handle_stale_scrcpy_feed(last_ft)
                    continue

                self.stale_feed_recovery_attempts = 0
                self.Play.pump_visual_debug_display()

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
                    time.sleep(0.005)
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

                screenshot_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                if self.state == "match" and (
                    is_in_brawl_pass(screenshot_bgr) or is_in_star_road(screenshot_bgr)
                ):
                    self.handle_brawl_pass_screen(frame)
                    time.sleep(0.05)
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

            if self.discord_control is not None:
                self.discord_control.close()
            if self.telegram_control is not None:
                self.telegram_control.close()
            self.control_window.close()
            if self.instance_id:
                from gui.instance_registry import remove_manifest

                remove_manifest(self.instance_id)

    main = Main()
    main.main()


def run_instance_worker(instance_id: str):
    from gui.instance_config import apply_instance_overrides, set_active_instance
    from gui.brawler_queue import load_queue

    set_active_instance(instance_id)
    profile = apply_instance_overrides(instance_id)
    if not profile:
        raise RuntimeError(f"Unknown instance profile '{instance_id}'.")
    queue = load_queue()
    if not queue:
        raise RuntimeError(f"Instance '{instance_id}' has an empty farm plan.")
    runtime_log.log_info("startup", f"Starting Pyla-RL worker for instance '{instance_id}' on port {profile['emulator_port']}.")
    pyla_main(queue)


def run_app():
    from gui.brand import FREE_NOTICE, OFFICIAL_GITHUB
    from tools.launcher_bat import remove_legacy_launchers

    remove_legacy_launchers(Path(__file__).resolve().parent)

    runtime_log.log_info("startup", f"{FREE_NOTICE} Official source: {OFFICIAL_GITHUB}")
    all_brawlers = get_brawler_list()
    if api_base_url != "localhost":
        update_missing_brawlers_info(all_brawlers)
        check_version()
        update_wall_model_classes()
        if not current_wall_model_is_latest():
            print("New Wall detection model found, downloading... (this might take a few minutes depending on your internet speed)")
            get_latest_wall_model_file()

    app = App(login, SelectBrawler, pyla_main, all_brawlers, HubMenu)
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
    import argparse

    parser = argparse.ArgumentParser(description="Pyla-RL")
    parser.add_argument("--instance", default="", help="Run as a multi-instance worker for the given instance id.")
    args = parser.parse_args()
    try:
        if str(args.instance or "").strip():
            run_instance_worker(str(args.instance).strip())
        else:
            run_app()
    except Exception as e:
        write_crash_log(e)
        try:
            input("Press Enter to close...")
        except EOFError:
            pass
        raise
