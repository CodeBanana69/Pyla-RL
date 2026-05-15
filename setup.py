import sys
import platform
import subprocess
import os

if platform.system() != "Windows" or "microsoft" in platform.uname()[3].lower():
    print("\n" + "!"*50)
    print("  ERROR: This version of PylaAi-XXZ is for WINDOWS ONLY.")
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

def force_install(reqs, no_deps=False):
    cmd = [sys.executable, "-m", "pip", "install"]
    if no_deps: cmd += ["--force-reinstall", "--no-deps"]
    subprocess.check_call(cmd + reqs)

def remove_onnxruntime_variants():
    subprocess.run([
        sys.executable, "-m", "pip", "uninstall", "-y",
        "onnxruntime", "onnxruntime-gpu", "onnxruntime-directml", "onnxruntime-openvino"
    ], check=False)

def install_onnxruntime_variant(req):
    remove_onnxruntime_variants()
    force_install([req])

def get_gpu_data():
    """Detects exact NVIDIA/AMD/Intel architecture for Windows."""
    # NVIDIA cards Check
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,compute_cap", "--format=csv,noheader,nounits"],
            encoding='utf-8', stderr=subprocess.DEVNULL).strip()
        name, cc = output.split(', ')
        return "nvidia", float(cc), name
    except: pass

    # AMD/Intel cards Check
    try:
        wmic = subprocess.check_output(["wmic", "path", "win32_VideoController", "get", "name"], encoding='utf-8')
        if "AMD" in wmic or "Radeon" in wmic: return "amd_windows", 0.0, "AMD Radeon"
        if "Intel" in wmic: return "intel", 0.0, "Intel HD/Arc Graphics"
    except: pass

    return "cpu", 0.0, "Generic CPU"

def ask_user(prompt_text):
    if os.environ.get("PYLAAI_SETUP_AUTO", "").strip().lower() in ("1", "true", "yes"):
        print(f"\n{prompt_text} (Y/N): Y [auto]")
        return True
    print(f"\n{prompt_text} (Y/N): ", end='', flush=True)
    response = sys.stdin.readline().strip().lower()
    return response in ['y', 'yes']

def setup_pyla():
    print("\n" + "="*50 + "\n   PylaAi-XXZ - Windows Setup   \n" + "="*50)
    
    # installing must have Pytorch CPU
    force_install(["torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cpu"])

    # installing some must have dependencies
    print("Installing Core Dependencies...")
    base_reqs = [
        "customtkinter>=5.2.0", "toml>=0.10.2", "Pillow>=10.0.0", "discord.py>=2.3.2",
        "opencv-python==4.8.0.76", "requests", "ultralytics", "aiohttp", "easyocr",
        "google-play-scraper", "pyautogui>=0.9.54", "packaging>=23.0"
    ]
    force_install(base_reqs)

    target, ver, name = get_gpu_data()
    status_pytorch, status_accel = "CPU Edition", "N/A"
    
    # We will use this flag to check if we need the standard CPU onnxruntime
    onnx_installed = False

    # --- THE CHOICE BRANCHES ---

    def nvidia_cuda_torch_command():
        if ver >= 10.0: # 50-Series Blackwell
            return ["--pre", "torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/nightly/cu128"], "CUDA 12.8 (Blackwell)"
        if ver >= 8.9: # 40-Series Ada
            return ["torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cu124"], "CUDA 12.4 (Ada)"
        return ["torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cu121"], "CUDA 12.1 (Standard)"
    
    # NVIDIA BRANCH (Series 10-50)
    if target == "nvidia":
        print(f"\n NVIDIA: {name} detected.")
        if os.environ.get("PYLAAI_SETUP_AUTO", "").strip().lower() in ("1", "true", "yes"):
            print("\nAuto setup: installing CUDA GPU acceleration for NVIDIA Windows systems.")
            torch_cmd, status_accel = nvidia_cuda_torch_command()
            force_install(torch_cmd)
            install_onnxruntime_variant("onnxruntime-gpu")
            onnx_installed = True
            status_pytorch = "CUDA Edition"
        elif ask_user("Install NVIDIA CUDA acceleration? (takes more storage but gives you more ips, about 2GB)"):
            torch_cmd, status_accel = nvidia_cuda_torch_command()
            force_install(torch_cmd)
            install_onnxruntime_variant("onnxruntime-gpu")
            onnx_installed = True
            status_pytorch = "CUDA Edition"
        elif ask_user("Install DirectML GPU acceleration instead? (smaller, works on most Windows GPUs)"):
            install_onnxruntime_variant("onnxruntime-directml")
            onnx_installed = True
            status_pytorch = "DirectML Edition"
            status_accel = "DirectML"

    # INTEL BRANCH (OpenVINO)
    elif target == "intel":
        print(f"\n Intel: {name} detected.")
        if ask_user("Install DirectML GPU acceleration? (recommended for most Windows Intel GPUs)"):
            install_onnxruntime_variant("onnxruntime-directml")
            onnx_installed = True
            status_pytorch = "DirectML Edition"
            status_accel = "DirectML"
        elif ask_user("Install Intel OpenVINO acceleration instead?"):
            install_onnxruntime_variant("onnxruntime-openvino")
            onnx_installed = True
            status_pytorch = "OpenVINO Edition"
            status_accel = "OpenVINO"

    # AMD BRANCH (DirectML)
    elif "amd" in target:
        print(f"\n AMD: {name} detected.")
        if ask_user("Install AMD DirectML acceleration?"):
            install_onnxruntime_variant("onnxruntime-directml")
            onnx_installed = True
            status_pytorch = "DirectML Edition"
            status_accel = "DirectML"

    elif ask_user("Install DirectML GPU acceleration? (works on many Windows GPUs)"):
        install_onnxruntime_variant("onnxruntime-directml")
        onnx_installed = True
        status_pytorch = "DirectML Edition"
        status_accel = "DirectML"

    # FALLBACK BRANCH (If user skipped acceleration or has a generic CPU)
    if not onnx_installed:
        print("\n Installing standard CPU ONNX Runtime...")
        install_onnxruntime_variant("onnxruntime")
        status_accel = "Standard CPU"

    # some conflict fixes
    print("\n Finalizing and Repairing Conflicts...")
    force_install(["numpy<2.0.0"], no_deps=True)
    force_install(["adbutils==2.12.0", "av==12.3.0"])
    force_install(["https://github.com/leng-yue/py-scrcpy-client/archive/refs/tags/v0.5.0.zip"], no_deps=True)

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

setup(
    name="PylaAi-XXZ", version="1.0.0",
    packages=find_packages(exclude=["api", "cfg", "models", "typization"]),
    install_requires=[]
)

if any(cmd in sys.argv for cmd in ["install", "develop"]):
    print(
        "\nWARNING: 'setup.py install' is deprecated. "
        "Run 'python setup.py --pyla-install' or setup.exe instead."
    )
    try: setup_pyla()
    except Exception as e: print(f"\n[ERROR] {e}"); sys.exit(1)
