from __future__ import annotations

import io
import asyncio
import sys
from pathlib import Path
from typing import Any

import aiohttp
import numpy as np
from PIL import Image

from utils import _config_bool, load_toml_as_dict, resolve_project_path, save_dict_as_toml


TELEGRAM_CONFIG_PATH = "cfg/telegram_config.toml"
LOCAL_TELEGRAM_CONFIG_PATH = "cfg/telegram_config.local.toml"
TELEGRAM_CHATS_PATH = "cfg/telegram_chats.toml"
_WINDOWS_AIOHTTP_CLEANUP_DELAY = 0.25


EVENT_TITLES = {
    "match": "Match finished",
    "brawler_complete": "Brawler target reached",
    "completed": "All targets complete",
    "bot_is_stuck": "Bot needs attention",
    "test": "Telegram test",
}


FIELD_LABELS = {
    "brawler": "Brawler",
    "result": "Result",
    "started_trophies": "Started trophies",
    "trophies": "Current trophies",
    "target": "Target",
    "wins": "Wins",
    "win_streak": "Win streak",
    "brawlers_left": "Brawlers left",
    "ips": "IPS",
    "state": "State",
    "emulator": "Emulator",
    "adb_device": "ADB device",
    "runtime": "Runtime",
}


def _clean_chat_id(value: Any) -> str:
    return str(value or "").strip()


def _as_chat_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [_clean_chat_id(item) for item in value if _clean_chat_id(item)]
    text = _clean_chat_id(value)
    if not text:
        return []
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def load_telegram_settings() -> dict[str, Any]:
    settings = {}
    if Path(resolve_project_path(TELEGRAM_CONFIG_PATH)).exists():
        settings.update(load_toml_as_dict(TELEGRAM_CONFIG_PATH))
    if Path(resolve_project_path(LOCAL_TELEGRAM_CONFIG_PATH)).exists():
        settings.update(load_toml_as_dict(LOCAL_TELEGRAM_CONFIG_PATH))
    settings.setdefault("enabled", False)
    settings["bot_token"] = str(settings.get("bot_token", "")).strip()
    settings["notification_chat_ids"] = _as_chat_ids(settings.get("notification_chat_ids"))
    settings["allowed_chat_ids"] = _as_chat_ids(settings.get("allowed_chat_ids"))
    settings.setdefault("send_match_summary", True)
    settings.setdefault("include_screenshot", True)
    settings.setdefault("allow_multiple_notification_chat_ids", False)
    settings.setdefault("remote_control_enabled", True)
    settings.setdefault("poll_timeout_seconds", 25)
    return settings


def load_known_chat_ids() -> list[str]:
    if not Path(resolve_project_path(TELEGRAM_CHATS_PATH)).exists():
        return []
    chats = load_toml_as_dict(TELEGRAM_CHATS_PATH)
    return _as_chat_ids(chats.get("chat_ids"))


def remember_chat_id(chat_id: int | str | None) -> bool:
    chat_id_text = _clean_chat_id(chat_id)
    if not chat_id_text:
        return False
    chat_ids = load_known_chat_ids()
    if chat_id_text in chat_ids:
        return False
    chat_ids.append(chat_id_text)
    save_dict_as_toml({"chat_ids": chat_ids}, TELEGRAM_CHATS_PATH)
    return True


def notification_chat_ids(settings: dict[str, Any] | None = None) -> list[str]:
    settings = settings or load_telegram_settings()
    ordered = []
    seen = set()
    for chat_id in _as_chat_ids(settings.get("notification_chat_ids")):
        if chat_id in seen:
            continue
        seen.add(chat_id)
        ordered.append(chat_id)
    return ordered


def allowed_chat_ids(settings: dict[str, Any] | None = None) -> list[str]:
    settings = settings or load_telegram_settings()
    explicit = _as_chat_ids(settings.get("allowed_chat_ids"))
    if explicit:
        return explicit
    return _as_chat_ids(settings.get("notification_chat_ids"))


def chat_ids_from_updates(updates: list[dict[str, Any]]) -> list[str]:
    ordered = []
    seen = set()
    for update in updates or []:
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        chat_id = _clean_chat_id(chat.get("id"))
        if not chat_id or chat_id in seen:
            continue
        seen.add(chat_id)
        ordered.append(chat_id)
    return ordered


async def drain_aiohttp_transports() -> None:
    # On Windows, aiohttp SSL/pipe transports can finish cleanup just after the
    # coroutine returns. If the caller closes a short-lived event loop
    # immediately, Python's ProactorEventLoop prints "Event loop is closed".
    if sys.platform.startswith("win"):
        await asyncio.sleep(_WINDOWS_AIOHTTP_CLEANUP_DELAY)


async def async_fetch_recent_chat_ids(token: str | None = None) -> list[str]:
    settings = load_telegram_settings()
    token = str(token or settings.get("bot_token", "")).strip()
    if not token:
        return []
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"timeout": 1, "allowed_updates": '["message"]'}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as response:
                data = await response.json()
    finally:
        await drain_aiohttp_transports()
    if not data.get("ok"):
        raise RuntimeError(str(data))
    return chat_ids_from_updates(list(data.get("result") or []))


def _format_title(event_type: str, details: dict[str, Any]) -> str:
    title = EVENT_TITLES.get(event_type, "PylaAi-XXZ update")
    if event_type == "match":
        result = str(details.get("result") or "finished")
        brawler = str(details.get("brawler") or "").title()
        if brawler:
            return f"{title}: {result} with {brawler}"
        return f"{title}: {result}"
    return title


def _format_message(event_type: str, details: dict[str, Any]) -> str:
    lines = [f"<b>{_format_title(event_type, details)}</b>"]
    message = str(details.get("message") or details.get("reason") or "").strip()
    if message:
        lines.append(message)

    hidden = {"message", "reason", "event_type"}
    ordered = [
        "brawler",
        "result",
        "started_trophies",
        "trophies",
        "target",
        "wins",
        "win_streak",
        "brawlers_left",
        "ips",
        "state",
        "emulator",
        "adb_device",
        "runtime",
    ]
    for key in ordered + [key for key in details if key not in ordered]:
        if key in hidden or key not in details:
            continue
        value = details.get(key)
        if value is None or value == "":
            continue
        text = str(value)
        if len(text) > 180:
            text = text[:177] + "..."
        lines.append(f"<b>{FIELD_LABELS.get(key, key.replace('_', ' ').title())}:</b> {text}")
    return "\n".join(lines)


def _image_to_png_bytes(screenshot: Any) -> bytes | None:
    if screenshot is None:
        return None
    if isinstance(screenshot, np.ndarray):
        image = Image.fromarray(screenshot)
    elif isinstance(screenshot, Image.Image):
        image = screenshot
    else:
        return None
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def async_send_message(chat_id: int | str, text: str, token: str | None = None) -> bool:
    settings = load_telegram_settings()
    token = token or settings.get("bot_token", "")
    if not token:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=15) as response:
                sent = response.status == 200
    except Exception as exc:
        print(f"Telegram message failed: {exc}")
        return False
    finally:
        await drain_aiohttp_transports()
    return sent


async def async_send_photo(chat_id: int | str, screenshot: Any, caption: str = "", token: str | None = None) -> bool:
    settings = load_telegram_settings()
    token = token or settings.get("bot_token", "")
    if not token:
        return False
    png_bytes = _image_to_png_bytes(screenshot)
    if not png_bytes:
        return await async_send_message(chat_id, caption or "No screenshot available.", token=token)
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    data = aiohttp.FormData()
    data.add_field("chat_id", str(chat_id))
    if caption:
        data.add_field("caption", caption[:1024])
        data.add_field("parse_mode", "HTML")
    data.add_field("photo", png_bytes, filename="pyla_screenshot.png", content_type="image/png")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, timeout=30) as response:
                sent = response.status == 200
    except Exception as exc:
        print(f"Telegram photo failed: {exc}")
        return False
    finally:
        await drain_aiohttp_transports()
    return sent


async def async_notify_user(
    event_type: str | None = None,
    screenshot: Any = None,
    details: dict[str, Any] | None = None,
) -> bool:
    settings = load_telegram_settings()
    if not _config_bool(settings.get("enabled"), False):
        return False
    token = settings.get("bot_token", "")
    if not token:
        print("Telegram skipped: no bot token configured.")
        return False
    chat_ids = notification_chat_ids(settings)
    if not chat_ids:
        print("Telegram skipped: no notification_chat_ids configured.")
        return False
    if len(chat_ids) > 1 and not _config_bool(settings.get("allow_multiple_notification_chat_ids"), False):
        print(
            "Telegram skipped: multiple notification_chat_ids are configured. "
            "Remove extra chat IDs or enable allow_multiple_notification_chat_ids only if this is intentional."
        )
        return False

    event_type = event_type or "update"
    details = dict(details or {})
    if event_type == "match" and not _config_bool(settings.get("send_match_summary"), False):
        return False

    text = _format_message(event_type, details)
    include_screenshot = _config_bool(settings.get("include_screenshot"), True)
    sent_any = False
    for chat_id in chat_ids:
        if include_screenshot and screenshot is not None:
            sent = await async_send_photo(chat_id, screenshot, caption=text, token=token)
        else:
            sent = await async_send_message(chat_id, text, token=token)
        sent_any = sent_any or sent
    if sent_any:
        print(f"Telegram notification sent: {event_type}")
    return sent_any


async def async_send_test_notification() -> bool:
    return await async_notify_user(
        "test",
        details={
            "state": "configured",
            "message": "Telegram is connected correctly.",
        },
    )
