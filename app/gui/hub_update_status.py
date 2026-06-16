"""Hub-facing update status based on main-branch SHA markers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tools.updater import (
    UPDATE_INFO_PATH,
    bundle_path,
    install_dir,
    latest_main_sha,
    read_local_update_sha,
    write_local_update_info,
)


def resolve_install_dir() -> Path:
    return install_dir()


def _read_update_info(install_dir: Path) -> dict:
    info_path = bundle_path(install_dir) / UPDATE_INFO_PATH
    if not info_path.is_file():
        info_path = install_dir / UPDATE_INFO_PATH
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


def read_git_head_sha(install_dir: Path) -> str | None:
    install_dir = Path(install_dir)
    if not (install_dir / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(install_dir),
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode != 0:
            return None
        sha = str(result.stdout or "").strip()
        return sha or None
    except Exception:
        return None


def read_effective_local_sha(install_dir: Path) -> tuple[str | None, str]:
    install_dir = Path(install_dir)
    marker_sha = str(read_local_update_sha(install_dir) or "").strip() or None
    git_sha = read_git_head_sha(install_dir)
    if git_sha:
        return git_sha, "git"
    if marker_sha:
        return marker_sha, "marker"
    return None, "none"


def resolve_updater_launcher(install_dir: Path | None = None) -> dict | None:
    root = Path(install_dir) if install_dir else resolve_install_dir()
    exe = root / "updater.exe"
    if exe.is_file():
        return {
            "kind": "exe",
            "label": "updater.exe",
            "path": str(exe),
            "cwd": str(root),
            "argv": [str(exe)],
        }

    cmd_script = root / "update.cmd"
    if cmd_script.is_file():
        return {
            "kind": "cmd",
            "label": "update.cmd",
            "path": str(cmd_script),
            "cwd": str(root),
            "argv": ["cmd", "/c", str(cmd_script)],
        }

    bundle = bundle_path(root)
    if (bundle / "tools" / "updater.py").is_file():
        return {
            "kind": "python",
            "label": "tools.updater",
            "path": str(bundle / "tools" / "updater.py"),
            "cwd": str(root),
            "argv": [sys.executable, "-m", "tools.updater"],
            "pythonpath": str(bundle),
        }

    return None


def launch_updater(install_dir: Path | None = None) -> tuple[bool, str]:
    from gui.i18n import t

    launcher = resolve_updater_launcher(install_dir)
    if launcher is None:
        return False, t("update.no_updater")

    env = os.environ.copy()
    if launcher.get("pythonpath"):
        env["PYTHONPATH"] = launcher["pythonpath"]

    subprocess.Popen(
        launcher["argv"],
        cwd=launcher["cwd"],
        env=env,
        close_fds=True,
    )

    kind = launcher["kind"]
    if kind == "cmd":
        return True, t("msg.updater_launched_cmd")
    if kind == "python":
        return True, t("msg.updater_launched_dev")
    return True, t("msg.updater_launched")


def default_update_status() -> dict:
    return {
        "status": "unknown",
        "localSha": "",
        "remoteSha": "",
        "updatedAt": "",
        "hasUpdater": False,
        "updaterLauncher": "",
        "updateSource": "none",
        "currentVersion": _current_version(),
        "latestReleaseVersion": "",
    }


def check_update_status(install_dir: Path | None = None) -> dict:
    root = Path(install_dir) if install_dir else resolve_install_dir()
    marker_sha = str(read_local_update_sha(root) or "").strip()
    local_sha, update_source = read_effective_local_sha(root)
    local_sha = str(local_sha or "").strip()
    remote_sha = str(latest_main_sha() or "").strip()
    info = _read_update_info(root)
    launcher = resolve_updater_launcher(root)

    if not remote_sha:
        status = "unknown"
    elif not local_sha or local_sha != remote_sha:
        status = "available"
    else:
        status = "current"
        if update_source == "git" and remote_sha and marker_sha != remote_sha:
            try:
                write_local_update_info(root, remote_sha)
            except Exception:
                pass

    return {
        "status": status,
        "localSha": local_sha[:8] if local_sha else "",
        "remoteSha": remote_sha[:8] if remote_sha else "",
        "updatedAt": str(info.get("updated_at") or ""),
        "hasUpdater": launcher is not None,
        "updaterLauncher": str(launcher.get("label", "") if launcher else ""),
        "updateSource": update_source,
        "currentVersion": _current_version(),
        "latestReleaseVersion": _latest_release_version(),
    }
