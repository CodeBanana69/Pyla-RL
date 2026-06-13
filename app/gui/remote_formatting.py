from __future__ import annotations

from typing import Any

from runtime_control import PAUSED, STOP_REQUESTED

RESULT_LABELS = {
    "1st": "1st Place",
    "2nd": "2nd Place",
    "3rd": "3rd Place (Tie)",
    "4th": "4th Place",
    "victory": "Victory",
    "defeat": "Defeat",
    "draw": "Draw",
}

EMBED_COLORS = {
    "running": 0x30D158,
    "paused": 0xFF9F0A,
    "stopping": 0xFF453A,
    "success": 0x30D158,
    "error": 0xFF453A,
    "info": 0x8E8E93,
    "match": 0xFF9F0A,
    "recovery": 0xFF9F0A,
}

STATUS_FIELD_LABELS = {
    "runtime": "Runtime",
    "state": "State",
    "ips": "IPS",
    "feed_fps": "Feed FPS",
    "emulator": "Emulator",
    "adb_device": "ADB Device",
    "brawler": "Brawler",
    "target": "Target",
    "last_match": "Last Match",
    "queue_preview": "Queue",
    "last_recovery": "Last Recovery",
}


def format_result(value: Any) -> str:
    result = str(value or "finished").strip()
    return RESULT_LABELS.get(result.lower(), result)


def format_number(value: Any) -> str:
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value)


def format_trophy_delta(value: Any) -> str:
    try:
        delta = int(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{delta:+d}" if delta else "0"


def format_queue_row_line(row: dict, *, active: bool = False) -> str:
    brawler = str(row.get("brawler", "?") or "?").title()
    row_type = str(row.get("type", "trophies") or "trophies")
    if row_type == "wins":
        current = row.get("wins", 0)
        target = row.get("push_until", row.get("wins", "?"))
    else:
        current = row.get("trophies", 0)
        target = row.get("push_until", "?")
    prefix = "▶ " if active else "  "
    return f"{prefix}{brawler} — {format_number(current)} / {format_number(target)}"


def format_queue_lines(queue, limit: int = 5) -> str:
    if not queue:
        return "Farm plan is empty."
    lines = []
    for index, row in enumerate(queue[:limit]):
        if not isinstance(row, dict):
            continue
        lines.append(format_queue_row_line(row, active=index == 0))
    remaining = len(queue) - limit
    if remaining > 0:
        lines.append(f"  … and {remaining} more")
    return "\n".join(lines)


def format_queue_preview_names(queue, limit: int = 3) -> str:
    if not queue:
        return ""
    names = []
    for row in queue[:limit]:
        if isinstance(row, dict):
            name = str(row.get("brawler", "") or "").title()
            if name:
                names.append(name)
    return ", ".join(names)


def format_status_lines(details: dict[str, Any]) -> list[tuple[str, str]]:
    lines = []
    for key in STATUS_FIELD_LABELS:
        value = details.get(key)
        if value is None or value == "":
            continue
        text = str(value)
        if key == "brawler":
            text = text.title()
        lines.append((STATUS_FIELD_LABELS[key], text))
    return lines


def runtime_label_from_state(state: str) -> str:
    if state == STOP_REQUESTED:
        return "stopping"
    if state == PAUSED:
        return "paused"
    return "running"


def runtime_color_from_state(state: str) -> int:
    label = runtime_label_from_state(state)
    return EMBED_COLORS.get(label, EMBED_COLORS["info"])


def format_command_result(title: str, summary: str, queue=None, *, limit: int = 5) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": title,
        "summary": summary,
        "color": EMBED_COLORS["success"],
    }
    if queue:
        payload["queue_text"] = format_queue_lines(queue, limit=limit)
    return payload


def format_match_description(details: dict[str, Any]) -> str:
    brawler = str(details.get("brawler") or "").title()
    result = format_result(details.get("result"))
    delta = details.get("trophy_delta")
    delta_text = ""
    if delta not in (None, ""):
        try:
            delta_value = int(delta)
        except (TypeError, ValueError):
            delta_value = 0
        if delta_value:
            delta_text = f" ({format_trophy_delta(delta_value)})"
    if brawler:
        return f"**{brawler}** — **{result}**{delta_text}"
    return f"Result: **{result}**{delta_text}"


def format_brawler_complete_description(details: dict[str, Any]) -> str:
    brawler = str(details.get("brawler") or "").title()
    if brawler:
        target = details.get("target")
        suffix = f" at **{format_number(target)}**" if target not in (None, "") else ""
        return f"**{brawler}** reached the target{suffix}."
    return "Configured target reached."


def format_recovery_description(details: dict[str, Any]) -> str:
    notice = str(details.get("notice") or details.get("detail") or "").strip()
    if notice:
        return notice
    return "Pyla-RL triggered a recovery action."


def format_field_value(key: str, value: Any) -> str:
    if key == "result":
        return format_result(value)
    if key == "brawler":
        return str(value).title()
    if key == "trophy_delta":
        return format_trophy_delta(value)
    if key in {"trophies", "started_trophies", "total_trophies", "target", "wins", "win_streak", "brawlers_left", "session_wins", "session_losses", "session_draws"}:
        return format_number(value)
    if key == "state":
        return str(value).replace("_", " ").strip().title()
    if key == "queue_preview":
        return str(value)
    return str(value)


def format_win_rate(wins: int, losses: int, draws: int = 0) -> str:
    total = wins + losses + draws
    if total <= 0:
        return "N/A"
    return f"{(wins / total) * 100:.1f}%"


def format_uptime(seconds: float) -> str:
    total = max(0, int(seconds or 0))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def build_session_stats(snapshot: dict[str, Any]) -> dict[str, Any]:
    wins = int(snapshot.get("session_wins", 0) or 0)
    losses = int(snapshot.get("session_losses", 0) or 0)
    draws = int(snapshot.get("session_draws", 0) or 0)
    matches = wins + losses + draws
    return {
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "matches": matches,
        "win_rate": format_win_rate(wins, losses, draws),
        "uptime": format_uptime(snapshot.get("uptime_s", 0)),
        "brawler": str(snapshot.get("brawler", "") or "").title(),
        "trophies": snapshot.get("trophies", ""),
    }


def format_telegram_stats(stats: dict[str, Any]) -> str:
    lines = [
        "<b>Session stats</b>",
        f"<b>Record:</b> {stats['wins']}W / {stats['losses']}L / {stats['draws']}D",
        f"<b>Win rate:</b> {stats['win_rate']}",
        f"<b>Matches:</b> {stats['matches']}",
        f"<b>Uptime:</b> {stats['uptime']}",
    ]
    if stats.get("brawler"):
        lines.append(f"<b>Active brawler:</b> {stats['brawler']}")
    if stats.get("trophies") not in (None, ""):
        lines.append(f"<b>Trophies:</b> {format_number(stats['trophies'])}")
    return "\n".join(lines)


def format_telegram_help() -> str:
    sections = [
        ("Control", "/status, /stats, /pause, /resume, /quit, /pause_menu"),
        ("Farm Plan", "/push, /skip, /remove, /target, /queue"),
        ("Recovery", "/restart_game, /restart_scrcpy, /restart_emulator"),
        ("Other", "/screenshot, /back, /press"),
    ]
    lines = ["<b>Pyla-RL Telegram commands</b>"]
    for title, commands in sections:
        lines.append(f"<b>{title}</b>")
        lines.append(commands)
        lines.append("")
    lines.append("Use /setup to show this list. Save this chat ID in the Telegram tab before control commands work.")
    return "\n".join(lines).strip()


def format_telegram_status(runtime_state: str, details: dict[str, Any]) -> str:
    runtime_label = runtime_label_from_state(runtime_state)
    lines = [
        "<b>Pyla-RL status</b>",
        f"<b>Runtime:</b> {runtime_label}",
    ]
    for label, value in format_status_lines(details):
        lines.append(f"<b>{label}:</b> {value}")
    return "\n".join(lines)


def format_telegram_queue(queue) -> str:
    return f"<b>Farm plan</b>\n<pre>{format_queue_lines(queue)}</pre>"


def format_telegram_command_result(title: str, summary: str, queue=None) -> str:
    lines = [f"<b>{title}</b>", summary]
    if queue:
        if isinstance(queue, str):
            lines.append(f"<pre>{queue}</pre>")
        else:
            lines.append(f"<pre>{format_queue_lines(queue)}</pre>")
    return "\n".join(lines)
