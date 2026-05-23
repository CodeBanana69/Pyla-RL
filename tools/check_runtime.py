"""Diagnose which Python Pyla-RL will use and whether OpenCV is installed."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.launcher_bat import candidate_python_commands
from tools.python_runtime import probe_cv2, read_python_pin, setup_status_path


def main() -> int:
    print("Pyla-RL runtime check")
    print(f"Project: {ROOT}")
    print()

    pin = read_python_pin(ROOT)
    if pin:
        print(f"Pinned Python (cfg/pyla_python.txt): {pin}")
        print(f"  cv2: {probe_cv2([pin])}")
        print()

    status_path = setup_status_path(ROOT)
    if status_path.exists():
        print(f"Last setup status: {status_path}")
        print(status_path.read_text(encoding="utf-8"))
        print()

    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        print(f".venv Python: {venv_python}")
        print(f"  cv2: {probe_cv2([str(venv_python)])}")
        print()

    print("Launcher candidates:")
    for label, command in candidate_python_commands():
        print(f"  [{label}] {' '.join(command)}")
        print(f"    cv2: {probe_cv2(command)}")
    print()
    print(f"Current interpreter: {sys.executable}")
    print(f"  cv2: {probe_cv2([sys.executable])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
