"""Ensure app/ is on sys.path when tests are imported as app.tests.*."""

from __future__ import annotations

import sys
from pathlib import Path

from . import cv2_bootstrap  # noqa: F401  — stub broken/missing OpenCV before app imports

_APP_ROOT = Path(__file__).resolve().parents[1]
if _APP_ROOT.is_dir() and str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))
