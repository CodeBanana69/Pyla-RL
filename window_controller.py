import atexit
import ctypes
import ctypes.wintypes
import glob
import json
import math
import os
import re
import subprocess
import socket
import threading
import time
import cv2
import numpy as np
from typing import List, Optional, Tuple

import scrcpy
from adbutils import adb

from utils import load_toml_as_dict

# --- Configuration ---
brawl_stars_width, brawl_stars_height = 1920, 1080

key_coords_dict = {
    "H": (1400, 990),
    "G": (1640, 990),
    "M": (1725, 800),
    "Q": (1660, 980),
    "E": (1510, 880),
    "F": (1360, 920),
}

directions_xy_deltas_dict = {
    "w": (0, -150),
    "a": (-150, 0),
    "s": (0, 150),
    "d": (150, 0),
}

BRAWL_STARS_PACKAGE = load_toml_as_dict("cfg/general_config.toml")["brawl_stars_package"]

EMULATOR_PORTS = {
    "LDPlayer": [5555, 5557, 5559, 5554],
    "MuMu": [16384, 16416, 16448, 7555, 5558, 5557, 5556, 5555, 5554],
}

SUPPORTED_EMULATORS = tuple(EMULATOR_PORTS.keys())

COMMON_LDPLAYER_CONSOLES = [
    r"C:\LDPlayer\LDPlayer9\dnconsole.exe",
    r"C:\LDPlayer\LDPlayer4.0\dnconsole.exe",
    r"C:\Program Files\LDPlayer\LDPlayer9\dnconsole.exe",
    r"C:\Program Files\LDPlayer\LDPlayer4.0\dnconsole.exe",
    r"C:\Program Files (x86)\LDPlayer\LDPlayer9\dnconsole.exe",
    r"C:\Program Files (x86)\LDPlayer\LDPlayer4.0\dnconsole.exe",
]

COMMON_MUMU_MANAGERS = [
    r"C:\Program Files\Netease\MuMuPlayer\nx_main\MuMuManager.exe",
    r"C:\Program Files (x86)\Netease\MuMuPlayer\nx_main\MuMuManager.exe",
]

LOCAL_ADB_EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adb.exe")
_ADB_ONLINE_CACHE = {}
_ADB_ONLINE_CACHE_TTL = 1.0
ADB_SERVER_PORT = 5037


def _infer_supported_emulator(configured_port):
    try:
        configured_port = int(configured_port)
    except (TypeError, ValueError):
        return "LDPlayer"
    if configured_port in (16384, 16416, 16448, 7555):
        return "MuMu"
    return "LDPlayer"


def _normalize_emulator_config(selected_emulator, configured_port):
    selected_emulator = str(selected_emulator or "LDPlayer").strip()
    try:
        configured_port = int(configured_port)
    except (TypeError, ValueError):
        configured_port = 0

    if configured_port == ADB_SERVER_PORT:
        configured_port = 0

    if selected_emulator not in EMULATOR_PORTS:
        selected_emulator = _infer_supported_emulator(configured_port)

    return selected_emulator, configured_port


def _unique_ports(ports):
    unique = []
    for port in ports:
        try:
            port = int(port)
        except (TypeError, ValueError):
            continue
        if port == 5037:
            continue
        if port not in unique:
            unique.append(port)
    return unique


def _is_port_open(host, port, timeout=0.05):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((host, port)) == 0
    except OSError:
        return False


def _serial_port(serial):
    if serial.startswith("emulator-"):
        try:
            return int(serial.rsplit("-", 1)[1])
        except ValueError:
            return None
    if ":" in serial:
        try:
            return int(serial.rsplit(":", 1)[1])
        except ValueError:
            return None
    return None


def _is_local_adb_serial(serial):
    return (
        str(serial or "").startswith("127.0.0.1:")
        or str(serial or "").startswith("localhost:")
        or str(serial or "").startswith("emulator-")
    )


def _find_existing_path(paths):
    for path in paths:
        expanded = os.path.expandvars(path)
        matches = glob.glob(expanded)
        for match in matches:
            if os.path.exists(match):
                return match
    return None


def _window_title_matches_emulator(title, selected_emulator):
    title = str(title or "").lower()
    selected_emulator = str(selected_emulator or "").lower()
    if not title:
        return False
    if "brawl stars" in title:
        return True
    if "ldplayer" in selected_emulator:
        return "ldplayer" in title or "dnplayer" in title
    if "mumu" in selected_emulator:
        return "mumu" in title or "android device" in title
    return any(token in title for token in ("ldplayer", "dnplayer", "mumu", "android device", "brawl stars"))


def _valid_window_rect(rect):
    left, top, right, bottom = rect
    return right - left >= 320 and bottom - top >= 240


def _adb_executable():
    if os.path.exists(LOCAL_ADB_EXE):
        return LOCAL_ADB_EXE
    return "adb"


def _run_adb(serial, args, timeout=5):
    command = [_adb_executable()]
    if serial:
        command.extend(["-s", serial])
    command.extend(args)
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def _is_adb_serial_online(serial, timeout=3):
    if not serial:
        return False
    now = time.time()
    cached = _ADB_ONLINE_CACHE.get(serial)
    if cached and now - cached[0] < _ADB_ONLINE_CACHE_TTL:
        return cached[1]
    try:
        completed = _run_adb(None, ["devices"], timeout=min(timeout, 1.0))
    except Exception:
        _ADB_ONLINE_CACHE[serial] = (now, False)
        return False
    online = False
    for line in completed.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == serial:
            online = parts[1] == "device"
            break
    _ADB_ONLINE_CACHE[serial] = (now, online)
    return online


def _foreground_package_from_text(text):
    patterns = (
        r"mCurrentFocus=.*?\s([A-Za-z0-9_.]+)/",
        r"mFocusedApp=.*?\s([A-Za-z0-9_.]+)/",
        r"topResumedActivity=.*?\s([A-Za-z0-9_.]+)/",
        r"ResumedActivity:.*?\s([A-Za-z0-9_.]+)/",
    )
    for pattern in patterns:
        match = re.search(pattern, text or "")
        if match:
            return match.group(1)
    return ""


def _package_task_display_from_text(text, package) -> Tuple[Optional[int], Optional[int]]:
    text = text or ""
    package = str(package or "").strip()
    if not package or package not in text:
        return None, None

    current_display = None
    fallback_task = None
    fallback_display = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        display_match = re.search(r"\bdisplayId=(\d+)\b", line)
        if display_match:
            current_display = int(display_match.group(1))
        if package not in line:
            continue

        line_display = current_display
        if display_match:
            line_display = int(display_match.group(1))
        task_match = re.search(r"\btaskId=(\d+)\b", line) or re.search(r"#(\d+)", line)
        task_id = int(task_match.group(1)) if task_match else None

        if task_id is not None and line_display is not None:
            return task_id, line_display
        if fallback_task is None:
            fallback_task = task_id
            fallback_display = line_display

    compact = re.sub(r"\s+", " ", text)
    patterns = (
        rf"(?:taskId=|#)(\d+).{{0,400}}{re.escape(package)}.{{0,400}}displayId=(\d+)",
        rf"displayId=(\d+).{{0,400}}(?:taskId=|#)(\d+).{{0,400}}{re.escape(package)}",
        rf"displayId=(\d+).{{0,400}}{re.escape(package)}.{{0,400}}(?:taskId=|#)(\d+)",
    )
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, compact)
        if not match:
            continue
        first = int(match.group(1))
        second = int(match.group(2))
        if index == 0:
            return first, second
        return second, first
    return fallback_task, fallback_display


def _get_package_task_display(serial, package, timeout=5) -> Tuple[Optional[int], Optional[int]]:
    try:
        for args in (
            ["shell", "dumpsys", "activity", "activities"],
            ["shell", "dumpsys", "activity", "recents"],
        ):
            completed = _run_adb(serial, args, timeout=timeout)
            if completed.returncode != 0:
                continue
            task_id, display_id = _package_task_display_from_text(completed.stdout, package)
            if task_id is not None or display_id is not None:
                return task_id, display_id
    except Exception:
        return None, None
    return None, None


def _move_android_task_to_display(serial, task_id, display_id=0, timeout=5):
    if task_id is None:
        return False
    commands = (
        ["shell", "cmd", "activity", "move-task-to-display", str(task_id), str(display_id)],
        ["shell", "am", "display", "move-task", str(task_id), str(display_id)],
    )
    for args in commands:
        try:
            completed = _run_adb(serial, args, timeout=timeout)
            if completed.returncode == 0:
                return True
        except Exception:
            continue
    return False


def _get_foreground_package(serial, timeout=5):
    try:
        for args in (
            ["shell", "dumpsys", "window"],
            ["shell", "dumpsys", "activity", "activities"],
        ):
            completed = _run_adb(serial, args, timeout=timeout)
            if completed.returncode == 0:
                package = _foreground_package_from_text(completed.stdout)
                if package:
                    return package
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"ADB foreground-app check timed out for {serial}.")
    except Exception:
        return ""
    return ""


def _start_android_app(serial, package, timeout=8, display_id=0):
    attempts = []
    if display_id is not None:
        args = ["shell", "monkey"]
        args.extend(["--display", str(display_id)])
        args.extend(["-p", package, "-c", "android.intent.category.LAUNCHER", "1"])
        attempts.append(args)
    attempts.append(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])
    for args in attempts:
        try:
            completed = _run_adb(serial, args, timeout=timeout)
            if completed.returncode == 0:
                return True
        except Exception:
            continue
    return False


def _start_android_app_on_display(serial, package, display_id=0, timeout=8):
    try:
        completed = _run_adb(
            serial,
            [
                "shell",
                "cmd",
                "package",
                "resolve-activity",
                "--brief",
                package,
            ],
            timeout=timeout,
        )
        component = ""
        for line in completed.stdout.splitlines():
            stripped = line.strip()
            if "/" in stripped and not stripped.startswith("priority="):
                component = stripped
        if component:
            completed = _run_adb(
                serial,
                ["shell", "am", "start", "--display", str(display_id), "-n", component],
                timeout=timeout,
            )
            if completed.returncode == 0:
                return True
    except Exception:
        pass
    return _start_android_app(serial, package, timeout=timeout, display_id=display_id)


def _stop_android_app(serial, package, timeout=8):
    try:
        completed = _run_adb(serial, ["shell", "am", "force-stop", package], timeout=timeout)
        return completed.returncode == 0
    except Exception:
        return False


def _wake_android_display(serial, timeout=4):
    for args in (
        ["shell", "input", "keyevent", "KEYCODE_WAKEUP"],
        ["shell", "wm", "dismiss-keyguard"],
    ):
        try:
            _run_adb(serial, args, timeout=timeout)
        except Exception:
            pass


def _get_mumu_manager_path(config=None):
    manager_path = ""
    if config:
        manager_path = str(config.get("mumu_manager_path", "")).strip()
    if manager_path:
        return manager_path
    return _find_existing_path(COMMON_MUMU_MANAGERS)


def get_running_mumu_profiles(config=None):
    manager_path = _get_mumu_manager_path(config)
    if not manager_path:
        return []
    try:
        completed = subprocess.run(
            [manager_path, "info", "--vmindex", "all"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if completed.returncode != 0:
            return []
        payload = json.loads(completed.stdout or "{}")
    except Exception:
        return []

    profiles = []
    for _, profile in payload.items():
        try:
            is_running = bool(profile.get("is_android_started")) or bool(profile.get("is_process_started"))
            adb_port = int(profile.get("adb_port", 0))
            index = int(profile.get("index", 0))
        except (TypeError, ValueError):
            continue
        if is_running and adb_port:
            profiles.append({"index": index, "adb_port": adb_port, "name": str(profile.get("name", ""))})
    profiles.sort(key=lambda item: item["index"])
    return profiles


def get_mumu_profiles(config=None):
    manager_path = _get_mumu_manager_path(config)
    if not manager_path:
        return []
    try:
        completed = subprocess.run(
            [manager_path, "info", "--vmindex", "all"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if completed.returncode != 0:
            return []
        payload = json.loads(completed.stdout or "{}")
    except Exception:
        return []

    profiles = []
    for _, profile in payload.items():
        try:
            index = int(profile.get("index", 0))
        except (TypeError, ValueError):
            continue
        try:
            adb_port = int(profile.get("adb_port", 0) or 0)
        except (TypeError, ValueError):
            adb_port = 0
        if not adb_port:
            adb_port = 16384 + (32 * index)
        profiles.append({
            "index": index,
            "adb_port": adb_port,
            "name": str(profile.get("name", "")),
            "is_running": bool(profile.get("is_android_started")) or bool(profile.get("is_process_started")),
        })
    profiles.sort(key=lambda item: item["index"])
    return profiles


def _infer_ldplayer_index(port):
    if port in (5555, 5554):
        return 0
    if port and port >= 5557 and (port - 5555) % 2 == 0:
        return max(0, (port - 5555) // 2)
    return 0


def _infer_mumu_index(port):
    if port in (16384, 7555, 5555, 5554):
        return 0
    if port and port >= 16384 and (port - 16384) % 32 == 0:
        return max(0, (port - 16384) // 32)
    return 0


def _config_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class WindowController:
    def __init__(self):
        self.scale_factor = None
        self.width = None
        self.height = None
        self.width_ratio = None
        self.height_ratio = None
        self.joystick_x, self.joystick_y = None, None
        self.are_we_moving = False
        self.PID_JOYSTICK = 1  # ID for WASD movement
        self.PID_ATTACK = 2  # ID for clicks/attacks
        self.check_if_brawl_stars_crashed_timer = load_toml_as_dict("cfg/time_tresholds.toml")["check_if_brawl_stars_crashed"]
        self.time_since_checked_if_brawl_stars_crashed = time.time()
        self.foreground_check_failures = 0
        self.foreground_failure_restart_threshold = int(
            load_toml_as_dict("cfg/time_tresholds.toml").get("foreground_failure_restart_threshold", 4)
        )
        self.last_emulator_restart_time = 0.0
        self.emulator_restart_cooldown = float(
            load_toml_as_dict("cfg/time_tresholds.toml").get("emulator_restart_cooldown", 180)
        )

        # --- 2. ADB & Scrcpy Connection ---
        print("Connecting to ADB...")
        try:
            def list_online_devices():
                devices = []
                for dev in adb.device_list():
                    try:
                        state = dev.get_state()
                    except Exception:
                        state = "unknown"
                    if state == "device":
                        devices.append(dev)
                    else:
                        print(f"Skipping ADB device {dev.serial} (state: {state})")
                return devices

            def prefer_selected_devices(devices, selected_emulator, configured_port):
                preferred_ports = set(_unique_ports([configured_port] + EMULATOR_PORTS.get(selected_emulator, [])))
                preferred_serials = {f"127.0.0.1:{port}" for port in preferred_ports}
                local_matches = [
                    dev for dev in devices
                    if (
                        _is_local_adb_serial(dev.serial)
                        and (_serial_port(dev.serial) in preferred_ports or dev.serial in preferred_serials)
                    )
                ]
                if local_matches:
                    return local_matches
                return [
                    dev for dev in devices
                    if (
                        configured_port
                        and _serial_port(dev.serial) == configured_port
                        and dev.serial in preferred_serials
                    )
                ]

            def choose_best_device(devices, selected_emulator, configured_port):
                preferred_ports = set(_unique_ports([configured_port] + EMULATOR_PORTS.get(selected_emulator, [])))
                configured_ports = _unique_ports([configured_port])
                configured_port = configured_ports[0] if configured_ports else None
                configured_serial = f"127.0.0.1:{configured_port}" if configured_port is not None else ""
                preferred_serials = {f"127.0.0.1:{port}" for port in preferred_ports}
                best_device = None
                best_package = ""
                best_score = None

                for index, dev in enumerate(devices):
                    port = _serial_port(dev.serial)
                    try:
                        opened_package = dev.app_current().package.strip()
                    except Exception:
                        opened_package = ""
                    score = (
                        opened_package == self.brawl_stars_package,
                        _is_local_adb_serial(dev.serial),
                        port == configured_port or dev.serial == configured_serial,
                        port in preferred_ports or dev.serial in preferred_serials,
                        -index,
                    )
                    if best_score is None or score > best_score:
                        best_device = dev
                        best_package = opened_package
                        best_score = score
                return best_device, best_package

            general_config = load_toml_as_dict("cfg/general_config.toml")
            raw_emulator = general_config.get("current_emulator", "LDPlayer")
            raw_port = general_config.get("emulator_port", 0)
            selected_emulator, configured_port = _normalize_emulator_config(raw_emulator, raw_port)
            self.brawl_stars_package = str(
                general_config.get("brawl_stars_package", BRAWL_STARS_PACKAGE)
            ).strip()
            if selected_emulator != raw_emulator or configured_port != raw_port:
                print(
                    f"Using supported emulator config: {selected_emulator} "
                    f"port {configured_port or 'auto'}."
                )
            self.scrcpy_max_fps = int(general_config.get("scrcpy_max_fps", 15))
            if self.scrcpy_max_fps <= 0:
                self.scrcpy_max_fps = None
            self.scrcpy_max_width = int(general_config.get("scrcpy_max_width", 960))
            if self.scrcpy_max_width < 0:
                self.scrcpy_max_width = 0
            self.scrcpy_bitrate = int(general_config.get("scrcpy_bitrate", 3000000))
            if self.scrcpy_bitrate <= 0:
                self.scrcpy_bitrate = 3000000
            self.selected_emulator = selected_emulator
            self.configured_port = configured_port
            self.configured_serial = f"127.0.0.1:{configured_port}" if configured_port else ""
            self.emulator_autorestart = _config_bool(general_config.get("emulator_autorestart", True), True)
            self.emulator_profile_index_is_auto = str(
                general_config.get("emulator_profile_index", "auto")
            ).strip().lower() == "auto"
            self.emulator_profile_index = self._resolve_emulator_profile_index(general_config)
            self.emulator_launch_command = self._resolve_emulator_launch_command(general_config)
            all_supported_ports = []
            for emulator_name in SUPPORTED_EMULATORS:
                all_supported_ports.extend(EMULATOR_PORTS[emulator_name])
            candidate_ports = _unique_ports(
                [configured_port]
                + EMULATOR_PORTS[selected_emulator]
                + all_supported_ports
                + list(range(5565, 5756, 10))
            )

            device_list = list_online_devices()
            preferred_devices = prefer_selected_devices(device_list, selected_emulator, configured_port)

            # Probe selected/common emulator ports quickly before calling adb.connect.
            # Port 5037 is filtered out by _unique_ports because it is the ADB server port.
            if not preferred_devices:
                ports_to_try = [port for port in candidate_ports if _is_port_open("127.0.0.1", port)]
                if not ports_to_try and not device_list:
                    ports_to_try = candidate_ports
                for port in ports_to_try:
                    try:
                        adb.connect(f"127.0.0.1:{port}")
                    except Exception:
                        pass
                device_list = list_online_devices()
                preferred_devices = prefer_selected_devices(device_list, selected_emulator, configured_port)

            if not preferred_devices and self.emulator_autorestart:
                print("Selected emulator profile is not online; trying to launch it.")
                self.launch_saved_emulator_profile(wait_for_device=True)
                device_list = list_online_devices()
                preferred_devices = prefer_selected_devices(device_list, selected_emulator, configured_port)

            if not device_list:
                tried_ports = ", ".join(str(port) for port in candidate_ports)
                raise ConnectionError(f"No online ADB devices found. Tried ports: {tried_ports}")

            self.device, opened_package = choose_best_device(device_list, selected_emulator, configured_port)
            if self.device is None:
                raise ConnectionError(
                    f"No matching ADB device found on port {configured_port}."
                )
            selected_is_preferred = self.device in preferred_devices
            if opened_package == self.brawl_stars_package:
                print(f"Selected ADB device with Brawl Stars in foreground: {self.device.serial}")
            if not selected_is_preferred:
                print(
                    f"Could not identify a {selected_emulator} device by port; "
                    f"using the best online LDPlayer/MuMu ADB device instead."
                )
            print(f"Connected to {selected_emulator}: {self.device.serial}")
            self.connected_serial = self.device.serial
            self.sync_restart_target_to_connected_device()
            self.ensure_brawl_stars_on_primary_display(log_only=True)

            self.frame_lock = threading.Lock()
            self.scrcpy_client = None
            self.last_frame = None
            self.last_frame_time = 0.0
            self.frame_id = 0
            self.last_stale_warning_time = 0.0
            self.scrcpy_generation = 0
            self.last_joystick_pos = (None, None)
            self.last_joystick_down_time = 0.0
            self.FRAME_STALE_TIMEOUT = 15.0
            self.start_scrcpy_client()
            atexit.register(self.close)
            print("Scrcpy client started successfully.")

        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Failed to initialize Scrcpy: {e}")

    def _resolve_emulator_profile_index(self, general_config):
        configured_index = general_config.get("emulator_profile_index", "auto")
        if str(configured_index).strip().lower() != "auto":
            try:
                return int(configured_index)
            except (TypeError, ValueError):
                print(f"Invalid emulator_profile_index '{configured_index}', falling back to port mapping.")

        if self.selected_emulator == "MuMu":
            return _infer_mumu_index(self.configured_port)
        return _infer_ldplayer_index(self.configured_port)

    def _resolve_emulator_launch_command(self, general_config):
        custom_command = str(general_config.get("emulator_launch_command", "")).strip()
        if custom_command:
            return custom_command

        if self.selected_emulator == "MuMu":
            manager_path = _get_mumu_manager_path(general_config)
            if manager_path:
                return [manager_path, "control", "--vmindex", str(self.emulator_profile_index), "launch"]
            return None

        console_path = str(general_config.get("ldplayer_console_path", "")).strip()
        if not console_path:
            console_path = _find_existing_path(COMMON_LDPLAYER_CONSOLES)
        if console_path:
            return [console_path, "launch", "--index", str(self.emulator_profile_index)]
        return None

    def sync_restart_target_to_connected_device(self):
        connected_port = _serial_port(self.connected_serial)
        if connected_port is None:
            return

        self.configured_port = connected_port
        self.configured_serial = self.connected_serial

        if not self.emulator_profile_index_is_auto:
            print(
                f"Auto-restart target locked to explicit {self.selected_emulator} "
                f"profile {self.emulator_profile_index} for ADB {self.configured_serial}."
            )
            return

        previous_index = self.emulator_profile_index
        if self.selected_emulator == "MuMu":
            self.emulator_profile_index = _infer_mumu_index(connected_port)
        else:
            self.emulator_profile_index = _infer_ldplayer_index(connected_port)

        if self.emulator_profile_index != previous_index:
            print(
                f"Auto-restart target updated from {self.selected_emulator} profile {previous_index} "
                f"to profile {self.emulator_profile_index} because the bot connected to {self.connected_serial}."
            )
        else:
            print(
                f"Auto-restart target is {self.selected_emulator} profile {self.emulator_profile_index} "
                f"for ADB {self.configured_serial}."
            )

    def _emulator_command_for(self, action):
        if not self.emulator_launch_command:
            return None
        if not isinstance(self.emulator_launch_command, list):
            return self.emulator_launch_command

        executable = self.emulator_launch_command[0]
        if self.selected_emulator == "MuMu":
            mumu_action = "restart" if action == "restart" else "launch"
            return [executable, "control", "--vmindex", str(self.emulator_profile_index), mumu_action]

        ld_action = {
            "launch": "launch",
            "restart": "reboot",
            "shutdown": "quit",
        }.get(action, "launch")
        return [executable, ld_action, "--index", str(self.emulator_profile_index)]

    def run_emulator_command(self, action, wait=True):
        command = self._emulator_command_for(action)
        if not command:
            print(
                f"Cannot auto-restart {self.selected_emulator}: launcher path was not found. "
                "Set emulator_launch_command, mumu_manager_path, or ldplayer_console_path in cfg/general_config.toml."
            )
            return False

        print(
            f"{action.capitalize()}ing {self.selected_emulator} profile {self.emulator_profile_index} "
            f"for ADB {self.configured_serial or 'auto'}."
        )
        try:
            if wait and isinstance(command, list):
                completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
                stdout = completed.stdout.strip()
                stderr = completed.stderr.strip()
                if stdout:
                    print(f"{self.selected_emulator} launcher: {stdout}")
                if stderr:
                    print(f"{self.selected_emulator} launcher error: {stderr}")
                if completed.returncode != 0:
                    print(f"{self.selected_emulator} launcher exited with code {completed.returncode}.")
                    return False
                return True

            if isinstance(command, list):
                subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError as e:
            if getattr(e, "winerror", None) == 740 and isinstance(command, list):
                return self._run_emulator_command_elevated(command, action)
            print(f"Could not run emulator {action} command: {e}")
            return False
        except Exception as e:
            print(f"Could not run emulator {action} command: {e}")
            return False

    def _run_emulator_command_elevated(self, command, action):
        if os.name != "nt" or not isinstance(command, list) or not command:
            return False

        executable = command[0]
        args = subprocess.list2cmdline(command[1:])
        print(
            f"{self.selected_emulator} launcher requires administrator permission. "
            "Opening a Windows UAC prompt now."
        )
        try:
            result = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                executable,
                args,
                None,
                1,
            )
        except Exception as e:
            print(f"Could not open elevated emulator {action} command: {e}")
            return False

        if result <= 32:
            print(
                f"Windows did not allow the elevated {self.selected_emulator} launch "
                f"(ShellExecute error {result}). Start the emulator manually or run Pyla as administrator."
            )
            return False
        return True

    def launch_saved_emulator_profile(self, wait_for_device=False, action="launch"):
        if not self.run_emulator_command(action, wait=wait_for_device):
            return False

        if not wait_for_device:
            return True
        return self.wait_for_saved_device()

    def wait_for_saved_device(self, timeout=120):
        deadline = time.time() + timeout
        disconnected_stale_serial = False
        stable_since = None
        expected_serials = [
            serial for serial in (
                getattr(self, "connected_serial", ""),
                self.configured_serial,
            ) if serial
        ]
        while time.time() < deadline:
            if self.configured_serial:
                try:
                    if not disconnected_stale_serial:
                        adb.disconnect(self.configured_serial)
                        disconnected_stale_serial = True
                    adb.connect(self.configured_serial)
                except Exception:
                    pass

            try:
                for device in adb.device_list():
                    if device.get_state() != "device":
                        continue
                    if device.serial in expected_serials or _serial_port(device.serial) == self.configured_port:
                        if stable_since is None:
                            stable_since = time.time()
                        if time.time() - stable_since >= 3:
                            self.device = device
                            self.connected_serial = device.serial
                            self.sync_restart_target_to_connected_device()
                            print(f"Reconnected to emulator ADB device: {device.serial}")
                            return True
                        break
                else:
                    stable_since = None
            except Exception:
                stable_since = None
                pass

            try:
                serial = expected_serials[0] if expected_serials else None
                device = adb.device(serial=serial)
                if device.get_state() == "device":
                    if stable_since is None:
                        stable_since = time.time()
                    if time.time() - stable_since >= 3:
                        self.device = device
                        self.connected_serial = device.serial
                        self.sync_restart_target_to_connected_device()
                        print(f"Reconnected to emulator ADB device: {device.serial}")
                        return True
            except Exception:
                stable_since = None
                pass
            time.sleep(2)
        print("Timed out waiting for emulator ADB device to come back online.")
        return False

    def ensure_emulator_online(self):
        serial = getattr(self, "connected_serial", "") or getattr(self, "configured_serial", "")
        if self.is_emulator_online():
            return True
        try:
            if self.device.get_state() == "device":
                return True
        except Exception as e:
            print(f"ADB device is not reachable: {e}")

        if not self.emulator_autorestart:
            return False

        return self.restart_emulator_profile()

    def is_emulator_online(self):
        serial = getattr(self, "connected_serial", "") or getattr(self, "configured_serial", "")
        if not serial:
            return False
        return _is_adb_serial_online(serial)

    def restart_emulator_profile(self):
        now = time.time()
        if now - self.last_emulator_restart_time < self.emulator_restart_cooldown:
            remaining = self.emulator_restart_cooldown - (now - self.last_emulator_restart_time)
            print(f"Skipping emulator restart; last restart was too recent ({remaining:.0f}s cooldown left).")
            return False
        self.last_emulator_restart_time = now
        print(f"{self.selected_emulator} appears to be down; restarting the saved emulator profile.")
        try:
            self.keys_up(list("wasd"))
        except Exception:
            pass
        old_client = getattr(self, "scrcpy_client", None)
        if old_client is not None:
            try:
                old_client.stop()
            except Exception as e:
                print(f"Could not stop scrcpy before emulator restart: {e}")
        self.scrcpy_client = None
        if not self.launch_saved_emulator_profile(wait_for_device=True, action="restart"):
            print("Emulator restart did not bring the profile online; trying explicit launch.")
            if not self.launch_saved_emulator_profile(wait_for_device=True, action="launch"):
                print(
                    "Could not restart emulator profile. "
                    "If Windows says elevation is required, run the emulator once normally or install it without admin-only permissions."
                )
                return False
        time.sleep(3)
        try:
            self.start_scrcpy_client()
        except Exception as e:
            print(f"Could not restart scrcpy after emulator profile launch: {e}")
            return False
        if not _start_android_app(self.connected_serial, self.brawl_stars_package):
            self.device.app_start(self.brawl_stars_package)
        time.sleep(3)
        self.time_since_checked_if_brawl_stars_crashed = time.time()
        print("Emulator profile restarted and Brawl Stars launched.")
        return True

    def start_scrcpy_client(self):
        if not self.ensure_emulator_online():
            raise ConnectionError("ADB device is offline; waiting for emulator cooldown before retrying.")
        self.ensure_brawl_stars_on_primary_display(allow_app_restart=True)
        self.scrcpy_generation += 1
        generation = self.scrcpy_generation

        def on_frame(frame):
            if frame is not None:
                if not getattr(scrcpy, "PYLA_RGB_FRAMES", False):
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                with self.frame_lock:
                    if generation != self.scrcpy_generation:
                        return
                    self.last_frame = frame
                    self.last_frame_time = time.time()
                    self.frame_id += 1

        with self.frame_lock:
            self.last_frame = None
            self.last_frame_time = 0.0
            self.frame_id = 0
            self.last_stale_warning_time = 0.0
        self.are_we_moving = False
        self.last_joystick_pos = (None, None)
        self.last_joystick_down_time = 0.0

        client_kwargs = {
            "device": self.device,
            "max_width": self.scrcpy_max_width,
            "bitrate": self.scrcpy_bitrate,
        }
        if self.scrcpy_max_fps:
            client_kwargs["max_fps"] = self.scrcpy_max_fps
        last_error = None
        for attempt in range(1, 4):
            try:
                self.scrcpy_client = scrcpy.Client(**client_kwargs)
                self.scrcpy_client.add_listener(scrcpy.EVENT_FRAME, on_frame)
                self.scrcpy_client.start(threaded=True)
                return
            except Exception as e:
                last_error = e
                print(f"Scrcpy start failed attempt {attempt}/3: {e}")
                try:
                    if self.scrcpy_client is not None:
                        self.scrcpy_client.stop()
                except Exception:
                    pass
                self.scrcpy_client = None
                time.sleep(2)
        raise last_error

    def restart_scrcpy_client(self):
        print("Restarting scrcpy client...")
        if not self.ensure_emulator_online():
            print("Cannot restart scrcpy yet because ADB is offline.")
            return False
        old_client = self.scrcpy_client
        self.scrcpy_client = None
        self.scrcpy_generation += 1
        if old_client is not None:
            def stop_old_client():
                try:
                    old_client.stop()
                except Exception as e:
                    print(f"Could not stop old scrcpy client cleanly: {e}")

            stop_thread = threading.Thread(target=stop_old_client, daemon=True)
            stop_thread.start()
            stop_thread.join(timeout=2)
            if stop_thread.is_alive():
                print("Old scrcpy client did not stop within 2s; starting a new client anyway.")
        time.sleep(0.4)
        try:
            self.start_scrcpy_client()
            if not self.wait_for_fresh_frame(timeout=6.0):
                print("Scrcpy restarted but no fresh frame arrived within 6s.")
                return False
        except Exception as e:
            print(f"Could not restart scrcpy client: {e}")
            if not self.is_emulator_online():
                print("ADB went offline while starting scrcpy; entering emulator recovery.")
                self.ensure_emulator_online()
            return False
        print("Scrcpy client restarted successfully.")
        return True

    def wait_for_fresh_frame(self, timeout=6.0):
        start_id = self.get_latest_frame_id()
        deadline = time.time() + timeout
        while time.time() < deadline:
            frame, frame_time = self.get_latest_frame()
            if frame is not None and self.get_latest_frame_id() != start_id and time.time() - frame_time <= 1.0:
                return True
            time.sleep(0.1)
        return False

    def get_latest_frame(self):
        with self.frame_lock:
            if self.last_frame is None:
                return None, 0.0
            return self.last_frame, self.last_frame_time

    def get_latest_frame_id(self):
        with self.frame_lock:
            return self.frame_id

    def ensure_brawl_stars_on_primary_display(self, log_only=False, allow_app_restart=False):
        task_id, display_id = _get_package_task_display(
            self.connected_serial,
            self.brawl_stars_package,
            timeout=4,
        )
        if display_id is None:
            return True
        if display_id == 0:
            return True

        print(
            f"Brawl Stars is on Android displayId={display_id}; "
            "moving it back to displayId=0 for scrcpy capture."
        )
        _wake_android_display(self.connected_serial)

        for attempt in range(1, 3):
            moved = _move_android_task_to_display(self.connected_serial, task_id, 0)
            if not moved:
                _start_android_app_on_display(
                    self.connected_serial,
                    self.brawl_stars_package,
                    display_id=0,
                )
            time.sleep(0.8)
            task_id, new_display_id = _get_package_task_display(
                self.connected_serial,
                self.brawl_stars_package,
                timeout=4,
            )
            if new_display_id == 0:
                return True
            if new_display_id is not None:
                print(
                    f"Display repair attempt {attempt}/2 still sees Brawl Stars "
                    f"on displayId={new_display_id}."
                )

        if log_only:
            print("Could not verify Brawl Stars on displayId=0 yet; continuing startup.")
            return False
        if not allow_app_restart:
            print("Could not verify Brawl Stars on displayId=0 yet.")
            return False

        print("Brawl Stars did not move to displayId=0; restarting the app on displayId=0.")
        try:
            _stop_android_app(self.connected_serial, self.brawl_stars_package)
        except Exception:
            pass
        time.sleep(0.5)
        started = _start_android_app_on_display(
            self.connected_serial,
            self.brawl_stars_package,
            display_id=0,
        )
        time.sleep(2)
        _task_id, new_display_id = _get_package_task_display(
            self.connected_serial,
            self.brawl_stars_package,
            timeout=4,
        )
        if new_display_id == 0:
            return True
        if new_display_id is None:
            return started
        print(
            f"Brawl Stars relaunched but Android still reports displayId={new_display_id}; "
            "scrcpy may keep receiving stale frames."
        )
        return False

    def restart_brawl_stars(self):
        if not self.ensure_emulator_online():
            print("Cannot restart Brawl Stars because the emulator ADB device is offline.")
            return False
        try:
            self.keys_up(list("wasd"))
        except Exception:
            pass
        try:
            if not _stop_android_app(self.connected_serial, self.brawl_stars_package):
                self.device.app_stop(self.brawl_stars_package)
        except Exception as e:
            print(f"Could not stop Brawl Stars cleanly: {e}")
            if not self.restart_emulator_profile():
                return False
        time.sleep(1)
        try:
            if not _start_android_app_on_display(self.connected_serial, self.brawl_stars_package, display_id=0):
                self.device.app_start(self.brawl_stars_package)
        except Exception as e:
            print(f"Could not start Brawl Stars because ADB is offline: {e}")
            if not self.restart_emulator_profile():
                return False
            if not _start_android_app_on_display(self.connected_serial, self.brawl_stars_package, display_id=0):
                self.device.app_start(self.brawl_stars_package)
        time.sleep(3)
        self.ensure_brawl_stars_on_primary_display(allow_app_restart=True)
        self.time_since_checked_if_brawl_stars_crashed = time.time()
        self.foreground_check_failures = 0
        print("Brawl stars restarted successfully.")
        return True

    def foreground_package(self, timeout=4):
        return _get_foreground_package(self.connected_serial, timeout=timeout)

    def host_emulator_screenshot(self):
        if os.name != "nt":
            return None
        try:
            from PIL import ImageGrab
        except Exception:
            return None

        rects = []
        user32 = ctypes.windll.user32

        def enum_handler(hwnd, _):
            try:
                if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value
                if not _window_title_matches_emulator(title, getattr(self, "selected_emulator", "")):
                    return True
                rect = ctypes.wintypes.RECT()
                if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    return True
                box = (rect.left, rect.top, rect.right, rect.bottom)
                if _valid_window_rect(box):
                    rects.append((box, title))
            except Exception:
                pass
            return True

        try:
            enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(enum_handler)
            user32.EnumWindows(enum_proc, 0)
        except Exception:
            return None

        if not rects:
            return None

        rect, _title = max(
            rects,
            key=lambda item: (item[0][2] - item[0][0]) * (item[0][3] - item[0][1]),
        )
        try:
            image = ImageGrab.grab(bbox=rect)
            frame = np.array(image)
            if frame.ndim == 3 and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2RGB)
            return frame
        except Exception:
            return None

    def screenshot(self):
        if not self.ensure_emulator_online():
            raise ConnectionError("Emulator is offline and auto-restart is disabled.")
        c_time = time.time()
        if c_time - self.time_since_checked_if_brawl_stars_crashed > self.check_if_brawl_stars_crashed_timer:
            try:
                opened_app = _get_foreground_package(self.connected_serial, timeout=4)
                if not opened_app:
                    raise TimeoutError("Could not read foreground package through bounded ADB check.")
            except Exception as e:
                self.foreground_check_failures += 1
                print(
                    f"Could not query foreground app ({self.foreground_check_failures}/"
                    f"{self.foreground_failure_restart_threshold}): {e}"
                )
                self.time_since_checked_if_brawl_stars_crashed = c_time
                if self.foreground_check_failures < self.foreground_failure_restart_threshold:
                    opened_app = self.brawl_stars_package
                else:
                    print("Foreground checks keep failing; restarting emulator profile.")
                    if not self.restart_emulator_profile():
                        opened_app = self.brawl_stars_package
                    else:
                        opened_app = _get_foreground_package(self.connected_serial, timeout=4)
            if opened_app != self.brawl_stars_package:
                self.foreground_check_failures = 0
                print(f"Brawl stars has crashed, {opened_app} is the app opened ! Restarting...")
                try:
                    if not _start_android_app_on_display(self.connected_serial, self.brawl_stars_package, display_id=0):
                        self.device.app_start(self.brawl_stars_package)
                except Exception as e:
                    print(f"Could not start Brawl Stars, restarting emulator profile: {e}")
                    self.restart_emulator_profile()
                time.sleep(3)
                self.ensure_brawl_stars_on_primary_display(allow_app_restart=True)
                self.time_since_checked_if_brawl_stars_crashed = time.time()
            else:
                self.ensure_brawl_stars_on_primary_display(allow_app_restart=True)
                self.foreground_check_failures = 0
                self.time_since_checked_if_brawl_stars_crashed = c_time
        frame, frame_time = self.get_latest_frame()

        deadline = time.time() + 15
        while frame is None:
            if time.time() > deadline:
                raise ConnectionError(
                    "No frame received from scrcpy within 15s. "
                    "Check USB/emulator connection."
                )
            print("Waiting for first frame...")
            time.sleep(0.1)
            frame, frame_time = self.get_latest_frame()

        age = time.time() - frame_time
        if frame_time > 0 and age > self.FRAME_STALE_TIMEOUT:
            if time.time() - self.last_stale_warning_time > 2:
                print(f"WARNING: scrcpy frame is {age:.1f}s stale -- feed may be frozen")
                self.last_stale_warning_time = time.time()


        if not self.width or not self.height:
            self.width = frame.shape[1]
            self.height = frame.shape[0]
            expected_ratio = brawl_stars_width / brawl_stars_height
            actual_ratio = self.width / max(1, self.height)
            if abs(actual_ratio - expected_ratio) > 0.05:
                print(
                    f"Unexpected aspect ratio: {self.width}x{self.height}. "
                    "Use a 16:9 landscape emulator resolution for best results."
                )
            self.width_ratio = self.width / brawl_stars_width
            self.height_ratio = self.height / brawl_stars_height
            self.joystick_x, self.joystick_y = 220 * self.width_ratio, 870 * self.height_ratio
            self.scale_factor = min(self.width_ratio, self.height_ratio)

        return frame
    def touch_down(self, x, y, pointer_id=0):
        # We explicitly pass the pointer_id
        self.scrcpy_client.control.touch(int(x), int(y), scrcpy.ACTION_DOWN, pointer_id)

    def touch_move(self, x, y, pointer_id=0):
        self.scrcpy_client.control.touch(int(x), int(y), scrcpy.ACTION_MOVE, pointer_id)

    def touch_up(self, x, y, pointer_id=0):
        self.scrcpy_client.control.touch(int(x), int(y), scrcpy.ACTION_UP, pointer_id)

    def move_joystick_angle(self, angle_degrees: float, radius: float = 150.0):
        """Move the joystick in an exact direction given by angle_degrees.

        0° = right, 90° = down, 180° = left, 270° = up (screen coordinates).
        radius controls how far from center the touch point is placed.
        """
        angle_rad = math.radians(angle_degrees)
        scaled_radius = radius * self.scale_factor
        target_x = self.joystick_x + math.cos(angle_rad) * scaled_radius
        target_y = self.joystick_y + math.sin(angle_rad) * scaled_radius

        joystick_needs_refresh = time.time() - self.last_joystick_down_time > 2.0
        if self.are_we_moving and joystick_needs_refresh:
            self.stop_joystick()

        if not self.are_we_moving:
            self.touch_down(self.joystick_x, self.joystick_y, pointer_id=self.PID_JOYSTICK)
            self.are_we_moving = True
            self.last_joystick_down_time = time.time()
            self.last_joystick_pos = (target_x, target_y)
            self.touch_move(target_x, target_y, pointer_id=self.PID_JOYSTICK)
        elif self.last_joystick_pos != (target_x, target_y):
            self.touch_move(target_x, target_y, pointer_id=self.PID_JOYSTICK)
            self.last_joystick_pos = (target_x, target_y)

    def stop_joystick(self):
        """Release the joystick touch."""
        if self.are_we_moving:
            try:
                self.touch_up(self.joystick_x, self.joystick_y, pointer_id=self.PID_JOYSTICK)
            except Exception as e:
                print(f"Could not release joystick cleanly: {e}")
            self.are_we_moving = False
            self.last_joystick_down_time = 0.0
            self.last_joystick_pos = (None, None)

    def keys_up(self, keys: List[str]):
        if "".join(keys).lower() == "wasd":
            self.stop_joystick()

    def keys_down(self, keys: List[str]):

        delta_x, delta_y = 0, 0
        for key in keys:
            if key in directions_xy_deltas_dict:
                dx, dy = directions_xy_deltas_dict[key]
                delta_x += dx
                delta_y += dy

        joystick_needs_refresh = time.time() - self.last_joystick_down_time > 2.0
        if self.are_we_moving and joystick_needs_refresh:
            self.stop_joystick()

        if not self.are_we_moving:
            self.touch_down(self.joystick_x, self.joystick_y, pointer_id=self.PID_JOYSTICK)
            self.are_we_moving = True
            self.last_joystick_down_time = time.time()
            self.last_joystick_pos = (self.joystick_x + delta_x, self.joystick_y + delta_y)

        if self.last_joystick_pos != (self.joystick_x + delta_x, self.joystick_y + delta_y):
            self.touch_move(self.joystick_x + delta_x, self.joystick_y + delta_y, pointer_id=self.PID_JOYSTICK)
            self.last_joystick_pos = (self.joystick_x + delta_x, self.joystick_y + delta_y)

    def click(self, x: int, y: int, delay=0.005, already_include_ratio=True, touch_up=True, touch_down=True):
        if not already_include_ratio:
            x = x * self.width_ratio
            y = y * self.height_ratio
        # Use PID_ATTACK for clicks so we don't interrupt movement
        if touch_down: self.touch_down(x, y, pointer_id=self.PID_ATTACK)
        time.sleep(delay)
        if touch_up: self.touch_up(x, y, pointer_id=self.PID_ATTACK)

    def long_press(self, x: int, y: int, duration=1.15, already_include_ratio=True):
        if not already_include_ratio:
            x = x * self.width_ratio
            y = y * self.height_ratio
        self.touch_down(x, y, pointer_id=self.PID_ATTACK)
        time.sleep(duration)
        self.touch_up(x, y, pointer_id=self.PID_ATTACK)

    def press_key(self, key, delay=0.005, touch_up=True, touch_down=True):
        if key not in key_coords_dict:
            return
        x, y = key_coords_dict[key]
        target_x = x * self.width_ratio
        target_y = y * self.height_ratio
        self.click(target_x, target_y, delay, touch_up=touch_up, touch_down=touch_down)

    def android_back(self):
        try:
            completed = _run_adb(self.connected_serial, ["shell", "input", "keyevent", "4"], timeout=3)
            return completed.returncode == 0
        except Exception as e:
            print(f"Could not press Android Back through ADB: {e}")
            return False

    def aim_attack_angle(self, angle_degrees: float, radius: float = 170.0, duration: float = 0.04):
        x, y = key_coords_dict["M"]
        start_x = x * self.width_ratio
        start_y = y * self.height_ratio
        scaled_radius = radius * self.scale_factor
        angle_rad = math.radians(angle_degrees)
        end_x = start_x + math.cos(angle_rad) * scaled_radius
        end_y = start_y + math.sin(angle_rad) * scaled_radius
        self.swipe(start_x, start_y, end_x, end_y, duration=duration)

    def swipe(self, start_x, start_y, end_x, end_y, duration=0.2):
        dist_x = end_x - start_x
        dist_y = end_y - start_y
        distance = math.sqrt(dist_x ** 2 + dist_y ** 2)

        if distance == 0:
            return

        step_len = 25
        steps = max(int(distance / step_len), 1)
        step_delay = duration / steps

        self.touch_down(int(start_x), int(start_y), pointer_id=self.PID_ATTACK)
        for i in range(1, steps + 1):
            t = i / steps
            cx = start_x + dist_x * t
            cy = start_y + dist_y * t
            time.sleep(step_delay)
            self.touch_move(int(cx), int(cy), pointer_id=self.PID_ATTACK)
        self.touch_up(int(end_x), int(end_y), pointer_id=self.PID_ATTACK)

    def close(self):
        if hasattr(self, 'scrcpy_client'):
            client = self.scrcpy_client
            self.scrcpy_client = None
            if hasattr(self, "scrcpy_generation"):
                self.scrcpy_generation += 1
            if client is not None:
                client.stop()
