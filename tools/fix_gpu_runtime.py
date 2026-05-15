import argparse
from pathlib import Path
import subprocess
import sys


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
        description="Switch PylaAi-XXZ's ONNX runtime between DirectML, CUDA, and CPU."
    )
    parser.add_argument(
        "variant",
        choices=["directml", "cuda", "cpu"],
        help="cuda is recommended for NVIDIA 40-series when DirectML is slow; directml works on most Windows GPUs.",
    )
    args = parser.parse_args()

    install_variant(args.variant)
    try:
        update_config(args.variant)
    except Exception as exc:
        print(f"WARNING: Could not update cfg/general_config.toml automatically: {exc}")

    import onnxruntime as ort

    print()
    print(f"Installed ONNX Runtime: {ort.__version__}")
    print(f"Available providers: {', '.join(ort.get_available_providers())}")
    if args.variant == "directml" and "DmlExecutionProvider" not in ort.get_available_providers():
        print("WARNING: DirectML provider is not visible. Restart the terminal and run setup again.")
    elif args.variant == "cuda" and "CUDAExecutionProvider" not in ort.get_available_providers():
        print("WARNING: CUDA provider is not visible. Make sure you ran this with Python 3.11 64-bit:")
        print("py -3.11-64 tools\\fix_gpu_runtime.py cuda")
    else:
        print("GPU runtime switch completed.")


if __name__ == "__main__":
    main()
