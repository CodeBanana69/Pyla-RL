"""Minimal frozen-exe bootstrap: delegate to on-disk app/tools/*.py via Python 3.11."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from subprocess_text import run_text, check_output_text

PYTHON_MAJOR_MINOR = "3.11"
SETUP_SCRIPT = Path("tools") / "setup_bootstrap.py"
UPDATER_SCRIPT = Path("tools") / "updater.py"


def install_root_from_frozen_exe() -> Path:
    return Path(sys.executable).resolve().parent


def bundle_dir_from_install(install_root: Path) -> Path:
    return install_root / "app"


def _python_info(command: list[str]) -> str | None:
    try:
        output = check_output_text(
            command
            + [
                "-c",
                "import platform,sys; "
                "print(sys.executable); "
                "print(platform.python_version()); "
                "print(platform.architecture()[0])",
            ],
            stderr=subprocess.DEVNULL,
            timeout=30,
        ).strip().splitlines()
    except Exception:
        return None
    if len(output) < 3:
        return None
    executable, version, arch = output[:3]
    if version.startswith(PYTHON_MAJOR_MINOR + ".") and arch == "64bit":
        return executable
    return None


def _system_python_candidates() -> list[list[str]]:
    candidates: list[list[str]] = [
        ["py", f"-{PYTHON_MAJOR_MINOR}-64"],
        ["py", PYTHON_MAJOR_MINOR],
        ["python"],
    ]
    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        for python_exe in Path(local_app).glob("Programs/Python/Python311/python.exe"):
            candidates.append([str(python_exe)])
    program_files = os.environ.get("ProgramFiles", "")
    if program_files:
        for python_exe in Path(program_files).glob("Python311/python.exe"):
            candidates.append([str(python_exe)])
    return candidates


def resolve_system_python() -> list[str] | None:
    for command in _system_python_candidates():
        if _python_info(command):
            return command
    return None


def _read_python_pin(bundle: Path) -> str | None:
    pin_path = bundle / "cfg" / "pyla_python.txt"
    if not pin_path.is_file():
        return None
    value = pin_path.read_text(encoding="utf-8").strip()
    if value and _python_info([value]):
        return value
    return None


def resolve_python_for_launch(bundle: Path, *, prefer_venv: bool) -> list[str] | None:
    if prefer_venv:
        pin = _read_python_pin(bundle)
        if pin:
            return [pin]
        venv_python = bundle / ".venv" / "Scripts" / "python.exe"
        if venv_python.is_file() and _python_info([str(venv_python)]):
            return [str(venv_python)]
    return resolve_system_python()


def delegate_to_script(bundle: Path, install_root: Path, script_relative: Path) -> int:
    script_path = bundle / script_relative
    if not script_path.is_file():
        print(f"Missing script: {script_path}")
        print("Re-download Pyla-RL or run the updater again.")
        return 1

    prefer_venv = script_relative.name == "updater.py"
    python_command = resolve_python_for_launch(bundle, prefer_venv=prefer_venv)
    if not python_command:
        print("Python 3.11 64-bit was not found.")
        if script_relative.name == "setup_bootstrap.py":
            print("Install Python 3.11 from python.org, then run setup.exe again.")
        else:
            print("Run setup.exe first, or install Python 3.11 and run:")
            print(f"  py -3.11-64 app\\{script_relative}")
        return 1

    env = os.environ.copy()
    env["PYTHONPATH"] = str(bundle)
    command = python_command + [str(script_path), *sys.argv[1:]]
    print(f"Using Python: {_python_info(python_command) or python_command[0]}")
    completed = subprocess.run(command, cwd=str(install_root), env=env)
    return int(completed.returncode)


def launch_setup() -> int:
    install_root = install_root_from_frozen_exe()
    bundle = bundle_dir_from_install(install_root)
    code = delegate_to_script(bundle, install_root, SETUP_SCRIPT)
    if code != 0 and os.environ.get("PYLAAI_SETUP_NO_PAUSE", "").strip().lower() not in ("1", "true", "yes"):
        input("Press Enter to close...")
    return code


def launch_updater() -> int:
    install_root = install_root_from_frozen_exe()
    bundle = bundle_dir_from_install(install_root)
    return delegate_to_script(bundle, install_root, UPDATER_SCRIPT)
