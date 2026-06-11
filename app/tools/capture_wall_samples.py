import argparse
import json
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from play import Play
from state_finder import get_state
from window_controller import WindowController


def save_sample(output, frame, metadata):
    output.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{int((time.time() % 1) * 1000):03d}"
    image_path = output / f"{stamp}.png"
    meta_path = output / f"{stamp}.json"
    cv2.imwrite(str(image_path), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Captured wall sample: {image_path}")


def main():
    parser = argparse.ArgumentParser(description="Capture wall-model frames for labeling/training.")
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--output", default="debug_frames/wall_vision")
    parser.add_argument("--start-match", action="store_true")
    args = parser.parse_args()

    controller = WindowController()
    play = Play("models/mainInGameModel.onnx", "models/tileDetector.onnx", controller)
    output = ROOT / args.output
    start = time.time()
    last_capture = 0.0
    last_state = None
    last_frame_id = -1
    last_continue_press = 0.0
    continue_interval = 0.35

    try:
        while time.time() - start < args.seconds:
            frame = controller.screenshot()
            frame_id = controller.get_latest_frame_id()
            if frame_id == last_frame_id:
                time.sleep(0.01)
                continue
            last_frame_id = frame_id

            state = get_state(frame)
            if state != last_state:
                print(f"State: {state}")
                last_state = state

            if args.start_match and state == "lobby":
                controller.press_key("Q")
                time.sleep(1)
                continue

            if args.start_match and state != "match":
                now = time.time()
                if now - last_continue_press > continue_interval:
                    controller.press_key("Q")
                    last_continue_press = now
                continue

            if state != "match":
                continue

            now = time.time()
            if now - last_capture < args.interval:
                continue
            last_capture = now

            tile_data = play.get_tile_data(frame)
            save_sample(
                output,
                frame,
                {
                    "state": state,
                    "raw_tile_detection": tile_data,
                    "classes": ["wall", "bush", "close_bush"],
                    "note": "Use raw_tile_detection only as a guide. Correct labels manually before training.",
                },
            )
    finally:
        controller.keys_up(list("wasd"))
        controller.close()


if __name__ == "__main__":
    main()
