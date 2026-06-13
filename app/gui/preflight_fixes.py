from __future__ import annotations

import subprocess
from typing import Any

from gui.emulator_adb import connect_emulator_adb, run_adb
from gui.instance_config import (
    _ldplayer_console_path,
    _mumu_manager_path,
    emulator_display_name,
    normalize_emulator_name,
    port_for_profile_index,
)
from utils import load_toml_as_dict


def run_preflight_fix(action: str, *, emulator: str | None = None, port: int | None = None) -> tuple[bool, str]:
    action = str(action or "").strip().lower()
    general = load_toml_as_dict("cfg/general_config.toml")
    selected = normalize_emulator_name(emulator or general.get("current_emulator", "LDPlayer"))
    try:
        configured_port = int(port or general.get("emulator_port", port_for_profile_index(selected, 0)))
    except (TypeError, ValueError):
        configured_port = port_for_profile_index(selected, 0)

    if action == "start_emulator":
        return _start_emulator(selected, configured_port)
    if action == "reconnect_adb":
        return _reconnect_adb(selected, configured_port)
    if action == "launch_game":
        return _launch_game(selected, configured_port)
    if action == "set_resolution":
        return False, "Set emulator resolution to 1920x1080 in the emulator settings, then re-run pre-flight."
    return False, f"Unknown fix action '{action}'."


def _start_emulator(emulator: str, port: int) -> tuple[bool, str]:
    index = max(0, (port - port_for_profile_index(emulator, 0)) // (2 if emulator == "ldplayer" else 32))
    if emulator == "mumu":
        manager = _mumu_manager_path()
        if not manager:
            return False, "MuMu manager not found."
        completed = subprocess.run(
            [manager, "control", "--vmindex", str(index), "launch"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        ok = completed.returncode == 0
        return ok, "MuMu launch requested." if ok else (completed.stderr or completed.stdout or "MuMu launch failed.")

    console = _ldplayer_console_path()
    if not console:
        return False, "LDPlayer console not found."
    completed = subprocess.run(
        [console, "launch", "--index", str(index)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    ok = completed.returncode == 0
    return ok, f"LDPlayer instance {index} launch requested." if ok else (completed.stderr or completed.stdout or "Launch failed.")


def _reconnect_adb(emulator: str, port: int) -> tuple[bool, str]:
    run_adb(["kill-server"])
    result = connect_emulator_adb(emulator_display_name(emulator), port, max_ports=4)
    if result.get("ok"):
        return True, str(result.get("detail") or "ADB reconnected.")
    return False, str(result.get("detail") or "ADB reconnect failed.")


def _launch_game(emulator: str, port: int) -> tuple[bool, str]:
    result = connect_emulator_adb(emulator_display_name(emulator), port, max_ports=4)
    if not result.get("ok"):
        return False, str(result.get("detail") or "ADB not connected.")
    serial = str(result.get("serial") or "")
    package = str(load_toml_as_dict("cfg/general_config.toml").get("brawl_stars_package", "com.supercell.brawlstars"))
    output, error = run_adb(
        ["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"],
        serial=serial,
    )
    if error and "Error" in error:
        return False, error
    return True, output or "Brawl Stars launch requested."
