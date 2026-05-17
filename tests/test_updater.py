import tempfile
import unittest
from pathlib import Path

from tools.updater import (
    backup_preserved_files,
    copy_update_files,
    download_url_for_ref,
    latest_download_url,
    MAIN_BRANCH_ZIP,
    merge_toml_text,
    newest_ref,
    previous_ref,
    read_local_update_sha,
    remove_obsolete_files,
    restore_preserved_files,
    selected_ref_from_choice,
    write_local_update_info,
)


class UpdaterTest(unittest.TestCase):
    def test_updater_downloads_main_branch_not_possibly_stale_release(self):
        url, label = latest_download_url()

        self.assertEqual(url, MAIN_BRANCH_ZIP)
        self.assertEqual(label, "main branch zip")

    def test_downgrade_ref_download_url_uses_requested_version(self):
        url, label = download_url_for_ref("abc123")

        self.assertEqual(url, "https://github.com/xxz-888/PylaAi-XXZ/archive/abc123.zip")
        self.assertEqual(label, "GitHub ref abc123")

    def test_previous_ref_chooses_commit_before_latest(self):
        commits = [{"sha": "latest"}, {"sha": "previous"}, {"sha": "older"}]

        self.assertEqual(previous_ref(commits), "previous")

    def test_version_picker_uses_one_for_newest_and_zero_for_previous(self):
        commits = [{"sha": "latest"}, {"sha": "previous"}, {"sha": "older"}]

        self.assertEqual(newest_ref(commits), "latest")
        self.assertEqual(selected_ref_from_choice("1", commits), "latest")
        self.assertEqual(selected_ref_from_choice("0", commits), "previous")
        self.assertEqual(selected_ref_from_choice("2", commits), "older")
        self.assertEqual(selected_ref_from_choice("abc123", commits), "abc123")

    def test_copy_update_preserves_user_api_config_and_skips_updater_exe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            source = root / "source"
            backup = root / "backup"

            (project / "cfg").mkdir(parents=True)
            (project / "cfg" / "brawl_stars_api.toml").write_text('api_token = "USER"\n', encoding="utf-8")
            (project / "cfg" / "general_config.toml").write_text(
                'max_ips = 24\nplayer_tag = "USER_TAG"\nold_local_key = "keep"\n',
                encoding="utf-8",
            )
            (project / "cfg" / "custom_state.json").write_text(
                '{"matches": 12, "old_only": true, "nested": {"user": 1}}',
                encoding="utf-8",
            )
            (project / "updater.exe").write_text("old updater", encoding="utf-8")
            (project / "downgrader.exe").write_text("old downgrader", encoding="utf-8")
            (project / "main.py").write_text("old", encoding="utf-8")

            (source / "cfg").mkdir(parents=True)
            (source / "cfg" / "brawl_stars_api.toml").write_text('api_token = ""\n', encoding="utf-8")
            (source / "cfg" / "general_config.toml").write_text(
                'max_ips = 30\nplayer_tag = ""\nnew_key = "added"\n',
                encoding="utf-8",
            )
            (source / "cfg" / "custom_state.json").write_text(
                '{"matches": 0, "new_only": true, "nested": {"default": 2}}',
                encoding="utf-8",
            )
            (source / "updater.exe").write_text("new updater", encoding="utf-8")
            (source / "downgrader.exe").write_text("new downgrader", encoding="utf-8")
            (source / "adb.exe").write_text("new adb", encoding="utf-8")
            (source / "cfg" / "telegram_config.local.toml").write_text('bot_token = "BAD"\n', encoding="utf-8")
            (source / "cfg" / "telegram_chats.toml").write_text('chat_ids = ["BAD"]\n', encoding="utf-8")
            (source / "cfg" / "brawl_stars_api.local.toml").write_text('api_token = "BAD"\n', encoding="utf-8")
            (source / "main.py").write_text("new", encoding="utf-8")
            (source / "new_file.py").write_text("added", encoding="utf-8")

            backup_preserved_files(project, backup)
            copy_update_files(source, project)
            remove_obsolete_files(project)
            restore_preserved_files(project, backup)

            self.assertEqual((project / "cfg" / "brawl_stars_api.toml").read_text(encoding="utf-8"), 'api_token = "USER"\n')
            general_config = (project / "cfg" / "general_config.toml").read_text(encoding="utf-8")
            self.assertIn("max_ips = 24", general_config)
            self.assertIn('player_tag = "USER_TAG"', general_config)
            self.assertIn('new_key = "added"', general_config)
            self.assertIn('old_local_key = "keep"', general_config)
            custom_state = (project / "cfg" / "custom_state.json").read_text(encoding="utf-8")
            self.assertIn('"matches": 12', custom_state)
            self.assertIn('"new_only": true', custom_state)
            self.assertIn('"old_only": true', custom_state)
            self.assertIn('"default": 2', custom_state)
            self.assertIn('"user": 1', custom_state)
            self.assertEqual((project / "updater.exe").read_text(encoding="utf-8"), "old updater")
            self.assertFalse((project / "downgrader.exe").exists())
            self.assertFalse((project / "adb.exe").exists())
            self.assertFalse((project / "cfg" / "telegram_config.local.toml").exists())
            self.assertFalse((project / "cfg" / "telegram_chats.toml").exists())
            self.assertFalse((project / "cfg" / "brawl_stars_api.local.toml").exists())
            self.assertEqual((project / "main.py").read_text(encoding="utf-8"), "new")
            self.assertEqual((project / "new_file.py").read_text(encoding="utf-8"), "added")

    def test_toml_merge_keeps_user_values_and_adds_new_defaults(self):
        merged = merge_toml_text(
            'api_token = ""\ntimeout_seconds = 15\nnew_key = true\n',
            'api_token = "USER_TOKEN"\nold_key = "kept"\n',
        )

        self.assertIn('api_token = "USER_TOKEN"', merged)
        self.assertIn("timeout_seconds = 15", merged)
        self.assertIn("new_key = true", merged)
        self.assertIn('old_key = "kept"', merged)

    def test_toml_merge_does_not_append_placeholder_tag_suffix(self):
        merged = merge_toml_text(
            'player_tag = "#YOURTAG"\ntimeout_seconds = 15\n',
            'player_tag = "#GRR010Y1"\n',
        )

        self.assertIn('player_tag = "#GRR010Y1"', merged)
        self.assertNotIn("#GRR010Y1#YOURTAG", merged)

    def test_toml_merge_repairs_existing_placeholder_tag_suffix(self):
        merged = merge_toml_text(
            'player_tag = "#YOURTAG"\ntimeout_seconds = 15\n',
            'player_tag = "#GRR010Y1#YOURTAG"\n',
        )

        self.assertIn('player_tag = "#GRR010Y1"', merged)
        self.assertNotIn("#GRR010Y1#YOURTAG", merged)

    def test_toml_merge_preserves_real_inline_comment(self):
        merged = merge_toml_text(
            'player_tag = "#YOURTAG" # Brawl Stars player tag\n',
            'player_tag = "#GRR010Y1"\n',
        )

        self.assertIn('player_tag = "#GRR010Y1" # Brawl Stars player tag', merged)

    def test_update_info_marker_round_trips_latest_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)

            self.assertIsNone(read_local_update_sha(project))
            write_local_update_info(project, "abc123", selected_ref="abc123")

            self.assertEqual(read_local_update_sha(project), "abc123")
            self.assertIn('"selected_ref": "abc123"', (project / "cfg" / "update_info.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
