"""Translation catalog parity tests.

Manual QA checklist (EN/RU toggle):
- Toggle EN/RU in header pill and Settings; labels refresh without restart.
- Visit each Hub tab; nav labels and panel titles match selected language.
- Run pre-flight checks and API test; status toasts use selected language.
- Complete setup wizard steps; license and step copy translate.
- Open Help topic and Open full guide; Russian opens docs/tutorials/ru/*.md.
- Restart Hub; ui_language persists in cfg/general_config.toml.
"""

from __future__ import annotations

import json
from pathlib import Path


def _flatten(data: dict, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(_flatten(value, full_key))
        else:
            flat[full_key] = str(value)
    return flat


def _load_flat(lang: str) -> dict[str, str]:
    path = Path(__file__).resolve().parents[1] / "gui" / "i18n" / f"{lang}.json"
    with open(path, encoding="utf-8") as handle:
        return _flatten(json.load(handle))


def test_en_ru_key_parity():
    en = _load_flat("en")
    ru = _load_flat("ru")
    missing_in_ru = sorted(set(en) - set(ru))
    missing_in_en = sorted(set(ru) - set(en))
    assert not missing_in_ru, f"Missing in ru.json: {missing_in_ru[:20]}"
    assert not missing_in_en, f"Missing in en.json: {missing_in_en[:20]}"


def test_tutorial_doc_paths_for_ru():
    from gui.i18n import tutorial_doc_path

    docs = [
        "docs/tutorials/getting-started.md",
        "docs/tutorials/overview-and-start.md",
        "docs/tutorials/farm-plan.md",
        "docs/tutorials/multi-instance.md",
        "docs/tutorials/settings-and-performance.md",
        "docs/tutorials/discord.md",
        "docs/tutorials/telegram.md",
        "docs/tutorials/brawl-stars-api.md",
        "docs/tutorials/timers-and-recovery.md",
        "docs/tutorials/match-history.md",
        "docs/tutorials/discord-remote-control.md",
        "docs/tutorials/troubleshooting.md",
    ]
    for doc in docs:
        localized = tutorial_doc_path(doc, "ru")
        assert localized.startswith("docs/tutorials/ru/")
        resolved = Path(__file__).resolve().parents[1] / localized.replace("/", "\\")
        assert resolved.exists(), f"Missing Russian tutorial: {localized}"
