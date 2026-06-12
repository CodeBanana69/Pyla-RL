"""Compatibility helpers for the subprocess-based debug view."""

import cv2

from debug_view import DEBUG_VIEW_TITLE, DebugViewPublisher

VISUAL_DEBUG_WINDOW_NAME = DEBUG_VIEW_TITLE
OPENCV_REPAIR_CMD = (
    "pip uninstall -y opencv-python-headless && pip install --no-deps opencv-python==4.8.0.76"
)


def reset_opencv_highgui_cache():
    return None


def opencv_highgui_available():
    try:
        cv2.namedWindow("__pyla_gui_check__", cv2.WINDOW_NORMAL)
        cv2.destroyWindow("__pyla_gui_check__")
        return True
    except cv2.error:
        return False


def visual_debug_backend_name():
    return "subprocess"


def log_visual_debug_startup():
    enabled = DebugViewPublisher.from_config().enabled
    opencv_status = "ok" if opencv_highgui_available() else "headless"
    print(
        f"[VisualDebug] enabled={enabled}; backend=subprocess; "
        f"OpenCV GUI (worker): {opencv_status}"
    )
    if enabled and not opencv_highgui_available():
        print(
            "Visual debug worker needs OpenCV GUI support. "
            f"Fix: {OPENCV_REPAIR_CMD}"
        )


def show_visual_debug_frame(_img):
    """Deprecated: rendering happens in the debug_view worker process."""
    return None
