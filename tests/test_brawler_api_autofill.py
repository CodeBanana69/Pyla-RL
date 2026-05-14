import unittest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from gui.select_brawler import SelectBrawler
import utils
from utils import get_config_player_tag


class BrawlerApiAutofillTest(unittest.TestCase):
    def test_latest_brawlers_exist_in_local_registry_and_icons(self):
        expected_brawlers = {"damian", "starrnova", "bolt", "buzzlightyear"}
        brawlers_info = json.loads(Path("cfg/brawlers_info.json").read_text())

        self.assertTrue(expected_brawlers.issubset(brawlers_info))
        for brawler in expected_brawlers:
            self.assertTrue(Path(f"api/assets/brawler_icons/{brawler}.png").is_file())

    def test_trophy_lookup_uses_normalized_brawler_name(self):
        selector = object.__new__(SelectBrawler)
        selector.api_trophies_by_brawler = {"8-bit": 731, "sprout": 642}
        selector.api_trophies_by_normalized_brawler = None

        self.assertEqual(selector.get_api_trophies_for_brawler("8 Bit"), 731)
        self.assertEqual(selector.get_api_trophies_for_brawler("SPROUT"), 642)

    def test_player_tag_selection(self):
        config = {
            "player_tag": "#AAAA",
        }

        self.assertEqual(get_config_player_tag(config), "#AAAA")

    def test_keeps_placeholder_when_no_player_tag_is_configured(self):
        config = {
            "player_tag": "#YOURTAG",
        }

        self.assertEqual(get_config_player_tag(config), "#YOURTAG")

    def test_failed_auto_refresh_does_not_mark_refresh_done(self):
        utils._brawl_stars_api_refresh_done = False
        utils._brawl_stars_api_refresh_signature = None
        config = {
            "auto_refresh_token": True,
            "developer_email": "",
            "developer_password": "",
        }

        with self.assertRaises(ValueError):
            utils.refresh_brawl_stars_api_token_if_enabled(config)

        self.assertFalse(utils._brawl_stars_api_refresh_done)

    def test_failed_auto_refresh_reports_detected_config_fields(self):
        config = {
            "auto_refresh_token": True,
            "developer_email": "user@example.com",
            "developer_password": "",
            "player_tag": "#PLAYER",
        }

        with self.assertRaisesRegex(ValueError, "developer_email_present=yes; developer_password_present=no"):
            utils.refresh_brawl_stars_api_token_if_enabled(config)

    @patch("utils.save_dict_as_toml")
    @patch("utils.get_public_ip", return_value="1.2.3.4")
    @patch("utils._developer_api_post")
    def test_auto_refresh_retries_when_previous_check_had_no_token(self, mock_post, _mock_ip, _mock_save):
        utils._brawl_stars_api_refresh_done = True
        utils._brawl_stars_api_refresh_signature = ("cfg/brawl_stars_api.toml", "old", "old", "#OLD")
        mock_post.side_effect = [
            {},
            {"developer": {"allowedScopes": ["brawlstars"]}},
            {"keys": []},
            {"key": {"key": "NEW_TOKEN"}},
        ]
        config = {
            "auto_refresh_token": True,
            "developer_email": "user@example.com",
            "developer_password": "secret",
            "player_tag": "#PLAYER",
            "api_token": "",
            "timeout_seconds": 15,
        }

        refreshed = utils.refresh_brawl_stars_api_token_if_enabled(config)

        self.assertEqual(refreshed["api_token"], "NEW_TOKEN")
        self.assertTrue(utils._brawl_stars_api_refresh_done)
        self.assertEqual(
            utils._brawl_stars_api_refresh_signature,
            (utils.resolve_project_path("cfg/brawl_stars_api.toml"), "user@example.com", "secret", "#PLAYER"),
        )

    @patch("utils.save_dict_as_toml")
    @patch("utils.time.sleep")
    @patch("utils.get_public_ip", return_value="1.2.3.4")
    @patch("utils._developer_api_post")
    def test_auto_refresh_retries_developer_session_not_found(self, mock_post, _mock_ip, _mock_sleep, _mock_save):
        utils._brawl_stars_api_refresh_done = False
        utils._brawl_stars_api_refresh_signature = None
        mock_post.side_effect = [
            {},
            RuntimeError("Developer portal error 401 at account/load: Session not found"),
            {},
            {"developer": {"allowedScopes": ["brawlstars"]}},
            {"keys": []},
            {"key": {"key": "NEW_TOKEN"}},
        ]
        config = {
            "auto_refresh_token": True,
            "developer_email": "user@example.com",
            "developer_password": "secret",
            "player_tag": "#PLAYER",
            "api_token": "",
            "timeout_seconds": 15,
        }

        refreshed = utils.refresh_brawl_stars_api_token_if_enabled(config)

        self.assertEqual(refreshed["api_token"], "NEW_TOKEN")
        self.assertEqual(
            [call.args[1] for call in mock_post.call_args_list],
            ["login", "account/load", "login", "account/load", "apikey/list", "apikey/create"],
        )

    @patch("utils.refresh_brawl_stars_api_token_if_enabled")
    def test_load_config_uses_existing_token_when_auto_refresh_session_fails(self, mock_refresh):
        utils._brawl_stars_api_refresh_done = False
        utils._brawl_stars_api_refresh_signature = None
        mock_refresh.side_effect = RuntimeError("Developer portal error 401 at account/load: Session not found")
        path = "cfg/test_brawl_stars_api_existing_token.toml"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    'api_token = "OLD_TOKEN"\n'
                    'player_tag = "#PLAYER"\n'
                    'auto_refresh_token = true\n'
                    'developer_email = "user@example.com"\n'
                    'developer_password = "secret"\n'
                )

            config = utils.load_brawl_stars_api_config(path)

            self.assertEqual(config["api_token"], "OLD_TOKEN")
            self.assertTrue(utils._brawl_stars_api_refresh_done)
        finally:
            import os
            utils.clear_toml_cache(path)
            if os.path.exists(path):
                os.remove(path)

    @patch("utils.refresh_brawl_stars_api_token_if_enabled")
    def test_force_refresh_still_reports_developer_refresh_failure(self, mock_refresh):
        mock_refresh.side_effect = RuntimeError("Developer portal error 401 at account/load: Session not found")
        path = "cfg/test_brawl_stars_api_force_refresh.toml"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    'api_token = "OLD_TOKEN"\n'
                    'player_tag = "#PLAYER"\n'
                    'auto_refresh_token = true\n'
                    'developer_email = "user@example.com"\n'
                    'developer_password = "secret"\n'
                )

            with self.assertRaisesRegex(RuntimeError, "Session not found"):
                utils.load_brawl_stars_api_config(path, force_refresh=True)
        finally:
            import os
            utils.clear_toml_cache(path)
            if os.path.exists(path):
                os.remove(path)

    @patch("utils.refresh_brawl_stars_api_token_if_enabled")
    def test_api_config_is_reloaded_fresh(self, mock_refresh):
        mock_refresh.side_effect = lambda config, file_path: config
        path = "cfg/test_brawl_stars_api_autofill.toml"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write('api_token = ""\nplayer_tag = "#FIRST"\nauto_refresh_token = false\n')
            self.assertEqual(utils.load_brawl_stars_api_config(path)["player_tag"], "#FIRST")

            with open(path, "w", encoding="utf-8") as f:
                f.write('api_token = ""\nplayer_tag = "#SECOND"\nauto_refresh_token = false\n')
            self.assertEqual(utils.load_brawl_stars_api_config(path)["player_tag"], "#SECOND")
        finally:
            import os
            utils.clear_toml_cache(path)
            if os.path.exists(path):
                os.remove(path)

    @patch("utils.refresh_brawl_stars_api_token_if_enabled")
    def test_api_config_path_is_project_relative_not_cwd_relative(self, mock_refresh):
        mock_refresh.side_effect = lambda config, file_path: config
        path = "cfg/test_brawl_stars_api_project_relative.toml"
        original_cwd = os.getcwd()
        try:
            Path(path).write_text(
                'api_token = ""\nplayer_tag = "#PROJECT"\nauto_refresh_token = false\n',
                encoding="utf-8",
            )
            with tempfile.TemporaryDirectory() as tmp:
                os.chdir(tmp)
                config = utils.load_brawl_stars_api_config(path)
                os.chdir(original_cwd)

            self.assertEqual(config["player_tag"], "#PROJECT")
        finally:
            os.chdir(original_cwd)
            utils.clear_toml_cache(path)
            if os.path.exists(path):
                os.remove(path)

    @patch("utils.refresh_brawl_stars_api_token_if_enabled")
    def test_default_api_config_merges_local_override(self, mock_refresh):
        mock_refresh.side_effect = lambda config, file_path: config
        local_path = utils.LOCAL_BRAWL_STARS_API_CONFIG_PATH
        try:
            Path(local_path).write_text(
                'player_tag = "#LOCAL"\n'
                'developer_email = "local@example.com"\n'
                'developer_password = "secret"\n',
                encoding="utf-8",
            )

            config = utils.load_brawl_stars_api_config()

            self.assertEqual(config["player_tag"], "#LOCAL")
            self.assertEqual(config["developer_email"], "local@example.com")
            self.assertEqual(config["developer_password"], "secret")
        finally:
            utils.clear_toml_cache(local_path)
            if os.path.exists(local_path):
                os.remove(local_path)

    @patch("utils.refresh_brawl_stars_api_token_if_enabled")
    def test_fallback_parser_accepts_unquoted_credentials_after_toml_error(self, mock_refresh):
        mock_refresh.side_effect = lambda config, file_path: config
        path = "cfg/test_brawl_stars_api_unquoted.toml"
        try:
            Path(path).write_text(
                'player_tag = "#PLAYER"\n'
                'auto_refresh_token = true\n'
                'developer_email = user@example.com\n'
                'developer_password = secret-password\n',
                encoding="utf-8",
            )

            config = utils.load_brawl_stars_api_config(path)

            self.assertEqual(config["developer_email"], "user@example.com")
            self.assertEqual(config["developer_password"], "secret-password")
            self.assertEqual(config["player_tag"], "#PLAYER")
        finally:
            utils.clear_toml_cache(path)
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
