from __future__ import annotations

import asyncio
import inspect
import threading
from pathlib import Path
from typing import Any, Callable

import discord
from discord import app_commands

from runtime_control import PAUSED, RUNNING, STOP_REQUESTED, read_state, request_stop, write_state
from utils import _config_bool, load_brawlers_info, normalize_brawler_name, resolve_brawler_name_alias
from discord_notifier import _image_to_file, load_webhook_settings


def _clean_id(value: Any) -> str:
    return str(value or "").strip().strip("<@!>")


def _ids_match(configured: str, actual: int | str | None) -> bool:
    configured = _clean_id(configured)
    if not configured:
        return True
    return configured == str(actual or "").strip()


def command_allowed(settings: dict[str, Any], user_id: int | str, channel_id: int | str | None, guild_id: int | str | None) -> bool:
    allowed_user = _clean_id(settings.get("discord_control_user_id") or settings.get("discord_id"))
    allowed_channel = _clean_id(settings.get("discord_control_channel_id"))
    allowed_guild = _clean_id(settings.get("discord_control_guild_id"))
    return (
        _ids_match(allowed_user, user_id)
        and _ids_match(allowed_channel, channel_id)
        and _ids_match(allowed_guild, guild_id)
    )


def set_runtime_state(state_path: str | Path, paused: bool) -> str:
    state = PAUSED if paused else RUNNING
    write_state(state_path, state)
    return state


def resolve_brawler_choice(name: str) -> str | None:
    raw = str(name or "").strip()
    if not raw:
        return None
    brawlers_info = load_brawlers_info()
    if not brawlers_info:
        return raw.lower()

    normalized_input = resolve_brawler_name_alias(raw)
    for brawler_key in brawlers_info.keys():
        if normalize_brawler_name(brawler_key) == normalized_input:
            return brawler_key
    if normalized_input in brawlers_info:
        return normalized_input
    return None


def status_text(state_path: str | Path, status_provider: Callable[[], dict[str, Any]] | None = None) -> str:
    state = read_state(state_path)
    try:
        details = status_provider() if status_provider else {}
    except Exception as exc:
        details = {"status_error": exc}
    if state == STOP_REQUESTED:
        runtime_label = "stopping"
    elif state == PAUSED:
        runtime_label = "paused"
    else:
        runtime_label = "running"
    lines = [
        "PylaAi-XXZ status",
        f"Runtime: {runtime_label}",
    ]
    for key in ("state", "ips", "feed_fps", "emulator", "adb_device", "brawler", "target"):
        value = details.get(key)
        if value is not None and value != "":
            lines.append(f"{key.replace('_', ' ').title()}: {value}")
    if details.get("status_error"):
        lines.append(f"Status Error: {details['status_error']}")
    return "\n".join(lines)


async def run_callback(callback: Callable[..., Any] | None, *args: Any) -> tuple[bool, str]:
    if callback is None:
        return False, "This command is not available in this process."
    try:
        if inspect.iscoroutinefunction(callback):
            result = await callback(*args)
        else:
            result = await asyncio.to_thread(callback, *args)
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:
        return False, f"Command failed: {exc}"
    if result is False:
        return False, "Command ran, but recovery reported a problem."
    if isinstance(result, str) and result.strip():
        return True, result.strip()
    return True, "Command finished."


class DiscordControlServer:
    def __init__(
            self,
            state_path: str | Path,
            settings_loader=load_webhook_settings,
            screenshot_provider: Callable[[], Any] | None = None,
            restart_game_callback: Callable[[], Any] | None = None,
            restart_scrcpy_callback: Callable[[], Any] | None = None,
            restart_emulator_callback: Callable[[], Any] | None = None,
            press_key_callback: Callable[[str], Any] | None = None,
            back_callback: Callable[[], Any] | None = None,
            status_provider: Callable[[], dict[str, Any]] | None = None,
            start_push_callback: Callable[[str, int | None], Any] | None = None,
            stop_all_callback: Callable[[], Any] | None = None,
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
        self.thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.client: discord.Client | None = None

    def start(self) -> bool:
        settings = self.settings_loader()
        if not _config_bool(settings.get("discord_control_enabled"), False):
            return False

        token = str(settings.get("discord_bot_token") or "").strip()
        if not token:
            print("Discord control skipped: enable it only after filling discord_bot_token in cfg/discord_config.toml.")
            return False

        if self.thread and self.thread.is_alive():
            return True

        self.thread = threading.Thread(target=self._thread_main, args=(token,), daemon=True)
        self.thread.start()
        return True

    def close(self) -> None:
        client = self.client
        loop = self.loop
        if client is not None and loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(client.close(), loop).result(timeout=3)
            except Exception:
                pass

    def _thread_main(self, token: str) -> None:
        try:
            asyncio.run(self._run(token))
        except Exception as exc:
            print(f"Discord control stopped: {exc}")

    async def _run(self, token: str) -> None:
        intents = discord.Intents.default()
        client = discord.Client(intents=intents)
        tree = app_commands.CommandTree(client)
        self.client = client
        self.loop = asyncio.get_running_loop()
        synced = False

        async def _ack(interaction: discord.Interaction) -> None:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

        async def _followup(interaction: discord.Interaction, message: str, file: discord.File | None = None) -> None:
            send_kwargs = {"ephemeral": True}
            if file is not None:
                send_kwargs["file"] = file
            if interaction.response.is_done():
                await interaction.followup.send(message, **send_kwargs)
            else:
                await interaction.response.send_message(message, **send_kwargs)

        async def _guard(interaction: discord.Interaction) -> bool:
            settings = self.settings_loader()
            if command_allowed(
                settings,
                getattr(interaction.user, "id", ""),
                getattr(interaction.channel, "id", None),
                getattr(interaction.guild, "id", None),
            ):
                return True
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "You are not allowed to control this PylaAi-XXZ bot.",
                    ephemeral=True,
                )
            return False

        async def _pause_bot(interaction: discord.Interaction) -> None:
            set_runtime_state(self.state_path, paused=True)
            await _followup(interaction, "PylaAi-XXZ paused. Use /start to resume.")

        @tree.command(name="stop", description="Pause PylaAi-XXZ.")
        async def stop_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            await _pause_bot(interaction)

        @tree.command(name="pause", description="Pause PylaAi-XXZ (alias for /stop).")
        async def pause_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            await _pause_bot(interaction)

        @tree.command(name="start", description="Resume PylaAi-XXZ.")
        async def start_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            set_runtime_state(self.state_path, paused=False)
            await _followup(interaction, "PylaAi-XXZ resumed.")

        @tree.command(name="stop_all", description="Stop the bot completely and exit the main loop.")
        async def stop_all_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            request_stop(self.state_path)
            ok, message = await run_callback(self.stop_all_callback)
            if ok:
                await _followup(
                    interaction,
                    message if message != "Command finished." else (
                        "PylaAi-XXZ is stopping. The bot process will exit shortly."
                    ),
                )
            else:
                await _followup(interaction, f"Stop request failed: {message}")

        @tree.command(name="status", description="Show whether PylaAi-XXZ is running or paused.")
        async def status_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            message = await asyncio.to_thread(status_text, self.state_path, self.status_provider)
            await _followup(interaction, message)

        @tree.command(name="screenshot", description="Send the current emulator screenshot.")
        async def screenshot_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            if self.screenshot_provider is None:
                await _followup(interaction, "Screenshot is not available in this process.")
                return
            try:
                screenshot = await asyncio.to_thread(self.screenshot_provider)
                file, _image_url = _image_to_file(screenshot)
            except Exception as exc:
                await _followup(interaction, f"Could not capture screenshot: {exc}")
                return
            if file is None:
                await _followup(interaction, "Could not send screenshot.")
                return
            await _followup(interaction, "Current emulator screenshot.", file=file)

        @tree.command(name="restart_game", description="Restart Brawl Stars and the scrcpy feed.")
        async def restart_game_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            ok, message = await run_callback(self.restart_game_callback)
            await _followup(
                interaction,
                "Brawl Stars restart finished." if ok else f"Brawl Stars restart failed: {message}",
            )

        @tree.command(name="restart_scrcpy", description="Restart only the scrcpy video feed.")
        async def restart_scrcpy_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            ok, message = await run_callback(self.restart_scrcpy_callback)
            await _followup(
                interaction,
                "Scrcpy restart finished." if ok else f"Scrcpy restart failed: {message}",
            )

        @tree.command(name="restart_emulator", description="Restart the full saved emulator profile.")
        async def restart_emulator_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            ok, message = await run_callback(self.restart_emulator_callback)
            await _followup(
                interaction,
                "Emulator restart finished." if ok else f"Emulator restart failed: {message}",
            )

        @tree.command(name="back", description="Press Android Back in the emulator.")
        async def back_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            ok, message = await run_callback(self.back_callback)
            await _followup(interaction, "Pressed Back." if ok else f"Back command failed: {message}")

        @tree.command(name="press", description="Press a game button: q, e, f, g, h, m, or back.")
        @app_commands.describe(key="Button to press: q, e, f, g, h, m, or back")
        async def press_command(interaction: discord.Interaction, key: str) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            normalized = str(key or "").strip().lower()
            allowed = {"q", "e", "f", "g", "h", "m", "back"}
            if normalized not in allowed:
                await _followup(interaction, "Allowed buttons: q, e, f, g, h, m, back.")
                return
            if normalized == "back":
                ok, message = await run_callback(self.back_callback)
            else:
                ok, message = await run_callback(self.press_key_callback, normalized)
            await _followup(interaction, f"Pressed {normalized}." if ok else f"Press command failed: {message}")

        async def brawler_autocomplete(
                interaction: discord.Interaction,
                current: str,
        ) -> list[app_commands.Choice[str]]:
            current_value = (current or "").strip().lower()
            choices = []
            for name in sorted(load_brawlers_info().keys()):
                if not current_value or current_value in name.lower():
                    choices.append(app_commands.Choice(name=name, value=name))
                if len(choices) >= 25:
                    break
            return choices

        @tree.command(name="push", description="Start pushing a specific brawler and reselect it in the lobby.")
        @app_commands.describe(
            brawler="Brawler to push",
            target="Optional trophy target (push_until)",
        )
        @app_commands.autocomplete(brawler=brawler_autocomplete)
        async def push_command(
                interaction: discord.Interaction,
                brawler: str,
                target: int | None = None,
        ) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            resolved = resolve_brawler_choice(brawler)
            if not resolved:
                await _followup(interaction, f"Unknown brawler '{brawler}'. Check the name and try again.")
                return
            ok, message = await run_callback(self.start_push_callback, resolved, target)
            await _followup(interaction, message if ok else f"Push command failed: {message}")

        @tree.error
        async def on_app_command_error(interaction: discord.Interaction, error: Exception) -> None:
            message = f"Discord command failed: {error}"
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(message, ephemeral=True)
                else:
                    await interaction.response.send_message(message, ephemeral=True)
            except Exception:
                print(message)

        @client.event
        async def on_ready() -> None:
            nonlocal synced
            if synced:
                return
            settings = self.settings_loader()
            guild_id = _clean_id(settings.get("discord_control_guild_id"))
            command_list = (
                "/start /stop /pause /stop_all /push /status /screenshot "
                "/restart_game /restart_scrcpy /restart_emulator /back /press"
            )
            try:
                if guild_id:
                    guild = discord.Object(id=int(guild_id))
                    tree.copy_global_to(guild=guild)
                    await tree.sync(guild=guild)
                    print(f"Discord control commands synced for guild {guild_id}: {command_list}")
                else:
                    await tree.sync()
                    print(f"Discord control commands synced globally: {command_list}")
                synced = True
            except Exception as exc:
                print(f"Discord control command sync failed: {exc}")

        await client.start(token)
