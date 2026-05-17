import argparse
import json
from pathlib import Path
import subprocess
import sys


BASE_REQUIREMENTS = [
    "customtkinter>=5.2.0",
    "toml>=0.10.2",
    "Pillow>=10.0.0",
    "discord.py>=2.3.2",
    "opencv-python==4.8.0.76",
    "requests",
    "ultralytics",
    "aiohttp",
    "easyocr",
    "google-play-scraper",
    "pyautogui>=0.9.54",
    "packaging>=23.0",
    "numpy<2.0.0",
    "adbutils==2.12.0",
    "av==12.3.0",
]
ONNX_VARIANTS = [
    "onnxruntime",
    "onnxruntime-gpu",
    "onnxruntime-directml",
    "onnxruntime-openvino",
]
CUDA_TORCH_INDEX_URL = "https://download.pytorch.org/whl/cu124"
BENCHMARK_MARKER = "PYLA_RUNTIME_BENCHMARK="


def run(command):
    print(" ".join(command))
    subprocess.check_call(command)


def install_base_requirements():
    print("Installing/repairing PylaAi core Python packages...")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    run([sys.executable, "-m", "pip", "install", "--upgrade", *BASE_REQUIREMENTS])
    run([
        sys.executable,
        "-m",
        "pip",
        "install",
        "https://github.com/leng-yue/py-scrcpy-client/archive/refs/tags/v0.5.0.zip",
        "--no-deps",
    ])


def detect_graphics_cards():
    cards = []
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader,nounits"],
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        ).strip()
        if output:
            for line in output.splitlines():
                name = line.strip()
                if name:
                    cards.append(("nvidia", name))
    except Exception:
        pass

    try:
        wmic = subprocess.check_output(
            ["wmic", "path", "win32_VideoController", "get", "name"],
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        )
        for line in wmic.splitlines():
            name = line.strip()
            if not name or name.lower() == "name":
                continue
            lower = name.lower()
            if "nvidia" in lower and not any(card[1] == name for card in cards):
                cards.append(("nvidia", name))
            elif "amd" in lower or "radeon" in lower:
                cards.append(("amd", name))
            elif "intel" in lower:
                cards.append(("intel", name))
    except Exception:
        pass

    if cards:
        print("Detected graphics cards:")
        for vendor, name in cards:
            print(f"  - {vendor}: {name}")
    else:
        print("No dedicated GPU was detected; CPU fallback will still be tested.")
    return cards


def auto_candidate_variants(cards):
    vendors = {vendor for vendor, _name in cards}
    candidates = ["directml"]
    if "nvidia" in vendors:
        candidates.append("cuda")
    candidates.append("cpu")
    return candidates


def detect_runtime_variant():
    return auto_candidate_variants(detect_graphics_cards())[0]


def install_variant(variant):
    package = {
        "directml": "onnxruntime-directml",
        "cuda": "onnxruntime-gpu",
        "cpu": "onnxruntime",
    }[variant]

    subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", *ONNX_VARIANTS], check=False)
    if variant == "cuda":
        run([
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "torch",
            "torchvision",
            "--index-url",
            CUDA_TORCH_INDEX_URL,
        ])
    run([sys.executable, "-m", "pip", "install", "--upgrade", package])


def prepare_cuda_dll_paths():
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from cuda_runtime_paths import add_cuda_dll_directories, has_cuda_dependency_dlls

    added_paths = add_cuda_dll_directories(verbose=True)
    ok, missing = has_cuda_dependency_dlls()
    if not ok:
        print()
        print(
            "WARNING: CUDA provider files are installed, but these CUDA DLLs were not found: "
            + ", ".join(missing)
        )
        print("Run this command again with Python 3.11 64-bit so PyTorch CUDA wheels install correctly:")
        print("py -3.11-64 tools\\fix_gpu_runtime.py cuda")
    elif added_paths:
        print("CUDA dependency DLLs found.")
    return ok


def update_config(variant):
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from utils import load_toml_as_dict, save_dict_as_toml

    config_path = root / "cfg" / "general_config.toml"
    config = load_toml_as_dict(str(config_path))
    config["cpu_or_gpu"] = variant
    if variant == "directml":
        config.setdefault("directml_device_id", "auto")
    save_dict_as_toml(config, str(config_path))
    print(f"Updated {config_path}: cpu_or_gpu = {variant!r}")


def benchmark_variant(variant, runs=12):
    root = Path(__file__).resolve().parents[1]
    code = f"""
import json
import sys
import time
from pathlib import Path
import numpy as np

root = Path({str(root)!r})
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from detect import Detect

model_path = root / "models" / "mainInGameModel.onnx"
detector = Detect(str(model_path), classes=["enemy", "teammate", "player"])
sample = np.zeros((1080, 1920, 3), dtype=np.uint8)
for _ in range(2):
    detector.detect_objects(sample, conf_tresh=0.75)
started = time.perf_counter()
for _ in range({int(runs)}):
    detector.detect_objects(sample, conf_tresh=0.75)
elapsed = max(time.perf_counter() - started, 1e-9)
print({BENCHMARK_MARKER!r} + json.dumps({{
    "variant": {variant!r},
    "provider": detector.device,
    "ips": {int(runs)} / elapsed,
}}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.stdout.strip():
        print(completed.stdout.strip())
    if completed.stderr.strip():
        print(completed.stderr.strip())
    for line in completed.stdout.splitlines():
        if line.startswith(BENCHMARK_MARKER):
            result = json.loads(line[len(BENCHMARK_MARKER):])
            result["ok"] = completed.returncode == 0
            return result
    return {
        "variant": variant,
        "provider": "",
        "ips": 0.0,
        "ok": False,
        "error": (completed.stderr or completed.stdout or "benchmark did not return a result").strip(),
    }


def install_and_benchmark_variant(variant):
    print()
    print("=" * 60)
    print(f"Testing runtime: {variant}")
    print("=" * 60)
    install_variant(variant)
    try:
        update_config(variant)
    except Exception as exc:
        print(f"WARNING: Could not update cfg/general_config.toml automatically: {exc}")
    if variant == "cuda":
        prepare_cuda_dll_paths()
    result = benchmark_variant(variant)
    print(
        f"Runtime result: variant={variant} provider={result.get('provider') or 'none'} "
        f"ips={float(result.get('ips') or 0):.2f} ok={result.get('ok')}"
    )
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Repair PylaAi-XXZ dependencies, test available ONNX runtimes, and keep the fastest working one."
    )
    parser.add_argument(
        "variant",
        nargs="?",
        default="auto",
        choices=["auto", "directml", "cuda", "cpu"],
        help=(
            "Optional. auto detects the graphics card, tries stable GPU runtimes first, benchmarks them, "
            "and keeps the fastest working runtime. Use cuda/directml/cpu to force one runtime."
        ),
    )
    args = parser.parse_args()

    install_base_requirements()
    cards = detect_graphics_cards()
    variants = auto_candidate_variants(cards) if args.variant == "auto" else [args.variant]
    print(f"Runtime test order: {', '.join(variants)}")

    results = []
    for variant in variants:
        try:
            results.append(install_and_benchmark_variant(variant))
        except Exception as exc:
            print(f"Runtime {variant} failed during install/test: {exc}")
            results.append({"variant": variant, "provider": "", "ips": 0.0, "ok": False, "error": str(exc)})

    working = [result for result in results if result.get("ok") and float(result.get("ips") or 0) > 0]
    if not working:
        print("No ONNX runtime worked. Leaving the last attempted runtime installed.")
        return 1

    best = max(working, key=lambda result: float(result.get("ips") or 0))
    best_variant = best["variant"]
    if results[-1].get("variant") != best_variant:
        print()
        print(f"Reinstalling best runtime: {best_variant}")
        install_variant(best_variant)
    update_config(best_variant)

    import onnxruntime as ort

    print()
    print(f"Installed ONNX Runtime: {ort.__version__}")
    print(f"Available providers: {', '.join(ort.get_available_providers())}")
    print("Benchmark summary:")
    for result in results:
        print(
            f"  - {result.get('variant')}: provider={result.get('provider') or 'none'} "
            f"ips={float(result.get('ips') or 0):.2f} ok={result.get('ok')}"
        )
    print(
        f"Selected best runtime: {best_variant} "
        f"({best.get('provider')}, {float(best.get('ips') or 0):.2f} detector IPS)."
    )
    print("Restart Pyla after this tool finishes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
