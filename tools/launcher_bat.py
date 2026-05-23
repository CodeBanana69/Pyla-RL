"""Create the single Run Pyla-RL.bat launcher and remove legacy launchers."""

from __future__ import annotations

from pathlib import Path

RUN_BAT_NAME = "Run Pyla-RL.bat"
LEGACY_BAT_NAMES = ("Run PylaAi-XXZ.bat",)


def _bat_content(python_invocation: str) -> str:
    return (
        "@echo off\n"
        "cd /d %~dp0\n"
        "set OMP_NUM_THREADS=2\n"
        "set OPENBLAS_NUM_THREADS=2\n"
        "set MKL_NUM_THREADS=2\n"
        "set NUMEXPR_NUM_THREADS=2\n"
        f"{python_invocation} main.py\n"
        "pause\n"
    )


def python_invocation_from_command(python_command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in python_command)


def create_run_file(project_dir: Path, python_command: list[str] | None = None, python_executable: str | None = None) -> Path:
    project_dir = Path(project_dir)
    if python_command is not None:
        invocation = python_invocation_from_command(python_command)
    elif python_executable:
        invocation = f'"{python_executable}"'
    else:
        raise ValueError("python_command or python_executable is required")

    for legacy_name in LEGACY_BAT_NAMES:
        legacy_path = project_dir / legacy_name
        if legacy_path.exists():
            legacy_path.unlink()
            print(f"Removed legacy launcher {legacy_name}")

    run_bat = project_dir / RUN_BAT_NAME
    run_bat.write_text(_bat_content(invocation), encoding="ascii")
    print(f"Created {run_bat.name}")
    return run_bat
