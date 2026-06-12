import asyncio
import gc
import os
import platform
import subprocess
import sys
import threading
import time
import traceback
import warnings
from collections import deque
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent
_INSTALL_ROOT = _APP_DIR.parent
for _path in (_APP_DIR, _INSTALL_ROOT):
    _entry = str(_path)
    if _path.is_dir() and _entry not in sys.path:
        sys.path.insert(0, _entry)

if __name__ == "__main__" and len(sys.argv) >= 9 and sys.argv[1] in ("--debug-viewer-worker", "--viewer-worker"):
    from debug_view import DEFAULT_DEBUG_VIEW_FPS, run_viewer_worker

    run_viewer_worker(
        shared_memory_name=sys.argv[2],
        debug_memory_name=sys.argv[3],
        height=int(sys.argv[4]),
        width=int(sys.argv[5]),
        channels=int(sys.argv[6]),
        dtype_text=sys.argv[7],
        title=sys.argv[8],
        clip_fps=float(sys.argv[9]) if len(sys.argv) >= 10 else DEFAULT_DEBUG_VIEW_FPS,
        record_clips=(len(sys.argv) >= 11 and sys.argv[10] == "1"),
    )
    sys.exit(0)

# requests<2.34 warns when urllib3>=2.7 is installed; harmless but noisy on every import.
warnings.filterwarnings("ignore", message=".*doesn't match a supported version.*", module="requests")


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
        return
    os.environ["PYLAAI_NUMPY_REPAIR"] = "1"
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-deps", "numpy<2.0.0",
    ])


repair_numpy_before_cv2_import()

try:
    import cv2
except ModuleNotFoundError:
    raise SystemExit(1) from None

from gui.win_dpi import bootstrap_windows_dpi

bootstrap_windows_dpi()

from adbutils import AdbError
from discord_control import DiscordControlServer
from gui.qml_hub import QmlHub
from gui.login import login
from gui.main import App
from gui.select_brawler import SelectBrawler
from lobby_automation import LobbyAutomation
from play import Play
from runtime_control import (
    PAUSED,
    RUNNING,
    RuntimeControlWindow,
    is_stop_requested,
    read_state,
    request_stop,
    write_state,
)
from runtime_metrics import metrics_path_for_pid, write_metrics
from stage_manager import StageManager
from state_finder import get_state, is_in_brawl_pass, is_in_star_road
from telegram_control import TelegramControlServer
from time_management import TimeManagement
from core.integration import (
    build_runtime_control,
    emit_recovery_event,
    format_state_label,
    get_webhook_settings,
    migrate_bot_config,
    normalize_queue,
    on_queue_file_changed,
    save_queue_data,
)
from utils import (
    api_base_url,
    async_notify_user,
    check_version,
    current_wall_model_is_latest,
    get_brawler_list,
    get_latest_version,
    get_latest_wall_model_file,
    load_pyla_script,
    load_toml_as_dict,
    notify_user,
    resolve_project_path,
    update_missing_brawlers_info,
    update_wall_model_classes,
)
import window_controller

pyla_version = load_toml_as_dict("./cfg/general_config.toml")["pyla_version"]
migrate_bot_config()


def configure_terminal_output():
    import runtime_log
    from logger_setup import setup_logging_if_enabled

    runtime_log.configure()
    log_path = setup_logging_if_enabled()
    if platform.architecture()[0] != "64bit":
        runtime_log.log_warn("startup", "Pyla-RL is running on 32-bit Python.")
    return log_path


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


def apply_play_order(queue_data):
    play_order = str(load_toml_as_dict("cfg/general_config.toml").get("play_order", "in_order")).strip().lower()
    if play_order == "lowest_to_highest":
        ordered = sorted(queue_data, key=lambda item: int(item.get("trophies", 0) or 0))
    elif play_order == "highest_to_lowest":
        ordered = sorted(queue_data, key=lambda item: int(item.get("trophies", 0) or 0), reverse=True)
    else:
        return queue_data
    for item in ordered:
        item["automatically_pick"] = True
    return ordered


OUT_OF_MATCH_REWARD_STATES = {"prestige_reward", "trophy_reward"}
TROPHY_REWARD_FOLLOWUP_STATES = {"reward_unlock"}
STAR_DROP_STATES = {
    "star_drop",
    "daily_star_drop",
    "nova_star_drop",
    "star_drop_regular",
    "star_drop_angelic",
    "star_drop_demonic",
    "star_drop_starr_nova",
}
MATCH_RESULT_STATES = {
    "end_victory",
    "end_defeat",
    "end_draw",
    "end_1st",
    "end_2nd",
    "end_3rd",
    "end_4th",
    "end_trio_showdown_0",
    "end_trio_showdown_1",
    "end_trio_showdown_2",
    "end_trio_showdown_3",
}
STUCK_RECOVERY_STATES = {
    "lobby",
    "reward_unlock",
    "trophy_reward",
    "prestige_reward",
    "brawler_selection",
}


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


def _log_stuck_recovery(worker, event_type: str, detail: str, step: str):
    from gui.recovery_screenshots import save_recovery_screenshot
    from recovery_events import log_recovery

    screenshot_path = ""
    try:
        screenshot_path = save_recovery_screenshot(worker.window_controller.screenshot(), step)
    except Exception:
        pass
    log_recovery(event_type, detail=detail, screenshot_path=screenshot_path)


def run_stuck_recovery(worker, state):
    now = time.time()
    if state == "match" or getattr(worker, "in_cooldown", False):
        worker.stuck_since = None
        worker.stuck_app_restart_count = 0
        if state != "lobby":
            worker.lobby_entered_at = None
        return False

    if state not in STUCK_RECOVERY_STATES:
        worker.stuck_since = None
        if state != "lobby":
            worker.lobby_entered_at = None
        return False

    if worker.stuck_since is None:
        worker.stuck_since = now
    if state == "lobby" and worker.lobby_entered_at is None:
        worker.lobby_entered_at = now

    stuck_age = now - worker.stuck_since

    if now - worker.last_stuck_recovery_press >= worker.lobby_start_retry_interval:
        import runtime_log

        runtime_log.log_info("recovery", f"Stuck recovery: retrying in {state}.")
        worker.window_controller.keys_up(list("wasd"))
        if state in worker.Stage_manager.states:
            try:
                worker.Stage_manager.do_state(state, None)
            except Exception as exc:
                runtime_log.log_warn("recovery", f"Stuck recovery state handler failed: {exc}")
        worker.window_controller.press_key("Q")
        worker.last_stuck_recovery_press = now
        if state == "lobby":
            worker.last_lobby_start_press = now

    if stuck_age < worker.lobby_stuck_restart_seconds:
        return False

    if now - worker.last_stuck_recovery_at < worker.lobby_stuck_restart_seconds:
        return False

    worker.last_stuck_recovery_at = now
    if worker.stuck_app_restart_count < 2:
        worker.stuck_app_restart_count += 1
        import runtime_log

        runtime_log.log_warn(
            "recovery",
            f"Stuck in {state} for {stuck_age:.1f}s; restarting Brawl Stars "
            f"(attempt {worker.stuck_app_restart_count}).",
        )
        _log_stuck_recovery(worker, "app_restart", f"state={state}", "app_restart")
        if getattr(worker, "ping_when_stuck", False):
            notify_user("bot_is_stuck", worker.window_controller.screenshot(), worker.Stage_manager)
        if worker.restart_brawl_stars():
            worker.stuck_since = now
        return True

    if not getattr(worker.window_controller, "emulator_autorestart", False):
        return False

    import runtime_log

    runtime_log.log_warn(
        "recovery",
        f"Stuck in {state} after app restarts; restarting emulator profile.",
    )
    _log_stuck_recovery(worker, "emulator_restart", f"state={state}", "emulator_restart")
    if getattr(worker, "ping_when_stuck", False):
        notify_user("bot_is_stuck", worker.window_controller.screenshot(), worker.Stage_manager)
    if worker.window_controller.restart_emulator_profile():
        worker.stuck_since = None
        worker.stuck_app_restart_count = 0
        worker.lobby_entered_at = None
        return True
    return False


def pyla_main(data):
    import runtime_log
    from gui.instance_config import get_active_instance_id, instance_context_for_notifications

    configure_terminal_output()

    class Main:
        def __init__(self):
            self.instance_id = get_active_instance_id()
            general_config = load_toml_as_dict("cfg/general_config.toml")
            webhook_settings = get_webhook_settings()
            self.max_ips = parse_max_ips(general_config.get("max_ips", 0))
            self.duplicate_frame_replay_enabled = str(
                general_config.get("duplicate_frame_replay_enabled", "yes")
            ).strip().lower() in ("yes", "true", "1", "on")
            self.duplicate_frame_replay_max_ips = parse_max_ips(
                general_config.get("duplicate_frame_replay_max_ips", 25)
            ) or 15

            self.window_controller = window_controller.WindowController()
            queue = normalize_queue(data)
            queue = apply_play_order(queue)
            if self.instance_id:
                from gui.session_state import apply_session_resume_to_queue

                queue = apply_session_resume_to_queue(queue, self.instance_id)
            if not queue:
                raise ValueError("No valid brawler data found. Add a brawler configuration in the Hub before starting.")
            save_queue_data(queue)

            current_playstyle = load_toml_as_dict("cfg/bot_config.toml").get(
                "current_playstyle", "team_showdown.pyla"
            )
            self.playstyle_info, pyla_code = load_pyla_script(current_playstyle)
            self.Play = Play(*self.load_models(), self.window_controller, pyla_code)
            self.Time_management = TimeManagement()
            self.lobby_automator = LobbyAutomation(self.window_controller)

            self.metrics_path = metrics_path_for_pid(os.getpid())
            self.control_window = RuntimeControlWindow(metrics_path=self.metrics_path)
            self.control_window.start()
            self.runtime_control = build_runtime_control(self.control_window.state_path)
            self.stop_event = threading.Event()

            self.Stage_manager = StageManager(
                queue,
                self.lobby_automator,
                self.window_controller,
                self.playstyle_info,
                self.get_latest_state,
                runtime_control=self.runtime_control,
            )
            self.states_requiring_data = ["lobby"]
            self.no_detections_action_threshold = 60 * 8
            self.state = None
            self.state_lock = threading.Lock()
            self.latest_state_frame_time = 0.0
            self.state_checker_stop_event = threading.Event()
            self.state_checker_thread = None
            self.update_trophy_observer()

            self.run_for_minutes = int(general_config.get("run_for_minutes", 0) or 0)
            self.webhook_ping_every_minutes = int(webhook_settings.get("ping_every_x_minutes", 0) or 0)
            self.ping_when_stuck = webhook_settings.get("ping_when_stuck", False)
            self.time_since_last_webhook_ping = time.time()
            self.start_time = time.time()
            self.started_at = time.time()
            self.in_cooldown = False
            self.cooldown_start_time = 0
            self.cooldown_duration = 3 * 60
            self.picked_first_brawler = False
            time_thresholds = load_toml_as_dict("cfg/time_tresholds.toml")
            self.check_if_brawl_stars_crashed_timer = float(
                time_thresholds.get("check_if_brawl_stars_crashed", 60)
            )
            self.lobby_start_retry_interval = float(time_thresholds.get("lobby_start_retry", 8.0))
            self.lobby_stuck_restart_seconds = float(time_thresholds.get("lobby_stuck_restart", 120.0))
            self.post_match_reward_window_seconds = float(
                time_thresholds.get("post_match_reward_window_seconds", 120.0)
            )
            self.lobby_after_match_confirm_seconds = float(
                time_thresholds.get("lobby_after_match_confirm_seconds", 3.0)
            )
            self.post_match_reward_until = 0.0
            self.reward_chain_seen = False
            self.lobby_seen_since_match = False
            self.match_launch_pending = False
            self.pending_lobby_since = None
            self.pending_lobby_notice = 0.0
            self.last_ignored_prestige_state_time = 0.0
            self.last_ignored_star_drop_state_time = 0.0
            self.guarded_state = None
            self.stuck_since = None
            self.last_stuck_recovery_press = 0.0
            self.stuck_app_restart_count = 0
            self.last_stuck_recovery_at = 0.0
            self.lobby_entered_at = None
            self.last_lobby_start_press = 0.0
            self.time_since_checked_if_brawl_stars_crashed = time.time()
            self.last_processed_frame_id = -1
            self.ips_ema = None
            self.perf_feed_fps = 0.0
            self.perf_frame_count = 0
            self.perf_last_frame_time = time.time()
            self.perf_last_frame_id = -1
            self.ips_history = deque(maxlen=45)
            from performance_autotuner import PerformanceAutoTuner

            self.performance_autotuner = PerformanceAutoTuner(target_ips=float(self.max_ips or 0))
            self._last_digest_sent_at = 0.0

            self.window_controller.screenshot()
            self.start_state_checker()
            self._wire_remote_control()
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

        def _wire_remote_control(self):
            if self.instance_id:
                self.discord_control = None
                self.telegram_control = None
                return
            callbacks = dict(
                screenshot_provider=self.window_controller.screenshot,
                restart_game_callback=self.restart_brawl_stars,
                restart_scrcpy_callback=self.window_controller.restart_scrcpy_client,
                restart_emulator_callback=self.window_controller.restart_emulator_profile,
                press_key_callback=self.discord_press_key,
                back_callback=self.window_controller.android_back,
                status_provider=self.remote_status,
                stats_provider=self.remote_session_stats,
                start_push_callback=self.discord_start_push,
                skip_brawler_callback=self.remote_skip_brawler,
                remove_brawler_callback=self.remote_remove_brawler,
                set_target_callback=self.remote_set_target,
                stop_all_callback=self.discord_stop_all,
                pause_menu_callback=self.control_window.show,
            )
            self.discord_control = DiscordControlServer(self.control_window.state_path, **callbacks)
            self.telegram_control = TelegramControlServer(self.control_window.state_path, **callbacks)
            self.discord_control.start()
            self.telegram_control.start()

        @staticmethod
        def load_models():
            return [
                resolve_project_path("models/mainInGameModel.onnx"),
                resolve_project_path("models/tileDetector.onnx"),
                resolve_project_path("models/closeTileDetector.onnx"),
            ]

        def update_trophy_observer(self):
            current = self.Stage_manager.brawlers_pick_data[0]
            self.Stage_manager.Trophy_observer.win_streak = current.get("win_streak", 0)
            self.Stage_manager.Trophy_observer.current_trophies = current.get("trophies", 0)
            wins = current.get("wins", 0)
            self.Stage_manager.Trophy_observer.current_wins = int(wins) if wins not in ("", None) else 0

        def should_stop(self):
            return (
                is_stop_requested(self.control_window.state_path)
                or self.stop_event.is_set()
                or self.runtime_control.should_stop()
            )

        def should_pause(self):
            return self.runtime_control.should_pause()

        def runtime_control_label(self):
            from gui.remote_formatting import runtime_label_from_state

            return runtime_label_from_state(read_state(self.control_window.state_path))

        def update_runtime_control_notice(self):
            label = self.runtime_control_label()
            prev = getattr(self, "_last_runtime_control_label", None)
            if label == prev:
                return
            if label == "paused":
                runtime_log.log_info(
                    "state",
                    "Pyla-RL is paused. Press F8 or use Discord/Telegram /start to resume.",
                )
            elif prev == "paused" and label == "running":
                runtime_log.log_info("state", "Pyla-RL resumed.")
            self._last_runtime_control_label = label

        def sleep_interruptible(self, duration, allow_pause=True, poll_interval=0.1):
            end_time = time.time() + duration
            while time.time() < end_time:
                if self.should_stop():
                    return "stop"
                if allow_pause and self.should_pause():
                    return "pause"
                time.sleep(min(poll_interval, max(end_time - time.time(), 0)))
            return None

        def start_state_checker(self):
            if self.state_checker_thread and self.state_checker_thread.is_alive():
                return
            self.state_checker_stop_event.clear()
            self.state_checker_thread = threading.Thread(
                target=self.state_checker_loop, daemon=True, name="pyla-state-checker"
            )
            self.state_checker_thread.start()

        def stop_state_checker(self):
            self.state_checker_stop_event.set()
            if self.state_checker_thread and self.state_checker_thread.is_alive():
                self.state_checker_thread.join(timeout=1.0)

        def set_latest_state(self, state):
            with self.state_lock:
                self.state = state

        def get_latest_state(self):
            with self.state_lock:
                return self.state

        def state_checker_loop(self):
            last_checked_frame_time = 0.0
            while not self.state_checker_stop_event.is_set():
                frame, frame_time = self.window_controller.get_latest_frame()
                if frame is None or frame_time <= last_checked_frame_time:
                    self.state_checker_stop_event.wait(0.01)
                    continue
                last_checked_frame_time = frame_time
                try:
                    self.set_latest_state(get_state(frame))
                except Exception as exc:
                    runtime_log.log_warn("recovery", f"State checker failed: {exc}")
                    self.state_checker_stop_event.wait(0.1)

        def handle_detected_state(self, state):
            if state is None:
                return
            self.set_latest_state(state)
            self.guarded_state = state
            runtime_log.log_info("state", format_state_label(state))
            on_queue_file_changed(self.Stage_manager)
            self.Stage_manager.do_state(state, None)
            if state != "match":
                self.Play.time_since_last_proceeding = time.time()

        def apply_state_context_guard(self, detected_state, previous_state, *, allow_panel_escape=False):
            now = time.time()
            if detected_state in MATCH_RESULT_STATES or (
                detected_state and str(detected_state).startswith("end_")
            ):
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
                state = apply_in_match_overlay_guard(
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
                        runtime_log.log_info(
                            "state",
                            "Ignoring lobby detection until it is stable after match "
                            f"({pending_for:.1f}/{self.lobby_after_match_confirm_seconds:.1f}s).",
                        )
                        self.pending_lobby_notice = now
                    return "match"
                self.pending_lobby_since = None

            if detected_state in OUT_OF_MATCH_REWARD_STATES and state != detected_state:
                if now - self.last_ignored_prestige_state_time >= 5.0:
                    runtime_log.log_info(
                        "state",
                        f"Ignoring {detected_state} detection until a match result or lobby is confirmed.",
                    )
                    self.last_ignored_prestige_state_time = now
            if detected_state in STAR_DROP_STATES and state != detected_state:
                if now - self.last_ignored_star_drop_state_time >= 5.0:
                    runtime_log.log_info(
                        "state",
                        "Ignoring star_drop detection because no post-match reward chain is active.",
                    )
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

        def handle_stuck_recovery(self, state):
            return run_stuck_recovery(self, state)

        def wait_while_paused(self):
            self.window_controller.release_movement()
            self.runtime_control.mark_paused()
            while self.should_pause() and not self.should_stop():
                if self.sleep_interruptible(0.75, allow_pause=False) == "stop":
                    return
            if not self.should_stop():
                self.runtime_control.mark_running()
                self.time_since_last_webhook_ping = time.time()

        def handle_pause_request(self):
            if self.should_pause() and not self.should_stop():
                self.wait_while_paused()

        def manage_time_tasks(self, frame):
            if self.Time_management.state_check():
                screenshot_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                allow_panel_escape = (
                    is_in_brawl_pass(screenshot_bgr) or is_in_star_road(screenshot_bgr)
                )
                detected_state = get_state(frame)
                previous_state = self.guarded_state
                state = self.apply_state_context_guard(
                    detected_state,
                    previous_state,
                    allow_panel_escape=allow_panel_escape,
                )
                if previous_state == "match" and state != "match":
                    if hasattr(self.Play, "reset_match_control_state"):
                        self.Play.reset_match_control_state()
                elif previous_state != "match" and state == "match":
                    if hasattr(self.Play, "reset_match_control_state"):
                        self.Play.reset_match_control_state()
                    if previous_state in {"lobby", "match_making"}:
                        self.Stage_manager.reset_prestige_reward_gate()
                if state is not None:
                    self.handle_detected_state(state)
                if state == "lobby":
                    self.match_launch_pending = True
                self.handle_stuck_recovery(state)
            if self.Time_management.no_detections_check():
                now = time.time()
                for key, value in self.Play.time_since_detections.items():
                    if now - value > self.no_detections_action_threshold:
                        self.restart_brawl_stars()
            if self.Time_management.idle_check():
                self.lobby_automator.check_for_idle(frame)
            now = time.time()
            if self.webhook_ping_every_minutes and now - self.time_since_last_webhook_ping >= self.webhook_ping_every_minutes * 60:
                notify_user("regular_minutes_ping", self.window_controller.screenshot(), self.Stage_manager)
                self.time_since_last_webhook_ping = now

        def record_feed_fps(self):
            frame_id = self.window_controller.get_latest_frame_id()
            now = time.time()
            if frame_id != self.perf_last_frame_id:
                self.perf_frame_count += 1
                self.perf_last_frame_id = frame_id
            elapsed = now - self.perf_last_frame_time
            if elapsed >= 1.0:
                self.perf_feed_fps = self.perf_frame_count / elapsed
                self.perf_frame_count = 0
                self.perf_last_frame_time = now

        def restart_brawl_stars(self):
            if not self.window_controller.restart_brawl_stars():
                return False
            if not self.window_controller.restart_scrcpy_client():
                emit_recovery_event("scrcpy_restart", "after brawl stars restart")
                return False
            self.Play.time_since_detections["player"] = time.time()
            self.Play.time_since_detections["enemy"] = time.time()
            if not self.window_controller.is_brawl_stars_running():
                if self.ping_when_stuck:
                    notify_user("bot_is_stuck", self.window_controller.screenshot(), self.Stage_manager)
                self.stop_gracefully()
                return False
            return True

        def check_and_handle_brawl_stars_crash(self):
            now = time.time()
            if now - self.time_since_checked_if_brawl_stars_crashed <= self.check_if_brawl_stars_crashed_timer:
                return
            try:
                if not self.window_controller.is_brawl_stars_running():
                    runtime_log.log_warn("recovery", "Brawl Stars is not in foreground; restarting...")
                    self.window_controller.device.app_start(self.window_controller.brawl_stars_package)
                    time.sleep(3)
                self.time_since_checked_if_brawl_stars_crashed = now
            except AdbError:
                emit_recovery_event("adb_error", "crash check reconnect")
                if not self.window_controller.reconnect_scrcpy():
                    self.restart_brawl_stars()

        def stop_gracefully(self):
            runtime_log.log_info("startup", "Pyla-RL is shutting down.")
            self.stop_state_checker()
            self.window_controller.release_movement()
            if self.discord_control is not None:
                self.discord_control.close()
            if self.telegram_control is not None:
                self.telegram_control.close()
            self.control_window.close()
            self.window_controller.close()
            if self.instance_id:
                from gui.instance_registry import remove_manifest
                from gui.session_state import clear_session_state

                clear_session_state(self.instance_id)
                remove_manifest(self.instance_id)

        def pump_remote_commands(self):
            from runtime_control import drain_remote_commands

            drain_remote_commands(self.control_window.state_path, self.handle_remote_command)

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
                    payload = {"ok": True, "result": self.remote_status()}
                elif action == "queue":
                    from gui.brawler_queue import load_queue
                    from gui.remote_formatting import format_queue_lines

                    payload = {"ok": True, "result": format_queue_lines(load_queue())}
                else:
                    payload = {"ok": False, "error": f"Unknown remote action '{action}'."}
                write_remote_reply(reply_path, payload)
            except Exception as exc:
                write_remote_reply(reply_path, {"ok": False, "error": str(exc)})

        def discord_press_key(self, key):
            normalized = str(key or "").strip().upper()
            if normalized in window_controller.press_coords_dict:
                self.window_controller.press(normalized.lower())
            else:
                self.window_controller.press_key(normalized)
            return True

        def discord_stop_all(self):
            request_stop(self.control_window.state_path)
            self.stop_event.set()
            return "Pyla-RL is stopping."

        def _apply_remote_queue_change(self, new_queue, message):
            from gui.remote_formatting import format_command_result, format_queue_lines

            self.Stage_manager.stage_queue_update(new_queue, reason="remote")
            write_state(self.control_window.state_path, RUNNING)
            return format_command_result("Farm Plan Updated", message, new_queue)

        def discord_start_push(self, brawler, target=None):
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
            from gui.brawler_queue import load_queue
            from gui.remote_queue_commands import skip_current_brawler

            queue = self.Stage_manager.brawlers_pick_data or load_queue()
            new_queue, message = skip_current_brawler(queue)
            return self._apply_remote_queue_change(new_queue, message)

        def remote_remove_brawler(self, brawler):
            from discord_control import resolve_brawler_choice
            from gui.brawler_queue import load_queue
            from gui.remote_queue_commands import remove_brawler_from_queue

            resolved = resolve_brawler_choice(brawler)
            if not resolved:
                return False
            queue = self.Stage_manager.brawlers_pick_data or load_queue()
            new_queue, message = remove_brawler_from_queue(queue, resolved)
            return self._apply_remote_queue_change(new_queue, message)

        def remote_set_target(self, target):
            from gui.brawler_queue import load_queue
            from gui.remote_queue_commands import set_active_target

            queue = self.Stage_manager.brawlers_pick_data or load_queue()
            new_queue, message = set_active_target(queue, int(target))
            return self._apply_remote_queue_change(new_queue, message)

        def build_runtime_snapshot(self):
            current = self.Stage_manager.brawlers_pick_data[0] if self.Stage_manager.brawlers_pick_data else {}
            total = self.Stage_manager.Trophy_observer.match_history.get("total", {})
            runtime_label = self.runtime_control_label()
            return {
                "uptime_s": time.time() - self.started_at,
                "state": format_state_label(self.state),
                "brawler": current.get("brawler", ""),
                "target": current.get("push_until", ""),
                "trophies": self.Stage_manager.Trophy_observer.current_trophies,
                "session_wins": int(total.get("victory", 0) or 0),
                "session_losses": int(total.get("defeat", 0) or 0),
                "session_draws": int(total.get("draw", 0) or 0),
                "notice": runtime_label.title(),
                "feed_fps": self.perf_feed_fps,
            }

        def remote_status(self):
            current = self.Stage_manager.brawlers_pick_data[0] if self.Stage_manager.brawlers_pick_data else {}
            return {
                "runtime": self.runtime_control_label(),
                "state": format_state_label(self.state),
                "ips": f"{self.ips_ema:.2f}" if self.ips_ema is not None else "",
                "feed_fps": f"{self.perf_feed_fps:.2f}",
                "emulator": getattr(self.window_controller, "selected_emulator", ""),
                "adb_device": getattr(self.window_controller, "connected_serial", ""),
                "brawler": current.get("brawler", ""),
                "target": current.get("push_until", ""),
            }

        def remote_session_stats(self):
            from gui.remote_formatting import build_session_stats

            return build_session_stats(self.build_runtime_snapshot())

        def should_replay_duplicate_frame(self, frame_time):
            if not self.duplicate_frame_replay_enabled:
                return False
            if self.get_latest_state() != "match":
                return False
            if not frame_time:
                return False
            return time.time() - frame_time <= 0.35

        def _maybe_send_daily_digest(self):
            from daily_digest import build_daily_digest, format_daily_digest_text, should_send_digest

            if not should_send_digest(last_sent_at=float(getattr(self, "_last_digest_sent_at", 0) or 0)):
                return
            try:
                payload = build_daily_digest(instance_id=self.instance_id or None)
                text = format_daily_digest_text(payload)
                notify_user(
                    "daily_digest",
                    None,
                    self.Stage_manager,
                    details={"message": text, **payload},
                )
                self._last_digest_sent_at = time.time()
            except Exception as exc:
                runtime_log.log_warn("digest", f"Daily digest failed: {exc}")

        def main(self):
            s_time = time.time()
            c = 0
            self.runtime_control.mark_running()
            while True:
                if is_stop_requested(self.control_window.state_path) or self.stop_event.is_set():
                    self.stop_gracefully()
                    break

                self.pump_remote_commands()
                if hasattr(self, "performance_autotuner"):
                    self.performance_autotuner.observe_ips(self.ips_history)
                    if self.get_latest_state() == "lobby":
                        self.performance_autotuner.apply_pending_adjustment(self.window_controller)
                self._maybe_send_daily_digest()
                if self.instance_id:
                    from gui.instance_registry import update_manifest_heartbeat
                    from gui.session_state import persist_worker_session

                    update_manifest_heartbeat(
                        self.instance_id,
                        self.build_runtime_snapshot(),
                        state_path=self.control_window.state_path,
                        metrics_path=self.metrics_path,
                    )
                    persist_worker_session(self)

                self.update_runtime_control_notice()

                if self.get_latest_state() == "lobby":
                    if self.should_pause():
                        self.handle_pause_request()
                        if self.should_stop():
                            self.stop_gracefully()
                            break

                if not self.picked_first_brawler and self.get_latest_state() == "lobby":
                    row = self.Stage_manager.brawlers_pick_data[0]
                    if row.get("automatically_pick"):
                        brawler_name = row["brawler"]
                        runtime_log.log_info("queue", f"Picking brawler automatically: {brawler_name}")
                        self.lobby_automator.selecting_brawler = True
                        try:
                            picked = self.lobby_automator.select_brawler(brawler_name)
                            attempts = 0
                            max_attempts = len(self.Stage_manager.brawlers_pick_data)
                            while not picked and attempts < max_attempts:
                                if self.ping_when_stuck:
                                    notify_user(
                                        "bot_failed_brawler_selection",
                                        self.window_controller.screenshot(),
                                        self.Stage_manager,
                                    )
                                failed = self.Stage_manager.brawlers_pick_data.pop(0)
                                self.Stage_manager.brawlers_pick_data.append(failed)
                                brawler_name = self.Stage_manager.brawlers_pick_data[0]["brawler"]
                                self.Stage_manager.quit_shop()
                                picked = self.lobby_automator.select_brawler(brawler_name)
                                attempts += 1
                            if picked:
                                self.update_trophy_observer()
                            else:
                                runtime_log.log_warn(
                                    "queue",
                                    f"Automatic brawler pick failed for {brawler_name}; continuing with current selection.",
                                )
                        finally:
                            self.lobby_automator.selecting_brawler = False
                    self.picked_first_brawler = True

                now = time.time()
                frame_start = time.perf_counter() if self.max_ips else None
                if self.run_for_minutes > 0 and not self.in_cooldown:
                    if (now - self.start_time) / 60 >= self.run_for_minutes:
                        self.in_cooldown = True
                        self.cooldown_start_time = now
                        self.Stage_manager.states["lobby"] = lambda: 0
                if self.in_cooldown and now - self.cooldown_start_time >= self.cooldown_duration:
                    self.stop_gracefully()
                    break

                if now - s_time >= 1.0:
                    elapsed = now - s_time
                    if elapsed > 0:
                        current_ips = c / elapsed
                        self.ips_ema = current_ips if self.ips_ema is None else (self.ips_ema * 0.75 + current_ips * 0.25)
                        if self.ips_ema is not None:
                            self.ips_history.append(self.ips_ema)
                            write_metrics(
                                self.metrics_path,
                                self.ips_ema,
                                self.perf_feed_fps,
                                self.ips_history,
                                session=self.build_runtime_snapshot(),
                            )
                        intent = getattr(self.Play, "match_intent_summary", "") or ""
                        runtime_label = self.runtime_control_label()
                        perf_text = f"{current_ips:.2f} IPS | feed {self.perf_feed_fps:.1f} FPS"
                        if runtime_label != "running":
                            perf_text = f"{runtime_label.upper()} | {perf_text}"
                        if intent:
                            perf_text += f" | {intent}"
                        runtime_log.log_status_line(perf_text)
                    s_time = now
                    c = 0

                self.check_and_handle_brawl_stars_crash()
                try:
                    frame = self.window_controller.screenshot()
                except ConnectionError:
                    emit_recovery_event("stale_feed", "screenshot connection error")
                    self.window_controller.restart_scrcpy_client()
                    continue

                _, last_ft = self.window_controller.get_latest_frame()
                if last_ft > 0 and (now - last_ft) > self.window_controller.FRAME_STALE_TIMEOUT:
                    stale_age = now - last_ft
                    self.window_controller.release_movement()
                    emit_recovery_event("stale_feed", f"age={stale_age:.1f}s")
                    if stale_age > 30:
                        if not self.window_controller.reconnect_scrcpy():
                            self.restart_brawl_stars()
                    else:
                        if self.sleep_interruptible(1) == "stop":
                            self.stop_gracefully()
                            break
                    continue

                self.record_feed_fps()
                frame_id = self.window_controller.get_latest_frame_id()
                if frame_id == self.last_processed_frame_id:
                    if self.should_replay_duplicate_frame(last_ft):
                        brawler = self.Stage_manager.brawlers_pick_data[0]["brawler"]
                        self.Play.current_brawler = brawler
                        self.Play.main(frame, brawler, self)
                        c += 1
                    time.sleep(0.005)
                    continue
                self.last_processed_frame_id = frame_id

                self.manage_time_tasks(frame)
                brawler = self.Stage_manager.brawlers_pick_data[0]["brawler"]
                self.Play.current_brawler = brawler
                self.Play.main(frame, brawler, self)
                c += 1

                if self.max_ips and frame_start is not None:
                    target_period = 1 / self.max_ips
                    work_time = time.perf_counter() - frame_start
                    if work_time < target_period:
                        time.sleep(target_period - work_time)

    worker = Main()
    worker.main()


def run_instance_worker(instance_id: str):
    from gui.instance_config import apply_instance_overrides, set_active_instance
    from gui.brawler_queue import load_queue
    from gui.session_state import apply_session_resume_to_queue

    set_active_instance(instance_id)
    profile = apply_instance_overrides(instance_id)
    if not profile:
        raise RuntimeError(f"Unknown instance profile '{instance_id}'.")
    queue = load_queue()
    if not queue:
        raise RuntimeError(f"Instance '{instance_id}' has an empty farm plan.")
    queue = apply_session_resume_to_queue(queue, instance_id)
    pyla_main(queue)


def run_app():
    import runtime_log
    from gui.brand import FREE_NOTICE, OFFICIAL_GITHUB
    from tools.launcher_bat import remove_legacy_launchers

    log_path = configure_terminal_output()
    from utils import install_root

    remove_legacy_launchers(Path(install_root()))
    runtime_log.log_info("startup", FREE_NOTICE)
    runtime_log.log_info("startup", f"Official source: {OFFICIAL_GITHUB}")
    runtime_log.log_info("startup", f"Pyla-RL v{pyla_version}")
    if log_path:
        runtime_log.log_info("startup", f"Terminal log: {log_path}")
    runtime_log.log_info(
        "startup",
        "Terminal verbosity changes apply after restarting the bot.",
    )
    all_brawlers = get_brawler_list()
    if api_base_url != "localhost":
        update_missing_brawlers_info(all_brawlers)
        check_version()
        update_wall_model_classes()
        if not current_wall_model_is_latest():
            get_latest_wall_model_file()

    app = App(login, SelectBrawler, pyla_main, all_brawlers, HubMenu)
    app.start(pyla_version, get_latest_version)


def write_crash_log(error):
    log_dir = Path(resolve_project_path("logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    crash_path = log_dir / "startup_crash.log"
    crash_path.write_text(
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        encoding="utf-8",
    )


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
    except Exception as exc:
        write_crash_log(exc)
        raise
