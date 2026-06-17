from __future__ import annotations

import asyncio
import inspect
import threading
from pathlib import Path
from typing import Any, Callable

import discord
from discord import app_commands

from gui.remote_formatting import (
    EMBED_COLORS,
    format_queue_lines,
    format_status_lines,
    runtime_color_from_state,
    runtime_label_from_state,
)
from runtime_control import (
    PAUSED,
    RUNNING,
    STOP_REQUESTED,
    read_state,
    request_stop,
    set_runtime_state,
    write_state,
)
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
    runtime_label = runtime_label_from_state(state)
    try:
        details = status_provider() if status_provider else {}
    except Exception as exc:
        details = {"status_error": exc}
    lines = [
        "Pyla-RL status",
        f"Runtime: {runtime_label}",
    ]
    for label, value in format_status_lines(details):
        lines.append(f"{label}: {value}")
    if details.get("status_error"):
        lines.append(f"Status Error: {details['status_error']}")
    return "\n".join(lines)


def build_status_embed(state_path: str | Path, status_provider: Callable[[], dict[str, Any]] | None = None) -> discord.Embed:
    state = read_state(state_path)
    runtime_label = runtime_label_from_state(state)
    try:
        details = status_provider() if status_provider else {}
    except Exception as exc:
        details = {"status_error": exc}
    embed = discord.Embed(
        title="Pyla-RL Status",
        description=f"Runtime: **{runtime_label.title()}**",
        color=runtime_color_from_state(state),
    )
    for label, value in format_status_lines(details):
        embed.add_field(name=label, value=value, inline=True)
    if details.get("status_error"):
        embed.add_field(name="Status Error", value=str(details["status_error"]), inline=False)
    embed.set_footer(text="Pyla • Remote Control")
    return embed


def build_queue_embed(queue) -> discord.Embed:
    embed = discord.Embed(
        title="Farm Plan",
        description=f"```\n{format_queue_lines(queue)}\n```",
        color=EMBED_COLORS["info"],
    )
    embed.set_footer(text="Pyla • Remote Control")
    return embed


def build_command_result_embed(payload: dict[str, Any]) -> discord.Embed:
    embed = discord.Embed(
        title=str(payload.get("title") or "Command Result"),
        description=str(payload.get("summary") or ""),
        color=int(payload.get("color") or EMBED_COLORS["success"]),
    )
    queue_text = payload.get("queue_text")
    if queue_text:
        embed.add_field(name="Updated Queue", value=f"```\n{queue_text}\n```", inline=False)
    embed.set_footer(text="Pyla • Remote Control")
    return embed


def build_error_embed(message: str) -> discord.Embed:
    embed = discord.Embed(
        title="Command Failed",
        description=message,
        color=EMBED_COLORS["error"],
    )
    embed.set_footer(text="Pyla • Remote Control")
    return embed


def build_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Pyla-RL Remote Commands",
        description="Use these slash commands to control your local bot instance.",
        color=EMBED_COLORS["info"],
    )
    sections = [
        ("Control", "/start, /pause, /stop_all, /status, /stats"),
        ("Farm Plan", "/push, /skip, /remove, /target, /queue"),
        ("Recovery", "/restart_game, /restart_scrcpy, /restart_emulator, /update"),
        ("Info", "/version, /check_update"),
        ("Other", "/screenshot, /press, /back, /pause_menu"),
    ]
    for name, commands in sections:
        embed.add_field(name=name, value=commands, inline=False)
    embed.set_footer(text="Pyla • Remote Control")
    return embed


def build_simple_embed(title: str, description: str, *, success: bool = True) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        color=EMBED_COLORS["success"] if success else EMBED_COLORS["error"],
    )


def build_stats_embed(stats: dict[str, Any]) -> discord.Embed:
    instance_name = str(stats.get("instance_name") or "").strip()
    title = f"Session Stats{f' — {instance_name}' if instance_name else ''}"
    embed = discord.Embed(
        title=title,
        description=(
            f"**{stats['wins']}W** / **{stats['losses']}L** / **{stats['draws']}D**"
            f"  •  Win rate **{stats['win_rate']}**"
        ),
        color=EMBED_COLORS["info"],
    )
    embed.add_field(name="Matches", value=str(stats["matches"]), inline=True)
    embed.add_field(name="Uptime", value=str(stats["uptime"]), inline=True)
    if stats.get("brawler"):
        embed.add_field(name="Active Brawler", value=str(stats["brawler"]), inline=True)
    if stats.get("trophies") not in (None, ""):
        from gui.remote_formatting import format_number

        embed.add_field(name="Trophies", value=format_number(stats["trophies"]), inline=True)
    embed.set_footer(text="Pyla • Remote Control")
    return embed


def callback_result_message(result: Any) -> str:
    if isinstance(result, dict):
        summary = str(result.get("summary") or "Command finished.")
        queue_text = result.get("queue_text")
        if queue_text:
            return f"{summary}\n\nUpdated queue:\n{queue_text}"
        return summary
    if isinstance(result, str) and result.strip():
        return result.strip()
    return "Command finished."


async def sync_discord_command_tree(tree: app_commands.CommandTree, guild_id: str | None) -> str:
    """Sync slash commands without leaving duplicate global + guild entries.

    When a guild ID is configured we publish commands to that guild only and
    clear stale global commands (old typo variants like /screeshot, etc.).
    """
    cleaned_guild = _clean_id(guild_id)
    if cleaned_guild:
        guild = discord.Object(id=int(cleaned_guild))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        tree.clear_commands(guild=None)
        await tree.sync()
        return f"guild {cleaned_guild} (cleared stale global commands)"
    await tree.sync()
    return "global"


async def run_callback(callback: Callable[..., Any] | None, *args: Any) -> tuple[bool, Any]:
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
    if isinstance(result, dict):
        return True, result
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
            stats_provider: Callable[[], dict[str, Any]] | None = None,
            start_push_callback: Callable[[str, int | None], Any] | None = None,
            skip_brawler_callback: Callable[[], Any] | None = None,
            remove_brawler_callback: Callable[[str], Any] | None = None,
            set_target_callback: Callable[[int], Any] | None = None,
            stop_all_callback: Callable[[], Any] | None = None,
            pause_menu_callback: Callable[[], Any] | None = None,
            self_update_callback: Callable[[str, bool, bool], Any] | None = None,
            version_callback: Callable[[], Any] | None = None,
            check_update_callback: Callable[[], Any] | None = None,
            command_router: Any | None = None,
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
        self.stats_provider = stats_provider
        self.start_push_callback = start_push_callback
        self.skip_brawler_callback = skip_brawler_callback
        self.remove_brawler_callback = remove_brawler_callback
        self.set_target_callback = set_target_callback
        self.stop_all_callback = stop_all_callback
        self.pause_menu_callback = pause_menu_callback
        self.self_update_callback = self_update_callback
        self.version_callback = version_callback
        self.check_update_callback = check_update_callback
        self.command_router = command_router
        self.router_mode = command_router is not None
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

        async def _followup_embed(
                interaction: discord.Interaction,
                embed: discord.Embed,
                file: discord.File | None = None,
        ) -> None:
            send_kwargs = {"embed": embed, "ephemeral": True}
            if file is not None:
                send_kwargs["file"] = file
            if interaction.response.is_done():
                await interaction.followup.send(**send_kwargs)
            else:
                await interaction.response.send_message(**send_kwargs)

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
                    embed=build_error_embed("You are not allowed to control this Pyla-RL bot."),
                    ephemeral=True,
                )
            return False

        async def instance_autocomplete(
                interaction: discord.Interaction,
                current: str,
        ) -> list[app_commands.Choice[str]]:
            if not self.command_router:
                return []
            current_value = (current or "").strip().lower()
            choices = []
            for instance_id in self.command_router.instance_choices():
                if not current_value or current_value in instance_id.lower():
                    choices.append(app_commands.Choice(name=instance_id, value=instance_id))
                if len(choices) >= 25:
                    break
            return choices

        async def _route_state_action(instance: str | None, action: str) -> tuple[bool, Any]:
            if not self.command_router:
                return False, "Router not configured."
            return await run_callback(self.command_router.dispatch_state_action, instance, action)

        async def _route_remote_action(instance: str | None, action: str, args: dict | None = None) -> tuple[bool, Any]:
            if not self.command_router:
                return False, "Router not configured."
            return await run_callback(self.command_router.dispatch_remote_action, instance, action, args or {})

        async def _pause_bot(interaction: discord.Interaction, instance: str | None = None) -> None:
            if self.command_router:
                ok, message = await _route_state_action(instance, "pause")
                if ok:
                    await _followup_embed(interaction, build_simple_embed("Pyla-RL Paused", str(message)))
                else:
                    await _followup_embed(interaction, build_error_embed(str(message)))
                return
            set_runtime_state(self.state_path, paused=True)
            await _followup_embed(
                interaction,
                build_simple_embed("Pyla-RL Paused", "Use /start to resume."),
            )

        @tree.command(name="pause", description="Pause Pyla-RL.")
        @app_commands.describe(instance="Target instance when multi-instance mode is enabled")
        @app_commands.autocomplete(instance=instance_autocomplete)
        async def pause_command(interaction: discord.Interaction, instance: str | None = None) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            await _pause_bot(interaction, instance)

        @tree.command(name="stop", description="Pause Pyla-RL. Prefer /pause (/stop is deprecated).")
        async def stop_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            await _pause_bot(interaction)

        @tree.command(name="start", description="Resume Pyla-RL.")
        @app_commands.describe(instance="Target instance when multi-instance mode is enabled")
        @app_commands.autocomplete(instance=instance_autocomplete)
        async def start_command(interaction: discord.Interaction, instance: str | None = None) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            if self.command_router:
                ok, message = await _route_state_action(instance, "resume")
                if ok:
                    await _followup_embed(interaction, build_simple_embed("Pyla-RL Resumed", str(message)))
                else:
                    await _followup_embed(interaction, build_error_embed(str(message)))
                return
            set_runtime_state(self.state_path, paused=False)
            await _followup_embed(
                interaction,
                build_simple_embed("Pyla-RL Resumed", "The bot is running again."),
            )

        @tree.command(name="stop_all", description="Stop the bot completely and exit the main loop.")
        async def stop_all_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            request_stop(self.state_path)
            ok, message = await run_callback(self.stop_all_callback)
            if ok:
                text = callback_result_message(message)
                if text == "Command finished.":
                    text = "Pyla-RL is stopping. The bot process will exit shortly."
                await _followup_embed(interaction, build_simple_embed("Stopping Pyla-RL", text))
            else:
                await _followup_embed(interaction, build_error_embed(str(message)))

        @tree.command(name="status", description="Show whether Pyla-RL is running or paused.")
        @app_commands.describe(instance="Target instance when multi-instance mode is enabled")
        @app_commands.autocomplete(instance=instance_autocomplete)
        async def status_command(interaction: discord.Interaction, instance: str | None = None) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            if self.command_router:
                provider = self.command_router.build_status_provider(instance)
                if provider is None:
                    _, error = self.command_router.resolve_target(instance)
                    await _followup_embed(interaction, build_error_embed(error or "Could not resolve instance."))
                    return
                embed = await asyncio.to_thread(build_status_embed, self.state_path, provider)
                await _followup_embed(interaction, embed)
                return
            embed = await asyncio.to_thread(build_status_embed, self.state_path, self.status_provider)
            await _followup_embed(interaction, embed)

        @tree.command(name="stats", description="Show current session wins, losses, draws, and win rate.")
        @app_commands.describe(instance="Target instance when multi-instance mode is enabled")
        @app_commands.autocomplete(instance=instance_autocomplete)
        async def stats_command(interaction: discord.Interaction, instance: str | None = None) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            if self.command_router:
                ok, message = await _route_remote_action(instance, "stats")
                if ok and isinstance(message, dict):
                    await _followup_embed(interaction, build_stats_embed(message))
                elif ok:
                    await _followup_embed(interaction, build_simple_embed("Session Stats", callback_result_message(message)))
                else:
                    await _followup_embed(interaction, build_error_embed(str(message)))
                return
            if self.stats_provider is None:
                await _followup_embed(interaction, build_error_embed("Session stats are not available in this process."))
                return
            try:
                stats = await asyncio.to_thread(self.stats_provider)
            except Exception as exc:
                await _followup_embed(interaction, build_error_embed(f"Could not load session stats: {exc}"))
                return
            await _followup_embed(interaction, build_stats_embed(stats))

        @tree.command(name="queue", description="Show the next brawlers in the farm plan.")
        @app_commands.describe(instance="Target instance when multi-instance mode is enabled")
        @app_commands.autocomplete(instance=instance_autocomplete)
        async def queue_command(interaction: discord.Interaction, instance: str | None = None) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            if self.command_router:
                ok, message = await _route_remote_action(instance, "queue")
                if ok:
                    from gui.brawler_queue import load_queue
                    from gui.instance_registry import require_resolved_instance

                    target, error = require_resolved_instance(instance)
                    if error:
                        await _followup_embed(interaction, build_error_embed(error))
                        return
                    from gui.instance_config import get_queue_path

                    queue = load_queue(get_queue_path(target["id"]))
                    if not queue:
                        await _followup_embed(interaction, build_simple_embed("Farm Plan", "Farm plan is empty.", success=False))
                        return
                    await _followup_embed(interaction, build_queue_embed(queue))
                else:
                    await _followup_embed(interaction, build_error_embed(str(message)))
                return
            from gui.brawler_queue import load_queue

            queue = load_queue()
            if not queue:
                await _followup_embed(
                    interaction,
                    build_simple_embed("Farm Plan", "Farm plan is empty.", success=False),
                )
                return
            await _followup_embed(interaction, build_queue_embed(queue))

        @tree.command(name="screenshot", description="Send the current emulator screenshot.")
        async def screenshot_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            if self.screenshot_provider is None:
                await _followup_embed(interaction, build_error_embed("Screenshot is not available in this process."))
                return
            try:
                screenshot = await asyncio.to_thread(self.screenshot_provider)
                file, _image_url = _image_to_file(screenshot)
            except Exception as exc:
                await _followup_embed(interaction, build_error_embed(f"Could not capture screenshot: {exc}"))
                return
            if file is None:
                await _followup_embed(interaction, build_error_embed("Could not send screenshot."))
                return
            embed = build_simple_embed("Screenshot", "Current emulator screenshot.")
            await _followup_embed(interaction, embed, file=file)

        @tree.command(name="restart_game", description="Restart Brawl Stars and the scrcpy feed.")
        async def restart_game_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            ok, message = await run_callback(self.restart_game_callback)
            if ok:
                await _followup_embed(interaction, build_simple_embed("Restart Complete", "Brawl Stars restart finished."))
            else:
                await _followup_embed(interaction, build_error_embed(f"Brawl Stars restart failed: {message}"))

        @tree.command(name="restart_scrcpy", description="Restart only the scrcpy video feed.")
        async def restart_scrcpy_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            ok, message = await run_callback(self.restart_scrcpy_callback)
            if ok:
                await _followup_embed(interaction, build_simple_embed("Restart Complete", "Scrcpy restart finished."))
            else:
                await _followup_embed(interaction, build_error_embed(f"Scrcpy restart failed: {message}"))

        @tree.command(name="restart_emulator", description="Restart the full saved emulator profile.")
        async def restart_emulator_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            ok, message = await run_callback(self.restart_emulator_callback)
            if ok:
                await _followup_embed(interaction, build_simple_embed("Restart Complete", "Emulator restart finished."))
            else:
                await _followup_embed(interaction, build_error_embed(f"Emulator restart failed: {message}"))

        @tree.command(name="back", description="Press Android Back in the emulator.")
        async def back_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            ok, message = await run_callback(self.back_callback)
            if ok:
                await _followup_embed(interaction, build_simple_embed("Back", "Pressed Back."))
            else:
                await _followup_embed(interaction, build_error_embed(f"Back command failed: {message}"))

        @tree.command(name="press", description="Press a game button: q, e, f, g, h, m, or back.")
        @app_commands.describe(key="Button to press: q, e, f, g, h, m, or back")
        async def press_command(interaction: discord.Interaction, key: str) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            normalized = str(key or "").strip().lower()
            allowed = {"q", "e", "f", "g", "h", "m", "back"}
            if normalized not in allowed:
                await _followup_embed(interaction, build_error_embed("Allowed buttons: q, e, f, g, h, m, back."))
                return
            if normalized == "back":
                ok, message = await run_callback(self.back_callback)
            else:
                ok, message = await run_callback(self.press_key_callback, normalized)
            if ok:
                await _followup_embed(interaction, build_simple_embed("Press", f"Pressed {normalized}."))
            else:
                await _followup_embed(interaction, build_error_embed(f"Press command failed: {message}"))

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

        async def _send_farm_plan_result(interaction: discord.Interaction, ok: bool, message: Any, *, title: str) -> None:
            if ok and isinstance(message, dict):
                payload = dict(message)
                payload.setdefault("title", title)
                await _followup_embed(interaction, build_command_result_embed(payload))
                return
            if ok:
                await _followup_embed(
                    interaction,
                    build_simple_embed(title, callback_result_message(message)),
                )
                return
            await _followup_embed(interaction, build_error_embed(str(message)))

        @tree.command(name="push", description="Prioritize a brawler at the front of the farm plan and move the current brawler down one slot.")
        @app_commands.describe(
            brawler="Brawler to push",
            target="Optional trophy target (push_until)",
            instance="Target instance when multi-instance mode is enabled",
        )
        @app_commands.autocomplete(brawler=brawler_autocomplete, instance=instance_autocomplete)
        async def push_command(
                interaction: discord.Interaction,
                brawler: str,
                target: int | None = None,
                instance: str | None = None,
        ) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            resolved = resolve_brawler_choice(brawler)
            if not resolved:
                await _followup_embed(interaction, build_error_embed(f"Unknown brawler '{brawler}'. Check the name and try again."))
                return
            if self.command_router:
                ok, message = await _route_remote_action(instance, "push", {"brawler": resolved, "target": target})
                await _send_farm_plan_result(interaction, ok, message, title="Push")
                return
            ok, message = await run_callback(self.start_push_callback, resolved, target)
            await _send_farm_plan_result(interaction, ok, message, title="Push")

        @tree.command(name="skip", description="Move the current brawler down one slot and play the next brawler.")
        @app_commands.describe(instance="Target instance when multi-instance mode is enabled")
        @app_commands.autocomplete(instance=instance_autocomplete)
        async def skip_command(interaction: discord.Interaction, instance: str | None = None) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            if self.command_router:
                ok, message = await _route_remote_action(instance, "skip")
            else:
                ok, message = await run_callback(self.skip_brawler_callback)
            await _send_farm_plan_result(interaction, ok, message, title="Skip")

        @tree.command(name="remove", description="Remove a brawler from the farm plan.")
        @app_commands.describe(brawler="Brawler to remove from the farm plan", instance="Target instance when multi-instance mode is enabled")
        @app_commands.autocomplete(brawler=brawler_autocomplete, instance=instance_autocomplete)
        async def remove_command(interaction: discord.Interaction, brawler: str, instance: str | None = None) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            resolved = resolve_brawler_choice(brawler)
            if not resolved:
                await _followup_embed(interaction, build_error_embed(f"Unknown brawler '{brawler}'. Check the name and try again."))
                return
            if self.command_router:
                ok, message = await _route_remote_action(instance, "remove", {"brawler": resolved})
            else:
                ok, message = await run_callback(self.remove_brawler_callback, resolved)
            await _send_farm_plan_result(interaction, ok, message, title="Remove")

        @tree.command(name="target", description="Set the trophy target for the current active brawler.")
        @app_commands.describe(trophies="Trophy target for the active brawler", instance="Target instance when multi-instance mode is enabled")
        @app_commands.autocomplete(instance=instance_autocomplete)
        async def target_command(interaction: discord.Interaction, trophies: int, instance: str | None = None) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            if self.command_router:
                ok, message = await _route_remote_action(instance, "target", {"target": trophies})
            else:
                ok, message = await run_callback(self.set_target_callback, trophies)
            await _send_farm_plan_result(interaction, ok, message, title="Target")

        @tree.command(name="pause_menu", description="Reopen the local pause control window.")
        async def pause_menu_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            ok, message = await run_callback(self.pause_menu_callback)
            if ok:
                await _followup_embed(interaction, build_simple_embed("Pause Menu", "Pause menu reopened."))
            else:
                await _followup_embed(interaction, build_error_embed(f"Could not reopen pause menu: {message}"))

        @tree.command(name="version", description="Show the running Pyla-RL version and build commit.")
        @app_commands.describe(instance="Target instance when multi-instance mode is enabled")
        @app_commands.autocomplete(instance=instance_autocomplete)
        async def version_command(interaction: discord.Interaction, instance: str | None = None) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            if self.command_router and instance:
                ok, message = await _route_remote_action(instance, "version")
            else:
                ok, message = await run_callback(self.version_callback)
            if ok:
                await _followup_embed(interaction, build_simple_embed("Pyla-RL Version", callback_result_message(message)))
            else:
                await _followup_embed(interaction, build_error_embed(str(message)))

        @tree.command(name="check_update", description="Check whether a newer Pyla-RL update is available.")
        @app_commands.describe(instance="Target instance when multi-instance mode is enabled")
        @app_commands.autocomplete(instance=instance_autocomplete)
        async def check_update_command(interaction: discord.Interaction, instance: str | None = None) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            if self.command_router and instance:
                ok, message = await _route_remote_action(instance, "check_update")
            else:
                ok, message = await run_callback(self.check_update_callback)
            if ok:
                await _followup_embed(interaction, build_simple_embed("Update Status", callback_result_message(message)))
            else:
                await _followup_embed(interaction, build_error_embed(str(message)))

        @tree.command(name="update", description="Update Pyla-RL and restart automatically.")
        @app_commands.describe(
            ref="Version to install: latest, previous, commit SHA, tag, or branch",
            force="Update immediately instead of waiting for the next lobby",
            reinstall="Reinstall even if this folder is already current",
            instance="Target instance when multi-instance mode is enabled",
        )
        @app_commands.autocomplete(instance=instance_autocomplete)
        async def update_command(
                interaction: discord.Interaction,
                ref: str | None = None,
                force: bool = False,
                reinstall: bool = False,
                instance: str | None = None,
        ) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            selected_ref = str(ref or "latest").strip() or "latest"
            if self.command_router:
                ok, message = await _route_remote_action(
                    instance,
                    "update",
                    {"ref": selected_ref, "immediate": bool(force), "reinstall": bool(reinstall)},
                )
            else:
                ok, message = await run_callback(self.self_update_callback, selected_ref, bool(reinstall), bool(force))
            if ok:
                await _followup_embed(interaction, build_simple_embed("Update Started", callback_result_message(message)))
            else:
                await _followup_embed(interaction, build_error_embed(str(message)))

        @tree.command(name="help", description="List available Pyla-RL remote commands.")
        async def help_command(interaction: discord.Interaction) -> None:
            if not await _guard(interaction):
                return
            await _ack(interaction)
            await _followup_embed(interaction, build_help_embed())

        @tree.error
        async def on_app_command_error(interaction: discord.Interaction, error: Exception) -> None:
            message = f"Discord command failed: {error}"
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(embed=build_error_embed(message), ephemeral=True)
                else:
                    await interaction.response.send_message(embed=build_error_embed(message), ephemeral=True)
            except Exception:
                print(message)

        @client.event
        async def on_ready() -> None:
            nonlocal synced
            if synced:
                return
            settings = self.settings_loader()
            guild_id = _clean_id(settings.get("discord_control_guild_id"))
            try:
                scope = await sync_discord_command_tree(tree, guild_id)
                print(f"Discord control commands synced for {scope}.")
                synced = True
            except Exception as exc:
                print(f"Discord control command sync failed: {exc}")

        await client.start(token)
