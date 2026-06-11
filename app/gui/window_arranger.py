from __future__ import annotations

import ctypes
import math
import os
import time
from dataclasses import dataclass
from typing import Iterable

SW_RESTORE = 9
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    rect: tuple[int, int, int, int]


def is_emulator_window_title(title: str) -> bool:
    title = str(title or "").lower()
    if not title:
        return False
    return any(token in title for token in (
        "ldplayer",
        "dnplayer",
        "mumu",
        "android device",
        "brawl stars",
    ))


def _usable_area() -> tuple[int, int, int, int]:
    if os.name != "nt":
        return 0, 0, 1600, 900
    user32 = ctypes.windll.user32
    return (
        0,
        0,
        int(user32.GetSystemMetrics(0)),
        int(user32.GetSystemMetrics(1)),
    )


def compute_grid_rects(count: int, area: tuple[int, int, int, int] | None = None) -> list[tuple[int, int, int, int]]:
    count = max(0, int(count or 0))
    if count == 0:
        return []
    left, top, right, bottom = area or _usable_area()
    width = max(640, right - left)
    height = max(360, bottom - top)
    cols = max(1, math.ceil(math.sqrt(count)))
    rows = max(1, math.ceil(count / cols))
    gap = 8
    cell_w = max(360, (width - gap * (cols + 1)) // cols)
    cell_h = max(240, (height - gap * (rows + 1)) // rows)
    rects = []
    for index in range(count):
        row = index // cols
        col = index % cols
        x = left + gap + col * (cell_w + gap)
        y = top + gap + row * (cell_h + gap)
        rects.append((x, y, cell_w, cell_h))
    return rects


def _window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    rect = ctypes.wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def _valid_rect(rect: tuple[int, int, int, int] | None) -> bool:
    if not rect:
        return False
    left, top, right, bottom = rect
    return right - left >= 300 and bottom - top >= 220


def enumerate_emulator_windows() -> list[WindowInfo]:
    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32
    windows: list[WindowInfo] = []

    def enum_handler(hwnd, _):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value
            if not is_emulator_window_title(title):
                return True
            rect = _window_rect(hwnd)
            if _valid_rect(rect):
                windows.append(WindowInfo(int(hwnd), title, rect))
        except Exception:
            pass
        return True

    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(enum_handler)
    user32.EnumWindows(enum_proc, 0)
    return _dedupe_windows(windows)


def _dedupe_windows(windows: Iterable[WindowInfo]) -> list[WindowInfo]:
    seen = set()
    unique = []
    for window in windows:
        key = (window.hwnd, window.title)
        if key in seen:
            continue
        seen.add(key)
        unique.append(window)
    unique.sort(key=lambda item: (item.title.lower(), item.hwnd))
    return unique


def arrange_emulator_windows(max_windows: int | None = None, wait_seconds: float = 0.0) -> int:
    if os.name != "nt":
        return 0
    deadline = time.time() + max(0.0, wait_seconds)
    windows = enumerate_emulator_windows()
    while not windows and time.time() < deadline:
        time.sleep(0.5)
        windows = enumerate_emulator_windows()
    if max_windows:
        windows = windows[:max(1, int(max_windows))]
    rects = compute_grid_rects(len(windows))
    user32 = ctypes.windll.user32
    for window, (x, y, width, height) in zip(windows, rects):
        try:
            if user32.IsIconic(window.hwnd):
                user32.ShowWindow(window.hwnd, SW_RESTORE)
            user32.SetWindowPos(window.hwnd, 0, x, y, width, height, SWP_NOZORDER | SWP_NOACTIVATE)
        except Exception:
            continue
    return len(windows)
