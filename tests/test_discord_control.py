import asyncio
import tempfile
import unittest
from pathlib import Path

from discord_control import (
    command_allowed,
    resolve_brawler_choice,
    run_callback,
    set_runtime_state,
    status_text,
)
from runtime_control import PAUSED, RUNNING, STOP_REQUESTED, is_stop_requested, read_state, request_stop


class DiscordControlTest(unittest.TestCase):
    def test_command_allowed_uses_discord_id_as_owner_fallback(self):
        settings = {
            "discord_id": "12345",
            "discord_control_user_id": "",
            "discord_control_channel_id": "",
            "discord_control_guild_id": "",
        }

        self.assertTrue(command_allowed(settings, user_id=12345, channel_id=99, guild_id=88))
        self.assertFalse(command_allowed(settings, user_id=54321, channel_id=99, guild_id=88))

    def test_command_allowed_can_restrict_channel_and_guild(self):
        settings = {
            "discord_control_user_id": "12345",
            "discord_control_channel_id": "222",
            "discord_control_guild_id": "333",
        }

        self.assertTrue(command_allowed(settings, user_id=12345, channel_id=222, guild_id=333))
        self.assertFalse(command_allowed(settings, user_id=12345, channel_id=999, guild_id=333))
        self.assertFalse(command_allowed(settings, user_id=12345, channel_id=222, guild_id=999))

    def test_start_stop_commands_write_runtime_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "runtime.state"

            self.assertEqual(set_runtime_state(state_path, paused=True), PAUSED)
            self.assertEqual(read_state(state_path), PAUSED)

            self.assertEqual(set_runtime_state(state_path, paused=False), RUNNING)
            self.assertEqual(read_state(state_path), RUNNING)

    def test_status_text_includes_runtime_details(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "runtime.state"
            set_runtime_state(state_path, paused=False)

            text = status_text(
                state_path,
                lambda: {
                    "state": "match",
                    "ips": "29.50",
                    "feed_fps": "60.00",
                    "emulator": "LDPlayer",
                    "adb_device": "emulator-5554",
                    "brawler": "nita",
                    "target": "500",
                },
            )

        self.assertIn("Runtime: running", text)
        self.assertIn("State: match", text)
        self.assertIn("Ips: 29.50", text)
        self.assertIn("Feed Fps: 60.00", text)

    def test_run_callback_runs_sync_callbacks_off_loop(self):
        async def runner():
            return await run_callback(lambda key: key == "q", "q")

        ok, message = asyncio.run(runner())

        self.assertTrue(ok)
        self.assertEqual(message, "Command finished.")

    def test_run_callback_reports_false_result(self):
        async def runner():
            return await run_callback(lambda: False)

        ok, message = asyncio.run(runner())

        self.assertFalse(ok)
        self.assertIn("reported a problem", message)

    def test_run_callback_returns_custom_confirmation_message(self):
        async def runner():
            return await run_callback(lambda: "Pushing shelly (target 500).")

        ok, message = asyncio.run(runner())

        self.assertTrue(ok)
        self.assertEqual(message, "Pushing shelly (target 500).")

    def test_request_stop_writes_stop_requested_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "runtime.state"
            self.assertEqual(request_stop(state_path), STOP_REQUESTED)
            self.assertTrue(is_stop_requested(state_path))

    def test_status_text_shows_stopping_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "runtime.state"
            request_stop(state_path)
            text = status_text(state_path)
        self.assertIn("Runtime: stopping", text)

    def test_resolve_brawler_choice_accepts_known_brawler(self):
        resolved = resolve_brawler_choice("shelly")
        self.assertEqual(resolved, "shelly")

    def test_resolve_brawler_choice_rejects_unknown_brawler(self):
        self.assertIsNone(resolve_brawler_choice("not_a_real_brawler_xyz"))


if __name__ == "__main__":
    unittest.main()
