"""English / Russian UI translations for Pyla-RL."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

SUPPORTED_LANGUAGES = ("en", "ru")
_DEFAULT_LANGUAGE = "en"
_CATALOG_DIR = Path(__file__).resolve().parent
_missing_keys_logged: set[str] = set()

_current_language = _DEFAULT_LANGUAGE
_config_loader = None
_cache_invalidator = None


def configure_cache_invalidator(callback) -> None:
    global _cache_invalidator
    _cache_invalidator = callback


def _flatten_mapping(data: Any, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flat.update(_flatten_mapping(value, path))
        return flat
    if isinstance(data, str):
        flat[prefix] = data
    return flat


@lru_cache(maxsize=8)
def _load_catalog(language: str) -> dict[str, str]:
    lang = normalize_language(language)
    path = _CATALOG_DIR / f"{lang}.json"
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload and all(isinstance(value, str) for value in payload.values()):
            return dict(payload)
        return _flatten_mapping(payload)
    from i18n.catalogs import EN_CATALOG, RU_CATALOG

    source = EN_CATALOG if lang == "en" else RU_CATALOG
    if lang == "ru":
        merged = _flatten_mapping(EN_CATALOG)
        merged.update(_flatten_mapping(RU_CATALOG))
        return merged
    return _flatten_mapping(source)


def normalize_language(value: str | None) -> str:
    lang = str(value or _DEFAULT_LANGUAGE).strip().lower()
    if lang in {"ru", "rus", "russian", "русский"}:
        return "ru"
    return "en"


def supported_languages() -> tuple[str, ...]:
    return SUPPORTED_LANGUAGES


def configure_config_loader(loader) -> None:
    """Optional callback returning ui_language from general_config.toml."""
    global _config_loader
    _config_loader = loader
    get_language.cache_clear()


@lru_cache(maxsize=1)
def get_language() -> str:
    if _config_loader is not None:
        try:
            return normalize_language(_config_loader())
        except Exception:
            pass
    return _current_language


def set_language(language: str, *, persist: bool = True) -> str:
    global _current_language
    lang = normalize_language(language)
    _current_language = lang
    get_language.cache_clear()
    if persist:
        from utils import load_toml_as_dict, save_dict_as_toml

        config = load_toml_as_dict("cfg/general_config.toml")
        config["ui_language"] = lang
        config["ui_language_selected"] = "yes"
        save_dict_as_toml(config, "cfg/general_config.toml")
    if _cache_invalidator is not None:
        try:
            _cache_invalidator()
        except Exception:
            pass
    return lang


def reload_language_from_config() -> str:
    get_language.cache_clear()
    return get_language()


def configure_from_general_config() -> str:
    """Load ui_language from cfg/general_config.toml on each get_language() call."""

    def _loader():
        from utils import load_toml_as_dict

        return load_toml_as_dict("cfg/general_config.toml").get("ui_language", _DEFAULT_LANGUAGE)

    configure_config_loader(_loader)
    return reload_language_from_config()


def catalog_for_language(language: str | None = None) -> dict[str, str]:
    lang = normalize_language(language or get_language())
    catalog = dict(_load_catalog(_DEFAULT_LANGUAGE))
    if lang != _DEFAULT_LANGUAGE:
        catalog.update(_load_catalog(lang))
    return catalog


def translate(key: str, /, *, default: str = "", language: str | None = None, **params: Any) -> str:
    lang = normalize_language(language or get_language())
    catalogs = (_load_catalog(lang), _load_catalog(_DEFAULT_LANGUAGE))
    text = ""
    for catalog in catalogs:
        text = catalog.get(key, "")
        if text:
            break
    if not text:
        if default:
            text = default
        elif key not in _missing_keys_logged:
            _missing_keys_logged.add(key)
            text = key
    for name, value in params.items():
        text = text.replace("{" + str(name) + "}", str(value))
    return text


def t(key: str, /, **params: Any) -> str:
    return translate(key, **params)


def tutorial_doc_path(relative_doc: str, language: str | None = None) -> str:
    rel = str(relative_doc or "").replace("\\", "/").lstrip("/")
    if normalize_language(language or get_language()) != "ru":
        return rel
    if rel.startswith("docs/tutorials/ru/"):
        return rel
    if rel.startswith("docs/tutorials/"):
        candidate = rel.replace("docs/tutorials/", "docs/tutorials/ru/", 1)
        resolved = Path(__file__).resolve().parents[1] / candidate
        if resolved.exists():
            return candidate
    return rel
