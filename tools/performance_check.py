import platform
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import load_toml_as_dict


def main():
    cfg = load_toml_as_dict(str(ROOT / "cfg" / "general_config.toml"))
    print("PylaAi-XXZ performance check")
    print(f"Python: {platform.python_version()} {platform.architecture()[0]} ({sys.executable})")
    print(f"ONNX Runtime: {ort.__version__}")
    print(f"Available providers: {', '.join(ort.get_available_providers())}")
    print(f"Configured cpu_or_gpu: {cfg.get('cpu_or_gpu', 'auto')}")
    print(f"Configured directml_device_id: {cfg.get('directml_device_id', 'auto')}")
    print(f"Configured onnx_cpu_threads: {cfg.get('onnx_cpu_threads', 'auto')}")
    configured_max_ips = cfg.get("max_ips", 0)
    max_ips_text = (
        "unlimited"
        if str(configured_max_ips).strip() == "0"
        else configured_max_ips
    )
    print(f"Configured max_ips: {max_ips_text}")
    print(f"Configured emulator: {cfg.get('current_emulator', 'LDPlayer')} port={cfg.get('emulator_port', 'auto')}")
    print(f"Configured scrcpy_max_fps: {cfg.get('scrcpy_max_fps', 'default')}")
    print(f"Configured scrcpy_max_width: {cfg.get('scrcpy_max_width', 'default')}")
    print(f"Configured scrcpy_bitrate: {cfg.get('scrcpy_bitrate', 'default')}")
    print("Tip: run `python tools/apply_performance_profile.py --profile balanced` to restore safe defaults.")

    print("\nVisual debug check")
    try:
        from visual_debug_window import (
            OPENCV_REPAIR_CMD,
            opencv_highgui_available,
            visual_debug_backend_name,
        )

        opencv_highgui_available()
        backend = visual_debug_backend_name()
        opencv_status = "ok" if backend == "opencv" else "headless"
        print(f"OpenCV GUI: {opencv_status}")
        print(f"Debug Screen backend: {backend}")
        if backend == "unavailable":
            print(f"WARNING: Debug Screen will not work. Fix: {OPENCV_REPAIR_CMD}")
        elif backend == "win32":
            print("WARNING: OpenCV GUI unavailable; Debug Screen will use the Win32 fallback window.")
            print(f"Recommended fix: {OPENCV_REPAIR_CMD}")
        else:
            print("Debug Screen: OK")
    except Exception as exc:
        print(f"Visual debug check failed: {exc}")

    print("\nRecovery log check")
    recovery_path = ROOT / "logs" / "recovery_events.jsonl"
    if recovery_path.exists():
        try:
            from recovery_events import read_recent_events

            recent = read_recent_events(limit=5, path=str(recovery_path))
            if recent:
                print(f"Recent recovery events ({recovery_path.name}):")
                for event in recent:
                    print(
                        f"  - {event.get('event_type')}: {event.get('detail') or event.get('notice')}"
                    )
                print(
                    "If MuMu black-screens or lags, check whether display_repair or "
                    "scrcpy_restart spiked right before the crash."
                )
            else:
                print("Recovery log exists but has no readable events yet.")
        except Exception as exc:
            print(f"Recovery log check failed: {exc}")
    else:
        print("No recovery log yet. It is created after the first bot recovery event.")

    model_path = ROOT / "models" / "mainInGameModel.onnx"
    if not model_path.exists():
        print(f"Missing model: {model_path}")
        return 1

    from detect import Detect

    detector = Detect(str(model_path), classes=["enemy", "teammate", "player"])
    print(f"Selected provider: {detector.device}")

    sample = np.zeros((1080, 1920, 3), dtype=np.uint8)
    for _ in range(3):
        detector.detect_objects(sample, conf_tresh=0.75)

    runs = 20
    started = time.perf_counter()
    for _ in range(runs):
        detector.detect_objects(sample, conf_tresh=0.75)
    elapsed = time.perf_counter() - started
    ips = runs / elapsed if elapsed > 0 else 0
    print(f"Detector-only speed: {ips:.2f} IPS")
    if ips >= 18:
        recommended_profile = "balanced"
        bottleneck = "none (vision compute is healthy)"
    elif ips >= 10:
        recommended_profile = "high_ips"
        bottleneck = "onnx (try high_ips profile: fewer fog/wall passes, debug off)"
    else:
        recommended_profile = "high_ips"
        bottleneck = "onnx (GPU provider may be slow or missing)"
    print(f"Recommended profile: {recommended_profile}")
    print(f"Likely bottleneck: {bottleneck}")
    print("Tip: if bot_ips is low but detector-only speed is fine, the emulator feed is the bottleneck (check scrcpy frame FPS below).")

    if platform.architecture()[0] != "64bit":
        print("WARNING: Python is not 64-bit. Re-run setup.exe to install Python 3.11 64-bit.")
    if detector.device == "CPUExecutionProvider":
        print("WARNING: ONNX is running on CPU.")
        print("- Stable GPU fix: py -3.11-64 tools\\fix_gpu_runtime.py directml")
        print("- CUDA is advanced only: py -3.11-64 tools\\fix_gpu_runtime.py cuda")
    if detector.device == "DmlExecutionProvider" and ips < 10:
        print("WARNING: DirectML is active but slow.")
        print("- Try directml_device_id = \"1\" on dual-GPU laptops and restart the bot.")

    print("\nFrame-source check")
    print("Start your emulator, open Brawl Stars, and keep it visible. Measuring scrcpy frames for 10 seconds...")
    try:
        from window_controller import WindowController

        controller = WindowController()
        frame_ids = []
        stale_samples = 0
        started = time.perf_counter()
        last_id = -1
        try:
            while time.perf_counter() - started < 10:
                frame = controller.screenshot()
                frame_id = controller.get_latest_frame_id()
                frame, frame_time = controller.get_latest_frame()
                if frame_id != last_id:
                    frame_ids.append(frame_id)
                    last_id = frame_id
                if frame_time and time.time() - frame_time > 2:
                    stale_samples += 1
                time.sleep(0.02)
        finally:
            controller.close()

        elapsed = time.perf_counter() - started
        frame_fps = max(0, len(frame_ids) - 1) / elapsed if elapsed > 0 else 0
        print(f"ADB device: {controller.device.serial}")
        print(f"Captured resolution: {controller.width}x{controller.height}")
        print(f"scrcpy frame FPS: {frame_fps:.2f}")
        if frame_fps < 8:
            print("Likely bottleneck: emulator feed (fix scrcpy/emulator FPS before tuning ONNX)")
        elif ips < 10:
            print("Likely bottleneck: onnx vision (apply high_ips profile and restart)")
        else:
            print("Likely bottleneck: none detected in quick check; use in-match bot_ips vs feed_fps if still slow")
        if frame_fps < 8:
            print("WARNING: Emulator/scrcpy is only delivering a few frames per second.")
            emulator = cfg.get("current_emulator", "LDPlayer")
            print(f"This causes 1-2 IPS with low Python CPU usage. Fix {emulator} settings first:")
            print("- Apply Pyla's balanced performance profile, then restart: python tools/apply_performance_profile.py --profile balanced")
            print("- Use Python 3.11 64-bit via Run Pyla-RL.bat, not 32-bit python.exe.")
            print("- Set emulator resolution to 1920x1080 landscape.")
            print("- Set emulator FPS to 60 and disable low-FPS/eco/power-saving mode.")
            print(f"- Disable Windows Efficiency mode for {emulator} and Python.")
            print("- In cfg/general_config.toml choose either current_emulator = \"LDPlayer\" or \"MuMu\" and use that emulator's ADB port.")
            print("- If the ADB device is 192.168.x.x, fix the emulator local ADB port; Wi-Fi ADB is usually too slow.")
        if stale_samples:
            print(f"WARNING: Saw {stale_samples} stale-frame samples during the frame test.")
    except Exception as exc:
        print(f"Frame-source check failed: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
