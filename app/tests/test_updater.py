import tempfile
import unittest
from pathlib import Path

from core.toml_merge import merge_toml_text, repair_unquoted_windows_paths
from tools.updater import (
    apply_pending_launcher_updates,
    backup_preserved_files,
    copy_root_launcher_files,
    copy_update_files,
    download_url_for_ref,
    latest_download_url,
    MAIN_BRANCH_ZIP,
    newest_ref,
    pending_launcher_path,
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

        self.assertEqual(url, "https://github.com/CodeBanana69/Pyla-RL/archive/abc123.zip")
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

    def test_copy_update_preserves_user_api_config_and_updates_launchers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            source = root / "source"
            backup = root / "backup"

            (project / "app" / "cfg").mkdir(parents=True)
            (project / "app" / "main.py").write_text("old", encoding="utf-8")
            (project / "app" / "cfg" / "brawl_stars_api.toml").write_text('api_token = "USER"\n', encoding="utf-8")
            (project / "app" / "cfg" / "general_config.toml").write_text(
                'max_ips = 24\nplayer_tag = "USER_TAG"\nold_local_key = "keep"\n',
                encoding="utf-8",
            )
            (project / "app" / "cfg" / "custom_state.json").write_text(
                '{"matches": 12, "old_only": true, "nested": {"user": 1}}',
                encoding="utf-8",
            )
            (project / "updater.exe").write_text("old updater", encoding="utf-8")
            (project / "setup.exe").write_text("old setup", encoding="utf-8")
            (project / "downgrader.exe").write_text("old downgrader", encoding="utf-8")

            (source / "app" / "cfg").mkdir(parents=True)
            (source / "app" / "main.py").write_text("new", encoding="utf-8")
            (source / "app" / "new_file.py").write_text("added", encoding="utf-8")
            (source / "app" / "cfg" / "brawl_stars_api.toml").write_text('api_token = ""\n', encoding="utf-8")
            (source / "app" / "cfg" / "general_config.toml").write_text(
                'max_ips = 30\nplayer_tag = ""\nnew_key = "added"\n',
                encoding="utf-8",
            )
            (source / "app" / "cfg" / "custom_state.json").write_text(
                '{"matches": 0, "new_only": true, "nested": {"default": 2}}',
                encoding="utf-8",
            )
            (source / "updater.exe").write_text("new updater", encoding="utf-8")
            (source / "setup.exe").write_text("new setup", encoding="utf-8")
            (source / "downgrader.exe").write_text("new downgrader", encoding="utf-8")
            (source / "adb.exe").write_text("new adb", encoding="utf-8")
            (source / "app" / "cfg" / "telegram_config.local.toml").write_text('bot_token = "BAD"\n', encoding="utf-8")
            (source / "app" / "cfg" / "telegram_chats.toml").write_text('chat_ids = ["BAD"]\n', encoding="utf-8")
            (source / "app" / "cfg" / "brawl_stars_api.local.toml").write_text('api_token = "BAD"\n', encoding="utf-8")

            backup_preserved_files(project, backup)
            copy_update_files(source, project)
            copy_root_launcher_files(source, project)
            remove_obsolete_files(project)
            restore_preserved_files(project, backup)

            self.assertEqual(
                (project / "app" / "cfg" / "brawl_stars_api.toml").read_text(encoding="utf-8"),
                'api_token = "USER"\n',
            )
            general_config = (project / "app" / "cfg" / "general_config.toml").read_text(encoding="utf-8")
            self.assertIn("max_ips = 24", general_config)
            self.assertIn('player_tag = "USER_TAG"', general_config)
            self.assertIn('new_key = "added"', general_config)
            self.assertIn('old_local_key = "keep"', general_config)
            custom_state = (project / "app" / "cfg" / "custom_state.json").read_text(encoding="utf-8")
            self.assertIn('"matches": 12', custom_state)
            self.assertIn('"new_only": true', custom_state)
            self.assertIn('"old_only": true', custom_state)
            self.assertIn('"default": 2', custom_state)
            self.assertIn('"user": 1', custom_state)
            self.assertEqual((project / "updater.exe").read_text(encoding="utf-8"), "new updater")
            self.assertEqual((project / "setup.exe").read_text(encoding="utf-8"), "new setup")
            self.assertFalse((project / "downgrader.exe").exists())
            self.assertFalse((project / "adb.exe").exists())
            self.assertFalse((project / "app" / "cfg" / "telegram_config.local.toml").exists())
            self.assertFalse((project / "app" / "cfg" / "telegram_chats.toml").exists())
            self.assertFalse((project / "app" / "cfg" / "brawl_stars_api.local.toml").exists())
            self.assertEqual((project / "app" / "main.py").read_text(encoding="utf-8"), "new")
            self.assertEqual((project / "app" / "new_file.py").read_text(encoding="utf-8"), "added")

    def test_apply_pending_launcher_updates_installs_new_exe(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            destination = project / "updater.exe"
            destination.write_text("old updater", encoding="utf-8")
            pending_launcher_path(destination).write_text("new updater", encoding="utf-8")
            installed = apply_pending_launcher_updates(project)
            self.assertEqual(installed, ["updater.exe"])
            self.assertEqual(destination.read_text(encoding="utf-8"), "new updater")
            self.assertFalse(pending_launcher_path(destination).exists())

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

    def test_toml_merge_does_not_duplicate_quoted_bom_personal_webhook(self):
        merged = merge_toml_text(
            '"\\ufeffpersonal_webhook" = ""\nperformance_autotune = "no"\n',
            '"\\ufeffpersonal_webhook" = "https://example.test"\nperformance_autotune = "yes"\n',
        )

        self.assertEqual(merged.count("personal_webhook"), 1)
        self.assertIn('personal_webhook = "https://example.test"', merged)
        self.assertIn('performance_autotune = "yes"', merged)
        self.assertNotIn("Kept from your previous config", merged)

    def test_toml_merge_dedupes_keys_already_present_in_new_template(self):
        merged = merge_toml_text(
            'max_ips = 30\nperformance_autotune = "no"\n',
            'max_ips = 24\nperformance_autotune = "yes"\n',
        )

        self.assertEqual(merged.count("performance_autotune"), 1)
        self.assertIn('performance_autotune = "yes"', merged)
        self.assertIn("max_ips = 24", merged)

    def test_toml_merge_dedupes_appended_keys_that_match_new_defaults(self):
        new_text = "max_ips = 30\nperformance_autotune = \"no\"\n"
        old_text = (
            "max_ips = 24\n"
            "performance_autotune = \"yes\"\n"
            "# Kept from your previous config\n"
            "performance_autotune = \"yes\"\n"
        )
        merged = merge_toml_text(new_text, old_text)

        self.assertEqual(merged.count("performance_autotune"), 1)
        self.assertIn('performance_autotune = "yes"', merged)

    def test_repair_unquoted_windows_paths_quotes_bare_paths(self):
        text = (
            "current_emulator = \"MuMu\"\n"
            "ldplayer_console_path = C:\\LDPlayer\\ldconsole.exe\n"
        )
        repaired = repair_unquoted_windows_paths(text)
        self.assertIn('ldplayer_console_path = "C:\\\\LDPlayer\\\\ldconsole.exe"', repaired)

    def test_update_info_marker_round_trips_latest_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "app" / "cfg").mkdir(parents=True)

            self.assertIsNone(read_local_update_sha(project))
            write_local_update_info(project, "abc123", selected_ref="abc123")

            self.assertEqual(read_local_update_sha(project), "abc123")
            self.assertIn(
                '"selected_ref": "abc123"',
                (project / "app" / "cfg" / "update_info.json").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
