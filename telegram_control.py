from __future__ import annotations

import asyncio
import inspect
import threading
from pathlib import Path
from typing import Any, Callable

import aiohttp

from discord_control import resolve_brawler_choice
from runtime_control import PAUSED, RUNNING, STOP_REQUESTED, read_state, request_stop, write_state
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


async def run_callback(callback: Callable[..., Any] | None, *args: Any) -> tuple[bool, str]:
    if callback is None:
        return False, "Command is not available in this process."
    try:
        result = callback(*args)
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:
        return False, f"Command failed: {exc}"
    if result is False:
        return False, "Command ran, but recovery reported a problem."
    if isinstance(result, str) and result.strip():
        return True, result.strip()
    return True, "Command finished."


class TelegramControlServer:
    def __init__(
            self,
            state_path: str | Path,
            settings_loader=load_telegram_settings,
            screenshot_provider: Callable[[], Any] | None = None,
            restart_game_callback: Callable[[], Any] | None = None,
            restart_scrcpy_callback: Callable[[], Any] | None = None,
            restart_emulator_callback: Callable[[], Any] | None = None,
            press_key_callback: Callable[[str], Any] | None = None,
            back_callback: Callable[[], Any] | None = None,
            status_provider: Callable[[], dict[str, Any]] | None = None,
            start_push_callback: Callable[[str, int | None], Any] | None = None,
            stop_all_callback: Callable[[], Any] | None = None,
            pause_menu_callback: Callable[[], Any] | None = None,
    ):
        self.state_path = Path(state_path)
        self.settings_loader = settings_loader
        self.screenshot_provider = screenshot_provider
        self.restart_game_callback = restart_game_callback
        self.restart_scrcpy_callback = restart_scrcpy_callback
        self.restart_emulator_callback = restart_emulator_callback
        self.press_key_callback = press_key_callback
        self.back_callback = back_callback
        self.status_provider = status_provider
        self.start_push_callback = start_push_callback
        self.stop_all_callback = stop_all_callback
        self.pause_menu_callback = pause_menu_callback
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
        print(
            "Telegram control started: /help /status /pause /resume /quit /push "
            "/pause_menu /screenshot /restart_game /restart_scrcpy /restart_emulator /back /press"
        )
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

        parts = text.split()
        command = parts[0].split("@", 1)[0].lower()
        remember_chat_id(chat_id)
        chat_id_text = str(chat_id).strip()
        allowed = allowed_chat_ids(self.settings_loader())

        if command in {"/help", "/setup"}:
            await async_send_message(chat_id, self._help_text(chat_id_text), token=token)
            return
        if allowed and chat_id_text not in allowed:
            await async_send_message(
                chat_id,
                "This chat is not allowed for this Pyla-RL instance. Add this chat ID in the Telegram tab first.",
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
            await async_send_message(chat_id, "Pyla-RL paused.", token=token)
            return
        if command == "/resume":
            set_runtime_state(self.state_path, paused=False)
            await async_send_message(chat_id, "Pyla-RL resumed.", token=token)
            return
        if command in {"/quit", "/stop_all"}:
            request_stop(self.state_path)
            ok, message = await run_callback(self.stop_all_callback)
            await async_send_message(chat_id, message if ok else f"Stop failed: {message}", token=token)
            return
        if command == "/status":
            await async_send_message(chat_id, self._status_text(), token=token)
            return
        if command == "/queue":
            from gui.brawler_queue import load_queue

            queue = load_queue()
            if not queue:
                await async_send_message(chat_id, "Farm plan is empty.", token=token)
                return
            lines = ["<b>Farm plan</b>"]
            for index, row in enumerate(queue[:10], start=1):
                if not isinstance(row, dict):
                    continue
                lines.append(
                    f"{index}. {row.get('brawler', '?')} -> {row.get('push_until', row.get('wins', '?'))}"
                )
            await async_send_message(chat_id, "\n".join(lines), token=token)
            return
        if command == "/screenshot":
            await self._send_screenshot(chat_id, token)
            return
        if command in {"/restart_game", "/restart"}:
            await self._run_named_action(chat_id, token, self.restart_game_callback, "Brawl Stars restart")
            return
        if command == "/restart_scrcpy":
            await self._run_named_action(chat_id, token, self.restart_scrcpy_callback, "Scrcpy restart")
            return
        if command == "/restart_emulator":
            await self._run_named_action(chat_id, token, self.restart_emulator_callback, "Emulator restart")
            return
        if command == "/back":
            ok, message = await run_callback(self.back_callback)
            await async_send_message(chat_id, "Pressed Back." if ok else message, token=token)
            return
        if command == "/press":
            if len(parts) < 2:
                await async_send_message(chat_id, "Usage: /press q|e|f|g|h|m|back", token=token)
                return
            normalized = parts[1].strip().lower()
            ok, message = await run_callback(self.press_key_callback, normalized)
            await async_send_message(chat_id, f"Pressed {normalized}." if ok else message, token=token)
            return
        if command == "/push":
            if len(parts) < 2:
                await async_send_message(chat_id, "Usage: /push brawler [target]", token=token)
                return
            brawler = parts[1]
            target = int(parts[2]) if len(parts) > 2 else None
            resolved = resolve_brawler_choice(brawler)
            if not resolved:
                await async_send_message(chat_id, f"Unknown brawler '{brawler}'.", token=token)
                return
            ok, message = await run_callback(self.start_push_callback, resolved, target)
            await async_send_message(chat_id, message if ok else f"Push failed: {message}", token=token)
            return
        if command == "/pause_menu":
            ok, message = await run_callback(self.pause_menu_callback)
            await async_send_message(
                chat_id,
                "Pause menu reopened." if ok else f"Could not reopen pause menu: {message}",
                token=token,
            )
            return

        await async_send_message(chat_id, "Unknown command. Send /help.", token=token)

    async def _run_named_action(self, chat_id, token, callback, label):
        await async_send_message(chat_id, f"{label} started...", token=token)
        ok, message = await run_callback(callback)
        await async_send_message(chat_id, message if ok else f"{label} failed: {message}", token=token)

    def _help_text(self, chat_id: str | None = None) -> str:
        lines = ["<b>Pyla-RL Telegram commands</b>"]
        if chat_id:
            lines.append(f"<b>This chat ID:</b> {chat_id}")
        lines.extend([
            "/status - bot status",
            "/pause - pause movement",
            "/resume - resume movement",
            "/quit - stop the bot process",
            "/queue - show next brawlers in farm plan",
            "/pause_menu - reopen local pause window",
            "/screenshot - send current emulator screenshot",
            "/restart_game - restart Brawl Stars and scrcpy",
            "/restart_scrcpy - restart scrcpy feed",
            "/restart_emulator - restart emulator profile",
            "/back - press Android Back",
            "/press q|e|f|g|h|m|back - press a game button",
        ])
        lines.append("")
        lines.append("Use /setup to show this list. Save this chat ID in the Telegram tab before control commands work.")
        return "\n".join(lines)

    def _status_text(self) -> str:
        state = read_state(self.state_path)
        if state == STOP_REQUESTED:
            runtime_label = "stopping"
        elif state == PAUSED:
            runtime_label = "paused"
        else:
            runtime_label = "running"
        details = self.status_provider() if self.status_provider else {}
        lines = [
            "<b>Pyla-RL status</b>",
            f"<b>Runtime:</b> {runtime_label}",
        ]
        for key in ("state", "ips", "feed_fps", "emulator", "adb_device", "brawler", "target", "last_match", "queue_preview", "last_recovery"):
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
