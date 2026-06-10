"""Hub tutorial topics for in-app quick guides and linked markdown docs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from utils import resolve_project_path


def _topic(
    topic_id: str,
    title: str,
    tab: str,
    summary: str,
    doc: str,
) -> dict[str, str]:
    return {
        "id": topic_id,
        "title": title,
        "tab": tab,
        "summary": summary.strip(),
        "doc": doc.replace("\\", "/"),
    }


TUTORIAL_TOPICS: list[dict[str, str]] = [
    _topic(
        "getting-started",
        "Getting Started",
        "Help",
        "1. Run setup.exe in the project folder.\n"
        "2. Launch pyla-rl.bat (or python main.py).\n"
        "3. Set emulator resolution to 1920x1080.\n"
        "4. Open Brawl Stars in the emulator before START.",
        "docs/tutorials/getting-started.md",
    ),
    _topic(
        "overview",
        "Overview and START",
        "Overview",
        "1. Pick LDPlayer or MuMu, then Run Checks.\n"
        "2. Fix required ADB failures before START.\n"
        "3. Choose Showdown Trio mode and a performance profile.\n"
        "4. Press START (single-instance) or use Instances tab (multi-instance).",
        "docs/tutorials/overview-and-start.md",
    ),
    _topic(
        "farm-plan",
        "Farm Plan",
        "Farm Plan",
        "1. Add brawlers or use Build Queue (Push All).\n"
        "2. Drag rows to reorder; first brawler is active.\n"
        "3. Import/Export JSON for backup.\n"
        "4. Leave empty to use the legacy picker after START.",
        "docs/tutorials/farm-plan.md",
    ),
    _topic(
        "multi-instance",
        "Multi-Instance",
        "Instances",
        "1. Enable Multi-Instance on the Instances tab.\n"
        "2. Add instances with unique emulator ports.\n"
        "3. Put each farm plan in instances/<id>/latest_brawler_data.json.\n"
        "4. Start each worker from Instances (not Overview START).",
        "docs/tutorials/multi-instance.md",
    ),
    _topic(
        "settings",
        "Settings and Performance",
        "Settings",
        "1. Accept the free-use license in About.\n"
        "2. Tune performance profile and debug options.\n"
        "3. Spacing Aggression purple circle = target hug distance in Debug Screen.\n"
        "4. After Round controls lobby return vs Play Again on wins.",
        "docs/tutorials/settings-and-performance.md",
    ),
    _topic(
        "discord",
        "Discord Notifications",
        "Discord",
        "1. Webhook URL + Send Match Summary posts a report after each game.\n"
        "2. Ping Every X Matches mentions you on match summaries (optional).\n"
        "3. Heartbeat Every X Minutes is optional; leave at 0 to avoid status spam.\n"
        "4. Remote slash commands need a bot token (separate from webhooks).",
        "docs/tutorials/discord.md",
    ),
    _topic(
        "telegram",
        "Telegram Control",
        "Telegram",
        "1. Create a bot with @BotFather and paste the token.\n"
        "2. Send /setup to the bot once to register your chat.\n"
        "3. Use /status, /pause, /push, and other commands remotely.\n"
        "4. Keep notification chat IDs private.",
        "docs/tutorials/telegram.md",
    ),
    _topic(
        "api",
        "Brawl Stars API",
        "API",
        "1. Create a developer account at developer.brawlstars.com.\n"
        "2. Fill player tag and credentials in the API tab.\n"
        "3. Enables trophy autofill and Push All queue building.\n"
        "4. Never commit filled API tokens to GitHub.",
        "docs/tutorials/brawl-stars-api.md",
    ),
    _topic(
        "timers",
        "Timers and Recovery",
        "Timers",
        "1. Low IPS recovery restarts scrcpy, game, or emulator.\n"
        "2. Adjust thresholds if recovery triggers too often.\n"
        "3. Emulator restart cooldown prevents rapid loops.\n"
        "4. Check Recovery Log on Overview for recent events.",
        "docs/tutorials/timers-and-recovery.md",
    ),
    _topic(
        "match-history",
        "Match History",
        "Match History",
        "1. Review recent matches and session summary.\n"
        "2. Sort by games or other columns.\n"
        "3. Reset history from the tab if needed.\n"
        "4. Discord /stats mirrors live session stats.",
        "docs/tutorials/match-history.md",
    ),
    _topic(
        "remote-control",
        "Remote Commands",
        "Help",
        "Discord: /pause, /start, /status, /queue, /push, /skip, /remove, /target, /screenshot.\n"
        "Telegram: /pause, /resume, /status, /queue, /push, /skip, /remove, /target, /screenshot.\n"
        "Multi-instance: add instance:ld-2 (Discord) or a third argument (Telegram).",
        "docs/tutorials/discord-remote-control.md",
    ),
    _topic(
        "troubleshooting",
        "Troubleshooting",
        "Help",
        "1. Run Checks on Overview for ADB/emulator issues.\n"
        "2. Run python tools/performance_check.py for IPS/GPU.\n"
        "3. Dual ADB devices: reconnect emulator ADB debugging.\n"
        "4. Read logs/recovery_events.jsonl for auto-recovery details.",
        "docs/tutorials/troubleshooting.md",
    ),
]

TOPIC_BY_ID: dict[str, dict[str, str]] = {topic["id"]: topic for topic in TUTORIAL_TOPICS}
TOPIC_BY_TAB: dict[str, str] = {}
for _item in TUTORIAL_TOPICS:
    tab = _item.get("tab", "")
    if tab and tab not in TOPIC_BY_TAB:
        TOPIC_BY_TAB[tab] = _item["id"]


def tutorial_topics() -> list[dict[str, str]]:
    return [dict(topic) for topic in TUTORIAL_TOPICS]


def tutorial_topic(topic_id: str) -> dict[str, str] | None:
    item = TOPIC_BY_ID.get(str(topic_id or "").strip())
    return dict(item) if item else None


def tutorial_topic_for_tab(tab_name: str) -> dict[str, str] | None:
    topic_id = TOPIC_BY_TAB.get(str(tab_name or "").strip())
    return tutorial_topic(topic_id) if topic_id else None


def resolve_tutorial_doc_path(doc_path: str) -> Path:
    return Path(resolve_project_path(doc_path))


def tutorial_doc_exists(doc_path: str) -> bool:
    return resolve_tutorial_doc_path(doc_path).exists()


def open_tutorial_doc(doc_path: str) -> str:
    path = resolve_tutorial_doc_path(doc_path)
    if not path.exists():
        raise FileNotFoundError(f"Tutorial doc not found: {path}")
    import os
    import webbrowser

    uri = path.resolve().as_uri()
    opened = webbrowser.open(uri)
    if not opened:
        os.startfile(str(path.resolve()))
    return str(path.resolve())
