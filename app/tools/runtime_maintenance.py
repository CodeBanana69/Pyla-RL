"""Small startup/post-update cleanup for long-running Pyla-RL installs.

The maintenance here is intentionally conservative: remove stale control/update
artifacts, rotate oversized logs, and warn about suspicious leftover processes.
It must never delete user cfg/data, models, or emulator state.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


DEFAULT_MAX_LOG_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_LOG_BACKUPS = 3
DEFAULT_STALE_RUNTIME_SECONDS = 24 * 60 * 60
DEFAULT_STALE_UPDATE_SECONDS = 24 * 60 * 60
DEFAULT_STALE_BACKUP_SECONDS = 7 * 24 * 60 * 60


def _now() -> float:
    return time.time()


def _age_seconds(path: Path) -> float:
    try:
        return max(0.0, _now() - path.stat().st_mtime)
    except OSError:
        return 0.0


def _safe_unlink(path: Path, report: dict, label: str = "removed") -> bool:
    try:
        path.unlink(missing_ok=True)
        report.setdefault(label, []).append(str(path))
        return True
    except OSError as exc:
        report.setdefault("warnings", []).append(f"Could not remove {path}: {exc}")
        return False


def _safe_rmtree(path: Path, report: dict, label: str = "removed") -> bool:
    import shutil

    try:
        shutil.rmtree(path, ignore_errors=False)
        report.setdefault(label, []).append(str(path))
        return True
    except OSError as exc:
        report.setdefault("warnings", []).append(f"Could not remove {path}: {exc}")
        return False


def _process_is_alive(pid: int) -> bool:
    try:
        from runtime_control import process_is_alive

        return bool(process_is_alive(pid))
    except Exception:
        if not pid or pid <= 0:
            return False
        if os.name == "nt":
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                return str(pid) in (result.stdout or "")
            except Exception:
                return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def rotate_large_file(path: Path, *, max_bytes: int = DEFAULT_MAX_LOG_BYTES, backups: int = DEFAULT_MAX_LOG_BACKUPS) -> bool:
    path = Path(path)
    try:
        if not path.is_file() or path.stat().st_size <= max_bytes:
            return False
    except OSError:
        return False

    backups = max(1, int(backups))
    oldest = path.with_name(f"{path.name}.{backups}")
    oldest.unlink(missing_ok=True)
    for index in range(backups - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        if source.exists():
            source.replace(path.with_name(f"{path.name}.{index + 1}"))
    path.replace(path.with_name(f"{path.name}.1"))
    return True


def rotate_large_logs(
    logs_dir: Path,
    *,
    max_bytes: int = DEFAULT_MAX_LOG_BYTES,
    backups: int = DEFAULT_MAX_LOG_BACKUPS,
    report: dict | None = None,
) -> dict:
    report = report if report is not None else {"removed": [], "rotated": [], "warnings": []}
    logs_dir = Path(logs_dir)
    if not logs_dir.is_dir():
        return report
    for pattern in ("*.log", "*.jsonl"):
        for path in logs_dir.glob(pattern):
            try:
                if rotate_large_file(path, max_bytes=max_bytes, backups=backups):
                    report.setdefault("rotated", []).append(str(path))
            except OSError as exc:
                report.setdefault("warnings", []).append(f"Could not rotate {path}: {exc}")
    return report


def cleanup_stale_update_lock(
    lock_path: Path,
    *,
    stale_seconds: float = 10.0,
    report: dict | None = None,
) -> dict:
    report = report if report is not None else {"removed": [], "rotated": [], "warnings": []}
    lock_path = Path(lock_path)
    if not lock_path.is_file():
        return report
    try:
        info = json.loads(lock_path.read_text(encoding="utf-8-sig"))
    except Exception:
        if _age_seconds(lock_path) >= stale_seconds:
            _safe_unlink(lock_path, report)
        return report
    try:
        pid = int((info if isinstance(info, dict) else {}).get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if pid and _process_is_alive(pid):
        return report
    if _age_seconds(lock_path) >= stale_seconds:
        _safe_unlink(lock_path, report)
    return report


def cleanup_stale_runtime_files(
    logs_dir: Path,
    *,
    stale_seconds: float = DEFAULT_STALE_RUNTIME_SECONDS,
    report: dict | None = None,
) -> dict:
    report = report if report is not None else {"removed": [], "rotated": [], "warnings": []}
    logs_dir = Path(logs_dir)
    if not logs_dir.is_dir():
        return report
    patterns = (
        "runtime_metrics_*.json",
        "runtime_metrics_*.json.tmp",
        "runtime_control_*.cmd",
        "runtime_control_*.remote.jsonl",
        "*.log.4",
        "*.jsonl.4",
    )
    for pattern in patterns:
        for path in logs_dir.glob(pattern):
            if path.is_file() and _age_seconds(path) >= stale_seconds:
                _safe_unlink(path, report)
    replies_dir = logs_dir / "instances" / "replies"
    if replies_dir.is_dir():
        for path in replies_dir.glob("*.json"):
            if path.is_file() and _age_seconds(path) >= stale_seconds:
                _safe_unlink(path, report)
    return report


def cleanup_update_artifacts(
    install_root: Path,
    *,
    stale_update_seconds: float = DEFAULT_STALE_UPDATE_SECONDS,
    stale_backup_seconds: float = DEFAULT_STALE_BACKUP_SECONDS,
    report: dict | None = None,
) -> dict:
    report = report if report is not None else {"removed": [], "rotated": [], "warnings": []}
    root = Path(install_root)
    update_artifacts = (
        root / "_pyla_finish_update.cmd",
        root / "updater.exe.new",
        root / "setup.exe.new",
    )
    for path in update_artifacts:
        if path.is_file() and _age_seconds(path) >= stale_update_seconds:
            _safe_unlink(path, report)
    backup_artifacts = (
        root / "updater.exe.old",
        root / "setup.exe.old",
    )
    for path in backup_artifacts:
        if path.is_file() and _age_seconds(path) >= stale_backup_seconds:
            _safe_unlink(path, report)
    return report


def cleanup_stale_update_temp_dirs(
    *,
    temp_root: Path | None = None,
    stale_seconds: float = DEFAULT_STALE_UPDATE_SECONDS,
    report: dict | None = None,
) -> dict:
    report = report if report is not None else {"removed": [], "rotated": [], "warnings": []}
    root = Path(temp_root) if temp_root else Path(tempfile.gettempdir())
    if not root.is_dir():
        return report
    for path in root.glob("pyla_update_*"):
        if path.is_dir() and _age_seconds(path) >= stale_seconds:
            _safe_rmtree(path, report)
    return report


def process_warnings(install_root: Path, *, current_pid: int | None = None) -> list[str]:
    if os.name != "nt":
        return []
    root_text = str(Path(install_root)).lower()
    if not root_text:
        return []
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "Get-CimInstance Win32_Process | "
            "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
        ),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
    except Exception:
        return []
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    processes = data if isinstance(data, list) else [data]
    current_pid = os.getpid() if current_pid is None else int(current_pid)
    pyla_main = []
    update_helpers = []
    media_helpers = []
    for item in processes:
        if not isinstance(item, dict):
            continue
        try:
            pid = int(item.get("ProcessId") or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid == current_pid:
            continue
        name = str(item.get("Name") or "").lower()
        cmd = str(item.get("CommandLine") or "").lower()
        if root_text not in cmd:
            continue
        if "main.py" in cmd:
            pyla_main.append(pid)
        elif "remote_update.py" in cmd:
            update_helpers.append(pid)
        elif name in {"scrcpy.exe", "adb.exe"} or "scrcpy" in cmd:
            media_helpers.append(pid)
    warnings = []
    if pyla_main:
        warnings.append(f"Other Pyla-RL main process(es) still reference this install: {pyla_main}.")
    if len(update_helpers) > 1:
        warnings.append(f"Multiple remote update helper processes detected: {update_helpers}.")
    if len(media_helpers) > 3:
        warnings.append(f"Several scrcpy/adb helper processes reference this install: {media_helpers}.")
    return warnings


def format_report(report: dict) -> str:
    removed = len(report.get("removed") or [])
    rotated = len(report.get("rotated") or [])
    warnings = report.get("warnings") or []
    parts = []
    if removed:
        parts.append(f"removed {removed} stale file(s)")
    if rotated:
        parts.append(f"rotated {rotated} oversized log(s)")
    if warnings:
        parts.append(f"{len(warnings)} warning(s)")
    return ", ".join(parts)


def run_startup_maintenance(install_root: Path | None = None) -> dict:
    root = Path(install_root) if install_root else Path(__file__).resolve().parents[2]
    logs = root / "app" / "logs"
    report = {"removed": [], "rotated": [], "warnings": []}
    logs.mkdir(parents=True, exist_ok=True)
    cleanup_stale_update_lock(logs / "remote_update.lock", report=report)
    rotate_large_logs(logs, report=report)
    cleanup_stale_runtime_files(logs, report=report)
    cleanup_update_artifacts(root, report=report)
    cleanup_stale_update_temp_dirs(report=report)
    report["warnings"].extend(process_warnings(root))
    return report
