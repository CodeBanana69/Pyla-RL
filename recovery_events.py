import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

EVENTS_PATH = Path("logs/recovery_events.jsonl")
_recent_alerts = {}


def log_recovery(event_type, detail="", notice="", session_id=None, path=None):
    events_path = Path(path or EVENTS_PATH)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": str(event_type or "unknown"),
        "detail": str(detail or ""),
        "notice": str(notice or ""),
        "session_id": session_id or str(os.getpid()),
    }
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    return record


def read_recent_events(limit=10, path=None):
    events_path = Path(path or EVENTS_PATH)
    if not events_path.exists():
        return []
    lines = events_path.read_text(encoding="utf-8").splitlines()
    records = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    records.reverse()
    return records


def count_session_events(session_id=None, path=None):
    session_id = session_id or str(os.getpid())
    return sum(
        1
        for event in read_recent_events(limit=500, path=path)
        if str(event.get("session_id", "")) == session_id
    )


def count_session_events_by_type(session_id=None, path=None):
    session_id = session_id or str(os.getpid())
    counts = {}
    for event in read_recent_events(limit=500, path=path):
        if str(event.get("session_id", "")) != session_id:
            continue
        event_type = str(event.get("event_type", "unknown"))
        counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def should_send_recovery_alert(
        event_type,
        threshold=3,
        window_seconds=600,
        session_id=None,
):
    session_id = session_id or str(os.getpid())
    now = time.time()
    key = (session_id, str(event_type or "unknown"))
    history = _recent_alerts.setdefault(key, [])
    history[:] = [stamp for stamp in history if now - stamp <= window_seconds]
    history.append(now)
    if len(history) >= max(1, int(threshold or 1)):
        history.clear()
        return True
    return False
