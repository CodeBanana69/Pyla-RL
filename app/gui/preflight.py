import os
import re
import shutil
import subprocess
from pathlib import Path

from gui.emulator_adb import (
    connect_emulator_adb,
    detect_emulator_process,
    normalize_emulator_name,
    ports_for_emulator,
    run_adb as _run_adb,
)
from utils import load_toml_as_dict, save_dict_as_toml

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


def _check_item(item_id, label, ok, detail, severity="required", fix=None):
    item = {
        "id": item_id,
        "label": label,
        "ok": bool(ok),
        "severity": severity,
        "detail": detail,
    }
    if fix and not ok:
        item["fix"] = fix
    return item


def _resolve_emulator_settings(general, emulator=None, port=None):
    selected = normalize_emulator_name(emulator or general.get("current_emulator", "LDPlayer"))
    if port is not None:
        try:
            configured_port = int(port)
        except (TypeError, ValueError):
            configured_port = ports_for_emulator(selected)[0]
    else:
        try:
            configured_port = int(general.get("emulator_port", ports_for_emulator(selected)[0]) or ports_for_emulator(selected)[0])
        except (TypeError, ValueError):
            configured_port = ports_for_emulator(selected)[0]
    return selected, configured_port


def _persist_discovered_port(emulator, port, previous_port):
    if not port or port == previous_port:
        return
    general_path = "cfg/general_config.toml"
    general = load_toml_as_dict(general_path)
    general["current_emulator"] = emulator
    general["emulator_port"] = int(port)
    save_dict_as_toml(general, general_path)


def check_emulator_status(emulator, port=None):
    selected = normalize_emulator_name(emulator)
    general = load_toml_as_dict("cfg/general_config.toml")
    _, configured_port = _resolve_emulator_settings(
        general,
        emulator=selected.lower(),
        port=port,
    )
    process_ok, process_detail = detect_emulator_process(selected)
    if not process_ok:
        return {
            "ok": False,
            "process_ok": False,
            "adb_ok": False,
            "process_detail": process_detail,
            "detail": process_detail,
            "checked": True,
        }

    adb_result = connect_emulator_adb(selected, configured_port)
    adb_ok = bool(adb_result.get("ok"))
    adb_detail = str(adb_result.get("detail") or "ADB check failed")
    return {
        "ok": adb_ok,
        "process_ok": True,
        "adb_ok": adb_ok,
        "process_detail": process_detail,
        "detail": adb_detail,
        "checked": True,
    }


def _emulator_status_summary(selected_emulator=None):
    if selected_emulator:
        key = normalize_emulator_name(selected_emulator).lower()
        return {key: check_emulator_status(key)}
    return {
        "ldplayer": check_emulator_status("ldplayer"),
        "mumu": check_emulator_status("mumu"),
    }


def _selected_emulator_status(selected_emulator, process_ok, process_detail, adb_result):
    selected_key = normalize_emulator_name(selected_emulator).lower()
    adb_ok = bool(adb_result.get("ok"))
    adb_detail = str(adb_result.get("detail") or "ADB check failed")
    if not process_ok:
        return {
            selected_key: {
                "ok": False,
                "process_ok": False,
                "adb_ok": False,
                "process_detail": process_detail,
                "detail": process_detail,
                "checked": True,
            }
        }
    return {
        selected_key: {
            "ok": adb_ok,
            "process_ok": True,
            "adb_ok": adb_ok,
            "process_detail": process_detail,
            "detail": adb_detail,
            "checked": True,
        }
    }


def run_preflight_checks(correct_zoom=True, emulator=None, port=None, persist_port=True):
    try:
        return _run_preflight_checks(
            correct_zoom=correct_zoom,
            emulator=emulator,
            port=port,
            persist_port=persist_port,
        )
    except Exception as exc:
        return {
            "ready": False,
            "checks": [
                _check_item(
                    "preflight",
                    "Pre-flight checks",
                    False,
                    str(exc),
                    "required",
                )
            ],
            "emulator_status": _emulator_status_summary(emulator or "LDPlayer"),
            "emulator": normalize_emulator_name(emulator or "LDPlayer"),
            "port": 0,
            "serial": "",
        }


def _run_preflight_checks(correct_zoom=True, emulator=None, port=None, persist_port=True):
    general = load_toml_as_dict("cfg/general_config.toml")
    selected_emulator, configured_port = _resolve_emulator_settings(general, emulator=emulator, port=port)
    previous_port = int(general.get("emulator_port", configured_port) or configured_port)
    process_ok, process_detail = detect_emulator_process(selected_emulator)

    checks = []

    adb_result = connect_emulator_adb(
        selected_emulator,
        configured_port,
        max_ports=4,
    )
    emulator_status = _selected_emulator_status(
        selected_emulator,
        process_ok,
        process_detail,
        adb_result,
    )
    adb_ok = bool(adb_result.get("ok"))
    serial = str(adb_result.get("serial") or "")
    connected_port = int(adb_result.get("port") or configured_port or 0)
    if adb_ok and persist_port and connected_port:
        _persist_discovered_port(selected_emulator, connected_port, previous_port)

    adb_label = f"ADB device {serial or f'127.0.0.1:{configured_port}'}"
    checks.append(_check_item(
        "adb",
        adb_label,
        adb_ok,
        adb_result.get("detail") if adb_ok else adb_result.get("detail", "ADB check failed"),
        "required",
        fix={"action": "reconnect_adb", "label": "Reconnect ADB"} if not adb_ok else None,
    ))

    selected_status = emulator_status.get(selected_emulator.lower(), {})
    process_ok = bool(selected_status.get("process_ok"))
    if process_ok:
        process_detail = str(selected_status.get("process_detail") or f"Detected {selected_emulator}")
    else:
        process_detail = str(
            selected_status.get("process_detail")
            or selected_status.get("detail")
            or f"No {selected_emulator} process found"
        )
    checks.append(_check_item(
        "emulator",
        f"{selected_emulator} process",
        process_ok,
        process_detail,
        "recommended",
        fix={"action": "start_emulator", "label": "Start Emulator"} if not process_ok else None,
    ))

    package = str(general.get("brawl_stars_package", "com.supercell.brawlstars"))
    foreground_ok = False
    if adb_ok and serial:
        output, _ = _run_adb(["shell", "dumpsys", "window", "windows"], serial=serial)
        if output:
            foreground_ok = package in output
    checks.append(_check_item(
        "game",
        "Brawl Stars foreground",
        foreground_ok,
        "In foreground" if foreground_ok else "Open Brawl Stars on the emulator before START",
        "recommended",
        fix={"action": "launch_game", "label": "Launch Game"} if not foreground_ok else None,
    ))

    resolution_ok = False
    resolution_detail = "Use 1920x1080 emulator resolution for best accuracy"
    if adb_ok and serial:
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
        fix={"action": "set_resolution", "label": "Resolution Help"} if not resolution_ok else None,
    ))

    checks.append(_check_item(
        "scaling",
        "Windows display scaling 100%",
        bool(correct_zoom),
        "Display scaling is 100%" if correct_zoom else "Set Windows display scaling to 100% to avoid misclicks",
        "recommended",
    ))

    ready = all(item["ok"] for item in checks if item["severity"] == "required")
    return {
        "ready": ready,
        "checks": checks,
        "emulator_status": emulator_status,
        "emulator": selected_emulator,
        "port": connected_port if adb_ok else configured_port,
        "serial": serial,
    }


def test_emulator_connection(emulator=None, port=None):
    result = run_preflight_checks(emulator=emulator, port=port, persist_port=False)
    adb = next((item for item in result["checks"] if item["id"] == "adb"), None)
    if adb and adb["ok"]:
        return True, adb["detail"]
    return False, adb["detail"] if adb else "ADB check failed"
