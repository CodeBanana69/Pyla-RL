"""GPU vs CPU inference health checks and fallback telemetry."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from gpu_support import (
    apply_gpu_config,
    detect_graphics_cards,
    gpu_help_message,
    normalize_preferred_device,
    primary_gpu_name,
    primary_vendor,
    recommended_directml_device_id,
    resolve_inference_device,
)
from utils import load_toml_as_dict, resolve_project_path

_EXPECTED_PROVIDER = {
    "cuda": "CUDAExecutionProvider",
    "directml": "DmlExecutionProvider",
    "openvino": "OpenVINOExecutionProvider",
}


def _gpu_provider_names() -> set[str]:
    return {"CUDAExecutionProvider", "DmlExecutionProvider", "OpenVINOExecutionProvider"}


def _infer_onnx_variant_installed(available_providers: list[str]) -> str:
    providers = set(available_providers or [])
    if "CUDAExecutionProvider" in providers:
        return "onnxruntime-gpu"
    if "DmlExecutionProvider" in providers:
        return "onnxruntime-directml"
    if "OpenVINOExecutionProvider" in providers:
        return "onnxruntime-openvino"
    return "onnxruntime"


def collect_provider_info(play) -> dict[str, dict[str, str]]:
    mapping = {
        "main": getattr(play, "Detect_main_info", None),
        "tile": getattr(play, "Detect_tile_detector", None),
        "close_tile": getattr(play, "Detect_close_tile_detector", None),
    }
    result = {}
    for tag, detector in mapping.items():
        if detector is None:
            continue
        info = detector.get_provider_info()
        result[tag] = {
            "requested": str(info.get("requested") or ""),
            "actual": str(info.get("actual") or ""),
            "model_path": str(info.get("model_path") or ""),
        }
    return result


def _has_physical_gpu(cards=None) -> bool:
    cards = cards if cards is not None else detect_graphics_cards()
    return bool(cards) and primary_vendor(cards) != "cpu"


def _build_fix_hint(*, configured_for_cpu: bool, missing_gpu_provider: bool, using_cpu_despite_gpu: bool, vendor: str) -> str:
    if configured_for_cpu:
        return 'Set cpu_or_gpu = "auto" in cfg/general_config.toml'
    if missing_gpu_provider:
        return gpu_help_message("missing_gpu_provider", vendor=vendor)
    if using_cpu_despite_gpu:
        return gpu_help_message("session_cpu_fallback", vendor=vendor)
    return ""


def audit_inference_setup(play, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config if config is not None else load_toml_as_dict("cfg/general_config.toml")
    cards = detect_graphics_cards()
    vendor = primary_vendor(cards)
    configured = str(config.get("cpu_or_gpu", "auto") or "auto")
    resolved = resolve_inference_device(configured, cards)
    configured_normalized = normalize_preferred_device(configured)
    configured_for_cpu = configured_normalized == "cpu"

    try:
        import onnxruntime as ort

        available_providers = list(ort.get_available_providers())
        onnxruntime_version = ort.__version__
    except Exception:
        available_providers = []
        onnxruntime_version = ""

    provider_info = collect_provider_info(play)
    actual_providers = {info.get("actual") for info in provider_info.values()}
    gpu_available_in_ort = bool(_gpu_provider_names() & set(available_providers))
    missing_gpu_provider = _has_physical_gpu(cards) and not configured_for_cpu and not gpu_available_in_ort
    using_cpu_despite_gpu = (
        _has_physical_gpu(cards)
        and not configured_for_cpu
        and all(provider == "CPUExecutionProvider" for provider in actual_providers if provider)
    )

    configured_dml = str(config.get("directml_device_id", "auto") or "auto")
    recommended_dml = str(recommended_directml_device_id(cards))
    wrong_directml_adapter = False
    if resolved == "directml" and configured_dml not in ("", "auto", "none") and recommended_dml not in ("", "auto", "none"):
        wrong_directml_adapter = configured_dml != recommended_dml

    smoke_ips = 0.0
    detector = getattr(play, "Detect_main_info", None)
    if detector is not None:
        sample = np.zeros((1080, 1920, 3), dtype=np.uint8)
        started = time.perf_counter()
        for _ in range(3):
            detector.detect_objects(sample, conf_tresh=0.99)
        elapsed = time.perf_counter() - started
        smoke_ips = (3.0 / elapsed) if elapsed > 0 else 0.0

    inference_health = {
        "using_cpu_despite_gpu": using_cpu_despite_gpu,
        "configured_for_cpu": configured_for_cpu,
        "missing_gpu_provider": missing_gpu_provider,
        "wrong_directml_adapter": wrong_directml_adapter,
        "smoke_ips": round(smoke_ips, 2),
        "fix_hint": _build_fix_hint(
            configured_for_cpu=configured_for_cpu,
            missing_gpu_provider=missing_gpu_provider,
            using_cpu_despite_gpu=using_cpu_despite_gpu,
            vendor=vendor,
        ),
    }

    provider_summary = "CPU"
    for info in provider_info.values():
        actual = info.get("actual") or ""
        if actual in _gpu_provider_names():
            if actual == "DmlExecutionProvider":
                provider_summary = "DirectML"
            elif actual == "CUDAExecutionProvider":
                provider_summary = "CUDA"
            else:
                provider_summary = actual.replace("ExecutionProvider", "")
            break
        if actual == "CPUExecutionProvider" and using_cpu_despite_gpu:
            provider_summary = "CPU(!)"

    return {
        "gpus_detected": [{"vendor": card_vendor, "name": name} for card_vendor, name in cards],
        "primary_gpu": primary_gpu_name(cards),
        "cpu_or_gpu_configured": configured,
        "cpu_or_gpu_resolved": resolved,
        "onnx_available_providers": available_providers,
        "onnx_variant_installed": _infer_onnx_variant_installed(available_providers),
        "onnxruntime_version": onnxruntime_version,
        "onnx_providers": provider_info,
        "directml_device_id": configured_dml,
        "directml_device_recommended": recommended_dml,
        "inference_health": inference_health,
        "provider_summary": provider_summary,
    }


def evaluate_gpu_runtime_status(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check whether the configured GPU ONNX runtime is installed and usable."""
    config = config if config is not None else load_toml_as_dict("cfg/general_config.toml")
    configured = str(config.get("cpu_or_gpu", "auto") or "auto")
    configured_normalized = normalize_preferred_device(configured)
    if configured_normalized == "cpu":
        return {"needs_repair": False, "reason": "cpu_configured"}

    cards = detect_graphics_cards()
    if not _has_physical_gpu(cards):
        return {"needs_repair": False, "reason": "no_gpu"}

    resolved = resolve_inference_device(configured, cards)
    vendor = primary_vendor(cards)
    expected_provider = _EXPECTED_PROVIDER.get(resolved, "")
    if not expected_provider:
        return {"needs_repair": False, "reason": "unsupported_resolution", "resolved": resolved}

    try:
        import onnxruntime as ort

        available_providers = list(ort.get_available_providers())
    except Exception as exc:
        return {
            "needs_repair": True,
            "reason": "onnxruntime_import_failed",
            "error": str(exc),
            "fix_hint": gpu_help_message("missing_gpu_provider", vendor=vendor),
        }

    if expected_provider not in available_providers:
        return {
            "needs_repair": True,
            "reason": "missing_gpu_provider",
            "resolved": resolved,
            "expected_provider": expected_provider,
            "available_providers": available_providers,
            "fix_hint": gpu_help_message("missing_gpu_provider", vendor=vendor),
        }

    if resolved == "cuda":
        from gpu_runtime_install import verify_cuda_dlls

        ok, missing = verify_cuda_dlls()
        if not ok:
            return {
                "needs_repair": True,
                "reason": "missing_cuda_dlls",
                "missing_cuda_dlls": missing,
                "fix_hint": gpu_help_message("session_cpu_fallback", vendor=vendor),
            }

    if os.environ.get("PYLAAI_SKIP_GPU_SMOKE") == "1":
        return {
            "needs_repair": False,
            "reason": "ok",
            "resolved": resolved,
            "expected_provider": expected_provider,
        }

    from gpu_runtime_install import _variant_verified, smoke_test_variant

    probe = smoke_test_variant(resolved, runs=1, timeout=120)
    if not _variant_verified(resolved, probe):
        return {
            "needs_repair": True,
            "reason": "session_cpu_fallback",
            "resolved": resolved,
            "expected_provider": expected_provider,
            "probe": probe,
            "fix_hint": gpu_help_message("session_cpu_fallback", vendor=vendor),
        }

    return {
        "needs_repair": False,
        "reason": "ok",
        "resolved": resolved,
        "expected_provider": expected_provider,
        "probe": probe,
    }


def ensure_gpu_inference_runtime(config: dict[str, Any] | None = None, *, auto_repair: bool = True) -> dict[str, Any]:
    """Repair GPU ONNX runtime before models load. Restarts the process when packages change."""
    status = evaluate_gpu_runtime_status(config)
    if not status.get("needs_repair"):
        return status
    if not auto_repair:
        print(
            "WARNING: GPU inference is not ready "
            f"({status.get('reason')}). {status.get('fix_hint') or ''}".strip()
        )
        return status
    if os.environ.get("PYLAAI_GPU_RUNTIME_REPAIR") == "1":
        print(
            "WARNING: GPU inference is still unavailable after an automatic repair attempt "
            f"({status.get('reason')}). Continuing on CPU."
        )
        return status

    print(
        "GPU inference is not ready "
        f"({status.get('reason')}). Installing the correct ONNX runtime..."
    )
    os.environ["PYLAAI_GPU_RUNTIME_REPAIR"] = "1"

    from gpu_runtime_install import auto_install_gpu_runtime

    import toml

    cards = detect_graphics_cards()
    chosen, _, _, _ = auto_install_gpu_runtime(cards=cards, verify=True, benchmark_runs=0)
    config_path = Path(resolve_project_path("cfg/general_config.toml"))
    cfg = toml.load(config_path) if config_path.exists() else {}
    apply_gpu_config(cfg, chosen, cards)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(toml.dumps(cfg), encoding="utf-8")
    print("GPU runtime repaired. Restarting Pyla-RL...")
    subprocess.run([sys.executable] + sys.argv)
    sys.exit(0)


def record_provider_fallback(model_tag: str, from_provider: str, to_provider: str, error: str | None = None) -> None:
    try:
        from perf_profiler import get_profiler

        profiler = get_profiler()
        profiler.mark_counter("onnx_provider_fallback")
        if to_provider == "CPUExecutionProvider":
            profiler.mark_counter("onnx_cpu_frames")
        profiler.write_trace_line(
            {
                "ts": time.time(),
                "event": "provider_fallback",
                "model_tag": model_tag,
                "from_provider": from_provider,
                "to_provider": to_provider,
                "error": str(error or "")[:500],
            }
        )
    except Exception:
        return None


def audit_main_detector(config: dict[str, Any] | None = None) -> dict[str, Any]:
    from detect import Detect
    from utils import resolve_project_path

    model_path = resolve_project_path("models/mainInGameModel.onnx")
    detector = Detect(model_path, classes=["enemy", "teammate", "player"], model_tag="main")

    class _PlayStub:
        Detect_main_info = detector
        Detect_tile_detector = None
        Detect_close_tile_detector = None

    return audit_inference_setup(_PlayStub(), config)


def log_startup_health(health: dict[str, Any]) -> None:
    inference = health.get("inference_health") or {}
    if inference.get("using_cpu_despite_gpu"):
        fix_hint = inference.get("fix_hint") or ""
        print(
            "WARNING: GPU detected but ONNX inference is running on CPU. "
            f"This will severely reduce IPS. {fix_hint}".strip()
        )
    elif inference.get("missing_gpu_provider"):
        fix_hint = inference.get("fix_hint") or ""
        print(f"WARNING: GPU detected but no GPU ONNX provider is installed. {fix_hint}".strip())
    elif inference.get("wrong_directml_adapter"):
        print(
            "WARNING: directml_device_id may not match the recommended discrete GPU adapter. "
            f"Configured={health.get('directml_device_id')} recommended={health.get('directml_device_recommended')}"
        )
