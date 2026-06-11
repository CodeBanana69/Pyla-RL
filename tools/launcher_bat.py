"""Create the single pyla-rl.bat launcher and remove legacy launchers."""

from __future__ import annotations

from pathlib import Path

RUN_BAT_NAME = "pyla-rl.bat"
_RUNTIME_IMPORT_CHECK = "import cv2, pandas"
LEGACY_BAT_NAMES = (
    "Run Pyla-RL.bat",
    "Run PylaAi-XXZ.bat",
    "start.bat",
    "pyla-xxz.bat",
    "Pyla-XXZ.bat",
    "PylaAi-XXZ.bat",
)

_BAT_CONTENT = """\
@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "BUNDLE=%~dp0app"
set "PYTHONPATH=%BUNDLE%"

set "OMP_NUM_THREADS=2"
set "OPENBLAS_NUM_THREADS=2"
set "MKL_NUM_THREADS=2"
set "NUMEXPR_NUM_THREADS=2"

title Pyla-RL

echo.
echo Pyla-RL launcher
echo Official free download: https://github.com/CodeBanana69/Pyla-RL
echo.

if exist "cfg\\pyla_python.txt" (
    set /p PYLA_PY=<cfg\\pyla_python.txt
    "%PYLA_PY%" -c "{_RUNTIME_IMPORT_CHECK}" >nul 2>&1
    if not errorlevel 1 (
        set "PY=%PYLA_PY%"
        goto :run
    )
    echo Pinned Python from setup is missing required packages; trying other interpreters...
    echo.
)

if exist ".venv\\Scripts\\python.exe" (
    ".venv\\Scripts\\python.exe" -c "{_RUNTIME_IMPORT_CHECK}" >nul 2>&1
    if not errorlevel 1 (
        set "PY=.venv\\Scripts\\python.exe"
        goto :run
    )
    echo Found .venv but required packages are missing there; trying other interpreters...
    echo.
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3.11-64 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PY=py -3.11-64"
        goto :precheck
    )
    py -3.11 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PY=py -3.11"
        goto :precheck
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.maxsize > 2**32 else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PY=python"
        goto :precheck
    )
)

echo Could not find a 64-bit Python 3.11 install.
echo Run setup.exe in this folder first, then try again.
echo.
pause
exit /b 1

:precheck
%PY% -c "{_RUNTIME_IMPORT_CHECK}" >nul 2>&1
if not errorlevel 1 goto :run

:run
echo Using: %PY%
echo.

%PY% -c "{_RUNTIME_IMPORT_CHECK}" >nul 2>&1
if errorlevel 1 (
    echo Dependencies are not installed for this Python.
    echo.
    if exist "setup.exe" (
        echo Run setup.exe in this folder again, then launch pyla-rl.bat.
    ) else (
        echo Run: %PY% app\\setup.py --pyla-install
    )
    echo.
    echo Diagnostic: %PY% tools\\check_runtime.py
    echo.
    pause
    exit /b 1
)

echo Make sure your emulator is running and Brawl Stars is open.
echo.

%PY% "%BUNDLE%\\main.py"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Pyla-RL exited with code %EXIT_CODE%.
    echo.
    pause
)

exit /b %EXIT_CODE%
"""


def candidate_python_commands() -> list[tuple[str, list[str]]]:
    """Return launcher Python candidates in priority order."""
    candidates: list[tuple[str, list[str]]] = []
    project_dir = Path(__file__).resolve().parents[1]
    pin = project_dir / "cfg" / "pyla_python.txt"
    if pin.exists():
        value = pin.read_text(encoding="utf-8").strip()
        if value:
            candidates.append(("pinned", [value]))

    venv_python = project_dir / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        candidates.append(("venv", [str(venv_python)]))

    for label, command in (
        ("py-3.11-64", ["py", "-3.11-64"]),
        ("py-3.11", ["py", "-3.11"]),
        ("python", ["python"]),
    ):
        candidates.append((label, command))
    return candidates


def remove_legacy_launchers(project_dir: Path) -> list[str]:
    project_dir = Path(project_dir)
    removed: list[str] = []
    for legacy_name in LEGACY_BAT_NAMES:
        legacy_path = project_dir / legacy_name
        if legacy_path.exists():
            legacy_path.unlink()
            removed.append(legacy_name)
            print(f"Removed legacy launcher {legacy_name}")
    return removed


def create_run_file(
    project_dir: Path,
    python_command: list[str] | None = None,
    python_executable: str | None = None,
) -> Path:
    del python_command
    if python_executable:
        from tools.python_runtime import write_python_pin

        write_python_pin(project_dir, python_executable)
    project_dir = Path(project_dir)

    remove_legacy_launchers(project_dir)

    run_bat = project_dir / RUN_BAT_NAME
    run_bat.write_text(_BAT_CONTENT.format(_RUNTIME_IMPORT_CHECK=_RUNTIME_IMPORT_CHECK), encoding="ascii")
    print(f"Created {run_bat.name}")
    return run_bat
