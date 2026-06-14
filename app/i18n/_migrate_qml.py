"""Extract static QML strings and append to catalogs + patch PylaHub.qml.

Run from app/:  python -m i18n._migrate_qml
"""
from __future__ import annotations

import re
from pathlib import Path

from i18n.catalogs import EN_CATALOG, RU_CATALOG, _deep_merge, _nest_flat

_QML = Path(__file__).resolve().parents[1] / "gui" / "qml" / "PylaHub.qml"
_CATALOGS = Path(__file__).resolve().parent / "catalogs.py"

# Match text:/label:/title:/hint: with a plain double-quoted string (no interpolation).
_ATTR_RE = re.compile(
    r'\b(text|label|title|hint):\s*"((?:\\.|[^"\\])*)"',
)

_SKIP_SUBSTR = (
    "+", "root.", "hub", "modelData", "theme.", "Math.", "String(",
    "settingsOnly", "hubBrand", "hubState", "hubBridge", "%",
)

_SKIP_EXACT = {
    "", "·", "?", "...", "—", "–", "OK", "API", "IPS", "FPS", "CSV", "JSON",
    "LDPlayer", "MuMu", "Discord", "Telegram", "Pyla-RL", "Pyla", "Brawl Stars",
    "Showdown Trio", "Brawl Ball", "GitHub", "Patreon", "CC BY-NC 4.0",
    "auto", "directml", "amd", "cuda", "openvino", "cpu", "balanced", "low-end",
    "quality", "high-ips", "follow", "hide", "lobby", "play_again",
}


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return slug[:48] or "text"


def _extract_strings(source: str) -> dict[str, str]:
    found: dict[str, str] = {}
    used_slugs: dict[str, int] = {}
    for match in _ATTR_RE.finditer(source):
        text = match.group(2).encode().decode("unicode_escape")
        if len(text) < 2 or text in _SKIP_EXACT:
            continue
        if any(part in text for part in _SKIP_SUBSTR):
            continue
        if text.startswith("root.") or text.startswith("tr("):
            continue
        if text in found.values():
            continue
        base = _slug(text)
        count = used_slugs.get(base, 0)
        used_slugs[base] = count + 1
        key = f"qml.{base}" if count == 0 else f"qml.{base}_{count}"
        found[key] = text
    return found


def _patch_qml(source: str, mapping: dict[str, str]) -> str:
    # longest strings first to avoid partial replacements
    by_text = sorted(mapping.items(), key=lambda item: len(item[1]), reverse=True)

    def replacer(match: re.Match[str]) -> str:
        attr = match.group(1)
        text = match.group(2).encode().decode("unicode_escape")
        for key, original in by_text:
            if text == original:
                return f'{attr}: root.tr("{key}")'
        return match.group(0)

    return _ATTR_RE.sub(replacer, source)


def main() -> None:
    source = _QML.read_text(encoding="utf-8")
    new_keys = _extract_strings(source)
    if not new_keys:
        print("No new strings found.")
        return

    # Filter keys already covered in flattened EN catalog
    from i18n import catalog_for_language

    existing = set(catalog_for_language("en").values())
    filtered = {k: v for k, v in new_keys.items() if v not in existing}
    if not filtered:
        print("All strings already in catalog.")
        return

    print(f"Adding {len(filtered)} QML string keys...")
    _deep_merge(EN_CATALOG, _nest_flat(filtered))
    # Russian: copy English as placeholder (review pass recommended)
    _deep_merge(RU_CATALOG, _nest_flat(filtered))

    patched = _patch_qml(source, filtered)
    _QML.write_text(patched, encoding="utf-8")

    # Regenerate catalogs.py flat sections is manual — run export for json
    from i18n._export_json import main as export_main

    export_main()
    print(f"Patched {_QML.name} and updated en.json / ru.json")


if __name__ == "__main__":
    main()
