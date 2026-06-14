import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from detect import Detect
from utils import resolve_project_path


def _bench_detector(detector, frame, iterations, warmup=3):
    for _ in range(warmup):
        detector.detect_objects(frame, conf_tresh=0.35)
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        detector.detect_objects(frame, conf_tresh=0.35)
        samples.append((time.perf_counter() - start) * 1000.0)
    return {
        "median_ms": statistics.median(samples),
        "mean_ms": statistics.mean(samples),
        "min_ms": min(samples),
        "max_ms": max(samples),
        "ips": 1000.0 / statistics.mean(samples) if samples else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark ONNX inference latency for Pyla-RL models.")
    parser.add_argument("--model", default="models/mainInGameModel.onnx", help="Model path relative to app root.")
    parser.add_argument("--iterations", type=int, default=30, help="Timed iterations after warmup.")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    args = parser.parse_args()

    import numpy as np

    model_path = resolve_project_path(args.model)
    frame = np.zeros((args.height, args.width, 3), dtype=np.uint8)
    detector = Detect(model_path, classes=["enemy", "teammate", "player"])
    stats = _bench_detector(detector, frame, args.iterations)
    print(f"Model: {model_path}")
    print(f"Provider: {detector.device}")
    print(
        "Latency: "
        f"median={stats['median_ms']:.2f}ms "
        f"mean={stats['mean_ms']:.2f}ms "
        f"min={stats['min_ms']:.2f}ms "
        f"max={stats['max_ms']:.2f}ms"
    )
    print(f"Estimated inference IPS: {stats['ips']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
