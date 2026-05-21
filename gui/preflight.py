import re
import shutil
import subprocess
from pathlib import Path

from utils import load_toml_as_dict


def _run_adb(args, timeout=8):
    adb = shutil.which("adb")
    if not adb:
        return None, "ADB not found in PATH"
    try:
        result = subprocess.run(
            [adb, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        return None, output.strip() or f"adb exited with code {result.returncode}"
    return output.strip(), ""


def _parse_wm_size(output):
    if not output:
        return None
    match = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
    if not match:
        match = re.search(r"Override size:\s*(\d+)x(\d+)", output)
    if not match:
        match = re.search(r"(\d{3,5})x(\d{3,5})", output)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


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

    checks = []

    adb_output, adb_error = _run_adb(["devices"])
    adb_ok = bool(adb_output) and serial in adb_output and "\tdevice" in adb_output
    checks.append(_check_item(
        "adb",
        f"ADB device {serial}",
        adb_ok,
        "Connected" if adb_ok else (adb_error or f"{serial} not listed as device"),
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
        output, _ = _run_adb(["-s", serial, "shell", "dumpsys", "window", "windows"])
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
        size_output, _ = _run_adb(["-s", serial, "shell", "wm", "size"])
        parsed = _parse_wm_size(size_output or "")
        if parsed:
            width, height = parsed
            resolution_ok = (width, height) == (1920, 1080) or (width, height) == (1080, 1920)
            resolution_detail = f"Detected {width}x{height}" + (
                "" if resolution_ok else " — 1920x1080 recommended"
            )
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
