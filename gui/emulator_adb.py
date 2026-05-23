"""Emulator-aware ADB discovery shared by preflight and window_controller."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

EMULATOR_PORTS = {
    "LDPlayer": [5555, 5557, 5559, 5554],
    "MuMu": [16384, 16416, 16448, 7555, 5558, 5557, 5556, 5555, 5554],
}

SUPPORTED_EMULATORS = tuple(EMULATOR_PORTS.keys())
ADB_SERVER_PORT = 5037

LOCAL_ADB_EXE = Path(__file__).resolve().parent.parent / "adb.exe"

LDPLAYER_PROCESS_NAMES = (
    "dnplayer.exe",
    "ldplayer.exe",
    "ld9boxheadless.exe",
    "ldboxheadless.exe",
    "ldplayerservice.exe",
)

MUMU_PROCESS_NAMES = (
    "mumuplayer.exe",
    "mumunxdevice.exe",
    "nemuplayer.exe",
    "mumu.exe",
)


def normalize_emulator_name(value: str) -> str:
    name = str(value or "LDPlayer").strip().lower()
    if name == "mumu":
        return "MuMu"
    return "LDPlayer"


def ports_for_emulator(emulator: str, preferred_port: int | None = None) -> list[int]:
    selected = normalize_emulator_name(emulator)
    ports = list(EMULATOR_PORTS.get(selected, EMULATOR_PORTS["LDPlayer"]))
    if preferred_port:
        try:
            port = int(preferred_port)
        except (TypeError, ValueError):
            port = 0
        if port and port != ADB_SERVER_PORT and port not in ports:
            ports.insert(0, port)
        elif port and port in ports:
            ports.remove(port)
            ports.insert(0, port)
    return ports


def adb_executable() -> str:
    if LOCAL_ADB_EXE.exists():
        return str(LOCAL_ADB_EXE)
    return shutil.which("adb") or ""


def _run_adb(args: list[str], serial: str | None = None, timeout: int = 8) -> tuple[str | None, str]:
    adb = adb_executable()
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


def list_adb_devices() -> tuple[list[str], str]:
    output, error = _run_adb(["devices"])
    if not output:
        return [], error
    devices = []
    for line in output.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices, ""


def serial_port(serial: str) -> int | None:
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


def is_local_adb_serial(serial: str) -> bool:
    return (
        str(serial or "").startswith("127.0.0.1:")
        or str(serial or "").startswith("localhost:")
        or str(serial or "").startswith("emulator-")
    )


def is_port_open(host: str, port: int, timeout: float = 0.05) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((host, port)) == 0
    except OSError:
        return False


def adb_start_server() -> None:
    _run_adb(["start-server"], timeout=10)


def adb_connect_serial(serial: str) -> tuple[bool, str]:
    devices, _ = list_adb_devices()
    if serial in devices:
        return True, "Connected"
    output, error = _run_adb(["connect", serial], timeout=10)
    if error:
        return False, error
    devices, _ = list_adb_devices()
    if serial in devices:
        return True, output or "Connected"
    return False, output or f"Could not connect to {serial}"


def adb_hint_for_emulator(emulator: str) -> str:
    if normalize_emulator_name(emulator) == "MuMu":
        return "In MuMu, open Settings and confirm ADB is enabled (default port 16384 for instance 0)."
    return "In LDPlayer, open Settings → Other settings → enable ADB debugging, then restart the emulator."


def connect_emulator_adb(
    emulator: str,
    preferred_port: int | None = None,
    *,
    probe_open_ports: bool = True,
) -> dict:
    selected = normalize_emulator_name(emulator)
    candidate_ports = ports_for_emulator(selected, preferred_port)
    adb_path = adb_executable()
    if not adb_path:
        return {
            "ok": False,
            "serial": "",
            "port": 0,
            "detail": "ADB not found (bundled adb.exe and PATH both missing)",
            "ports_tried": candidate_ports,
        }

    adb_start_server()
    devices, devices_error = list_adb_devices()
    allowed_ports = set(candidate_ports)

    for device in devices:
        port = serial_port(device)
        if is_local_adb_serial(device) and port in allowed_ports:
            return {
                "ok": True,
                "serial": device,
                "port": port or 0,
                "detail": f"Connected to {device}",
                "ports_tried": candidate_ports,
            }

    ports_to_try = candidate_ports
    if probe_open_ports:
        open_ports = [port for port in candidate_ports if is_port_open("127.0.0.1", port)]
        if open_ports:
            ports_to_try = open_ports + [port for port in candidate_ports if port not in open_ports]

    last_message = devices_error or ""
    for port in ports_to_try:
        serial = f"127.0.0.1:{port}"
        connected, message = adb_connect_serial(serial)
        if connected:
            return {
                "ok": True,
                "serial": serial,
                "port": port,
                "detail": f"Connected to {serial}",
                "ports_tried": candidate_ports,
            }
        last_message = message or last_message

    device_hint = ", ".join(devices) if devices else "none"
    detail = (
        f"No {selected} ADB device online on ports {', '.join(str(p) for p in candidate_ports)} "
        f"using {adb_path}. Seen devices: {device_hint}."
    )
    if last_message:
        detail += f" {last_message}"
    detail += f" {adb_hint_for_emulator(selected)}"
    return {
        "ok": False,
        "serial": "",
        "port": 0,
        "detail": detail,
        "ports_tried": candidate_ports,
    }


def detect_emulator_process(emulator: str) -> tuple[bool, str]:
    selected = normalize_emulator_name(emulator)
    names = LDPLAYER_PROCESS_NAMES if selected == "LDPlayer" else MUMU_PROCESS_NAMES
    if not shutil.which("tasklist"):
        return False, "tasklist unavailable"
    try:
        result = subprocess.run(
            ["tasklist"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        output = (result.stdout or "").lower()
    except (OSError, subprocess.TimeoutExpired):
        return False, f"No {selected} process found"

    for name in names:
        if name.lower() in output:
            return True, f"Detected {name}"
    return False, f"No {selected} process found ({', '.join(names[:3])}, ...)"


def device_matches_emulator(serial: str, emulator: str, preferred_port: int | None = None) -> bool:
    port = serial_port(serial)
    if port is None:
        return False
    return port in set(ports_for_emulator(emulator, preferred_port))
