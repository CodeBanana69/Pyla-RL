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
CUDA_TORCH_INDEX_DEFAULT = "https://download.pytorch.org/whl/cu124"
BENCHMARK_MARKER = "PYLA_RUNTIME_BENCHMARK="


def project_root() -> Path:
    return Path(__file__).resolve().parent


def pip_run(args, python=None, upgrade=False):
    python = python or sys.executable
    command = [python, "-m", "pip", "install"]
    if upgrade:
        command.append("--upgrade")
    subprocess.check_call(command + list(args))


def uninstall_onnx_variants(python=None):
    python = python or sys.executable
    subprocess.run(
        [python, "-m", "pip", "uninstall", "-y", *ONNX_VARIANTS],
        check=False,
    )


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
        pip_run(torch_cuda_install_args(compute_cap), python=python, upgrade=True)
    pip_run([package], python=python, upgrade=True)


def verify_cuda_dlls(verbose=False):
    root = project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from cuda_runtime_paths import add_cuda_dll_directories, has_cuda_dependency_dlls

    add_cuda_dll_directories(verbose=verbose)
    return has_cuda_dependency_dlls()


def repair_cuda_torch(compute_cap=0.0, python=None, verbose=False):
    pip_run(torch_cuda_install_args(compute_cap), python=python, upgrade=True)
    return verify_cuda_dlls(verbose=verbose)


def smoke_test_variant(variant, python=None, runs=2, timeout=180):
    python = python or sys.executable
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

from visual_debug_window import opencv_runtime_ready, repair_opencv_runtime

if not opencv_runtime_ready():
    repair_opencv_runtime()
    import importlib
    import cv2 as _cv2
    importlib.reload(_cv2)

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
            results.append(
                {"variant": "cpu", "provider": "CPUExecutionProvider", "ips": 1.0, "ok": True}
            )

    status_pytorch, status_accel = variant_status_labels(chosen)
    return chosen, status_pytorch, status_accel, results
