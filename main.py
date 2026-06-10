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
    request_stop,
    write_state,
)
from runtime_metrics import metrics_path_for_pid, write_metrics
from stage_manager import StageManager
from state_finder import get_state
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
            self.check_if_brawl_stars_crashed_timer = float(
                load_toml_as_dict("cfg/time_tresholds.toml").get("check_if_brawl_stars_crashed", 60)
            )
            self.time_since_checked_if_brawl_stars_crashed = time.time()
            self.last_processed_frame_id = -1
            self.ips_ema = None
            self.perf_feed_fps = 0.0
            self.perf_frame_count = 0
            self.perf_last_frame_time = time.time()
            self.perf_last_frame_id = -1
            self.ips_history = deque(maxlen=45)

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
            folder = "./models/"
            return [
                folder + "mainInGameModel.onnx",
                folder + "tileDetector.onnx",
                folder + "closeTileDetector.onnx",
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
            runtime_log.log_info("state", format_state_label(state))
            on_queue_file_changed(self.Stage_manager)
            self.Stage_manager.do_state(state, None)
            if state != "match":
                self.Play.time_since_last_proceeding = time.time()

        def wait_while_paused(self):
            self.window_controller.release_movement()
            self.runtime_control.mark_paused()
            runtime_log.log_info(
                "startup",
                "Pyla-RL is paused. Press F8 or use Discord/Telegram /resume to continue.",
            )
            while self.should_pause() and not self.should_stop():
                if self.sleep_interruptible(0.75, allow_pause=False) == "stop":
                    return
            if not self.should_stop():
                self.runtime_control.mark_running()
                self.time_since_last_webhook_ping = time.time()
                runtime_log.log_info("startup", "Pause released, resuming run.")

        def handle_pause_request(self):
            if self.should_pause() and not self.should_stop():
                self.wait_while_paused()

        def manage_time_tasks(self, frame):
            if self.Time_management.state_check():
                state = self.get_latest_state()
                if state is not None:
                    self.handle_detected_state(state)
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
                    self.window_controller.device.app_start(self.window_controller.BRAWL_STARS_PACKAGE)
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
            return {
                "uptime_s": time.time() - self.started_at,
                "state": format_state_label(self.state),
                "brawler": current.get("brawler", ""),
                "target": current.get("push_until", ""),
                "trophies": self.Stage_manager.Trophy_observer.current_trophies,
                "session_wins": int(total.get("victory", 0) or 0),
                "session_losses": int(total.get("defeat", 0) or 0),
                "session_draws": int(total.get("draw", 0) or 0),
                "notice": "Running",
                "feed_fps": self.perf_feed_fps,
            }

        def remote_status(self):
            current = self.Stage_manager.brawlers_pick_data[0] if self.Stage_manager.brawlers_pick_data else {}
            return {
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

        def main(self):
            s_time = time.time()
            c = 0
            self.runtime_control.mark_running()
            while True:
                if is_stop_requested(self.control_window.state_path) or self.stop_event.is_set():
                    self.stop_gracefully()
                    break

                self.pump_remote_commands()
                if self.instance_id:
                    from gui.instance_registry import update_manifest_heartbeat

                    update_manifest_heartbeat(
                        self.instance_id,
                        self.build_runtime_snapshot(),
                        state_path=self.control_window.state_path,
                        metrics_path=self.metrics_path,
                    )

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
                            )
                        intent = getattr(self.Play, "match_intent_summary", "") or ""
                        perf_text = f"{current_ips:.2f} IPS | feed {self.perf_feed_fps:.1f} FPS"
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
                        self.Play.pump_visual_debug_display()
                        c += 1
                    time.sleep(0.005)
                    continue
                self.last_processed_frame_id = frame_id

                self.manage_time_tasks(frame)
                brawler = self.Stage_manager.brawlers_pick_data[0]["brawler"]
                self.Play.current_brawler = brawler
                self.Play.main(frame, brawler, self)
                self.Play.pump_visual_debug_display()
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

    set_active_instance(instance_id)
    profile = apply_instance_overrides(instance_id)
    if not profile:
        raise RuntimeError(f"Unknown instance profile '{instance_id}'.")
    queue = load_queue()
    if not queue:
        raise RuntimeError(f"Instance '{instance_id}' has an empty farm plan.")
    pyla_main(queue)


def run_app():
    import runtime_log
    from gui.brand import FREE_NOTICE, OFFICIAL_GITHUB
    from tools.launcher_bat import remove_legacy_launchers

    log_path = configure_terminal_output()
    remove_legacy_launchers(Path(__file__).resolve().parent)
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
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
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
