import json
import os
import time
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent


def metrics_path_for_pid(pid=None):
    pid = os.getpid() if pid is None else pid
    return project_root() / "logs" / f"runtime_metrics_{pid}.json"


def _write_metrics_text(path, text):
    path = Path(path)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    try:
        os.replace(temp_path, path)
        return
    except OSError:
        pass
    try:
        path.write_text(text, encoding="utf-8")
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _normalize_session(session):
    if not isinstance(session, dict):
        return None
    normalized = {}
    try:
        normalized["uptime_s"] = max(0.0, float(session.get("uptime_s", 0.0)))
    except (TypeError, ValueError):
        normalized["uptime_s"] = 0.0
    for key in ("state", "brawler", "target", "notice"):
        value = session.get(key)
        normalized[key] = "" if value is None else str(value)
    try:
        trophies = session.get("trophies")
        normalized["trophies"] = None if trophies in (None, "") else int(trophies)
    except (TypeError, ValueError):
        normalized["trophies"] = None
    for key in ("session_wins", "session_losses"):
        try:
            normalized[key] = max(0, int(session.get(key, 0) or 0))
        except (TypeError, ValueError):
            normalized[key] = 0
    return normalized


def format_uptime(seconds):
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return "--"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def format_session_summary(metrics):
    if not metrics:
        return "PylaAi-XXZ | status unavailable"
    session = metrics.get("session") or {}
    uptime = format_uptime(session.get("uptime_s"))
    brawler = session.get("brawler") or "--"
    target = session.get("target")
    trophies = session.get("trophies")
    if target not in (None, ""):
        progress = f"{brawler} -> {target}"
        if trophies is not None:
            progress = f"{progress} ({trophies})"
    else:
        progress = brawler
    wins = session.get("session_wins", 0)
    losses = session.get("session_losses", 0)
    ips = metrics.get("ips")
    ips_text = f"{ips:.1f}" if isinstance(ips, (int, float)) else "--"
    state = session.get("state") or "--"
    notice = session.get("notice") or "Running"
    return (
        f"PylaAi-XXZ | {uptime} | {progress} | W{wins} L{losses} | "
        f"IPS {ips_text} | {state} | {notice}"
    )


def write_metrics(path, ips, feed_fps, history, max_samples=None, session=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = list(history)
    if max_samples is not None and max_samples > 0:
        samples = samples[-max_samples:]
    payload = {
        "ips": float(ips),
        "feed_fps": float(feed_fps),
        "history": [float(v) for v in samples],
    }
    normalized_session = _normalize_session(session)
    if normalized_session is not None:
        payload["session"] = normalized_session
    text = json.dumps(payload)
    for attempt in range(3):
        try:
            _write_metrics_text(path, text)
            return
        except OSError:
            if attempt == 2:
                return
            time.sleep(0.02 * (attempt + 1))


def read_metrics(path):
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    history = data.get("history")
    if not isinstance(history, list):
        history = []
    try:
        ips = float(data.get("ips", 0.0))
        feed_fps = float(data.get("feed_fps", 0.0))
        history = [float(v) for v in history]
    except (TypeError, ValueError):
        return None
    result = {"ips": ips, "feed_fps": feed_fps, "history": history}
    session = _normalize_session(data.get("session"))
    if session is not None:
        result["session"] = session
    return result


def delete_metrics(path):
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
