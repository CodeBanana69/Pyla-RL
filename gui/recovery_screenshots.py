from __future__ import annotations

import time
from pathlib import Path

RECOVERY_DIR = Path("logs/recovery")
MAX_SCREENSHOTS = 20


def save_recovery_screenshot(screenshot, step: str) -> str:
    RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{int(time.time())}_{step}.png"
    path = RECOVERY_DIR / filename
    try:
        if screenshot is None:
            return ""
        if hasattr(screenshot, "save"):
            screenshot.save(path)
        else:
            from PIL import Image

            Image.fromarray(screenshot).save(path)
    except Exception:
        return ""
    _prune_old_screenshots()
    return str(path)


def _prune_old_screenshots() -> None:
    files = sorted(RECOVERY_DIR.glob("*.png"), key=lambda item: item.stat().st_mtime, reverse=True)
    for stale in files[MAX_SCREENSHOTS:]:
        try:
            stale.unlink(missing_ok=True)
        except OSError:
            pass
