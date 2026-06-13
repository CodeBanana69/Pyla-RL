import sys
import platform
import subprocess
import os
from pathlib import Path

if platform.system() != "Windows" or "microsoft" in platform.uname()[3].lower():
    print("\n" + "!"*50)
    print("  ERROR: This version of Pyla-RL is for WINDOWS ONLY.")
    print("  Mac or Linux detected. Please use the Universal branch.")
    print("!"*50 + "\n")
    sys.exit(1)

# Fixes missing setuptools
def bootstrap():
    if os.environ.get("PYLAAI_BOOTSTRAP") == "1": return
    try:
        import setuptools
    except ImportError:
        print("\nDetected missing core tools. Stabilizing environment...")
        os.environ["PYLAAI_BOOTSTRAP"] = "1"
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
        subprocess.run([sys.executable] + sys.argv)
        sys.exit(0) 

if any(cmd in sys.argv for cmd in ["install", "develop"]):
    bootstrap()

from setuptools import setup, find_packages

from gpu_support import (
    apply_gpu_config,
    detect_graphics_cards,
    get_gpu_data as detect_gpu_data,
)
from gpu_runtime_install import (
    auto_install_gpu_runtime,
    install_variant as install_gpu_runtime_variant,
    repair_cuda_torch,
    variant_status_labels,
    verify_cuda_dlls,
)

def force_install(reqs, no_deps=False):
    cmd = [sys.executable, "-m", "pip", "install"]
    if no_deps: cmd += ["--force-reinstall", "--no-deps"]
    subprocess.check_call(cmd + reqs)

def save_gpu_runtime_config(variant, cards):
    import toml

    from utils import resolve_project_path

    config_path = Path(resolve_project_path("cfg/general_config.toml"))
    config = toml.load(config_path) if config_path.exists() else {}
    apply_gpu_config(config, variant, cards)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(toml.dumps(config), encoding="utf-8")
    print(
        f"Saved GPU runtime config: cpu_or_gpu={config.get('cpu_or_gpu')}, "
        f"directml_device_id={config.get('directml_device_id', 'auto')}"
    )

def get_gpu_data():
    return detect_gpu_data()

def ask_user(prompt_text):
    if os.environ.get("PYLAAI_SETUP_AUTO", "").strip().lower() in ("1", "true", "yes"):
        print(f"\n{prompt_text} (Y/N): Y [auto]")
        return True
    print(f"\n{prompt_text} (Y/N): ", end='', flush=True)
    response = sys.stdin.readline().strip().lower()
    return response in ['y', 'yes']

def setup_pyla():
    print("\n" + "="*50 + "\n   Pyla-RL - Windows Setup   \n" + "="*50)
    cards = detect_graphics_cards()
    auto_setup = os.environ.get("PYLAAI_SETUP_AUTO", "").strip().lower() in ("1", "true", "yes")

    # Repair NumPy before installing/importing packages that load cv2.
    # OpenCV 4.8 wheels crash with NumPy 2.x (_ARRAY_API / multiarray errors).
    force_install(["numpy<2.0.0"], no_deps=True)
    
    # installing must have Pytorch CPU
    force_install(["torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cpu"])

    # installing some must have dependencies
    print("Installing Core Dependencies...")
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", "opencv-python-headless"],
        check=False,
    )
    base_reqs = [
        "numpy<2.0.0",
        "customtkinter>=5.2.0", "toml>=0.10.2", "Pillow>=10.0.0", "discord.py>=2.3.2",
        "opencv-python==4.8.0.76", "requests>=2.34.0", "pandas>=2.0.0", "ultralytics", "aiohttp",
        "google-play-scraper", "pyautogui>=0.9.54", "packaging>=23.0", "PySide6>=6.7.0",
    ]
    force_install(base_reqs)
    force_install(["easyocr"], no_deps=True)
    # EasyOCR is installed without pip deps to avoid opencv-python-headless conflicts.
    force_install([
        "scikit-image", "ninja", "pyclipper", "python-bidi", "Shapely",
    ])

    target, ver, name = get_gpu_data()
    status_pytorch, status_accel = "CPU Edition", "N/A"
    
    # We will use this flag to check if we need the standard CPU onnxruntime
    onnx_installed = False
    onnx_variant = None

    # --- THE CHOICE BRANCHES ---

    def install_acceleration_variant(variant):
        nonlocal status_pytorch, status_accel, onnx_installed, onnx_variant
        install_gpu_runtime_variant(variant, compute_cap=ver if target == "nvidia" else 0.0)
        if variant == "cuda":
            ok, missing = verify_cuda_dlls(verbose=True)
            if not ok:
                print(
                    "CUDA DLLs still missing ("
                    + ", ".join(missing)
                    + "); repairing PyTorch CUDA wheels..."
                )
                ok, missing = repair_cuda_torch(compute_cap=ver, verbose=True)
            if not ok:
                print(
                    "WARNING: CUDA acceleration installed but CUDA DLLs are still missing. "
                    "Run: py -3.11-64 tools\\fix_gpu_runtime.py cuda"
                )
        status_pytorch, status_accel = variant_status_labels(variant)
        onnx_variant = variant
        onnx_installed = True
        return True

    if auto_setup:
        print(f"\nAuto setup: detecting and installing GPU acceleration for {name}...")
        onnx_variant, status_pytorch, status_accel, _runtime_results = auto_install_gpu_runtime(
            cards=cards,
            compute_cap=ver if target == "nvidia" else 0.0,
            verify=True,
        )
        onnx_installed = True

    # NVIDIA BRANCH (Series 10-50)
    elif target == "nvidia":
        print(f"\n NVIDIA: {name} detected.")
        if ask_user("Install NVIDIA CUDA acceleration? (recommended for NVIDIA GPUs)"):
            install_acceleration_variant("cuda")
        elif ask_user("Install DirectML GPU acceleration instead? (stable fallback on Windows)"):
            install_acceleration_variant("directml")

    # INTEL BRANCH (OpenVINO)
    elif target == "intel":
        print(f"\n Intel: {name} detected.")
        if ask_user("Install DirectML GPU acceleration? (recommended for most Windows Intel GPUs)"):
            install_acceleration_variant("directml")
        elif ask_user("Install Intel OpenVINO acceleration instead?"):
            install_acceleration_variant("openvino")

    # AMD BRANCH (DirectML)
    elif "amd" in target:
        print(f"\n AMD: {name} detected.")
        if ask_user("Install AMD DirectML acceleration?"):
            install_acceleration_variant("directml")

    elif ask_user("Install DirectML GPU acceleration? (works on many Windows GPUs)"):
        install_acceleration_variant("directml")

    # FALLBACK BRANCH (If user skipped acceleration or has a generic CPU)
    if not onnx_installed:
        print("\n Installing standard CPU ONNX Runtime...")
        install_gpu_runtime_variant("cpu")
        status_pytorch, status_accel = variant_status_labels("cpu")
        onnx_variant = "cpu"

    if onnx_variant:
        save_gpu_runtime_config(onnx_variant, cards)

    # some conflict fixes
    print("\n Finalizing and Repairing Conflicts...")
    force_install(["numpy<2.0.0"], no_deps=True)
    force_install(["adbutils==2.12.0", "av==12.3.0"])
    force_install(["https://github.com/leng-yue/py-scrcpy-client/archive/refs/tags/v0.5.0.zip"], no_deps=True)
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "opencv-python-headless"], check=False)
    force_install(["opencv-python==4.8.0.76"], no_deps=True)
    try:
        from visual_debug_window import OPENCV_REPAIR_CMD, opencv_highgui_available, visual_debug_backend_name

        opencv_highgui_available()
        backend = visual_debug_backend_name()
        if backend == "unavailable":
            print("WARNING: OpenCV GUI is unavailable after setup. Debug Screen will not work until repaired.")
            print(f"  Fix: {OPENCV_REPAIR_CMD}")
        else:
            print(f"Visual debug backend check: {backend}")
    except Exception as exc:
        print(f"WARNING: Could not verify visual debug backend: {exc}")

    import cv2
    import onnxruntime as ort
    import pandas as pd

    print(f"OpenCV verified: {cv2.__version__} ({sys.executable})")
    print(f"Pandas verified: {pd.__version__} ({sys.executable})")
    print(f"ONNX Runtime verified: {ort.__version__} providers={ort.get_available_providers()}")
    # the setup completes
    os.system('cls')
    print("="*50)
    print("            SETUP COMPLETED!")
    print("="*50)
    print(f"  - GPU Detected:     {name}")
    print(f"  - PyTorch:          {status_pytorch}")
    print(f"  - Accel Status:     {status_accel}")
    print("="*50 + "\n")

if "--pyla-install" in sys.argv:
    try:
        setup_pyla()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
    sys.exit(0)

if any(cmd in sys.argv for cmd in ["install", "develop"]):
    print(
        "\nWARNING: 'setup.py install' is deprecated. "
        "Redirecting to PylaAi setup mode."
    )
    try:
        setup_pyla()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
    sys.exit(0)

setup(
    name="PylaAi-XXZ", version="1.0.0",
    packages=find_packages(exclude=["api", "cfg", "models"]),
    install_requires=[]
)
