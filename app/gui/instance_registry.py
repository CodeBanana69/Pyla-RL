from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from gui.instance_config import (
    MANIFEST_DIR,
    compute_instance_readiness,
    get_instance_profile,
    list_instance_profiles,
    load_instance_local_settings,
    normalize_instance_profile,
    queue_brawler_count,
)
from recovery_events import read_recent_events
from runtime_control import process_is_alive
from utils import resolve_project_path


def compute_instance_health(instance_id: str, *, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = manifest or read_manifest(instance_id) or {}
    started_at = float(manifest.get("started_at", 0) or 0)
    uptime_s = max(0.0, time.time() - started_at) if started_at else 0.0
    recovery_count = len(read_recent_events(limit=200))
    recoveries_per_hour = (recovery_count / (uptime_s / 3600.0)) if uptime_s > 3600 else recovery_count
    heartbeat_at = float(manifest.get("heartbeat_at", 0) or 0)
    heartbeat_age = time.time() - heartbeat_at if heartbeat_at else 999.0

    if heartbeat_age > 30 and manifest.get("pid"):
        status = "poor"
        message = "Worker heartbeat is stale."
    elif recoveries_per_hour >= 6:
        status = "poor"
        message = "Frequent recoveries detected."
    elif recoveries_per_hour >= 2 or heartbeat_age > 15:
        status = "degraded"
        message = "Some instability detected."
    else:
        status = "good"
        message = "Healthy."

    return {
        "status": status,
        "message": message,
        "recoveries_per_hour": round(recoveries_per_hour, 2),
        "recent_recoveries": read_recent_events(limit=5),
    }


def manifest_path(instance_id: str) -> Path:
    return Path(resolve_project_path(MANIFEST_DIR)) / f"{instance_id}.json"


def write_manifest(instance_id: str, payload: dict[str, Any]) -> Path:
    path = manifest_path(instance_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temp_path, path)
    return path


def read_manifest(instance_id: str) -> dict[str, Any] | None:
    path = manifest_path(instance_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def remove_manifest(instance_id: str) -> None:
    try:
        manifest_path(instance_id).unlink(missing_ok=True)
    except OSError:
        pass


def build_manifest(
        instance_id: str,
        *,
        pid: int | None = None,
        state_path: str | Path | None = None,
        metrics_path: str | Path | None = None,
        snapshot: dict[str, Any] | None = None,
        status: str = "running",
) -> dict[str, Any]:
    profile = get_instance_profile(instance_id) or normalize_instance_profile(instance_id, {"id": instance_id})
    payload = {
        "instance_id": profile["id"],
        "display_name": profile["name"],
        "pid": int(pid or os.getpid()),
        "started_at": time.time(),
        "state_path": str(state_path or ""),
        "metrics_path": str(metrics_path or ""),
        "emulator": profile["emulator"],
        "emulator_port": profile["emulator_port"],
        "status": status,
        "heartbeat_at": time.time(),
    }
    if snapshot:
        payload.update({
            "runtime_state": snapshot.get("state", ""),
            "brawler": snapshot.get("brawler", ""),
            "target": snapshot.get("target", ""),
            "session_wins": snapshot.get("session_wins", 0),
            "session_losses": snapshot.get("session_losses", 0),
            "session_draws": snapshot.get("session_draws", 0),
            "uptime_s": snapshot.get("uptime_s", 0),
            "queue_preview": snapshot.get("queue_preview", ""),
        })
    return payload


def update_manifest_heartbeat(instance_id: str, snapshot: dict[str, Any], *, state_path, metrics_path) -> None:
    existing = read_manifest(instance_id) or {}
    payload = build_manifest(
        instance_id,
        pid=int(existing.get("pid") or os.getpid()),
        state_path=state_path,
        metrics_path=metrics_path,
        snapshot=snapshot,
        status=str(existing.get("status") or "running"),
    )
    payload["started_at"] = existing.get("started_at", payload["started_at"])
    payload["heartbeat_at"] = time.time()
    write_manifest(instance_id, payload)


def list_live_manifests() -> list[dict[str, Any]]:
    root = Path(resolve_project_path(MANIFEST_DIR))
    if not root.exists():
        return []
    manifests = []
    for path in root.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        pid = int(data.get("pid") or 0)
        if pid and not process_is_alive(pid):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            continue
        manifests.append(data)
    return manifests


def list_instances(*, include_config_only: bool = True) -> list[dict[str, Any]]:
    live_by_id = {item.get("instance_id"): item for item in list_live_manifests() if item.get("instance_id")}
    merged = []
    seen = set()

    for profile in list_instance_profiles():
        instance_id = profile["id"]
        seen.add(instance_id)
        live = live_by_id.get(instance_id)
        readiness = compute_instance_readiness(instance_id)
        local = load_instance_local_settings(instance_id)
        health = compute_instance_health(instance_id, manifest=live)
        merged.append({
            **profile,
            "health": health,
            "running": bool(live),
            "pid": live.get("pid") if live else None,
            "state_path": live.get("state_path", "") if live else "",
            "metrics_path": live.get("metrics_path", "") if live else "",
            "brawler": live.get("brawler", "") if live else "",
            "runtime_state": live.get("runtime_state", "") if live else "",
            "session_wins": live.get("session_wins", 0) if live else 0,
            "session_losses": live.get("session_losses", 0) if live else 0,
            "session_draws": live.get("session_draws", 0) if live else 0,
            "uptime_s": live.get("uptime_s", 0) if live else 0,
            "queue_count": queue_brawler_count(instance_id),
            "readiness": readiness,
            "local_settings": {
                "player_tag": str((local.get("player") or {}).get("tag", "") or profile.get("player_tag", "")),
                "discord_webhook_url": str((local.get("discord") or {}).get("webhook_url", "")),
                "discord_id": str((local.get("discord") or {}).get("discord_id", "")),
                "telegram_notification_chat_id": str((local.get("telegram") or {}).get("notification_chat_id", "")),
            },
        })

    if include_config_only:
        return merged

    for instance_id, live in live_by_id.items():
        if instance_id in seen:
            continue
        merged.append({
            "id": instance_id,
            "name": live.get("display_name", instance_id),
            "running": True,
            **live,
        })
    return merged


def resolve_instance(name_or_id: str | None) -> dict[str, Any] | None:
    needle = str(name_or_id or "").strip().lower()
    if not needle:
        return None
    instances = list_instances()
    for item in instances:
        if item["id"].lower() == needle:
            return item
        if str(item.get("name", "")).lower() == needle:
            return item
    for item in instances:
        if needle in item["id"].lower() or needle in str(item.get("name", "")).lower():
            return item
    return None


def get_default_instance_id(running_only: bool = True) -> str | None:
    from gui.instance_config import load_instances_config

    running = [item for item in list_instances() if item.get("running")]
    if running_only:
        if len(running) == 1:
            return running[0]["id"]
        configured = str(load_instances_config().get("multi_instance", {}).get("default_instance", "")).strip()
        if configured and any(item["id"] == configured for item in running):
            return configured
        return None

    profiles = list_instance_profiles()
    if len(profiles) == 1:
        return profiles[0]["id"]
    configured = str(load_instances_config().get("multi_instance", {}).get("default_instance", "")).strip()
    return configured or None


def require_resolved_instance(name_or_id: str | None) -> tuple[dict[str, Any] | None, str | None]:
    if name_or_id:
        resolved = resolve_instance(name_or_id)
        if not resolved:
            return None, f"Unknown instance '{name_or_id}'."
        if not resolved.get("running"):
            return None, f"Instance '{resolved['id']}' is not running."
        return resolved, None

    default_id = get_default_instance_id(running_only=True)
    if default_id:
        return resolve_instance(default_id), None

    running = [item for item in list_instances() if item.get("running")]
    if not running:
        return None, "No running instances."
    if len(running) == 1:
        return running[0], None

    choices = ", ".join(item["id"] for item in running)
    return None, f"Multiple instances are running. Specify one with the instance option: {choices}"
