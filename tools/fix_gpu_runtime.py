import argparse
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


def detect_runtime_variant():
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader,nounits"],
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        ).strip()
        if output:
            print(f"NVIDIA GPU detected: {output}. Selecting CUDA runtime.")
            return "cuda"
    except Exception:
        pass
    print("No NVIDIA GPU detected. Selecting DirectML runtime.")
    return "directml"


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


def main():
    parser = argparse.ArgumentParser(
        description="Repair PylaAi-XXZ dependencies and switch ONNX runtime between DirectML, CUDA, and CPU."
    )
    parser.add_argument(
        "variant",
        nargs="?",
        default="auto",
        choices=["auto", "directml", "cuda", "cpu"],
        help=(
            "Optional. auto detects NVIDIA and chooses cuda, otherwise directml. "
            "Use cuda/directml/cpu to force a runtime."
        ),
    )
    args = parser.parse_args()
    variant = detect_runtime_variant() if args.variant == "auto" else args.variant

    install_base_requirements()
    install_variant(variant)
    try:
        update_config(variant)
    except Exception as exc:
        print(f"WARNING: Could not update cfg/general_config.toml automatically: {exc}")

    if variant == "cuda":
        prepare_cuda_dll_paths()

    import onnxruntime as ort

    print()
    print(f"Installed ONNX Runtime: {ort.__version__}")
    print(f"Available providers: {', '.join(ort.get_available_providers())}")
    if variant == "directml" and "DmlExecutionProvider" not in ort.get_available_providers():
        print("WARNING: DirectML provider is not visible. Restart the terminal and run setup again.")
    elif variant == "cuda" and "CUDAExecutionProvider" not in ort.get_available_providers():
        print("WARNING: CUDA provider is not visible. Make sure you ran this with Python 3.11 64-bit:")
        print("py -3.11-64 tools\\fix_gpu_runtime.py cuda")
    else:
        print("Dependency repair and GPU runtime switch completed.")


if __name__ == "__main__":
    main()
