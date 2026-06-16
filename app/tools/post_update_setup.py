"""Shared post-update and full-project dependency setup."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tools.setup_bootstrap import (
    ensure_project_venv,
    find_python,
    run,
    _venv_pip_usable,
)
from tools.python_runtime import probe_runtime_imports, verify_runtime_imports, write_setup_status


@dataclass
class PostUpdateSetupResult:
    skipped: bool
    ok: bool
    message: str


def bundle_dir(project_dir: Path) -> Path:
    return project_dir / "app"


def _probe_pyside6(python_command: list[str]) -> bool:
    try:
        result = subprocess.run(
            python_command + ["-c", "import PySide6"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode == 0
    except Exception:
        return False


def needs_full_setup(project_dir: Path) -> tuple[bool, str]:
    app_bundle = bundle_dir(project_dir)
    venv_python = app_bundle / ".venv" / "Scripts" / "python.exe"
    if not venv_python.is_file():
        return True, "project .venv is missing"
    if not _venv_pip_usable(venv_python):
        return True, "project .venv has a broken pip install"
    venv_command = [str(venv_python)]
    runtime = probe_runtime_imports(venv_command)
    if not runtime.get("ok"):
        return True, runtime.get("error") or "required runtime imports failed"
    if not _probe_pyside6(venv_command):
        return True, "PySide6 is not installed in project .venv"
    return False, ""


def run_full_project_setup(
    project_dir: Path,
    *,
    reason: str = "",
    progress_callback=None,
    interactive: bool = True,
    install_vc_redist=None,
) -> bool:
    app_bundle = bundle_dir(project_dir)
    if reason:
        print(f"Running dependency setup: {reason}")

    python_command, python_executable = find_python()
    if not python_command:
        message = (
            "Python 3.11 64-bit was not found. Run setup.exe once to install Python, "
            "then run: py -3.11-64 app\\setup.py --pyla-install"
        )
        print(message)
        return False

    print(f"Using Python: {python_executable}")
    venv_command, venv_executable = ensure_project_venv(app_bundle, python_command)
    print(f"Project venv: {venv_executable}")

    if install_vc_redist:
        install_vc_redist()

    if progress_callback:
        progress_callback("Upgrading pip and setuptools...")
    run(venv_command + ["-m", "pip", "install", "setuptools>=70,<82", "wheel"])
    run(venv_command + ["-m", "pip", "install", "--upgrade", "pip"])
    run(venv_command + ["-m", "pip", "install", "--force-reinstall", "--no-deps", "numpy<2.0.0"])
    subprocess.run(venv_command + ["-m", "pip", "uninstall", "-y", "opencv-python-headless"], check=False)
    run(venv_command + ["-m", "pip", "install", "--force-reinstall", "--no-deps", "opencv-python==4.8.0.76"])

    env = os.environ.copy()
    env["PYLAAI_SETUP_AUTO"] = "1"
    if progress_callback:
        progress_callback("Installing Pyla-RL dependencies and GPU runtime...")
    run(venv_command + ["setup.py", "--pyla-install"], cwd=app_bundle, env=env)

    if progress_callback:
        progress_callback("Verifying EasyOCR runtime...")
    try:
        run(venv_command + ["-c", "import skimage; import easyocr"], cwd=app_bundle)
    except SystemExit:
        print("")
        print("EasyOCR verification failed. Re-run setup or install missing packages with:")
        print(f'  "{venv_executable}" -m pip install scikit-image ninja pyclipper python-bidi Shapely')
        return False

    from tools.hub_first_run import ensure_hub_first_run_wizard
    from tools.launcher_bat import create_run_file

    try:
        runtime_info = verify_runtime_imports(venv_command)
    except RuntimeError as exc:
        print("")
        print(str(exc))
        print("")
        print("Setup did not finish cleanly. Try running:")
        print(f'  "{venv_executable}" -m pip install pandas>=2.0.0')
        print(f'  "{venv_executable}" -m pip install --force-reinstall --no-deps opencv-python==4.8.0.76')
        print(f'  "{venv_executable}" tools\\fix_gpu_runtime.py auto')
        print(f'  "{venv_executable}" tools\\check_runtime.py')
        if interactive:
            input("Press Enter to close...")
        return False

    versions = runtime_info.get("versions") or {}
    write_setup_status(
        app_bundle,
        python_executable=venv_executable,
        cv2_version=str(versions.get("cv2", "")),
    )
    ensure_hub_first_run_wizard(app_bundle)
    create_run_file(project_dir, python_executable=venv_executable)
    return True


def run_post_update_setup(project_dir: Path) -> PostUpdateSetupResult:
    needs_setup, reason = needs_full_setup(project_dir)
    if not needs_setup:
        return PostUpdateSetupResult(
            skipped=True,
            ok=True,
            message="Runtime OK — skipped dependency setup.",
        )

    print("")
    print("Checking project dependencies after update...")
    ok = run_full_project_setup(project_dir, reason=reason, interactive=False)
    if ok:
        return PostUpdateSetupResult(
            skipped=False,
            ok=True,
            message="Dependency setup completed.",
        )
    return PostUpdateSetupResult(
        skipped=False,
        ok=False,
        message=(
            "Update files were installed, but dependency setup failed. "
            "Run setup.exe or: py -3.11-64 app\\setup.py --pyla-install"
        ),
    )
