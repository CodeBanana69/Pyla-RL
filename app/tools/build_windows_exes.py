"""Build setup.exe and updater.exe with PyInstaller for Windows releases."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1]
INSTALL_ROOT = BUNDLE.parent
BUILD_DIR = INSTALL_ROOT / "build" / "pyinstaller"
DIST_DIR = INSTALL_ROOT / "dist" / "windows_exes"

TARGETS: tuple[tuple[str, Path], ...] = (
    ("setup.exe", BUNDLE / "tools" / "frozen_launcher_setup.py"),
    ("updater.exe", BUNDLE / "tools" / "frozen_launcher_updater.py"),
)


def _run(command: list[str], *, cwd: Path = INSTALL_ROOT) -> None:
    print("> " + " ".join(command))
    subprocess.check_call(command, cwd=str(cwd))


def build_exe(exe_name: str, script: Path) -> Path:
    stem = Path(exe_name).stem
    _run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--console",
            "--name",
            stem,
            "--distpath",
            str(DIST_DIR),
            "--workpath",
            str(BUILD_DIR / stem),
            "--specpath",
            str(BUILD_DIR),
            "--paths",
            str(BUNDLE),
            str(script),
        ]
    )
    built = DIST_DIR / exe_name
    if not built.exists():
        raise FileNotFoundError(f"PyInstaller did not produce {built}")
    return built


def install_to_project_root(built: Path, exe_name: str) -> Path:
    destination = INSTALL_ROOT / exe_name
    if destination.exists():
        backup = INSTALL_ROOT / f"{exe_name}.old"
        if backup.exists():
            backup.unlink()
        try:
            destination.replace(backup)
        except PermissionError:
            destination.unlink(missing_ok=True)
    shutil.copy2(built, destination)
    print(f"Installed {destination}")
    return destination


def smoke_test(exe_path: Path, expected_text: str) -> None:
    result = subprocess.run(
        [str(exe_path), "--smoke-test"],
        cwd=str(INSTALL_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    print(output.strip())
    if result.returncode != 0:
        raise RuntimeError(f"{exe_path.name} smoke test failed with exit code {result.returncode}")
    if expected_text not in output:
        raise RuntimeError(f"{exe_path.name} smoke test output missing {expected_text!r}")


def main() -> int:
    if sys.platform != "win32":
        print("This build script is for Windows only.")
        return 1

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    _run([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"])

    for exe_name, script in TARGETS:
        built = build_exe(exe_name, script)
        install_to_project_root(built, exe_name)

    smoke_test(INSTALL_ROOT / "setup.exe", "Smoke test passed. Python and project files are available.")
    smoke_test(INSTALL_ROOT / "updater.exe", "Pyla-RL Updater")
    smoke_test(INSTALL_ROOT / "updater.exe", "Pyla-RL project folder")

    _run([sys.executable, str(BUNDLE / "tools" / "write_build_info.py")])
    print("")
    print("Built setup.exe and updater.exe for Pyla-RL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
