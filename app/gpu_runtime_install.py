"""Shared GPU / ONNX runtime installation used by setup.py and fix_gpu_runtime.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from gpu_support import (
    auto_candidate_variants,
    primary_vendor,
    select_best_runtime_result,
)

ONNX_VARIANT_PACKAGES = {
    "directml": "onnxruntime-directml",
    "cuda": "onnxruntime-gpu",
    "openvino": "onnxruntime-openvino",
    "cpu": "onnxruntime",
}
ONNX_VARIANTS = tuple(ONNX_VARIANT_PACKAGES.values())
NUMPY_PIN = "numpy<2.0.0"
OPENCV_PIN = "opencv-python==4.8.0.76"
CUDA_TORCH_INDEX_DEFAULT = "https://download.pytorch.org/whl/cu124"
BENCHMARK_MARKER = "PYLA_RUNTIME_BENCHMARK="


def project_root() -> Path:
    return Path(__file__).resolve().parent


def _numpy_major_version(python=None) -> int | None:
    python = python or sys.executable
    completed = subprocess.run(
        [python, "-c", "import numpy; print(numpy.__version__)"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    version = (completed.stdout or "").strip()
    try:
        return int(version.split(".", 1)[0])
    except (TypeError, ValueError):
        return None


def repair_numpy(python=None, *, verbose=True, reinstall_opencv=True) -> bool:
    """Pin NumPy 1.x and rebuild OpenCV 4.8 wheels that break on NumPy 2.x."""
    python = python or sys.executable
    try:
        from tools.python_runtime import is_supported_python, unsupported_python_message

        if not is_supported_python(python):
            raise RuntimeError(unsupported_python_message(python))
    except ImportError:
        pass

    major = _numpy_major_version(python)
    if major is not None and major < 2:
        return False
    if verbose:
        label = "missing" if major is None else f"{major}.x"
        print(f"Repairing NumPy ({label} -> 1.x) for OpenCV 4.8 compatibility...")

    def _pip_no_deps(*packages: str) -> None:
        completed = subprocess.run(
            [python, "-m", "pip", "install", "--force-reinstall", "--no-deps", *packages],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(
                f"pip install failed for {', '.join(packages)} using {python}.\n{detail}"
            )

    _pip_no_deps(NUMPY_PIN)
    if reinstall_opencv:
        subprocess.run(
            [python, "-m", "pip", "uninstall", "-y", "opencv-python-headless"],
            check=False,
        )
        _pip_no_deps(OPENCV_PIN)
    return True


def pip_run(args, python=None, upgrade=False, force_reinstall=False):
    python = python or sys.executable
    command = [python, "-m", "pip", "install"]
    if force_reinstall:
        command.extend(["--force-reinstall", "--no-cache-dir"])
    elif upgrade:
        command.append("--upgrade")
    subprocess.check_call(command + list(args))


def _uninstall_torch(python=None):
    python = python or sys.executable
    subprocess.run([python, "-m", "pip", "uninstall", "-y", "torch", "torchvision"], check=False)


NVIDIA_CUDA_DLL_PACKAGES = [
    "nvidia-cublas-cu12",
    "nvidia-cudnn-cu12",
    "nvidia-cuda-runtime-cu12",
]


def _pip_install_torch_cuda(compute_cap=0.0, python=None, *, force_reinstall=False):
    pip_run(
        torch_cuda_install_args(compute_cap),
        python=python,
        upgrade=not force_reinstall,
        force_reinstall=force_reinstall,
    )


def _onnx_package_installed(package: str, python=None) -> bool:
    python = python or sys.executable
    completed = subprocess.run(
        [python, "-m", "pip", "show", package],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def uninstall_onnx_variants(python=None):
    """Remove any installed ONNX Runtime variant before installing another."""
    python = python or sys.executable
    installed = [package for package in ONNX_VARIANTS if _onnx_package_installed(package, python)]
    if not installed:
        return
    subprocess.run([python, "-m", "pip", "uninstall", "-y", *installed], check=False)


def torch_cuda_install_args(compute_cap=0.0):
    if compute_cap >= 10.0:
        return [
            "--pre",
            "torch",
            "torchvision",
            "--index-url",
            "https://download.pytorch.org/whl/nightly/cu128",
        ]
    if compute_cap >= 8.9:
        return ["torch", "torchvision", "--index-url", CUDA_TORCH_INDEX_DEFAULT]
    return ["torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cu121"]


def variant_status_labels(variant):
    labels = {
        "cuda": ("CUDA Edition", "CUDA 12.x"),
        "directml": ("DirectML Edition", "DirectML"),
        "openvino": ("OpenVINO Edition", "OpenVINO"),
        "cpu": ("CPU Edition", "Standard CPU"),
    }
    return labels.get(variant, ("CPU Edition", "Standard CPU"))


def setup_candidate_variants(cards=None):
    """Runtime install order for unattended setup.exe."""
    vendor = primary_vendor(cards)
    if vendor == "nvidia":
        return ["cuda", "directml", "cpu"]
    if vendor == "amd":
        return ["directml", "cpu"]
    if vendor == "intel":
        return ["directml", "cpu"]
    return ["directml", "cpu"]


def install_variant(variant, compute_cap=0.0, python=None):
    variant = str(variant or "cpu").strip().lower()
    package = ONNX_VARIANT_PACKAGES[variant]
    python = python or sys.executable

    uninstall_onnx_variants(python)
    if variant == "cuda":
        _uninstall_torch(python)
        _pip_install_torch_cuda(compute_cap, python=python, force_reinstall=True)
    pip_run([package], python=python, upgrade=True)
    repair_numpy(python=python, verbose=False)


def verify_cuda_dlls(verbose=False):
    root = project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from cuda_runtime_paths import add_cuda_dll_directories, has_cuda_dependency_dlls

    add_cuda_dll_directories(verbose=verbose)
    return has_cuda_dependency_dlls()


def repair_cuda_torch(compute_cap=0.0, python=None, verbose=False):
    _uninstall_torch(python=python)
    _pip_install_torch_cuda(compute_cap, python=python, force_reinstall=True)
    ok, missing = verify_cuda_dlls(verbose=verbose)
    if not ok:
        print("Installing NVIDIA CUDA dependency wheels for cuDNN/cuBLAS...")
        pip_run(NVIDIA_CUDA_DLL_PACKAGES, python=python, upgrade=True)
        ok, missing = verify_cuda_dlls(verbose=verbose)
    return ok, missing


def smoke_test_variant(variant, python=None, runs=2, timeout=180):
    python = python or sys.executable
    repair_numpy(python=python, verbose=False)
    root = project_root()
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
        [python, "-c", code],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout,
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
        "error": (completed.stderr or completed.stdout or "runtime smoke test returned no result").strip(),
    }


def _variant_verified(variant, result):
    if not result.get("ok"):
        return False
    provider = str(result.get("provider") or "")
    if variant == "cpu":
        return provider == "CPUExecutionProvider"
    if variant == "cuda":
        return provider == "CUDAExecutionProvider"
    if variant == "directml":
        return provider == "DmlExecutionProvider"
    if variant == "openvino":
        return provider == "OpenVINOExecutionProvider"
    return float(result.get("ips") or 0) > 0


def install_and_verify_variant(
    variant,
    compute_cap=0.0,
    python=None,
    *,
    smoke_runs=2,
    verbose_cuda=False,
):
    install_variant(variant, compute_cap=compute_cap, python=python)
    if variant == "cuda":
        ok, missing = verify_cuda_dlls(verbose=verbose_cuda)
        if not ok:
            print(
                "CUDA DLLs missing after install ("
                + ", ".join(missing)
                + "); repairing PyTorch CUDA wheels..."
            )
            ok, missing = repair_cuda_torch(compute_cap=compute_cap, python=python, verbose=verbose_cuda)
        if not ok:
            return {
                "variant": variant,
                "provider": "",
                "ips": 0.0,
                "ok": False,
                "error": "missing CUDA DLLs: " + ", ".join(missing),
            }

    result = smoke_test_variant(variant, python=python, runs=smoke_runs)
    if not _variant_verified(variant, result):
        error = result.get("error") or f"provider={result.get('provider') or 'none'}"
        result["ok"] = False
        result["error"] = error
    return result


def auto_install_gpu_runtime(
    cards=None,
    compute_cap=0.0,
    python=None,
    *,
    verify=True,
    benchmark_runs=0,
):
    """Install the best working ONNX runtime for the detected GPU."""
    from gpu_support import detect_graphics_cards

    cards = cards if cards is not None else detect_graphics_cards()
    python = python or sys.executable
    variants = (
        auto_candidate_variants(cards)
        if benchmark_runs > 0
        else setup_candidate_variants(cards)
    )

    results = []
    chosen = None
    for variant in variants:
        print()
        print("=" * 60)
        print(f"GPU runtime setup: trying {variant}")
        print("=" * 60)
        try:
            if verify:
                result = install_and_verify_variant(
                    variant,
                    compute_cap=compute_cap,
                    python=python,
                    smoke_runs=max(2, min(benchmark_runs, 12)) if benchmark_runs else 2,
                    verbose_cuda=True,
                )
            else:
                install_variant(variant, compute_cap=compute_cap, python=python)
                if variant == "cuda":
                    ok, missing = verify_cuda_dlls(verbose=True)
                    if not ok:
                        ok, missing = repair_cuda_torch(
                            compute_cap=compute_cap,
                            python=python,
                            verbose=True,
                        )
                    if not ok:
                        continue
                result = {"variant": variant, "provider": variant, "ips": 1.0, "ok": True}
        except Exception as exc:
            print(f"GPU runtime {variant} failed during install: {exc}")
            result = {
                "variant": variant,
                "provider": "",
                "ips": 0.0,
                "ok": False,
                "error": str(exc),
            }

        results.append(result)
        if result.get("ok") and _variant_verified(variant, result):
            print(
                f"GPU runtime ready: {variant} "
                f"(provider={result.get('provider')}, ips={float(result.get('ips') or 0):.2f})"
            )
            if benchmark_runs <= 0:
                chosen = variant
                break
        else:
            print(
                f"GPU runtime {variant} did not verify cleanly: "
                f"{result.get('error') or result.get('provider') or 'unknown error'}"
            )

    if benchmark_runs > 0:
        best = select_best_runtime_result(results, cards)
        chosen = best["variant"] if best else None
        if chosen and results[-1].get("variant") != chosen:
            print()
            print(f"Reinstalling best benchmarked runtime: {chosen}")
            install_variant(chosen, compute_cap=compute_cap, python=python)

    if not chosen:
        chosen = "cpu"
        if not any(result.get("variant") == "cpu" and result.get("ok") for result in results):
            install_variant("cpu", python=python)
            repair_numpy(python=python, verbose=False)
            results.append(
                {"variant": "cpu", "provider": "CPUExecutionProvider", "ips": 1.0, "ok": True}
            )
        vendor = primary_vendor(cards)
        if vendor not in ("cpu", None):
            print(
                "WARNING: No GPU ONNX runtime verified; using CPU packages for now. "
                "Fix GPU inference before farming: py -3.11-64 tools\\fix_gpu_runtime.py auto"
            )

    status_pytorch, status_accel = variant_status_labels(chosen)
    return chosen, status_pytorch, status_accel, results
