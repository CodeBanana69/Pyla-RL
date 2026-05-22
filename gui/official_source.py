import json
import os
import subprocess
from pathlib import Path

from gui.brand import OFFICIAL_GITHUB

BUILD_INFO_PATH = Path("cfg") / "build_info.json"
ALLOWED_GIT_REMOTES = ("CodeBanana69/Pyla-RL",)


def read_build_info(path=None):
    info_path = Path(path or BUILD_INFO_PATH)
    if not info_path.exists():
        return {}
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _remote_matches_official(remote_url):
    remote = str(remote_url or "").strip().lower()
    if not remote:
        return False
    return any(token.lower() in remote for token in ALLOWED_GIT_REMOTES)


def _build_info_matches_official(build_info):
    repo_url = str(build_info.get("repo_url", "") or "").strip()
    if not repo_url:
        return False
    return _remote_matches_official(repo_url) or repo_url.rstrip("/").lower() == OFFICIAL_GITHUB.lower()


def detect_git_remote():
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return (result.stderr or result.stdout or "").strip()
    return (result.stdout or "").strip()


def detect_git_commit():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def verify_official_source():
    if os.environ.get("PYLA_RL_DEV", "").strip().lower() in {"1", "true", "yes", "on"}:
        commit = detect_git_commit() or read_build_info().get("commit", "unknown")
        return {
            "official": True,
            "reason": "Developer mode (PYLA_RL_DEV)",
            "repo_url": OFFICIAL_GITHUB,
            "commit": str(commit),
        }

    build_info = read_build_info()
    commit = str(build_info.get("commit") or detect_git_commit() or "unknown")
    repo_url = str(build_info.get("repo_url") or OFFICIAL_GITHUB)

    if _build_info_matches_official(build_info):
        return {
            "official": True,
            "reason": "Official build metadata",
            "repo_url": repo_url,
            "commit": commit,
        }

    remote = detect_git_remote()
    if _remote_matches_official(remote):
        return {
            "official": True,
            "reason": "Official git remote",
            "repo_url": OFFICIAL_GITHUB,
            "commit": commit,
        }

    reason = "Could not verify official GitHub or Pyla Discord source."
    if remote:
        reason = f"Unofficial git remote: {remote}"
    elif build_info:
        reason = f"Unofficial build metadata repo_url: {repo_url or 'missing'}"
    return {
        "official": False,
        "reason": reason,
        "repo_url": repo_url,
        "commit": commit,
    }
