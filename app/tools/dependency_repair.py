"""Centralized pip conflict repair for Pyla-RL setup."""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Sequence

from subprocess_text import run_text

OPENCV_PIN = "opencv-python==4.8.0.76"
ADBUTILS_PIN = "adbutils==2.12.0"
AV_PIN = "av==12.3.0"
SCRCPY_CLIENT_URL = (
    "https://github.com/leng-yue/py-scrcpy-client/archive/refs/tags/v0.5.0.zip"
)

# pip check warnings we intentionally accept after --no-deps installs.
_PIP_CHECK_ALLOWLIST = (
    # Allow easyocr having a conflict involving opencv-python-headless
    re.compile(r"\beasyocr\b.*\bopencv-python-headless\b", re.I),
    # Allow scrcpy-client having a conflict involving adbutils
    re.compile(r"\bscrcpy-client\b.*\badbutils\b", re.I),
)


def _python_command(python: Sequence[str] | str | None) -> list[str]:
    if python is None:
        return [sys.executable]
    if isinstance(python, str):
        return [python]
    return list(python)


def _pip(python: Sequence[str] | str | None, *args: str, check: bool = True) -> None:
    command = _python_command(python) + ["-m", "pip", *args]
    if check:
        subprocess.check_call(command)
    else:
        subprocess.run(command, check=False)


def repair_opencv_conflicts(python: Sequence[str] | str | None = None, *, verbose: bool = False) -> None:
    if verbose:
        print("Repairing OpenCV conflicts (remove headless, pin full OpenCV)...")
    _pip(python, "uninstall", "-y", "opencv-python-headless", check=False)
    _pip(python, "install", "--force-reinstall", "--no-deps", OPENCV_PIN)


def repair_scrcpy_stack(python: Sequence[str] | str | None = None, *, verbose: bool = False) -> None:
    if verbose:
        print("Repairing scrcpy/adbutils stack...")
    _pip(python, "uninstall", "-y", "scrcpy-client", "scrcpy_client", check=False)
    _pip(python, "install", "--force-reinstall", ADBUTILS_PIN, AV_PIN)
    _pip(
        python,
        "install",
        "--force-reinstall",
        "--no-deps",
        SCRCPY_CLIENT_URL,
    )


def repair_all_conflicts(
    python: Sequence[str] | str | None = None,
    *,
    verbose: bool = False,
    repair_numpy: bool = True,
) -> None:
    if repair_numpy:
        from gpu_runtime_install import repair_numpy as _repair_numpy

        _repair_numpy(python=_python_command(python)[0], verbose=verbose, reinstall_opencv=False)
    repair_opencv_conflicts(python, verbose=verbose)
    repair_scrcpy_stack(python, verbose=verbose)


def verify_pip_health(python: Sequence[str] | str | None = None) -> tuple[bool, list[str]]:
    """Run pip check; fail only on conflicts outside our allowlist."""
    command = _python_command(python)
    completed = run_text(command + ["-m", "pip", "check"], capture_output=True, check=False)
    output = ((completed.stdout or "") + (completed.stderr or "")).strip()
    if completed.returncode == 0 and not output:
        return True, []

    issues: list[str] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("no broken requirements"):
            continue
        if any(pattern.search(line) for pattern in _PIP_CHECK_ALLOWLIST):
            continue
        issues.append(line)

    if issues:
        return False, issues
    return True, []
