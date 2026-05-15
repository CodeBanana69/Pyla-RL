from __future__ import annotations

import asyncio
import inspect
import threading
from pathlib import Path
from typing import Any, Callable

import aiohttp

from runtime_control import PAUSED, RUNNING, read_state, write_state
from telegram_notifier import (
    allowed_chat_ids,
    async_send_message,
    async_send_photo,
    drain_aiohttp_transports,
    load_telegram_settings,
    remember_chat_id,
)
from utils import _config_bool


def set_runtime_state(state_path: str | Path, paused: bool) -> str:
    state = PAUSED if paused else RUNNING
    write_state(state_path, state)
    return state


class TelegramControlServer:
    def __init__(
            self,
            state_path: str | Path,
            settings_loader=load_telegram_settings,
            screenshot_provider: Callable[[], Any] | None = None,
            restart_game_callback: Callable[[], Any] | None = None,
            status_provider: Callable[[], dict[str, Any]] | None = None,
    ):
        self.state_path = Path(state_path)
        self.settings_loader = settings_loader
        self.screenshot_provider = screenshot_provider
        self.restart_game_callback = restart_game_callback
        self.status_provider = status_provider
        self.thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.stop_event: asyncio.Event | None = None
        self._offset = 0

    def start(self) -> bool:
        settings = self.settings_loader()
        if not _config_bool(settings.get("enabled"), False):
            return False
        if not _config_bool(settings.get("remote_control_enabled"), False):
            return False
        token = str(settings.get("bot_token") or "").strip()
        if not token:
            print("Telegram control skipped: fill bot_token in cfg/telegram_config.toml first.")
            return False
        if self.thread and self.thread.is_alive():
            return True

        self.thread = threading.Thread(target=self._thread_main, daemon=True)
        self.thread.start()
        return True

    def close(self) -> None:
        loop = self.loop
        stop_event = self.stop_event
        if loop is not None and stop_event is not None and loop.is_running():
            loop.call_soon_threadsafe(stop_event.set)

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:
            print(f"Telegram control stopped: {exc}")

    async def _run(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.stop_event = asyncio.Event()
        print("Telegram control started: /help /status /pause /resume /screenshot /restart_game")
        while not self.stop_event.is_set():
            settings = self.settings_loader()
            token = str(settings.get("bot_token") or "").strip()
            if not token:
                await asyncio.sleep(5)
                continue
            timeout_seconds = max(5, int(settings.get("poll_timeout_seconds", 25) or 25))
            try:
                updates = await self._get_updates(token, timeout_seconds)
                for update in updates:
                    self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
                    await self._handle_update(token, update)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"Telegram control polling error: {exc}")
                await asyncio.sleep(5)

    async def _get_updates(self, token: str, timeout_seconds: int) -> list[dict[str, Any]]:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        params = {
            "timeout": timeout_seconds,
            "offset": self._offset,
            "allowed_updates": '["message"]',
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=timeout_seconds + 10) as response:
                    data = await response.json()
        finally:
            await drain_aiohttp_transports()
        if not data.get("ok"):
            raise RuntimeError(str(data))
        return list(data.get("result") or [])

    async def _handle_update(self, token: str, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = str(message.get("text") or "").strip()
        if not text or chat_id is None:
            return

        command = text.split()[0].split("@", 1)[0].lower()
        remember_chat_id(chat_id)
        chat_id_text = str(chat_id).strip()
        allowed = allowed_chat_ids(self.settings_loader())
        if command in {"/help", "/start"}:
            await async_send_message(chat_id, self._help_text(chat_id_text), token=token)
            return
        if allowed and chat_id_text not in allowed:
            await async_send_message(
                chat_id,
                "This chat is not allowed for this PylaAi-XXZ instance. Add this chat ID in the Telegram tab first.",
                token=token,
            )
            return
        if not allowed:
            await async_send_message(
                chat_id,
                "Remote control is not enabled for any chat yet. Add this chat ID in the Telegram tab first.",
                token=token,
            )
            return

        if command in {"/pause", "/stop"}:
            set_runtime_state(self.state_path, paused=True)
            await async_send_message(chat_id, "PylaAi-XXZ paused.", token=token)
            return
        if command in {"/resume", "/start"}:
            set_runtime_state(self.state_path, paused=False)
            await async_send_message(chat_id, "PylaAi-XXZ resumed.", token=token)
            return
        if command == "/status":
            await async_send_message(chat_id, self._status_text(), token=token)
            return
        if command == "/screenshot":
            await self._send_screenshot(chat_id, token)
            return
        if command in {"/restart_game", "/restart"}:
            await self._restart_game(chat_id, token)
            return

        await async_send_message(chat_id, "Unknown command. Send /help.", token=token)

    def _help_text(self, chat_id: str | None = None) -> str:
        lines = [
            "<b>PylaAi-XXZ Telegram commands</b>",
        ]
        if chat_id:
            lines.append(f"<b>This chat ID:</b> {chat_id}")
        lines.extend([
            "/status - bot status",
            "/pause - pause movement",
            "/resume - resume movement",
            "/screenshot - send current emulator screenshot",
            "/restart_game - restart Brawl Stars and scrcpy",
        ])
        lines.append("")
        lines.append("This chat can be used only after its chat ID is saved in the Telegram tab.")
        return "\n".join(lines)

    def _status_text(self) -> str:
        state = read_state(self.state_path)
        details = self.status_provider() if self.status_provider else {}
        lines = [
            "<b>PylaAi-XXZ status</b>",
            f"<b>Runtime:</b> {'paused' if state == PAUSED else 'running'}",
        ]
        for key in ("state", "ips", "feed_fps", "emulator", "adb_device", "brawler", "target"):
            value = details.get(key)
            if value is not None and value != "":
                lines.append(f"<b>{key.replace('_', ' ').title()}:</b> {value}")
        return "\n".join(lines)

    async def _send_screenshot(self, chat_id: int | str, token: str) -> None:
        if self.screenshot_provider is None:
            await async_send_message(chat_id, "Screenshot is not available in this process.", token=token)
            return
        try:
            screenshot = self.screenshot_provider()
        except Exception as exc:
            await async_send_message(chat_id, f"Could not capture screenshot: {exc}", token=token)
            return
        sent = await async_send_photo(chat_id, screenshot, caption="<b>Current screenshot</b>", token=token)
        if not sent:
            await async_send_message(chat_id, "Could not send screenshot.", token=token)

    async def _restart_game(self, chat_id: int | str, token: str) -> None:
        if self.restart_game_callback is None:
            await async_send_message(chat_id, "Restart callback is not available.", token=token)
            return
        await async_send_message(chat_id, "Restarting Brawl Stars and scrcpy...", token=token)
        try:
            result = self.restart_game_callback()
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            await async_send_message(chat_id, f"Restart failed: {exc}", token=token)
            return
        await async_send_message(
            chat_id,
            "Restart finished." if result else "Restart command ran, but recovery reported a problem.",
            token=token,
        )
