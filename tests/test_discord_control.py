import asyncio
import tempfile
import unittest
from pathlib import Path

from discord_control import command_allowed, run_callback, set_runtime_state, status_text
from runtime_control import PAUSED, RUNNING, read_state


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

    def test_discord_commands_ack_then_send_followups(self):
        source = Path("discord_control.py").read_text(encoding="utf-8")

        self.assertIn("async def _ack", source)
        self.assertIn("await interaction.response.defer(ephemeral=True)", source)
        self.assertIn("async def _followup", source)
        self.assertIn("await asyncio.to_thread(status_text", source)
        self.assertIn("@tree.error", source)


if __name__ == "__main__":
    unittest.main()
