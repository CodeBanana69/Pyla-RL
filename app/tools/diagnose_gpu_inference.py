#!/usr/bin/env python3
"""Diagnose ONNX GPU provider selection and CPU fallback causes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from inference_health import audit_main_detector, evaluate_gpu_runtime_status
from utils import load_toml_as_dict


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose GPU ONNX inference setup.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    config = load_toml_as_dict("cfg/general_config.toml")
    status = evaluate_gpu_runtime_status(config)
    health = audit_main_detector(config)
    report = {
        "runtime_status": status,
        "audit": health,
    }

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    print("GPU inference diagnosis")
    print("-" * 40)
    print(f"Primary GPU: {health.get('primary_gpu')}")
    print(
        f"Configured cpu_or_gpu={health.get('cpu_or_gpu_configured')} "
        f"resolved={health.get('cpu_or_gpu_resolved')}"
    )
    print(f"ONNX package: {health.get('onnx_variant_installed')} ({health.get('onnxruntime_version')})")
    print(f"Available providers: {', '.join(health.get('onnx_available_providers') or [])}")
    print(f"Pre-start check: {status.get('reason')} needs_repair={status.get('needs_repair')}")
    if status.get("missing_cuda_dlls"):
        print(f"Missing CUDA DLLs: {', '.join(status.get('missing_cuda_dlls') or [])}")
    for tag, info in (health.get("onnx_providers") or {}).items():
        print(f"  {tag}: requested={info.get('requested')} actual={info.get('actual')}")
    inference = health.get("inference_health") or {}
    if inference.get("fix_hint"):
        print(f"Fix hint: {inference.get('fix_hint')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
