from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from gui.instance_config import get_active_instance_id, resolve_project_path
from utils import load_toml_as_dict


SESSION_MAX_AGE_SECONDS = 3600


def session_state_path(instance_id: str | None = None) -> Path:
    instance_id = str(instance_id or get_active_instance_id() or "").strip()
    if not instance_id:
        return Path()
    return Path(resolve_project_path("instances")) / instance_id / "session_state.json"


def write_session_state(
    instance_id: str,
    *,
    brawler: str,
    wins: int,
    started_trophies: int,
    target: int | None = None,
) -> None:
    path = session_state_path(instance_id)
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "saved_at": time.time(),
        "brawler": str(brawler or "").strip().lower(),
        "wins": int(wins or 0),
        "started_trophies": int(started_trophies or 0),
        "target": int(target or 0),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_session_state(instance_id: str | None = None) -> dict[str, Any] | None:
    path = session_state_path(instance_id)
    if not path or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    saved_at = float(data.get("saved_at", 0) or 0)
    if saved_at and time.time() - saved_at > SESSION_MAX_AGE_SECONDS:
        return None
    return data


def clear_session_state(instance_id: str | None = None) -> None:
    path = session_state_path(instance_id)
    if not path:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def apply_session_resume_to_queue(queue: list[dict[str, Any]], instance_id: str | None = None) -> list[dict[str, Any]]:
    state = read_session_state(instance_id)
    if not state or not queue:
        return queue

    brawler = str(state.get("brawler", "") or "").strip().lower()
    if not brawler:
        return queue

    head = dict(queue[0] or {})
    if str(head.get("brawler", "") or "").strip().lower() != brawler:
        return queue

    resumed = dict(head)
    if state.get("wins") not in (None, ""):
        resumed["wins"] = int(state.get("wins", 0) or 0)
    if state.get("started_trophies") not in (None, ""):
        resumed["trophies"] = int(state.get("started_trophies", 0) or 0)
    if state.get("target"):
        resumed["push_until"] = int(state.get("target", resumed.get("push_until", 1000)) or 1000)

    updated = list(queue)
    updated[0] = resumed
    return updated


def snapshot_from_worker(worker) -> dict[str, Any]:
    current = worker.Stage_manager.brawlers_pick_data[0] if worker.Stage_manager.brawlers_pick_data else {}
    return {
        "brawler": str(current.get("brawler", "") or ""),
        "wins": int(current.get("wins", 0) or 0),
        "started_trophies": int(current.get("trophies", 0) or 0),
        "target": int(current.get("push_until", 0) or 0),
    }


def persist_worker_session(worker) -> None:
    if not getattr(worker, "instance_id", ""):
        return
    snap = snapshot_from_worker(worker)
    if not snap.get("brawler"):
        return
    write_session_state(
        worker.instance_id,
        brawler=snap["brawler"],
        wins=snap["wins"],
        started_trophies=snap["started_trophies"],
        target=snap.get("target"),
    )
