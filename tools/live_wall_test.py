import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from play import Play
from state_finder import get_state
from window_controller import WindowController


class MainShim:
    def __init__(self):
        self.state = None


def looks_like_disconnect_dialog(frame):
    h, w = frame.shape[:2]
    dialog_crop = frame[int(h * 0.32):int(h * 0.62), int(w * 0.24):int(w * 0.76)]
    if dialog_crop.size == 0:
        return False
    dialog_mean = float(dialog_crop.mean())
    dialog_std = float(dialog_crop.std())
    dialog_hsv = cv2.cvtColor(dialog_crop, cv2.COLOR_RGB2HSV)
    dialog_saturation = float(dialog_hsv[:, :, 1].mean())
    return dialog_mean <= 90 and dialog_std <= 75 and dialog_saturation <= 85


def load_brawler():
    data_path = ROOT / "latest_brawler_data.json"
    if not data_path.exists():
        return "shelly"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    if not data:
        return "shelly"
    return data[0].get("brawler") or "shelly"


def main():
    parser = argparse.ArgumentParser(description="Run a short live wall-detection test.")
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--rounds", type=int, default=0, help="Stop after this many completed rounds. 0 disables round counting.")
    parser.add_argument("--visual-debug", action="store_true", help="Show the live PylaAi-XXZ Visual Debug overlay window.")
    parser.add_argument("--brawler", default=None)
    args = parser.parse_args()

    brawler = args.brawler or load_brawler()
    controller = WindowController()
    play = Play("models/mainInGameModel.onnx", "models/tileDetector.onnx", controller)
    play.current_brawler = brawler
    shim = MainShim()

    print(f"Live wall test using brawler: {brawler}")
    start = time.time()
    ips_start = time.time()
    frames = 0
    last_frame_id = -1
    last_state = None
    wall_counts = []
    raw_wall_counts = []
    object_counts = Counter()
    last_continue_press = 0.0
    last_reload_press = 0.0
    continue_interval = 0.35
    completed_rounds = 0
    active_end_state = None

    try:
        while time.time() - start < args.seconds:
            frame = controller.screenshot()
            frame_id = controller.get_latest_frame_id()
            if frame_id == last_frame_id:
                time.sleep(0.01)
                continue
            last_frame_id = frame_id

            current_state = get_state(frame)
            if current_state != last_state:
                print(f"State: {current_state}")
                last_state = current_state

            if looks_like_disconnect_dialog(frame) and time.time() - last_reload_press > 4.0:
                print("Disconnect dialog detected in live wall test; pressing Reload.")
                controller.keys_up(list("wasd"))
                controller.click(650, 610, delay=0.08, already_include_ratio=False)
                last_reload_press = time.time()
                time.sleep(2.0)
                continue

            if current_state.startswith("end_"):
                if current_state != active_end_state:
                    completed_rounds += 1
                    active_end_state = current_state
                    print(f"Completed round {completed_rounds}/{args.rounds or '?'}: {current_state}")
                    if args.rounds and completed_rounds >= args.rounds:
                        break
            elif current_state == "match":
                active_end_state = None

            if current_state == "lobby":
                print("state is lobby, starting game")
                controller.press_key("Q")
                time.sleep(1)
                continue
            if current_state != "match":
                now = time.time()
                if now - last_continue_press > continue_interval:
                    controller.press_key("Q")
                    last_continue_press = now
                continue

            if current_state == "match":
                raw_tile_data = play.get_tile_data(frame)
                raw_walls = [box for name, boxes in raw_tile_data.items() if name != "bush" for box in boxes]
                walls, map_objects = play.process_tile_data(raw_tile_data, frame)
                raw_wall_counts.append(len(raw_walls))
                wall_counts.append(len(walls))
                object_counts.update({name: len(boxes) for name, boxes in map_objects.items() if boxes})

                data = play.get_main_data(frame)
                data["wall"] = walls
                data["line_of_sight_wall"] = play.map_object_boxes_for_classes(
                    map_objects,
                    play.line_of_sight_map_object_classes(),
                )
                data["map_objects"] = map_objects
                data["jump_pad"] = map_objects.get("jump_pad", [])
                data = play.validate_game_data(data)
                if data:
                    play.time_since_player_last_found = time.time()
                    play.current_frame = frame
                    play.loop(brawler, data, time.time())
                    if args.visual_debug:
                        play.show_visual_debug(frame, data, brawler)
                elif time.time() - play.time_since_player_last_found > 1.0:
                    controller.keys_up(list("wasd"))

            frames += 1
            if time.time() - ips_start >= 5:
                elapsed = time.time() - ips_start
                ips = frames / elapsed if elapsed > 0 else 0
                raw_avg = sum(raw_wall_counts) / len(raw_wall_counts) if raw_wall_counts else 0
                merged_avg = sum(wall_counts) / len(wall_counts) if wall_counts else 0
                object_samples = max(1, len(wall_counts))
                objects = ", ".join(
                    f"{name}={count / object_samples:.1f}"
                    for name, count in object_counts.most_common(8)
                ) or "none"
                print(
                    f"{ips:.2f} IPS | walls raw avg={raw_avg:.1f} "
                    f"merged avg={merged_avg:.1f} | objects: {objects}"
                )
                frames = 0
                ips_start = time.time()
                wall_counts.clear()
                raw_wall_counts.clear()
                object_counts.clear()
    finally:
        controller.keys_up(list("wasd"))
        controller.close()


if __name__ == "__main__":
    main()
