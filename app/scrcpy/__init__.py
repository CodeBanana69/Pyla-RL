"""
Python Scrcpy Client's core module
"""

from .const import *
from .core import Client

# This vendored Pyla scrcpy build emits rgb24 frames directly.
# Keep this marker so callers do not spend time converting BGR -> RGB again.
PYLA_RGB_FRAMES = True
