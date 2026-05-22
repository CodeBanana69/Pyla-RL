import os
import re
import shutil
import subprocess
from pathlib import Path

from utils import load_toml_as_dict

LOCAL_ADB_EXE = Path(__file__).resolve().parent.parent / "adb.exe"
RESOLUTION_1080P_OK = {
    (1920, 1080),
    (1080, 1920),
    (960, 540),
    (540, 960),
}
RESOLUTION_720P_OK = {
    (1280, 720),
    (720, 1280),
}


def _adb_executable():
    if LOCAL_ADB_EXE.exists():
        return str(LOCAL_ADB_EXE)
    found = shutil.which("adb")
    return found or ""


def _run_adb(args, serial=None, timeout=8):
    adb = _adb_executable()
    if not adb:
        return None, "ADB not found (bundled adb.exe and PATH both missing)"
    command = [adb]
    if serial:
        command.extend(["-s", serial])
    command.extend(args)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        return None, output.strip() or f"adb exited with code {result.returncode}"
    return output.strip(), ""


def _list_adb_devices():
    output, error = _run_adb(["devices"])
    if not output:
        return [], error
    devices = []
    for line in output.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices, ""


def _is_serial_online(serial):
    if not serial:
        return False
    for device in _list_adb_devices()[0]:
        if device == serial:
            return True
    return False


def _adb_connect(serial):
    if _is_serial_online(serial):
        return True, "Connected"
    output, error = _run_adb(["connect", serial], timeout=10)
    if error:
        return False, error
    if _is_serial_online(serial):
        return True, output or "Connected"
    return False, output or f"Could not connect to {serial}"


def _parse_wm_sizes(output):
    if not output:
        return None, None
    physical = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
    override = re.search(r"Override size:\s*(\d+)x(\d+)", output)
    physical_size = None
    override_size = None
    if physical:
        physical_size = (int(physical.group(1)), int(physical.group(2)))
    if override:
        override_size = (int(override.group(1)), int(override.group(2)))
    if not physical_size and not override_size:
        fallback = re.search(r"(\d{3,5})x(\d{3,5})", output)
        if fallback:
            physical_size = (int(fallback.group(1)), int(fallback.group(2)))
    return physical_size, override_size


def _resolution_status(width, height):
    pair = (width, height)
    reverse = (height, width)
    if pair in RESOLUTION_1080P_OK or reverse in RESOLUTION_1080P_OK:
        if pair in {(960, 540), (540, 960)} or reverse in {(960, 540), (540, 960)}:
            return True, f"Detected {width}x{height} (1080p half-scale OK)"
        return True, f"Detected {width}x{height}"
    if pair in RESOLUTION_720P_OK or reverse in RESOLUTION_720P_OK:
        return True, f"Detected {width}x{height} (720p OK, 1080p recommended)"
    return False, f"Detected {width}x{height} — 1920x1080 recommended"


def _check_item(item_id, label, ok, detail, severity="required"):
    return {
        "id": item_id,
        "label": label,
        "ok": bool(ok),
        "severity": severity,
        "detail": detail,
    }


def run_preflight_checks(correct_zoom=True):
    general = load_toml_as_dict("cfg/general_config.toml")
    emulator = str(general.get("current_emulator", "LDPlayer")).strip()
    port = int(general.get("emulator_port", 5555) or 5555)
    serial = f"127.0.0.1:{port}"
    adb_path = _adb_executable()

    checks = []

    devices, devices_error = _list_adb_devices()
    adb_ok = _is_serial_online(serial)
    if not adb_ok:
        connected, connect_message = _adb_connect(serial)
        adb_ok = connected
        if not adb_ok:
            devices, devices_error = _list_adb_devices()
    adb_detail = "Connected"
    if not adb_ok:
        device_hint = ", ".join(devices) if devices else "none"
        adb_detail = (
            f"{serial} not online using {adb_path or 'missing adb'}. "
            f"Configured port {port}. Seen devices: {device_hint}."
        )
        if devices_error:
            adb_detail += f" {devices_error}"
        elif not adb_ok and connect_message:
            adb_detail += f" {connect_message}"
    checks.append(_check_item(
        "adb",
        f"ADB device {serial}",
        adb_ok,
        adb_detail,
        "required",
    ))

    process_hint = "dnplayer" if emulator.lower() == "ldplayer" else "MuMu"
    process_ok = False
    if shutil.which("tasklist"):
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {process_hint}*"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            process_ok = process_hint.lower() in (result.stdout or "").lower()
        except (OSError, subprocess.TimeoutExpired):
            process_ok = False
    checks.append(_check_item(
        "emulator",
        f"{emulator} process",
        process_ok,
        "Detected" if process_ok else f"No {process_hint} process found",
        "required",
    ))

    package = str(general.get("brawl_stars_package", "com.supercell.brawlstars"))
    foreground_ok = False
    if adb_ok:
        output, _ = _run_adb(["shell", "dumpsys", "window", "windows"], serial=serial)
        if output:
            foreground_ok = package in output
    checks.append(_check_item(
        "game",
        "Brawl Stars foreground",
        foreground_ok,
        "In foreground" if foreground_ok else "Open Brawl Stars on the emulator before START",
        "recommended",
    ))

    resolution_ok = False
    resolution_detail = "Use 1920x1080 emulator resolution for best accuracy"
    if adb_ok:
        size_output, size_error = _run_adb(["shell", "wm", "size"], serial=serial)
        physical_size, override_size = _parse_wm_sizes(size_output or "")
        chosen = physical_size or override_size
        if chosen:
            resolution_ok, resolution_detail = _resolution_status(chosen[0], chosen[1])
        elif size_error:
            resolution_detail = size_error

    checks.append(_check_item(
        "resolution",
        "1080p recommended",
        resolution_ok,
        resolution_detail,
        "recommended",
    ))

    checks.append(_check_item(
        "scaling",
        "Windows display scaling 100%",
        bool(correct_zoom),
        "Display scaling is 100%" if correct_zoom else "Set Windows display scaling to 100% to avoid misclicks",
        "recommended",
    ))

    ready = all(item["ok"] for item in checks if item["severity"] == "required")
    return {"ready": ready, "checks": checks}


def test_emulator_connection():
    result = run_preflight_checks()
    adb = next((item for item in result["checks"] if item["id"] == "adb"), None)
    if adb and adb["ok"]:
        return True, adb["detail"]
    return False, adb["detail"] if adb else "ADB check failed"
