"""Regenerate en.json and ru.json from embedded catalogs. Run: python -m i18n._export_json"""
from __future__ import annotations

import json
from pathlib import Path

from i18n.catalogs import EN_CATALOG, RU_CATALOG

_DIR = Path(__file__).resolve().parent


def main() -> None:
    (_DIR / "en.json").write_text(
        json.dumps(EN_CATALOG, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (_DIR / "ru.json").write_text(
        json.dumps(RU_CATALOG, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote en.json and ru.json ({len(_flatten(EN_CATALOG))} keys)")


def _flatten(data, prefix=""):
    out = {}
    if isinstance(data, dict):
        for k, v in data.items():
            p = f"{prefix}.{k}" if prefix else k
            out.update(_flatten(v, p))
    elif isinstance(data, str):
        out[prefix] = data
    return out


if __name__ == "__main__":
    main()
