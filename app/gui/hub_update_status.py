"""Hub-facing update status based on main-branch SHA markers."""

from __future__ import annotations

import json
from pathlib import Path

from tools.updater import UPDATE_INFO_PATH, bundle_path, latest_main_sha, read_local_update_sha


def _read_update_info(project_dir: Path) -> dict:
    info_path = bundle_path(project_dir) / UPDATE_INFO_PATH
    if not info_path.is_file():
        info_path = project_dir / UPDATE_INFO_PATH
    if not info_path.is_file():
        return {}
    try:
        data = json.loads(info_path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _current_version() -> str:
    try:
        from utils import load_toml_as_dict, resolve_project_path

        return str(load_toml_as_dict(resolve_project_path("cfg/general_config.toml")).get("pyla_version", "") or "")
    except Exception:
        return ""


def _latest_release_version() -> str:
    try:
        from utils import get_latest_version

        return str(get_latest_version() or "")
    except Exception:
        return ""


def default_update_status() -> dict:
    return {
        "status": "unknown",
        "localSha": "",
        "remoteSha": "",
        "updatedAt": "",
        "hasUpdater": False,
        "currentVersion": _current_version(),
        "latestReleaseVersion": "",
    }


def check_update_status(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    local_sha = str(read_local_update_sha(project_dir) or "").strip()
    remote_sha = str(latest_main_sha() or "").strip()
    info = _read_update_info(project_dir)

    if not remote_sha:
        status = "unknown"
    elif not local_sha or local_sha != remote_sha:
        status = "available"
    else:
        status = "current"

    return {
        "status": status,
        "localSha": local_sha[:8] if local_sha else "",
        "remoteSha": remote_sha[:8] if remote_sha else "",
        "updatedAt": str(info.get("updated_at") or ""),
        "hasUpdater": (project_dir / "updater.exe").is_file(),
        "currentVersion": _current_version(),
        "latestReleaseVersion": _latest_release_version(),
    }
