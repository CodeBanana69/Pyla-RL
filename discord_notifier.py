from __future__ import annotations

import io
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp
import discord
import numpy as np
from discord import Webhook
from PIL import Image

from gui.remote_formatting import (
    format_brawler_complete_description,
    format_field_value,
    format_match_description,
    format_recovery_description,
    format_result,
)
from utils import _config_bool, load_toml_as_dict


DISCORD_CONFIG_PATH = "cfg/discord_config.toml"
LEGACY_WEBHOOK_CONFIG_PATH = "cfg/webhook_config.toml"

WEBHOOK_URL_RE = re.compile(
    r"^https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/"
    r"(?P<id>[0-9]{17,20})/(?P<token>[A-Za-z0-9._-]{60,})/?$"
)


_match_count = 0
_last_minute_ping = 0.0
_last_error = ""


def normalize_discord_webhook_url(url: Any) -> str:
    cleaned = str(url or "").strip().strip("<>").strip()
    if not cleaned:
        return ""
    parts = urlsplit(cleaned)
    if not parts.scheme or not parts.netloc:
        return cleaned
    host = parts.netloc.lower()
    if host in {"canary.discord.com", "ptb.discord.com", "discordapp.com"}:
        host = "discord.com"
    path = parts.path.rstrip("/")
    return urlunsplit(("https", host, path, "", ""))


def validate_discord_webhook_url(url: Any) -> tuple[bool, str]:
    normalized = normalize_discord_webhook_url(url)
    if not normalized:
        return False, "Discord webhook URL is empty."
    if WEBHOOK_URL_RE.match(normalized):
        return True, normalized
    return False, "Discord webhook URL must look like https://discord.com/api/webhooks/<id>/<token>."


def last_discord_error() -> str:
    return _last_error


EVENT_COLORS = {
    "match": 0xFF9F0A,
    "brawler_complete": 0xFF9F0A,
    "completed": 0x30D158,
    "bot_is_stuck": 0xFF453A,
    "recovery_alert": 0xFF9F0A,
    "test": 0x8E8E93,
}

EVENT_FOOTERS = {
    "match": "Match Report",
    "brawler_complete": "Target Complete",
    "completed": "Queue Complete",
    "bot_is_stuck": "Needs Attention",
    "recovery_alert": "Recovery Alert",
    "test": "Webhook Test",
}


FIELD_LABELS = {
    "brawler": "Brawler",
    "result": "Result",
    "started_trophies": "Started Trophies",
    "trophies": "Current Trophies",
    "trophy_delta": "Trophy Change",
    "total_trophies": "Player Trophies",
    "target": "Target",
    "wins": "Wins",
    "win_streak": "Win Streak",
    "brawlers_left": "Brawlers Left",
    "next_up": "Next Up",
    "queue_preview": "Up Next",
    "ips": "IPS",
    "state": "State",
    "emulator": "Emulator",
    "adb_device": "ADB Device",
    "runtime": "Runtime",
    "source": "Source",
    "event_type": "Event",
    "detail": "Detail",
    "notice": "Notice",
}


RESULT_LABELS = {
    "1st": "1st Place",
    "2nd": "2nd Place",
    "3rd": "3rd Place (Tie)",
    "4th": "4th Place",
    "victory": "Victory",
    "defeat": "Defeat",
    "draw": "Draw",
}


def load_webhook_settings() -> dict[str, Any]:
    general_config = load_toml_as_dict("cfg/general_config.toml")
    config_path = DISCORD_CONFIG_PATH
    if not Path(config_path).exists() and Path(LEGACY_WEBHOOK_CONFIG_PATH).exists():
        config_path = LEGACY_WEBHOOK_CONFIG_PATH
    webhook_config = dict(load_toml_as_dict(config_path))
    webhook_config["webhook_url"] = normalize_discord_webhook_url(
        webhook_config.get("webhook_url") or general_config.get("personal_webhook", "")
    )
    webhook_config["discord_id"] = str(
        webhook_config.get("discord_id") or general_config.get("discord_id", "")
    ).strip().strip("<@!>")
    webhook_config.setdefault("username", "Pyla-RL")
    webhook_config.setdefault("send_match_summary", False)
    webhook_config.setdefault("include_screenshot", True)
    webhook_config.setdefault("ping_when_stuck", False)
    webhook_config.setdefault("ping_when_target_is_reached", False)
    webhook_config.setdefault("ping_every_x_match", 0)
    webhook_config.setdefault("ping_every_x_minutes", 0)
    webhook_config.setdefault("discord_control_enabled", False)
    webhook_config["discord_bot_token"] = str(webhook_config.get("discord_bot_token", "")).strip()
    webhook_config["discord_control_user_id"] = str(
        webhook_config.get("discord_control_user_id") or webhook_config.get("discord_id", "")
    ).strip().strip("<@!>")
    webhook_config["discord_control_channel_id"] = str(webhook_config.get("discord_control_channel_id", "")).strip()
    webhook_config["discord_control_guild_id"] = str(webhook_config.get("discord_control_guild_id", "")).strip()
    return webhook_config


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ping_content(event_type: str, settings: dict[str, Any]) -> str:
    global _match_count, _last_minute_ping
    user_id = settings.get("discord_id", "")
    if not user_id:
        return ""

    should_ping = False
    if event_type == "bot_is_stuck":
        should_ping = _config_bool(settings.get("ping_when_stuck"), False)
    elif event_type in ("completed", "brawler_complete"):
        should_ping = _config_bool(settings.get("ping_when_target_is_reached"), False)

    every_matches = _as_int(settings.get("ping_every_x_match", 0))
    if event_type == "match" and every_matches > 0:
        _match_count += 1
        should_ping = should_ping or (_match_count % every_matches == 0)

    every_minutes = _as_float(settings.get("ping_every_x_minutes", 0))
    if event_type == "regular_minutes_ping" and every_minutes > 0:
        now = time.time()
        if now - _last_minute_ping >= every_minutes * 60:
            _last_minute_ping = now
            should_ping = True

    return f"<@{user_id}>" if should_ping else ""


def _format_result(value: Any) -> str:
    return format_result(value)


def _title_and_description(event_type: str, details: dict[str, Any]) -> tuple[str, str]:
    instance_name = str(details.get("instance_name") or "").strip()
    instance_prefix = f"[{instance_name}] " if instance_name else ""
    if event_type == "match":
        return f"{instance_prefix}Match Report", format_match_description(details)
    if event_type == "brawler_complete":
        return "Target Complete", format_brawler_complete_description(details)
    if event_type == "completed":
        total = details.get("total_trophies")
        session_wins = details.get("session_wins")
        session_losses = details.get("session_losses")
        session_text = ""
        if session_wins not in (None, "") or session_losses not in (None, ""):
            session_text = f" Session: **{session_wins or 0}W / {session_losses or 0}L**."
        if total not in (None, ""):
            return "Queue Complete", f"All queued targets completed. Player trophies: **{format_field_value('total_trophies', total)}**.{session_text}"
        return "Queue Complete", f"All queued targets completed.{session_text}"
    if event_type == "bot_is_stuck":
        reason = str(details.get("reason") or "Pyla-RL could not recover automatically.")
        return "Attention Required", reason
    if event_type == "recovery_alert":
        return "Recovery Alert", format_recovery_description(details)
    if event_type == "test":
        return "Webhook Test", "Connection verified."
    return "Pyla Update", str(details.get("message") or "Bot event received.")


def _format_field_name(key: str) -> str:
    return FIELD_LABELS.get(key, key.replace("_", " ").strip().title())


def _format_field_value(key: str, value: Any) -> str:
    return format_field_value(key, value)


def _add_fields(embed: discord.Embed, details: dict[str, Any]) -> None:
    hidden = {"message", "reason", "event_type"}
    if str(details.get("event_type") or "") == "match":
        hidden.add("brawler")
    ordered_keys = [
        "brawler",
        "result",
        "started_trophies",
        "trophies",
        "trophy_delta",
        "total_trophies",
        "target",
        "wins",
        "win_streak",
        "brawlers_left",
        "next_up",
        "queue_preview",
        "event_type",
        "notice",
        "detail",
        "ips",
        "state",
        "emulator",
        "adb_device",
        "runtime",
        "source",
    ]
    keys = ordered_keys + [key for key in details.keys() if key not in ordered_keys]
    for key in keys:
        if key in hidden or key not in details:
            continue
        value = details.get(key)
        if value is None or value == "":
            continue
        text = _format_field_value(key, value)
        if len(text) > 250:
            text = text[:247] + "..."
        embed.add_field(name=_format_field_name(key), value=text, inline=True)


def _build_embed(event_type: str, details: dict[str, Any]) -> discord.Embed:
    title, description = _title_and_description(event_type, details)
    embed = discord.Embed(
        title=title,
        description=description,
        color=EVENT_COLORS.get(event_type, 0xFF9F0A),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text=f"Pyla • {EVENT_FOOTERS.get(event_type, 'Notification')}")
    _add_fields(embed, details)
    return embed


def _image_to_file(screenshot: Any) -> tuple[discord.File | None, str | None]:
    if screenshot is None:
        return None, None
    if isinstance(screenshot, np.ndarray):
        image = Image.fromarray(screenshot)
    elif isinstance(screenshot, Image.Image):
        image = screenshot
    else:
        return None, None
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="pyla_screenshot.png"), "attachment://pyla_screenshot.png"


async def async_notify_user(
    event_type: str | None = None,
    screenshot: Any = None,
    details: dict[str, Any] | None = None,
) -> bool:
    global _last_error
    _last_error = ""
    settings = load_webhook_settings()
    webhook_url = settings["webhook_url"]
    if not webhook_url:
        _last_error = "No webhook URL configured."
        print("Discord webhook skipped: no webhook URL configured.")
        return False
    valid, message = validate_discord_webhook_url(webhook_url)
    if not valid:
        _last_error = message
        print(f"Discord webhook skipped: {message}")
        return False

    event_type = event_type or "update"
    details = dict(details or {})
    ping = _ping_content(event_type, settings)

    if event_type == "regular_matches_ping":
        return False

    if event_type == "regular_minutes_ping":
        if _as_float(settings.get("ping_every_x_minutes", 0)) <= 0:
            return False

    if event_type == "match" and not (
        _config_bool(settings.get("send_match_summary"), False) or ping
    ):
        return False

    details["event_type"] = event_type
    embed = _build_embed(event_type, details)

    file = None
    if _config_bool(settings.get("include_screenshot"), True):
        file, image_url = _image_to_file(screenshot)
        if image_url:
            embed.set_image(url=image_url)

    send_kwargs = {
        "embed": embed,
        "username": str(settings.get("username") or "Pyla-RL"),
        "allowed_mentions": discord.AllowedMentions(users=True, roles=False, everyone=False),
    }
    if ping:
        send_kwargs["content"] = ping
    if file is not None:
        send_kwargs["file"] = file

    try:
        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(webhook_url, session=session)
            await webhook.send(**send_kwargs)
        print(f"Discord webhook sent: {event_type}")
        return True
    except Exception as exc:
        _last_error = str(exc)
        print(f"Discord webhook failed ({event_type}): {exc}")
        return False


async def async_send_test_notification() -> bool:
    return await async_notify_user(
        "test",
        details={
            "state": "connected",
            "message": "This is a manual test from the Pyla-RL Hub.",
        },
    )
