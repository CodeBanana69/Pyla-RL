#!/usr/bin/env python3
"""Analyze perf_trace JSONL logs for IPS bottlenecks."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * pct))
    return ordered[max(0, min(index, len(ordered) - 1))]


def load_trace(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _startup_system(rows: list[dict]) -> dict:
    for row in rows:
        if row.get("event") == "startup":
            return row.get("system") or {}
        if row.get("system"):
            return row.get("system") or {}
    return {}


def _gpu_report(system: dict) -> list[str]:
    lines = []
    health = system.get("inference_health") or {}
    if not system and not health:
        return lines
    lines.append("GPU / inference health")
    lines.append("-" * 40)
    if system.get("primary_gpu"):
        lines.append(f"Primary GPU: {system.get('primary_gpu')}")
    if system.get("cpu_or_gpu_configured") is not None:
        lines.append(
            f"Configured cpu_or_gpu={system.get('cpu_or_gpu_configured')} "
            f"resolved={system.get('cpu_or_gpu_resolved')}"
        )
    if system.get("onnx_variant_installed"):
        lines.append(f"ONNX package: {system.get('onnx_variant_installed')}")
    providers = system.get("onnx_providers") or {}
    for tag, info in providers.items():
        lines.append(f"  {tag}: requested={info.get('requested')} actual={info.get('actual')}")
    if health.get("using_cpu_despite_gpu"):
        lines.append("WARNING: GPU detected but ONNX is running on CPU.")
        if health.get("fix_hint"):
            lines.append(f"Fix: {health.get('fix_hint')}")
    elif health.get("missing_gpu_provider"):
        lines.append("WARNING: GPU detected but no GPU ONNX provider is installed.")
        if health.get("fix_hint"):
            lines.append(f"Fix: {health.get('fix_hint')}")
    elif health.get("wrong_directml_adapter"):
        lines.append(
            "WARNING: directml_device_id may not match recommended adapter "
            f"({system.get('directml_device_id')} vs {system.get('directml_device_recommended')})."
        )
    smoke_ips = health.get("smoke_ips")
    if smoke_ips is not None and health.get("using_cpu_despite_gpu") and float(smoke_ips) < 10:
        lines.append(f"Smoke IPS {smoke_ips:.1f} is consistent with CPU fallback.")
    lines.append("")
    return lines


def analyze(rows: list[dict]) -> str:
    if not rows:
        return "No readable perf trace rows found."

    ips_values = [float(row["ips"]) for row in rows if isinstance(row.get("ips"), (int, float))]
    feed_values = [float(row["feed_fps"]) for row in rows if isinstance(row.get("feed_fps"), (int, float))]
    bottlenecks = Counter()
    stage_totals = defaultdict(float)
    stage_p95 = defaultdict(list)
    counter_totals = Counter()

    for row in rows:
        perf = row.get("perf") or {}
        bottleneck = perf.get("bottleneck")
        if bottleneck:
            bottlenecks[str(bottleneck)] += 1
        for name, stats in (perf.get("stages") or {}).items():
            if not isinstance(stats, dict):
                continue
            stage_totals[name] += float(stats.get("total_ms") or 0.0)
            if stats.get("p95_ms") is not None:
                stage_p95[name].append(float(stats["p95_ms"]))
        for name, value in (perf.get("counters") or {}).items():
            counter_totals[str(name)] += int(value or 0)

    lines = []
    startup = _startup_system(rows)
    lines.extend(_gpu_report(startup))

    lines.append("Session summary")
    lines.append("-" * 40)
    lines.append(f"Samples: {len(rows)}")
    if ips_values:
        lines.append(
            f"IPS: avg={statistics.mean(ips_values):.2f} p50={_percentile(ips_values, 0.5):.2f} "
            f"p95={_percentile(ips_values, 0.95):.2f}"
        )
    if feed_values:
        lines.append(
            f"Feed FPS: avg={statistics.mean(feed_values):.2f} p50={_percentile(feed_values, 0.5):.2f} "
            f"p95={_percentile(feed_values, 0.95):.2f}"
        )
    if bottlenecks:
        lines.append("")
        lines.append("Bottleneck distribution")
        lines.append("-" * 40)
        total = sum(bottlenecks.values())
        for name, count in bottlenecks.most_common():
            lines.append(f"  {name}: {count} ({100.0 * count / total:.1f}%)")

    if stage_totals:
        lines.append("")
        lines.append("Top stages by total time")
        lines.append("-" * 40)
        for name, total_ms in sorted(stage_totals.items(), key=lambda item: item[1], reverse=True)[:10]:
            p95 = _percentile(stage_p95.get(name, []), 0.95)
            lines.append(f"  {name}: total={total_ms:.1f}ms p95={p95:.1f}ms")

    if counter_totals:
        lines.append("")
        lines.append("Counters")
        lines.append("-" * 40)
        for name, count in counter_totals.most_common():
            lines.append(f"  {name}: {count}")

    lines.append("")
    lines.append("Recommendations")
    lines.append("-" * 40)
    health = (startup.get("inference_health") or {})
    if health.get("using_cpu_despite_gpu") or health.get("missing_gpu_provider"):
        lines.append("- Repair GPU runtime before tuning capture settings.")
    top_bottleneck = bottlenecks.most_common(1)[0][0] if bottlenecks else ""
    if top_bottleneck == "emulator_bound":
        lines.append("- Lower scrcpy_max_width/bitrate or fix emulator ADB feed.")
    elif top_bottleneck == "inference_bound":
        lines.append("- Use high_ips profile, disable visual_debug, or verify GPU inference.")
    elif top_bottleneck == "debug_view_bound":
        lines.append("- Disable visual_debug / advanced_visuals.")
    elif top_bottleneck == "wall_spike":
        lines.append("- Increase wall_detection interval or enable close tile detector.")
    elif top_bottleneck == "throttled":
        lines.append("- max_ips is limiting throughput; raise or set to 0.")
    elif not lines[-1].startswith("-"):
        lines.append("- No dominant bottleneck detected in this trace.")

    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Analyze Pyla-RL perf_trace JSONL logs.")
    parser.add_argument("path", nargs="?", default="", help="Path to perf_trace JSONL")
    args = parser.parse_args(argv)

    if args.path:
        path = Path(args.path)
    else:
        logs_dir = ROOT / "logs"
        candidates = sorted(logs_dir.glob("perf_trace_*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)
        if not candidates:
            print("No perf_trace JSONL files found in logs/.")
            return 1
        path = candidates[0]
        print(f"Using latest trace: {path}")

    if not path.exists():
        print(f"Trace not found: {path}")
        return 1

    print(analyze(load_trace(path)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
