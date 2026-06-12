import json
from datetime import datetime, timezone
from pathlib import Path

from utils import resolve_project_path

JOURNAL_PATH = Path(resolve_project_path("logs/matches.jsonl"))


def append_match_record(
        brawler,
        result,
        delta=None,
        mode="showdown",
        session_id=None,
        path=None,
):
    journal_path = Path(path or JOURNAL_PATH)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "brawler": str(brawler or ""),
        "mode": str(mode or "showdown"),
        "result": str(result or ""),
        "delta": delta,
        "session_id": session_id or "",
    }
    with journal_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    return record


def read_recent_matches(limit=50, path=None):
    journal_path = Path(path or JOURNAL_PATH)
    if not journal_path.exists():
        return []
    lines = journal_path.read_text(encoding="utf-8").splitlines()
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


def read_all_matches(path=None):
    journal_path = Path(path or JOURNAL_PATH)
    if not journal_path.exists():
        return []
    records = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def clear_journal(path=None):
    journal_path = Path(path or JOURNAL_PATH)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text("", encoding="utf-8")
