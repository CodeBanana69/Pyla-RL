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


def run_preflight_checks():
    general = load_toml_as_dict("cfg/general_config.toml")
    emulator = str(general.get("current_emulator", "LDPlayer")).strip()
    port = int(general.get("emulator_port", 5555) or 5555)
    serial = f"127.0.0.1:{port}"

    checks = []

    adb_output, adb_error = _run_adb(["devices"])
    adb_ok = bool(adb_output) and serial in adb_output and "\tdevice" in adb_output
    checks.append({
        "id": "adb",
        "label": f"ADB device {serial}",
        "ok": adb_ok,
        "detail": "Connected" if adb_ok else (adb_error or f"{serial} not listed as device"),
    })

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
    checks.append({
        "id": "emulator",
        "label": f"{emulator} process",
        "ok": process_ok,
        "detail": "Detected" if process_ok else f"No {process_hint} process found",
    })

    package = str(general.get("brawl_stars_package", "com.supercell.brawlstars"))
    foreground_ok = False
    if adb_ok:
        output, _ = _run_adb(["-s", serial, "shell", "dumpsys", "window", "windows"])
        if output:
            foreground_ok = package in output
    checks.append({
        "id": "game",
        "label": "Brawl Stars foreground",
        "ok": foreground_ok,
        "detail": "In foreground" if foreground_ok else "Open Brawl Stars on the emulator before START",
    })

    checks.append({
        "id": "resolution",
        "label": "1080p recommended",
        "ok": True,
        "detail": "Use 1920x1080 emulator resolution and 100% Windows display scaling for best accuracy",
    })

    ready = all(item["ok"] for item in checks if item["id"] != "game")
    return {"ready": ready, "checks": checks}


def test_emulator_connection():
    result = run_preflight_checks()
    adb = next((item for item in result["checks"] if item["id"] == "adb"), None)
    if adb and adb["ok"]:
        return True, adb["detail"]
    return False, adb["detail"] if adb else "ADB check failed"
