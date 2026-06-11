"""Windows DPI awareness bootstrap — must run before any GUI toolkit imports."""

from __future__ import annotations

import ctypes
import sys

_BOOTSTRAPPED = False

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
PROCESS_PER_MONITOR_DPI_AWARE = 2


def bootstrap_windows_dpi() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED or sys.platform != "win32":
        return
    _BOOTSTRAPPED = True

    user32 = ctypes.windll.user32
    try:
        if user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        ):
            return
    except (AttributeError, OSError, TypeError):
        pass

    try:
        shcore = ctypes.windll.shcore
        if shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE) == 0:
            return
    except (AttributeError, OSError, TypeError):
        pass

    try:
        user32.SetProcessDPIAware()
    except (AttributeError, OSError, TypeError):
        pass
