"""Pin and verify the Python interpreter used by Pyla-RL on Windows."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

PYTHON_PIN_RELATIVE = Path("cfg") / "pyla_python.txt"
SETUP_STATUS_RELATIVE = Path("cfg") / "setup_runtime.json"


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
        output = subprocess.check_output(
            python_command + ["-c", script],
            stderr=subprocess.STDOUT,
            text=True,
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
        "for module_name, attr in (('cv2', '__version__'), ('pandas', '__version__')):\n"
        "    try:\n"
        "        module = __import__(module_name)\n"
        "        versions[module_name] = getattr(module, attr, 'ok')\n"
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
        output = subprocess.check_output(
            python_command + ["-c", script],
            stderr=subprocess.STDOUT,
            text=True,
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


def write_setup_status(project_dir: Path, *, python_executable: str, cv2_version: str) -> Path:
    status_path = setup_status_path(project_dir)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "python_executable": python_executable,
        "cv2_version": cv2_version,
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    status_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return status_path
