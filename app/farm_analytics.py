from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from match_journal import read_all_matches


def _parse_record_ts(record: dict[str, Any]) -> float:
    raw = record.get("ts", 0)
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw or "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _normalize_result(result: str) -> str:
    return str(result or "").strip().lower()


def _is_win(result: str) -> bool:
    text = _normalize_result(result)
    return text in {"victory", "win", "1st", "2nd", "3rd"} or "win" in text


def brawler_stats(*, since_hours: float = 168.0) -> dict[str, dict[str, Any]]:
    cutoff = time.time() - (since_hours * 3600.0)
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "matches": 0,
        "wins": 0,
        "trophy_delta": 0,
        "first_ts": None,
        "last_ts": None,
    })

    for record in read_all_matches():
        ts = _parse_record_ts(record)
        if ts and ts < cutoff:
            continue
        brawler = str(record.get("brawler", "") or "").strip().lower()
        if not brawler:
            continue
        bucket = buckets[brawler]
        bucket["matches"] += 1
        if _is_win(record.get("result")):
            bucket["wins"] += 1
        try:
            bucket["trophy_delta"] += int(record.get("delta", 0) or 0)
        except (TypeError, ValueError):
            pass
        bucket["first_ts"] = ts if bucket["first_ts"] is None else min(bucket["first_ts"], ts)
        bucket["last_ts"] = ts if bucket["last_ts"] is None else max(bucket["last_ts"], ts)

    stats = {}
    for brawler, bucket in buckets.items():
        matches = int(bucket["matches"] or 0)
        wins = int(bucket["wins"] or 0)
        hours = 0.0
        if bucket["first_ts"] and bucket["last_ts"] and bucket["last_ts"] > bucket["first_ts"]:
            hours = max((bucket["last_ts"] - bucket["first_ts"]) / 3600.0, matches / 60.0)
        trophies_per_hour = (bucket["trophy_delta"] / hours) if hours > 0 else 0.0
        stats[brawler] = {
            "matches": matches,
            "wins": wins,
            "win_rate": (wins / matches) if matches else 0.0,
            "trophy_delta": int(bucket["trophy_delta"] or 0),
            "trophies_per_hour": round(trophies_per_hour, 1),
            "matches_per_hour": round(matches / hours, 2) if hours > 0 else 0.0,
        }
    return stats


def stuck_brawlers(*, threshold: float = 0.4, min_matches: int = 10, since_hours: float = 168.0) -> list[str]:
    stats = brawler_stats(since_hours=since_hours)
    stuck = []
    for brawler, item in stats.items():
        if item["matches"] < min_matches:
            continue
        if item["win_rate"] < threshold:
            stuck.append(brawler)
    return sorted(stuck)


def estimated_time_to_target(queue: list[dict[str, Any]], stats: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    stats = stats or brawler_stats()
    global_rate = 0.0
    rates = [item.get("trophies_per_hour", 0) for item in stats.values() if item.get("trophies_per_hour", 0) > 0]
    if rates:
        global_rate = sum(rates) / len(rates)

    estimates = []
    for row in queue or []:
        brawler = str(row.get("brawler", "") or "").strip().lower()
        current = int(row.get("trophies", 0) or 0)
        target = int(row.get("push_until", 1000) or 1000)
        gap = max(0, target - current)
        rate = float((stats.get(brawler) or {}).get("trophies_per_hour", 0) or global_rate)
        hours = (gap / rate) if rate > 0 else None
        estimates.append({
            "brawler": brawler,
            "gap": gap,
            "trophies_per_hour": rate,
            "estimated_hours": round(hours, 2) if hours is not None else None,
        })
    return estimates


def efficiency_sort_key(row: dict[str, Any], stats: dict[str, dict[str, Any]] | None = None) -> tuple:
    stats = stats or brawler_stats()
    brawler = str(row.get("brawler", "") or "").strip().lower()
    rate = float((stats.get(brawler) or {}).get("trophies_per_hour", 0) or 0)
    trophies = int(row.get("trophies", 0) or 0)
    return (-1 if rate > 0 else 0, -rate, -trophies, brawler)
