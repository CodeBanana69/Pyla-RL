import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import load_toml_as_dict, save_dict_as_toml
from window_controller import WindowController


PROFILES = [
    {"name": "current", "width": None, "fps": None, "bitrate": None},
    {"name": "960w_30fps_3mb", "width": 960, "fps": 30, "bitrate": 3000000},
    {"name": "854w_30fps_2mb", "width": 854, "fps": 30, "bitrate": 2000000},
    {"name": "720w_30fps_1_5mb", "width": 720, "fps": 30, "bitrate": 1500000},
    {"name": "720w_20fps_1_5mb", "width": 720, "fps": 20, "bitrate": 1500000},
    {"name": "640w_20fps_1mb", "width": 640, "fps": 20, "bitrate": 1000000},
    {"name": "540w_15fps_800kb", "width": 540, "fps": 15, "bitrate": 800000},
]


def apply_profile(controller, profile, original):
    controller.scrcpy_max_width = original["width"] if profile["width"] is None else profile["width"]
    controller.scrcpy_max_fps = original["fps"] if profile["fps"] is None else profile["fps"]
    controller.scrcpy_bitrate = original["bitrate"] if profile["bitrate"] is None else profile["bitrate"]


def measure_profile(controller, seconds):
    if not controller.restart_scrcpy_client():
        return {"ok": False, "reason": "scrcpy restart did not deliver a fresh frame"}

    start = time.perf_counter()
    last_frame_id = controller.get_latest_frame_id()
    fresh_frames = 0
    loop_count = 0
    duplicate_waits = 0
    stale_samples = 0
    max_frame_age = 0.0

    while time.perf_counter() - start < seconds:
        try:
            controller.screenshot()
        except Exception as exc:
            return {"ok": False, "reason": f"screenshot failed: {exc}"}

        loop_count += 1
        frame_id = controller.get_latest_frame_id()
        _, frame_time = controller.get_latest_frame()
        frame_age = time.time() - frame_time if frame_time else 999.0
        max_frame_age = max(max_frame_age, frame_age)
        if frame_age > 2.0:
            stale_samples += 1

        if frame_id != last_frame_id:
            fresh_frames += 1
            last_frame_id = frame_id
        else:
            duplicate_waits += 1
            time.sleep(0.01)

    elapsed = max(0.001, time.perf_counter() - start)
    return {
        "ok": stale_samples == 0 and fresh_frames > 0,
        "feed_fps": fresh_frames / elapsed,
        "loop_ips": loop_count / elapsed,
        "duplicate_waits": duplicate_waits,
        "stale_samples": stale_samples,
        "max_frame_age": max_frame_age,
    }


def score_result(result):
    if not result.get("ok"):
        return -1
    return (
        result.get("feed_fps", 0) * 10
        + result.get("loop_ips", 0)
        - result.get("duplicate_waits", 0) * 0.02
        - result.get("max_frame_age", 0) * 3
    )


def write_profile(profile):
    config_path = ROOT / "cfg" / "general_config.toml"
    config = load_toml_as_dict(str(config_path))
    config["scrcpy_max_width"] = int(profile["width"])
    config["scrcpy_max_fps"] = int(profile["fps"])
    config["scrcpy_bitrate"] = int(profile["bitrate"])
    save_dict_as_toml(config, str(config_path))


def main():
    parser = argparse.ArgumentParser(
        description="Run while Brawl Stars is in a match. Tries scrcpy capture profiles until frame IPS is stable."
    )
    parser.add_argument("--seconds", type=float, default=8.0, help="Seconds to test each profile.")
    parser.add_argument("--min-feed-fps", type=float, default=8.0, help="First profile above this fresh-frame FPS wins.")
    parser.add_argument("--apply", action="store_true", help="Write the winning scrcpy settings to cfg/general_config.toml.")
    args = parser.parse_args()

    controller = WindowController()
    original = {
        "width": controller.scrcpy_max_width,
        "fps": controller.scrcpy_max_fps,
        "bitrate": controller.scrcpy_bitrate,
    }
    print("Live IPS tuner")
    print("Keep Brawl Stars open in an active match/loading scene while this runs.")
    print(f"Original profile: width={original['width']} fps={original['fps']} bitrate={original['bitrate']}")

    results = []
    winner = None
    try:
        for profile in PROFILES:
            apply_profile(controller, profile, original)
            print(
                f"\nTesting {profile['name']}: "
                f"width={controller.scrcpy_max_width} fps={controller.scrcpy_max_fps} bitrate={controller.scrcpy_bitrate}"
            )
            result = measure_profile(controller, args.seconds)
            result["profile"] = {
                "name": profile["name"],
                "width": controller.scrcpy_max_width,
                "fps": controller.scrcpy_max_fps,
                "bitrate": controller.scrcpy_bitrate,
            }
            results.append(result)
            if not result.get("ok"):
                print(f"  failed: {result.get('reason', 'stale/empty feed')}")
                continue

            print(
                "  "
                f"feed_fps={result['feed_fps']:.2f} "
                f"loop_ips={result['loop_ips']:.2f} "
                f"duplicates={result['duplicate_waits']} "
                f"max_age={result['max_frame_age']:.2f}s"
            )
            if result["feed_fps"] >= args.min_feed_fps:
                winner = result
                print("  stable enough; stopping early.")
                break

        if winner is None:
            valid = [result for result in results if result.get("ok")]
            winner = max(valid, key=score_result, default=None)

        print("\nSummary")
        for result in results:
            profile = result["profile"]
            if result.get("ok"):
                print(
                    f"- {profile['name']}: feed_fps={result['feed_fps']:.2f}, "
                    f"loop_ips={result['loop_ips']:.2f}, dup={result['duplicate_waits']}, "
                    f"age={result['max_frame_age']:.2f}s"
                )
            else:
                print(f"- {profile['name']}: failed ({result.get('reason', 'stale/empty feed')})")

        if winner is None:
            print("\nNo stable profile found. This points to emulator/ADB/scrcpy freezing, not bot inference.")
            return 2

        profile = winner["profile"]
        print(
            "\nRecommended profile:",
            f"scrcpy_max_width={profile['width']}",
            f"scrcpy_max_fps={profile['fps']}",
            f"scrcpy_bitrate={profile['bitrate']}",
        )
        if args.apply:
            write_profile(profile)
            print("Applied to cfg/general_config.toml. Restart the bot after this test.")
        else:
            print("Run again with --apply to save this profile.")
        return 0
    finally:
        controller.keys_up(list("wasd"))
        controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
