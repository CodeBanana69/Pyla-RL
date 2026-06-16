"""Hub UI translations (English / Russian)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from utils import load_toml_as_dict, resolve_project_path, save_dict_as_toml

_I18N_DIR = Path(__file__).resolve().parent
_SUPPORTED = frozenset({"en", "ru"})
_DEFAULT_LANGUAGE = "en"
_CONFIG_PATH = "cfg/general_config.toml"
_CONFIG_KEY = "ui_language"


def normalize_language(value: Any) -> str:
    text = str(value or _DEFAULT_LANGUAGE).strip().lower()
    if text in _SUPPORTED:
        return text
    if text.startswith("ru"):
        return "ru"
    return _DEFAULT_LANGUAGE


def _load_catalog(lang: str) -> dict[str, str]:
    path = _I18N_DIR / f"{normalize_language(lang)}.json"
    if not path.exists():
        path = _I18N_DIR / f"{_DEFAULT_LANGUAGE}.json"
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return _flatten_catalog(data)


def _flatten_catalog(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(_flatten_catalog(value, full_key))
        else:
            flat[full_key] = str(value)
    return flat


@lru_cache(maxsize=4)
def _catalog(lang: str) -> dict[str, str]:
    return _load_catalog(lang)


def clear_catalog_cache() -> None:
    _catalog.cache_clear()


def get_language() -> str:
    try:
        config = load_toml_as_dict(_CONFIG_PATH)
        return normalize_language(config.get(_CONFIG_KEY, _DEFAULT_LANGUAGE))
    except Exception:
        return _DEFAULT_LANGUAGE


def set_language(lang: str) -> str:
    normalized = normalize_language(lang)
    config = load_toml_as_dict(_CONFIG_PATH)
    config[_CONFIG_KEY] = normalized
    save_dict_as_toml(config, _CONFIG_PATH)
    clear_catalog_cache()
    return normalized


def t(key: str, /, **kwargs: Any) -> str:
    lang = get_language()
    catalog = _catalog(lang)
    fallback = _catalog(_DEFAULT_LANGUAGE)
    template = catalog.get(key) or fallback.get(key) or key
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return template


def qml_strings(lang: str | None = None) -> dict[str, str]:
    code = normalize_language(lang or get_language())
    catalog = dict(_catalog(code))
    if code != _DEFAULT_LANGUAGE:
        catalog = {**_catalog(_DEFAULT_LANGUAGE), **catalog}
    return catalog


def tutorial_doc_path(base_doc: str, lang: str | None = None) -> str:
    doc = str(base_doc or "").replace("\\", "/").strip()
    if not doc:
        return doc
    code = normalize_language(lang or get_language())
    if code == _DEFAULT_LANGUAGE:
        return doc
    if doc.startswith("docs/tutorials/ru/"):
        return doc
    if doc.startswith("docs/tutorials/"):
        localized = doc.replace("docs/tutorials/", "docs/tutorials/ru/", 1)
        resolved = resolve_project_path(localized)
        if Path(resolved).exists():
            return localized
    return doc


def localized_tutorial_topics(lang: str | None = None) -> list[dict[str, str]]:
    from gui.hub_tutorials import TUTORIAL_TOPICS

    code = normalize_language(lang or get_language())
    topics: list[dict[str, str]] = []
    for topic in TUTORIAL_TOPICS:
        topic_id = str(topic.get("id", ""))
        entry = dict(topic)
        entry["title"] = t(f"tutorial.{topic_id}.title")
        entry["summary"] = t(f"tutorial.{topic_id}.summary")
        entry["doc"] = tutorial_doc_path(str(topic.get("doc", "")), code)
        topics.append(entry)
    return topics


def translate_preflight_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    translated: list[dict[str, Any]] = []
    for item in checks:
        entry = dict(item)
        item_id = str(item.get("id", ""))
        label_key = f"preflight.{item_id}.label"
        if label_key in _catalog(get_language()) or label_key in _catalog(_DEFAULT_LANGUAGE):
            entry["label"] = t(label_key)
        detail = str(item.get("detail", "") or "")
        entry["detail"] = _translate_preflight_detail(item_id, detail, bool(item.get("ok")))
        fix = item.get("fix")
        if isinstance(fix, dict):
            fix_entry = dict(fix)
            action = str(fix.get("action", ""))
            fix_label_key = f"preflight.fix.{action}"
            if fix_label_key in _catalog(get_language()) or fix_label_key in _catalog(_DEFAULT_LANGUAGE):
                fix_entry["label"] = t(fix_label_key)
            entry["fix"] = fix_entry
        translated.append(entry)
    return translated


def _translate_preflight_detail(item_id: str, detail: str, ok: bool) -> str:
    if not detail:
        return detail
    lang = get_language()
    if item_id == "game":
        return t("preflight.game.detail_ok" if ok else "preflight.game.detail_fail")
    if item_id == "scaling":
        return t("preflight.scaling.detail_ok" if ok else "preflight.scaling.detail_fail")
    if item_id == "gpu_inference" and ok:
        provider = detail
        prefix = "Inference provider: "
        if detail.startswith(prefix):
            provider = detail[len(prefix):]
        return t("preflight.gpu_inference.detail_ok", provider=provider)
    if item_id == "resolution":
        match = re.match(r"Detected (\d+)x(\d+)(.*)", detail)
        if match:
            suffix = (match.group(3) or "").strip()
            if "half-scale" in suffix:
                return t("preflight.resolution.half_scale", width=match.group(1), height=match.group(2))
            if "720p" in suffix:
                return t("preflight.resolution.720p", width=match.group(1), height=match.group(2))
            if ok:
                return t("preflight.resolution.ok", width=match.group(1), height=match.group(2))
            return t("preflight.resolution.fail", width=match.group(1), height=match.group(2))
        if "1920x1080 recommended" in detail:
            return t("preflight.resolution.recommended")
    if item_id == "emulator" and ok and detail.startswith("Detected "):
        return t("preflight.emulator.detected", emulator=detail.replace("Detected ", "", 1))
    if item_id == "emulator" and not ok and "No " in detail and "process found" in detail:
        emulator = detail.replace("No ", "", 1).replace(" process found", "", 1)
        return t("preflight.emulator.missing", emulator=emulator)
    if item_id == "adb" and detail.startswith("ADB device "):
        return t("preflight.adb.label", serial=detail.replace("ADB device ", "", 1))
    if item_id == "easyocr":
        if ok and detail.startswith("EasyOCR ready (torch "):
            torch_version = detail.replace("EasyOCR ready (torch ", "", 1).rstrip(")")
            return t("preflight.easyocr.detail_ok", torch=torch_version)
        if not ok:
            return t("preflight.easyocr.detail_fail", error=detail)
    return detail
