import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gpu_runtime_install import (
    auto_install_gpu_runtime,
    install_and_verify_variant,
    install_variant,
    verify_cuda_dlls,
)
from gpu_support import (
    apply_gpu_config,
    auto_candidate_variants as gpu_auto_candidate_variants,
    detect_graphics_cards as gpu_detect_graphics_cards,
    detect_runtime_variant as gpu_detect_runtime_variant,
)


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
    "PySide6>=6.7.0",
    "numpy<2.0.0",
    "adbutils==2.12.0",
    "av==12.3.0",
]


def run(command):
    print(" ".join(command))
    subprocess.check_call(command)


def install_base_requirements():
    print("Installing/repairing PylaAi core Python packages...")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    run([sys.executable, "-m", "pip", "install", "--upgrade", *BASE_REQUIREMENTS])
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "opencv-python-headless"], check=False)
    run([sys.executable, "-m", "pip", "install", "--upgrade", "opencv-python==4.8.0.76"])
    run([
        sys.executable,
        "-m",
        "pip",
        "install",
        "https://github.com/leng-yue/py-scrcpy-client/archive/refs/tags/v0.5.0.zip",
        "--no-deps",
    ])


def detect_graphics_cards():
    cards = gpu_detect_graphics_cards()

    if cards:
        print("Detected graphics cards:")
        for vendor, name in cards:
            print(f"  - {vendor}: {name}")
    else:
        print("No dedicated GPU was detected; CPU fallback will still be tested.")
    return cards


def auto_candidate_variants(cards):
    return gpu_auto_candidate_variants(cards)


def detect_runtime_variant():
    return gpu_detect_runtime_variant()


def update_config(variant):
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from utils import load_toml_as_dict, save_dict_as_toml

    config_path = root / "cfg" / "general_config.toml"
    config = load_toml_as_dict(str(config_path))
    apply_gpu_config(config, variant, detect_graphics_cards())
    save_dict_as_toml(config, str(config_path))
    print(
        f"Updated {config_path}: cpu_or_gpu = {config.get('cpu_or_gpu')!r}, "
        f"directml_device_id = {config.get('directml_device_id', 'auto')!r}"
    )


def prepare_cuda_dll_paths():
    ok, missing = verify_cuda_dlls(verbose=True)
    if not ok:
        print()
        print(
            "WARNING: CUDA provider files are installed, but these CUDA DLLs were not found: "
            + ", ".join(missing)
        )
        print("Run this command again with Python 3.11 64-bit so PyTorch CUDA wheels install correctly:")
        print("py -3.11-64 tools\\fix_gpu_runtime.py cuda")
    else:
        print("CUDA dependency DLLs found.")
    return ok


def benchmark_variant(variant, runs=12):
    from gpu_runtime_install import smoke_test_variant

    result = smoke_test_variant(variant, python=sys.executable, runs=runs)
    print(
        f"Runtime result: variant={variant} provider={result.get('provider') or 'none'} "
        f"ips={float(result.get('ips') or 0):.2f} ok={result.get('ok')}"
    )
    return result


def install_and_benchmark_variant(variant):
    print()
    print("=" * 60)
    print(f"Testing runtime: {variant}")
    print("=" * 60)
    result = install_and_verify_variant(variant, smoke_runs=12)
    if variant == "cuda":
        prepare_cuda_dll_paths()
    try:
        update_config(variant)
    except Exception as exc:
        print(f"WARNING: Could not update cfg/general_config.toml automatically: {exc}")
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

    if args.variant == "auto":
        chosen, _pytorch_label, _accel_label, results = auto_install_gpu_runtime(
            cards=cards,
            verify=True,
            benchmark_runs=12,
        )
        try:
            update_config(chosen)
        except Exception as exc:
            print(f"WARNING: Could not update cfg/general_config.toml automatically: {exc}")
    else:
        results = [install_and_benchmark_variant(args.variant)]
        chosen = args.variant if results[-1].get("ok") else "cpu"
        if chosen != args.variant:
            install_variant("cpu")
        update_config(chosen)

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
    best = next((result for result in results if result.get("variant") == chosen), results[-1])
    print(
        f"Selected best runtime: {chosen} "
        f"({best.get('provider')}, {float(best.get('ips') or 0):.2f} detector IPS)."
    )
    print("Restart Pyla after this tool finishes.")
    return 0 if best.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
