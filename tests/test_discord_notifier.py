import unittest

import numpy as np

import discord_notifier
import discord

from discord_notifier import _add_fields, _image_to_file, _ping_content, _title_and_description


class DiscordNotifierTest(unittest.TestCase):
    def setUp(self):
        discord_notifier._match_count = 0
        discord_notifier._last_minute_ping = 0.0

    def test_match_ping_every_x_matches(self):
        settings = {
            "discord_id": "12345",
            "ping_every_x_match": 2,
            "ping_every_x_minutes": 0,
        }

        self.assertEqual(_ping_content("match", settings), "")
        self.assertEqual(_ping_content("match", settings), "<@12345>")

    def test_target_completion_ping(self):
        settings = {
            "discord_id": "12345",
            "ping_when_target_is_reached": True,
            "ping_every_x_minutes": 0,
        }

        self.assertEqual(_ping_content("brawler_complete", settings), "<@12345>")

    def test_titles_include_useful_event_context(self):
        title, description = _title_and_description("match", {"result": "1st"})

        self.assertEqual(title, "🏁 Match Finished")
        self.assertIn("🥇 1st Place", description)

    def test_brawler_complete_without_name_has_no_current_brawler_wording(self):
        _, description = _title_and_description("brawler_complete", {})

        self.assertEqual(description, "A brawler reached the configured target.")

    def test_match_summary_does_not_show_potentially_stale_brawler_name(self):
        _, description = _title_and_description("match", {"result": "4th", "brawler": "amber"})

        self.assertNotIn("Amber", description)

    def test_match_fields_hide_potentially_stale_brawler_name(self):
        embed = discord.Embed(title="test")

        _add_fields(embed, {"event_type": "match", "brawler": "amber", "result": "4th"})

        self.assertEqual(len(embed.fields), 1)

    def test_brawlers_left_field_is_user_friendly(self):
        embed = discord.Embed(title="test")

        _add_fields(embed, {"brawlers_left": 3})

        self.assertEqual(embed.fields[0].name, "📋 Brawlers Left")

    def test_started_trophies_is_shown_before_current_trophies(self):
        embed = discord.Embed(title="test")

        _add_fields(embed, {"trophies": 250, "started_trophies": 100})

        self.assertEqual(embed.fields[0].name, "📍 Started Trophies")
        self.assertEqual(embed.fields[1].name, "🏆 Current Trophies")

    def test_numpy_screenshot_becomes_discord_file(self):
        image = np.zeros((16, 16, 3), dtype=np.uint8)

        file, url = _image_to_file(image)

        self.assertIsNotNone(file)
        self.assertEqual(url, "attachment://pyla_screenshot.png")


if __name__ == "__main__":
    unittest.main()
