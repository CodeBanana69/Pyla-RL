"""Windows + AMD ROCm environment tweaks (see README and requirements-rocm-windows.txt)."""

from __future__ import annotations

import os
import sys


def configure_amd_windows() -> None:
    """
    Workaround for MIOpen HIPRTC JIT failures on Windows + gfx1100 (RDNA3).

    The hiprtc compiler can't find C++ stdlib headers on Windows, causing
    repeated BatchNorm / conv kernel compile errors. FIND_MODE=5 forces
    MIOpen to use only pre-compiled kernels and skip the broken JIT path.
    """
    if sys.platform == "win32":
        os.environ.setdefault("MIOPEN_FIND_MODE", "5")
        os.environ.setdefault("MIOPEN_DEBUG_DISABLE_FIND_DB", "0")
