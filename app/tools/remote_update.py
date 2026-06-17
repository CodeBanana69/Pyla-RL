"""Detached remote updater used by Discord/Telegram commands.

The running bot cannot safely replace all of its own files and then continue
inside the same Python process. This helper is launched as a separate process:
it asks the bot to stop, waits for it to exit, runs the normal updater, then
starts the bot again in a non-interactive resume mode.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


STOP_REQUESTED = "stop_requested"
DEFAULT_GRACE_TIMEOUT_SECONDS = 120.0


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


def log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    try:
        with remote_update_log_path().open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


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

    if not args.no_restart:
        try:
            restart_bot(args.mode, args.instance)
        except Exception as exc:
            log(f"Restart failed: {exc}")
            return 1

    return update_exit


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
