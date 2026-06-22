"""Pin and verify the Python interpreter used by Pyla-RL on Windows."""

from __future__ import annotations

import json
import os
import subprocess

from subprocess_text import run_text, check_output_text
import sys
import time
from pathlib import Path

PYTHON_PIN_RELATIVE = Path("cfg") / "pyla_python.txt"
SETUP_STATUS_RELATIVE = Path("cfg") / "setup_runtime.json"
SUPPORTED_PYTHON = (3, 11)


def bundle_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def project_dir() -> Path:
    return bundle_dir().parent


def python_version_info(python_command: list[str] | str) -> tuple[int, int, int] | None:
    if isinstance(python_command, str):
        python_command = [python_command]
    completed = run_text(
        python_command + ["-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    parts = (completed.stdout or "").strip().split(".")
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except (IndexError, TypeError, ValueError):
        return None


def is_supported_python(python_command: list[str] | str) -> bool:
    version = python_version_info(python_command)
    return version is not None and version[:2] == SUPPORTED_PYTHON


def unsupported_python_message(python_command: list[str] | str) -> str:
    version = python_version_info(python_command)
    label = version and f"{version[0]}.{version[1]}.{version[2]}" or "unknown"
    executable = python_command if isinstance(python_command, str) else " ".join(python_command)
    return (
        f"Pyla-RL requires Python 3.11 64-bit (current: {label} via {executable}). "
        "Run setup.cmd, use pyla-rl.bat, or rerun with: py -3.11-64 tools\\fix_gpu_runtime.py auto"
    )


def resolve_project_python_executable() -> str | None:
    bundle = bundle_dir()
    pin = read_python_pin(bundle)
    if pin and is_supported_python(pin):
        return pin

    venv_python = bundle / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists() and is_supported_python(str(venv_python)):
        return str(venv_python)

    for command in (["py", "-3.11-64"], ["py", "-3.11"]):
        if is_supported_python(command):
            probe = probe_runtime_imports(command)
            if probe.get("ok"):
                return str(probe.get("executable") or "")

    if is_supported_python(sys.executable):
        return sys.executable
    return None


def ensure_project_python_for_tools(*, script_path: Path | None = None) -> str:
    resolved = resolve_project_python_executable()
    if not resolved:
        raise SystemExit(unsupported_python_message(sys.executable))

    if script_path is not None and os.path.normcase(resolved) != os.path.normcase(sys.executable):
        print(unsupported_python_message(sys.executable))
        print(f"Switching to project Python: {resolved}")
        os.execv(resolved, [resolved, str(script_path), *sys.argv[1:]])
    return resolved



def python_pin_path(project_dir: Path) -> Path:
    return Path(project_dir) / PYTHON_PIN_RELATIVE


def setup_status_path(project_dir: Path) -> Path:
    return Path(project_dir) / SETUP_STATUS_RELATIVE


def write_python_pin(project_dir: Path, executable: str) -> Path:
    pin_path = python_pin_path(project_dir)
    pin_path.parent.mkdir(parents=True, exist_ok=True)
    pin_path.write_text(executable.strip() + "\n", encoding="utf-8")
    return pin_path


def read_python_pin(project_dir: Path) -> str | None:
    pin_path = python_pin_path(project_dir)
    if not pin_path.exists():
        return None
    value = pin_path.read_text(encoding="utf-8").strip()
    return value or None


def probe_cv2(python_command: list[str]) -> dict:
    script = (
        "import json, sys\n"
        "try:\n"
        "    import cv2\n"
        "    print(json.dumps({'ok': True, 'executable': sys.executable, 'cv2': cv2.__version__}))\n"
        "except Exception as exc:\n"
        "    print(json.dumps({'ok': False, 'executable': sys.executable, 'error': str(exc)}))\n"
    )
    try:
        output = check_output_text(
            python_command + ["-c", script],
            stderr=subprocess.STDOUT,
        ).strip()
        return json.loads(output.splitlines()[-1])
    except Exception as exc:
        return {"ok": False, "executable": " ".join(python_command), "error": str(exc)}


def verify_cv2_import(python_command: list[str]) -> dict:
    result = probe_cv2(python_command)
    if not result.get("ok"):
        raise RuntimeError(
            f"OpenCV (cv2) is not importable with {result.get('executable')}: "
            f"{result.get('error', 'unknown error')}"
        )
    return result


def probe_runtime_imports(python_command: list[str]) -> dict:
    script = (
        "import json, sys\n"
        "errors = []\n"
        "versions = {}\n"
        "for module_name, attr in (('cv2', '__version__'), ('pandas', '__version__'), ('onnxruntime', '__version__')):\n"
        "    try:\n"
        "        module = __import__(module_name)\n"
        "        versions[module_name] = getattr(module, attr, 'ok')\n"
        "        if module_name == 'onnxruntime':\n"
        "            versions['onnxruntime_providers'] = module.get_available_providers()\n"
        "    except Exception as exc:\n"
        "        errors.append(f'{module_name}: {exc}')\n"
        "print(json.dumps({\n"
        "    'ok': not errors,\n"
        "    'executable': sys.executable,\n"
        "    'versions': versions,\n"
        "    'error': '; '.join(errors),\n"
        "}))\n"
    )
    try:
        output = check_output_text(
            python_command + ["-c", script],
            stderr=subprocess.STDOUT,
        ).strip()
        return json.loads(output.splitlines()[-1])
    except Exception as exc:
        return {"ok": False, "executable": " ".join(python_command), "error": str(exc)}


def verify_runtime_imports(python_command: list[str]) -> dict:
    result = probe_runtime_imports(python_command)
    if not result.get("ok"):
        raise RuntimeError(
            f"Required runtime packages are missing for {result.get('executable')}: "
            f"{result.get('error', 'unknown error')}"
        )
    return result


def write_setup_status(
    project_dir: Path,
    *,
    python_executable: str,
    cv2_version: str,
    easyocr_verified: bool = False,
    torch_version: str = "",
) -> Path:
    status_path = setup_status_path(project_dir)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "python_executable": python_executable,
        "cv2_version": cv2_version,
        "easyocr_verified": bool(easyocr_verified),
        "torch_version": torch_version,
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    status_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return status_path
