"""Compatibility helpers for the subprocess-based debug view."""

import cv2

from debug_view import DEBUG_VIEW_TITLE, DebugViewPublisher
from opencv_runtime import OPENCV_REPAIR_CMD, opencv_runtime_ready, repair_opencv_runtime

VISUAL_DEBUG_WINDOW_NAME = DEBUG_VIEW_TITLE


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
