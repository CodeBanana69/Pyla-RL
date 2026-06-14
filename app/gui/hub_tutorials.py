"""Hub tutorial topics for in-app quick guides and linked markdown docs."""

from __future__ import annotations

from pathlib import Path

from i18n import get_language, translate, tutorial_doc_path
from utils import resolve_project_path

TUTORIAL_TOPIC_ORDER = (
    "getting-started",
    "overview",
    "farm-plan",
    "multi-instance",
    "settings",
    "discord",
    "telegram",
    "api",
    "timers",
    "match-history",
    "remote-control",
    "troubleshooting",
)

TUTORIAL_DOCS = {
    "getting-started": "docs/tutorials/getting-started.md",
    "overview": "docs/tutorials/overview-and-start.md",
    "farm-plan": "docs/tutorials/farm-plan.md",
    "multi-instance": "docs/tutorials/multi-instance.md",
    "settings": "docs/tutorials/settings-and-performance.md",
    "discord": "docs/tutorials/discord.md",
    "telegram": "docs/tutorials/telegram.md",
    "api": "docs/tutorials/brawl-stars-api.md",
    "timers": "docs/tutorials/timers-and-recovery.md",
    "match-history": "docs/tutorials/match-history.md",
    "remote-control": "docs/tutorials/discord-remote-control.md",
    "troubleshooting": "docs/tutorials/troubleshooting.md",
}

_CATALOG_TOPIC_IDS = {
    "getting-started": "gettingStarted",
    "overview": "overview",
    "farm-plan": "farmPlan",
    "multi-instance": "multiInstance",
    "settings": "settings",
    "discord": "discord",
    "telegram": "telegram",
    "api": "api",
    "timers": "timers",
    "match-history": "matchHistory",
    "remote-control": "remoteControl",
    "troubleshooting": "troubleshooting",
}

TAB_ID_TO_TOPIC = {
    "Overview": "overview",
    "Instances": "multi-instance",
    "Farm Plan": "farm-plan",
    "Settings": "settings",
    "Discord": "discord",
    "Telegram": "telegram",
    "API": "api",
    "Timers": "timers",
    "Match History": "match-history",
    "Help": "getting-started",
}


def _catalog_id(topic_id: str) -> str:
    return _CATALOG_TOPIC_IDS.get(topic_id, topic_id.replace("-", ""))


def tutorial_topics(lang: str | None = None) -> list[dict[str, str]]:
    language = lang or get_language()
    topics = []
    for topic_id in TUTORIAL_TOPIC_ORDER:
        catalog_id = _catalog_id(topic_id)
        doc = TUTORIAL_DOCS[topic_id]
        topics.append({
            "id": topic_id,
            "title": translate(f"tutorial.{catalog_id}.title", language=language),
            "tab": translate(f"tutorial.{catalog_id}.tab", language=language),
            "summary": translate(f"tutorial.{catalog_id}.summary", language=language),
            "doc": tutorial_doc_path(doc, language=language),
        })
    return topics


def tutorial_topic(topic_id: str, lang: str | None = None) -> dict[str, str] | None:
    topic_id = str(topic_id or "").strip()
    for topic in tutorial_topics(lang):
        if topic["id"] == topic_id:
            return dict(topic)
    return None


def tutorial_topic_for_tab(tab_name: str, lang: str | None = None) -> dict[str, str] | None:
    topic_id = TAB_ID_TO_TOPIC.get(str(tab_name or "").strip())
    return tutorial_topic(topic_id, lang) if topic_id else None


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
