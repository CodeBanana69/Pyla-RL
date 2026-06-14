"""OpenCV install checks and repair (headless wheel conflicts)."""

from __future__ import annotations

import importlib
import subprocess
import sys

OPENCV_PACKAGE = "opencv-python==4.8.0.76"
OPENCV_REPAIR_CMD = (
    "pip uninstall -y opencv-python-headless && pip install --no-deps opencv-python==4.8.0.76"
)


def opencv_runtime_ready(cv2_module=None) -> bool:
    module = cv2_module or sys.modules.get("cv2")
    if module is None:
        return False
    return (
        callable(getattr(module, "imdecode", None))
        and hasattr(module, "IMREAD_COLOR")
        and hasattr(module, "__version__")
    )


def repair_opencv_runtime(python=None) -> None:
    """Reinstall full OpenCV after headless/conflicting wheels break cv2."""
    python = python or sys.executable
    subprocess.run(
        [python, "-m", "pip", "uninstall", "-y", "opencv-python-headless"],
        check=False,
    )
    subprocess.check_call(
        [python, "-m", "pip", "install", "--force-reinstall", "--no-deps", OPENCV_PACKAGE],
    )


def ensure_opencv_runtime():
    """Import cv2 or repair/reload it before pyautogui/pyscreeze load."""
    try:
        import cv2
    except ModuleNotFoundError as exc:
        print(
            "OpenCV is not installed. Run setup or repair with:\n"
            f"  {OPENCV_REPAIR_CMD}"
        )
        raise SystemExit(1) from exc

    if opencv_runtime_ready(cv2):
        return cv2

    print("OpenCV install looks broken; repairing...")
    repair_opencv_runtime()
    importlib.reload(cv2)
    if not opencv_runtime_ready(cv2):
        print(
            "OpenCV is still broken after repair. Run manually:\n"
            f"  {OPENCV_REPAIR_CMD}"
        )
        raise SystemExit(1)
    return cv2
