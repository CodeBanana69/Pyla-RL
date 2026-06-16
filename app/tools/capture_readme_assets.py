"""Capture README screenshot assets from live Pyla-RL windows (Windows only)."""

from __future__ import annotations

import argparse
import ctypes
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "docs" / "assets"
MAX_WIDTH = 1280
HUB_STARTUP_SECONDS = 4.0

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _require_windows() -> None:
    if sys.platform != "win32":
        raise SystemExit("This script only runs on Windows.")


def find_windows(title_substring: str) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value
        if title_substring.lower() in title.lower():
            matches.append((int(hwnd), title))
        return True

    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(callback)
    user32.EnumWindows(enum_proc, 0)
    matches.sort(key=lambda item: len(item[1]))
    return matches


def capture_hwnd(hwnd: int):
    from PIL import Image

    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise OSError("GetWindowRect failed")
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise OSError("Window has zero size")

    hwnd_dc = user32.GetWindowDC(hwnd)
    if not hwnd_dc:
        raise OSError("GetWindowDC failed")
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)
    # PW_RENDERFULLCONTENT helps with layered / custom chrome windows.
    if not user32.PrintWindow(hwnd, mem_dc, 2):
        user32.PrintWindow(hwnd, mem_dc, 0)

    bmi = ctypes.create_string_buffer(40)
    ctypes.c_int32.from_buffer(bmi, 0).value = 40
    ctypes.c_int32.from_buffer(bmi, 4).value = width
    ctypes.c_int32.from_buffer(bmi, 8).value = -height
    ctypes.c_uint16.from_buffer(bmi, 12).value = 1
    ctypes.c_uint16.from_buffer(bmi, 14).value = 32
    buffer_size = width * height * 4
    pixel_buffer = ctypes.create_string_buffer(buffer_size)
    if gdi32.GetDIBits(mem_dc, bitmap, 0, height, pixel_buffer, bmi, 0) == 0:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)
        raise OSError("GetDIBits failed")

    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)

    image = Image.frombuffer("RGBA", (width, height), pixel_buffer, "raw", "BGRA", 0, 1)
    return image.convert("RGB")


def save_asset(image, filename: str) -> Path:
    from PIL import Image

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    path = ASSETS_DIR / filename
    if image.width > MAX_WIDTH:
        ratio = MAX_WIDTH / image.width
        size = (MAX_WIDTH, max(1, int(image.height * ratio)))
        image = image.resize(size, Image.Resampling.LANCZOS)
    image.save(path, format="PNG", optimize=True)
    return path


def capture_window_title(title_substring: str, output_name: str, wait_seconds: float = 15.0) -> Path:
    deadline = time.time() + wait_seconds
    hwnd = None
    while time.time() < deadline:
        windows = find_windows(title_substring)
        if windows:
            hwnd = windows[0][0]
            break
        time.sleep(0.25)
    if hwnd is None:
        raise RuntimeError(f"No visible window matching '{title_substring}' within {wait_seconds:.0f}s")

    time.sleep(0.6)
    image = capture_hwnd(hwnd)
    path = save_asset(image, output_name)
    print(f"Saved {path} ({image.width}x{image.height}) from hwnd={hwnd}")
    return path


def launch_hub(initial_tab: str | None = None) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "gui.qml_hub"]
    if initial_tab:
        cmd.extend(["--initial-tab", initial_tab])
    return subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def launch_control_window() -> subprocess.Popen:
    state_dir = ROOT / "logs"
    state_dir.mkdir(exist_ok=True)
    state_path = state_dir / "readme_capture_control.state"
    metrics_path = state_dir / "readme_capture_metrics.json"
    metrics_path.write_text(
        '{"ips": 24.5, "feed_fps": 58.0, "history": [20,22,24,25,26,24], '
        '"session": {"uptime_s": 3600, "state": "lobby", "brawler": "nita", '
        '"target": "1000", "trophies": 842, "session_wins": 3, "session_losses": 1, "notice": "Running"}}',
        encoding="utf-8",
    )
    return subprocess.Popen(
        [sys.executable, str(ROOT / "runtime_control.py"), "--window", str(state_path), str(metrics_path)],
        cwd=str(ROOT),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )


def capture_hub_asset(output_name: str, initial_tab: str | None, wait_seconds: float, launch: bool) -> Path:
    hub_process = None
    try:
        if launch:
            label = initial_tab or "Overview"
            print(f"Launching Pyla-RL Hub ({label})...")
            hub_process = launch_hub(initial_tab)
            time.sleep(HUB_STARTUP_SECONDS)
        return capture_window_title("Pyla-RL Hub", output_name, wait_seconds=wait_seconds)
    finally:
        stop_process(hub_process)


def capture_control_asset(wait_seconds: float, launch: bool) -> Path:
    control = None
    try:
        if launch:
            print("Launching Pyla-RL Control window...")
            control = launch_control_window()
            time.sleep(2.5)
        return capture_window_title("Pyla-RL Control", "control-window.png", wait_seconds=wait_seconds)
    finally:
        stop_process(control)


def main() -> None:
    _require_windows()
    parser = argparse.ArgumentParser(description="Capture README assets from Pyla-RL windows.")
    parser.add_argument(
        "--target",
        choices=["all", "hub-overview", "hub-farm-plan", "control-window"],
        default="all",
        help="Which asset(s) to capture.",
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Capture from already-open windows instead of launching new ones.",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=20.0,
        help="Seconds to wait for each target window.",
    )
    args = parser.parse_args()
    launch = not args.no_launch
    targets = (
        ["hub-overview", "hub-farm-plan", "control-window"]
        if args.target == "all"
        else [args.target]
    )

    saved: list[Path] = []
    try:
        for target in targets:
            if target == "hub-overview":
                saved.append(capture_hub_asset("hub-overview.png", None, args.wait, launch))
            elif target == "hub-farm-plan":
                saved.append(capture_hub_asset("hub-farm-plan.png", "Farm Plan", args.wait, launch))
            elif target == "control-window":
                saved.append(capture_control_asset(args.wait, launch))
    except Exception as exc:
        raise SystemExit(str(exc)) from exc

    print("Captured:")
    for path in saved:
        print(f"  - {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
