"""Detached remote updater used by Discord/Telegram commands.

The running bot cannot safely replace all of its own files and then continue
inside the same Python process. This helper is launched as a separate process:
it asks the bot to stop, waits for it to exit, runs the normal updater, then
starts the bot again in a non-interactive resume mode.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


STOP_REQUESTED = "stop_requested"
DEFAULT_GRACE_TIMEOUT_SECONDS = 120.0
UPDATE_LOCK_STALE_SECONDS = 6 * 60 * 60


def install_root() -> Path:
    return Path(__file__).resolve().parents[2]


def app_root() -> Path:
    return Path(__file__).resolve().parents[1]


def logs_dir() -> Path:
    path = app_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def remote_update_log_path() -> Path:
    return logs_dir() / "remote_update.log"


def update_lock_path() -> Path:
    return logs_dir() / "remote_update.lock"


def log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    try:
        with remote_update_log_path().open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def _timestamp() -> float:
    return time.time()


def _lock_payload(status: str, *, ref: str = "latest", force: bool = False, immediate: bool = False) -> dict:
    now = _timestamp()
    return {
        "pid": os.getpid(),
        "status": str(status or "running"),
        "ref": str(ref or "latest"),
        "force": bool(force),
        "immediate": bool(immediate),
        "created_at": now,
        "updated_at": now,
    }


def read_update_lock(path: str | Path | None = None) -> dict:
    lock_path = Path(path) if path else update_lock_path()
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _lock_pid(info: dict) -> int:
    try:
        return int(info.get("pid") or 0)
    except (TypeError, ValueError):
        return 0


def _lock_age_seconds(info: dict) -> float:
    try:
        updated_at = float(info.get("updated_at") or info.get("created_at") or 0)
    except (TypeError, ValueError):
        return UPDATE_LOCK_STALE_SECONDS + 1
    if updated_at <= 0:
        return UPDATE_LOCK_STALE_SECONDS + 1
    return max(0.0, _timestamp() - updated_at)


def update_lock_is_active(info: dict | None = None) -> bool:
    info = info if info is not None else read_update_lock()
    if not info:
        return False
    pid = _lock_pid(info)
    if pid and process_is_alive(pid):
        return True
    return _lock_age_seconds(info) < 10.0


def describe_update_lock(info: dict | None = None) -> str:
    info = info if info is not None else read_update_lock()
    if not info:
        return "No remote update is running."
    status = str(info.get("status") or "running")
    ref = str(info.get("ref") or "latest")
    pid = _lock_pid(info)
    age = int(_lock_age_seconds(info))
    return f"Remote update is already {status} for {ref} (pid {pid or 'unknown'}, {age}s ago)."


def write_update_lock(status: str, *, ref: str = "latest", force: bool = False, immediate: bool = False) -> dict:
    payload = _lock_payload(status, ref=ref, force=force, immediate=immediate)
    path = update_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def acquire_update_lock(
    *,
    status: str = "pending",
    ref: str = "latest",
    force: bool = False,
    immediate: bool = False,
) -> tuple[bool, dict]:
    path = update_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _lock_payload(status, ref=ref, force=force, immediate=immediate)
    for _attempt in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, json.dumps(payload, indent=2).encode("utf-8"))
            finally:
                os.close(fd)
            return True, payload
        except FileExistsError:
            existing = read_update_lock(path)
            if update_lock_is_active(existing):
                return False, existing
            try:
                path.unlink()
            except OSError:
                return False, existing
    return False, read_update_lock(path)


def release_update_lock(path: str | Path | None = None) -> None:
    lock_path = Path(path) if path else update_lock_path()
    try:
        lock_path.unlink(missing_ok=True)
    except OSError as exc:
        log(f"Could not remove update lock {lock_path}: {exc}")


def _python_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(app_root())
    return env


def _creationflags(*, hidden: bool = True) -> int:
    if os.name != "nt":
        return 0
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if hidden:
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return flags


def _popen_kwargs(*, hidden: bool = True) -> dict:
    kwargs: dict = {
        "cwd": str(install_root()),
        "env": _python_env(),
        "stdin": subprocess.DEVNULL,
    }
    flags = _creationflags(hidden=hidden)
    if flags:
        kwargs["creationflags"] = flags
    return kwargs


def request_stop(state_path: str | Path | None) -> None:
    if not state_path:
        return
    try:
        path = Path(state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(STOP_REQUESTED, encoding="utf-8")
        log(f"Stop requested through {path}")
    except OSError as exc:
        log(f"Could not request stop through {state_path}: {exc}")


def process_is_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        from runtime_control import process_is_alive as _process_is_alive

        return bool(_process_is_alive(pid))
    except Exception:
        if os.name == "nt":
            completed = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            return str(pid) in (completed.stdout or "")
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def wait_for_process_exit(pid: int | None, timeout_seconds: float = DEFAULT_GRACE_TIMEOUT_SECONDS) -> bool:
    if not pid:
        return True
    deadline = time.time() + max(0.0, float(timeout_seconds))
    while time.time() < deadline:
        if not process_is_alive(pid):
            return True
        time.sleep(0.5)
    return not process_is_alive(pid)


def force_kill_process(pid: int | None) -> bool:
    if not pid or not process_is_alive(pid):
        return True
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        log((completed.stdout or completed.stderr or "").strip() or f"taskkill exit={completed.returncode}")
        return completed.returncode == 0 or not process_is_alive(pid)
    try:
        os.kill(pid, 15)
    except OSError as exc:
        log(f"Could not terminate pid {pid}: {exc}")
    return wait_for_process_exit(pid, 15)


def build_updater_command(ref: str = "latest", *, force: bool = False, skip_setup: bool = False) -> list[str]:
    updater = app_root() / "tools" / "updater.py"
    ref = str(ref or "latest").strip()
    command = [sys.executable, str(updater)]
    if ref:
        command.append(ref)
    if force:
        command.append("--force")
    if skip_setup:
        command.append("--skip-setup")
    return command


def run_updater(ref: str = "latest", *, force: bool = False, skip_setup: bool = False) -> int:
    command = build_updater_command(ref, force=force, skip_setup=skip_setup)
    log("Running updater: " + " ".join(command))
    with remote_update_log_path().open("a", encoding="utf-8") as handle:
        handle.write("\n--- updater start ---\n")
        completed = subprocess.run(
            command,
            cwd=str(install_root()),
            env=_python_env(),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        handle.write(f"--- updater exit={completed.returncode} ---\n")
    return int(completed.returncode)


def build_restart_command(mode: str = "single", instance_id: str = "") -> list[str]:
    main_py = app_root() / "main.py"
    mode = str(mode or "single").strip().lower()
    if mode == "instance":
        return [sys.executable, str(main_py), "--instance", str(instance_id or "").strip()]
    return [sys.executable, str(main_py), "--resume"]


def restart_bot(mode: str = "single", instance_id: str = "") -> subprocess.Popen:
    command = build_restart_command(mode, instance_id)
    log("Restarting bot: " + " ".join(command))
    restart_log_path = logs_dir() / "remote_restart.log"
    restart_log = restart_log_path.open("a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command,
            stdout=restart_log,
            stderr=subprocess.STDOUT,
            **_popen_kwargs(hidden=True),
        )
    finally:
        restart_log.close()
    log(f"Restarted bot pid={process.pid}")
    return process


def spawn_remote_update(
    *,
    mode: str = "single",
    instance_id: str = "",
    state_path: str | Path | None = None,
    ref: str = "latest",
    force: bool = False,
    skip_setup: bool = False,
    pid: int | None = None,
    grace_timeout: float = DEFAULT_GRACE_TIMEOUT_SECONDS,
    stop_delay: float = 2.0,
) -> subprocess.Popen:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--mode",
        str(mode or "single"),
        "--pid",
        str(pid or os.getpid()),
        "--ref",
        str(ref or "latest"),
        "--grace-timeout",
        str(float(grace_timeout)),
        "--stop-delay",
        str(float(stop_delay)),
    ]
    if instance_id:
        command.extend(["--instance", str(instance_id)])
    if state_path:
        command.extend(["--state-path", str(state_path)])
    if force:
        command.append("--force")
    if skip_setup:
        command.append("--skip-setup")

    log("Spawning remote update helper: " + " ".join(command))
    return subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **_popen_kwargs(hidden=True),
    )


def run_remote_update(args: argparse.Namespace) -> int:
    write_update_lock("running", ref=args.ref, force=args.force, immediate=True)
    log(
        "Remote update requested "
        f"mode={args.mode} instance={args.instance or '-'} pid={args.pid} ref={args.ref}"
    )
    if args.stop_delay > 0:
        log(f"Waiting {args.stop_delay:.1f}s before requesting stop so remote replies can be sent.")
        time.sleep(args.stop_delay)
    request_stop(args.state_path)
    exited = wait_for_process_exit(args.pid, args.grace_timeout)
    if not exited:
        log(f"Process {args.pid} did not stop within {args.grace_timeout:.0f}s; forcing it down.")
        force_kill_process(args.pid)

    update_exit = 1
    try:
        update_exit = run_updater(args.ref, force=args.force, skip_setup=args.skip_setup)
    except Exception as exc:
        log(f"Updater failed before completion: {exc}")

    try:
        from tools.runtime_maintenance import format_report, run_startup_maintenance

        report = run_startup_maintenance(install_root())
        summary = format_report(report)
        if summary:
            log(f"Post-update cleanup: {summary}.")
    except Exception as exc:
        log(f"Post-update cleanup skipped: {exc}")

    if not args.no_restart:
        try:
            restart_bot(args.mode, args.instance)
        except Exception as exc:
            log(f"Restart failed: {exc}")
            release_update_lock()
            return 1

    release_update_lock()
    return update_exit


def build_version_info() -> dict:
    info = {
        "version": "",
        "commit": "",
        "commitSource": "",
        "builtAt": "",
        "repoUrl": "",
        "python": sys.version.split()[0],
    }
    try:
        from utils import load_toml_as_dict, resolve_project_path

        general = load_toml_as_dict(resolve_project_path("cfg/general_config.toml"))
        info["version"] = str(general.get("pyla_version", "") or "")
    except Exception:
        pass
    try:
        from gui.official_source import read_build_info

        build_info = read_build_info()
        info["builtAt"] = str(build_info.get("built_at") or "")
        info["repoUrl"] = str(build_info.get("repo_url") or "")
        if build_info.get("commit"):
            info["commit"] = str(build_info.get("commit") or "")
            info["commitSource"] = "build_info"
    except Exception:
        pass
    try:
        from gui.hub_update_status import read_effective_local_sha

        sha, source = read_effective_local_sha(install_root())
        if sha:
            info["commit"] = str(sha)
            info["commitSource"] = str(source or info.get("commitSource") or "")
    except Exception:
        pass
    return info


def short_sha(value: str) -> str:
    value = str(value or "").strip()
    return value[:8] if len(value) > 8 else value


def format_version_info(info: dict | None = None) -> str:
    info = dict(info or build_version_info())
    version = info.get("version") or "unknown"
    commit = short_sha(str(info.get("commit") or "")) or "unknown"
    source = str(info.get("commitSource") or "unknown")
    python = str(info.get("python") or sys.version.split()[0])
    lines = [
        f"Pyla-RL version: {version}",
        f"Commit: {commit} ({source})",
        f"Python: {python}",
    ]
    if info.get("builtAt"):
        lines.append(f"Built at: {info['builtAt']}")
    if info.get("repoUrl"):
        lines.append(f"Source: {info['repoUrl']}")
    return "\n".join(lines)


def build_update_status() -> dict:
    from gui.hub_update_status import check_update_status, resolve_install_dir

    return check_update_status(resolve_install_dir())


def format_update_status(status: dict | None = None) -> str:
    status = dict(status or build_update_status())
    state = str(status.get("status") or "unknown")
    current_version = str(status.get("currentVersion") or "unknown")
    latest_version = str(status.get("latestReleaseVersion") or "")
    local_sha = str(status.get("localSha") or "unknown")
    remote_sha = str(status.get("remoteSha") or "unknown")
    launcher = str(status.get("updaterLauncher") or "not found")
    if state == "available":
        headline = "Update available."
    elif state == "current":
        headline = "Pyla-RL is up to date."
    else:
        headline = "Update status is unknown."
    lines = [
        headline,
        f"Current: {current_version} ({local_sha})",
        f"Latest: {latest_version or 'unknown'} ({remote_sha})",
        f"Updater: {launcher}",
    ]
    if status.get("updatedAt"):
        lines.append(f"Last updated: {status['updatedAt']}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pyla-RL remote self-updater")
    parser.add_argument("--mode", choices=("single", "instance"), default="single")
    parser.add_argument("--instance", default="")
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--state-path", default="")
    parser.add_argument("--ref", default="latest")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-setup", action="store_true")
    parser.add_argument("--no-restart", action="store_true")
    parser.add_argument("--grace-timeout", type=float, default=DEFAULT_GRACE_TIMEOUT_SECONDS)
    parser.add_argument("--stop-delay", type=float, default=0.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run_remote_update(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
