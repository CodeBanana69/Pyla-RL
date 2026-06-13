"""Maintainer-side automatic bug reports to a dedicated Discord support webhook."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import platform
import re
import sys
import threading
import time
import traceback
import weakref
from pathlib import Path
from typing import Any

import aiohttp
import discord
import numpy as np
from discord import Webhook
from PIL import Image

from discord_notifier import normalize_discord_webhook_url, validate_discord_webhook_url
from utils import (
    _config_bool,
    clear_toml_cache,
    load_toml_as_dict,
    resolve_project_path,
    save_dict_as_toml,
)

SUPPORT_REPORTING_LOCAL_PATH = "cfg/support_reporting.local.toml"
SUPPORT_REPORTING_EXAMPLE_PATH = "cfg/support_reporting.example.toml"
_WEBHOOK_ENC_KEY_MATERIAL = "pyla-support-webhook-v1"
DEFAULT_SUPPORT_WEBHOOK_ENC = (
    "ydSXmgSYMTYShEvqkXhMr5U2UfaQQ+pxF2AJAtCu0fOOkdbbQpMoIUTaD7rIOhywwmEN695+9jkIKFwm2YmP0uXFm6AhwSdeO78A/4g/"
    "HrWwFUubgUPPPxJfBjro9dXPkei5iS2UT38f3H/4u01k6p0cC++GZOU4CA=="
)


def _derive_webhook_key() -> bytes:
    return hashlib.sha256(_WEBHOOK_ENC_KEY_MATERIAL.encode("utf-8")).digest()


def encrypt_webhook_url(url: str) -> str:
    key = _derive_webhook_key()
    data = url.encode("utf-8")
    encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.b64encode(encrypted).decode("ascii")


def decrypt_webhook_url(encrypted_b64: str) -> str:
    key = _derive_webhook_key()
    encrypted = base64.b64decode(encrypted_b64.encode("ascii"))
    decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(encrypted))
    return decrypted.decode("utf-8")

SECRET_PATTERNS = [
    re.compile(r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\S+", re.I),
    re.compile(r"\bMT[A-Za-z0-9._-]{20,}\b"),
    re.compile(r"\b[A-Za-z0-9]{32,}\b"),
]

_NO_DEDUPE_TRIGGERS = frozenset({"unhandled_exception", "startup_crash", "thread_exception"})
_recent_fingerprints: dict[str, float] = {}
_runtime_context_ref: weakref.ReferenceType | None = None
_terminal_log_path: str | None = None
_installed = False
_original_excepthook = None
_original_threading_excepthook = None
_send_lock = threading.Lock()


def set_terminal_log_path(path: str | None) -> None:
    global _terminal_log_path
    _terminal_log_path = str(path) if path else None


def set_runtime_context(worker: Any) -> None:
    global _runtime_context_ref
    _runtime_context_ref = weakref.ref(worker) if worker is not None else None


def _get_runtime_context() -> Any | None:
    if _runtime_context_ref is None:
        return None
    return _runtime_context_ref()


def _migrate_plaintext_webhook(settings: dict[str, Any]) -> dict[str, Any]:
    plain = settings.get("webhook_url")
    if not plain:
        return settings
    migrated = dict(settings)
    migrated["webhook_url_encrypted"] = encrypt_webhook_url(str(plain))
    migrated.pop("webhook_url", None)
    save_dict_as_toml(migrated, SUPPORT_REPORTING_LOCAL_PATH)
    clear_toml_cache(SUPPORT_REPORTING_LOCAL_PATH)
    return migrated


def _resolve_webhook_url(settings: dict[str, Any]) -> str:
    encrypted = settings.get("webhook_url_encrypted")
    if encrypted:
        return decrypt_webhook_url(str(encrypted))
    return decrypt_webhook_url(DEFAULT_SUPPORT_WEBHOOK_ENC)


def load_support_settings() -> dict[str, Any]:
    path = resolve_project_path(SUPPORT_REPORTING_LOCAL_PATH)
    settings: dict[str, Any] = {}
    if os.path.exists(path):
        settings = dict(load_toml_as_dict(path))
        if settings.get("webhook_url"):
            settings = _migrate_plaintext_webhook(settings)
    webhook = normalize_discord_webhook_url(_resolve_webhook_url(settings))
    return {
        "enabled": _config_bool(settings.get("enabled"), True),
        "webhook_url": webhook,
        "username": str(settings.get("username") or "Pyla Support"),
        "min_interval_seconds": float(settings.get("min_interval_seconds", 120) or 120),
    }


def ensure_support_reporting_defaults() -> None:
    path = Path(resolve_project_path(SUPPORT_REPORTING_LOCAL_PATH))
    if path.exists():
        return
    example_path = Path(resolve_project_path(SUPPORT_REPORTING_EXAMPLE_PATH))
    if example_path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    import toml

    path.write_text(
        toml.dumps(
            {
                "enabled": True,
                "webhook_url_encrypted": DEFAULT_SUPPORT_WEBHOOK_ENC,
                "username": "Pyla Support",
                "min_interval_seconds": 120,
            }
        ),
        encoding="utf-8",
    )


def sanitize_text(value: Any) -> str:
    text = str(value or "")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in details.items():
        if value is None:
            continue
        if isinstance(value, dict):
            cleaned[key] = sanitize_details(value)
        elif isinstance(value, (list, tuple)):
            cleaned[key] = [
                sanitize_details(item) if isinstance(item, dict) else sanitize_text(item)
                for item in value
            ]
        else:
            cleaned[key] = sanitize_text(value)
    return cleaned


def _fingerprint(trigger: str, message: str, exc: BaseException | None = None) -> str:
    parts = [trigger, message]
    if exc is not None:
        parts.append(type(exc).__name__)
        tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
        if tb:
            parts.append(tb[-1].strip())
    digest = hashlib.sha256("|".join(parts).encode("utf-8", errors="replace")).hexdigest()
    return digest


def _should_send(trigger: str, fingerprint: str, min_interval: float) -> bool:
    if trigger in _NO_DEDUPE_TRIGGERS:
        return True
    now = time.time()
    last = _recent_fingerprints.get(fingerprint)
    if last is not None and now - last < min_interval:
        return False
    _recent_fingerprints[fingerprint] = now
    if len(_recent_fingerprints) > 500:
        cutoff = now - max(min_interval, 60.0)
        stale = [key for key, stamp in _recent_fingerprints.items() if stamp < cutoff]
        for key in stale:
            _recent_fingerprints.pop(key, None)
    return True


def _read_log_tail(max_lines: int = 40) -> str:
    candidates = []
    if _terminal_log_path and os.path.exists(_terminal_log_path):
        candidates.append(Path(_terminal_log_path))
    crash_path = Path(resolve_project_path("logs/startup_crash.log"))
    if crash_path.exists():
        candidates.append(crash_path)
    if not candidates:
        return ""
    try:
        lines = candidates[0].read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except OSError:
        return ""


def _read_recent_recovery(limit: int = 8) -> list[dict[str, Any]]:
    path = Path(resolve_project_path("logs/recovery_events.jsonl"))
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    records = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _build_info() -> dict[str, str]:
    info_path = Path(resolve_project_path("cfg/build_info.json"))
    if not info_path.exists():
        return {}
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def collect_support_context(
    trigger: str,
    message: str,
    *,
    exc: BaseException | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    general_config = load_toml_as_dict("cfg/general_config.toml")
    bot_config = load_toml_as_dict("cfg/bot_config.toml")
    build_info = _build_info()
    worker = _get_runtime_context()

    context: dict[str, Any] = {
        "trigger": trigger,
        "message": message,
        "version": str(general_config.get("pyla_version", "")),
        "commit": str(build_info.get("commit", "")),
        "built_at": str(build_info.get("built_at", "")),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "instance_id": str(os.environ.get("PYLA_INSTANCE_ID", "") or ""),
        "cpu_or_gpu": str(general_config.get("cpu_or_gpu", "")),
        "gamemode": str(bot_config.get("gamemode", "")),
        "emulator": str(general_config.get("current_emulator", "")),
        "playstyle": str(bot_config.get("current_playstyle", "")),
        "recent_recovery": _read_recent_recovery(),
        "log_tail": _read_log_tail(),
    }

    if exc is not None:
        context["traceback"] = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )

    if worker is not None:
        try:
            context["game_state"] = str(worker.get_latest_state())
        except Exception:
            pass
        play = getattr(worker, "Play", None)
        if play is not None:
            context["match_intent"] = str(getattr(play, "match_intent_summary", "") or "")
            context["spacing_action"] = str(getattr(play, "_spacing_action", "") or "")
            context["threat_count"] = int(getattr(play, "_spacing_threat_count", 0) or 0)
            detector = getattr(play, "detector", None)
            if detector is not None:
                context["gpu_provider"] = str(getattr(detector, "device", "") or "")
        stage = getattr(worker, "Stage_manager", None)
        queue = getattr(stage, "brawlers_pick_data", None) if stage is not None else None
        if queue:
            front = dict(queue[0])
            context["queue_front"] = {
                "brawler": front.get("brawler"),
                "trophies": front.get("trophies"),
                "automatically_pick": front.get("automatically_pick"),
                "selection_method": front.get("selection_method"),
            }

    if extra:
        context.update(extra)
    return sanitize_details(context)


def capture_screenshot(worker: Any | None = None) -> Any | None:
    worker = worker or _get_runtime_context()
    if worker is None:
        return None
    window_controller = getattr(worker, "window_controller", None)
    if window_controller is None:
        return None
    try:
        return window_controller.screenshot()
    except Exception:
        return None


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
    return discord.File(buffer, filename="support_screenshot.png"), "attachment://support_screenshot.png"


def _format_field_name(key: str) -> str:
    return key.replace("_", " ").title()


def _truncate(value: str, limit: int = 250) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def build_support_embed(context: dict[str, Any]) -> discord.Embed:
    trigger = str(context.get("trigger", "support_report"))
    message = str(context.get("message", ""))
    embed = discord.Embed(
        title=f"Support Report: {trigger}",
        description=_truncate(message, 1000),
        color=0xED4245,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text="Pyla • Support Reporter")

    priority_keys = [
        "version",
        "commit",
        "game_state",
        "match_intent",
        "queue_front",
        "gpu_provider",
        "cpu_or_gpu",
        "gamemode",
        "emulator",
        "playstyle",
        "spacing_action",
        "threat_count",
        "platform",
        "python",
        "instance_id",
    ]
    for key in priority_keys:
        if key not in context:
            continue
        value = context.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=True, default=str)
        else:
            text = str(value)
        embed.add_field(name=_format_field_name(key), value=_truncate(text), inline=True)

    log_tail = str(context.get("log_tail", "") or "")
    if log_tail:
        embed.add_field(name="Log Tail", value=f"```\n{_truncate(log_tail, 900)}\n```", inline=False)

    tb = str(context.get("traceback", "") or "")
    if tb:
        embed.add_field(name="Traceback", value=f"```\n{_truncate(tb, 900)}\n```", inline=False)
    return embed


async def async_send_support_report(
    trigger: str,
    message: str,
    *,
    exc: BaseException | None = None,
    screenshot: Any = None,
    extra: dict[str, Any] | None = None,
) -> bool:
    settings = load_support_settings()
    if not settings.get("enabled", True):
        return False

    webhook_url = settings.get("webhook_url", "")
    valid, normalized = validate_discord_webhook_url(webhook_url)
    if not valid:
        print(f"Support report skipped: {normalized}")
        return False

    fingerprint = _fingerprint(trigger, message, exc)
    if not _should_send(trigger, fingerprint, float(settings.get("min_interval_seconds", 120))):
        return False

    context = collect_support_context(trigger, message, exc=exc, extra=extra)
    embed = build_support_embed(context)

    screenshot = screenshot if screenshot is not None else capture_screenshot()
    file, image_url = _image_to_file(screenshot)
    if image_url:
        embed.set_image(url=image_url)

    send_kwargs: dict[str, Any] = {
        "embed": embed,
        "username": str(settings.get("username") or "Pyla Support"),
        "allowed_mentions": discord.AllowedMentions.none(),
    }
    tb = str(context.get("traceback", "") or "")
    if file is not None:
        send_kwargs["file"] = file
    elif len(tb) > 900:
        send_kwargs["file"] = discord.File(
            io.BytesIO(tb.encode("utf-8")),
            filename="traceback.txt",
        )

    try:
        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(normalized, session=session)
            await webhook.send(**send_kwargs)
        print(f"Support report sent: {trigger}")
        return True
    except Exception as send_exc:
        print(f"Support report failed ({trigger}): {send_exc}")
        return False


def _dispatch_report(
    trigger: str,
    message: str,
    *,
    exc: BaseException | None = None,
    screenshot: Any = None,
    extra: dict[str, Any] | None = None,
) -> None:
    def _runner():
        try:
            asyncio.run(
                async_send_support_report(
                    trigger,
                    message,
                    exc=exc,
                    screenshot=screenshot,
                    extra=extra,
                )
            )
        except Exception as dispatch_exc:
            print(f"Support report dispatch failed: {dispatch_exc}")

    thread = threading.Thread(target=_runner, daemon=True, name="support-reporter")
    thread.start()


def report_support_event(
    trigger: str,
    message: str,
    *,
    exc: BaseException | None = None,
    screenshot: Any = None,
    extra: dict[str, Any] | None = None,
) -> None:
    if not str(message or "").strip() and exc is None:
        return
    with _send_lock:
        _dispatch_report(trigger, message, exc=exc, screenshot=screenshot, extra=extra)


def _handle_exception(exc_type, exc, tb, *, trigger: str):
    if exc_type is None or exc is None:
        return
    if issubclass(exc_type, KeyboardInterrupt):
        if _original_excepthook:
            _original_excepthook(exc_type, exc, tb)
        return
    message = f"{exc_type.__name__}: {exc}"
    report_support_event(trigger, message, exc=exc)
    if _original_excepthook:
        _original_excepthook(exc_type, exc, tb)


def _excepthook(exc_type, exc, tb):
    _handle_exception(exc_type, exc, tb, trigger="unhandled_exception")


def _threading_excepthook(args):
    _handle_exception(args.exc_type, args.exc_value, args.exc_traceback, trigger="thread_exception")
    if _original_threading_excepthook:
        _original_threading_excepthook(args)


def install() -> None:
    global _installed, _original_excepthook, _original_threading_excepthook
    if _installed:
        return
    ensure_support_reporting_defaults()
    _original_excepthook = sys.excepthook
    _original_threading_excepthook = getattr(threading, "excepthook", None)
    sys.excepthook = _excepthook
    if hasattr(threading, "excepthook"):
        threading.excepthook = _threading_excepthook
    _installed = True
