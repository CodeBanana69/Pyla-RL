"""Capture the trophy_observer crop region from the live emulator.

Run this while the end-of-match screen is visible. It saves the exact
region used by state_finder.find_game_result() as a PNG so that
screenshots used for template matching are pixel-aligned with the
detector.

Usage:
    python tools/capture_result_region.py [output_filename.png]

Defaults to images/end_results/capture.png if no filename is given.
"""
import os
import sys
import time

# Make sure the project root is on the import path so `utils`, `window_controller`
# etc. resolve the same way as when running main.py.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

import cv2

from utils import load_toml_as_dict
from window_controller import WindowController


ORIG_WIDTH, ORIG_HEIGHT = 1920, 1080


def main():
    out_name = sys.argv[1] if len(sys.argv) > 1 else "capture.png"
    if not out_name.lower().endswith(".png"):
        out_name += ".png"
    out_path = os.path.join("images", "end_results", out_name)

    region = load_toml_as_dict("cfg/lobby_config.toml")["lobby"]["trophy_observer"]
    orig_x, orig_y, orig_w, orig_h = region
    print(f"Region (1920x1080 reference): x={orig_x}, y={orig_y}, w={orig_w}, h={orig_h}")

    wc = WindowController()
    # Prime the frame pipeline — first frame can take a moment.
    frame = wc.screenshot()
    time.sleep(0.2)
    frame = wc.screenshot()

    h, w = frame.shape[:2]
    wr, hr = w / ORIG_WIDTH, h / ORIG_HEIGHT
    x, y = int(orig_x * wr), int(orig_y * hr)
    cw, ch = int(orig_w * wr), int(orig_h * hr)
    print(f"Frame: {w}x{h} -> crop at x={x}, y={y}, w={cw}, h={ch}")

    cropped = frame[y:y + ch, x:x + cw]
    # Frames come through the pipeline as RGB; cv2.imwrite expects BGR.
    cv2.imwrite(out_path, cv2.cvtColor(cropped, cv2.COLOR_RGB2BGR))
    print(f"Saved: {out_path}")

    wc.close()


if __name__ == "__main__":
    main()
