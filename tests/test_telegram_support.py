import tempfile
import unittest
import asyncio
from pathlib import Path
from unittest.mock import patch

import telegram_notifier
from runtime_control import PAUSED, RUNNING, read_state
from telegram_control import set_runtime_state


class TelegramSupportTests(unittest.TestCase):
    def test_local_config_overrides_template_without_committing_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "telegram_config.toml"
            local = Path(tmp) / "telegram_config.local.toml"
            base.write_text(
                'enabled = false\nbot_token = ""\n',
                encoding="utf-8",
            )
            local.write_text(
                'enabled = true\nbot_token = "local-token"\nnotification_chat_ids = [123]\nallowed_chat_ids = [456]\n',
                encoding="utf-8",
            )
            with patch.object(telegram_notifier, "TELEGRAM_CONFIG_PATH", str(base)), \
                    patch.object(telegram_notifier, "LOCAL_TELEGRAM_CONFIG_PATH", str(local)):
                settings = telegram_notifier.load_telegram_settings()

        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["bot_token"], "local-token")
        self.assertEqual(settings["notification_chat_ids"], ["123"])
        self.assertEqual(settings["allowed_chat_ids"], ["456"])

    def test_known_chats_are_remembered_for_picker_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            chat_path = Path(tmp) / "telegram_chats.toml"
            with patch.object(telegram_notifier, "TELEGRAM_CHATS_PATH", str(chat_path)):
                self.assertTrue(telegram_notifier.remember_chat_id(123))
                self.assertFalse(telegram_notifier.remember_chat_id("123"))
                self.assertTrue(telegram_notifier.remember_chat_id(456))
                self.assertEqual(telegram_notifier.load_known_chat_ids(), ["123", "456"])

    def test_notification_chat_ids_use_explicit_config_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            chat_path = Path(tmp) / "telegram_chats.toml"
            with patch.object(telegram_notifier, "TELEGRAM_CHATS_PATH", str(chat_path)):
                telegram_notifier.remember_chat_id(456)
                ids = telegram_notifier.notification_chat_ids({"notification_chat_ids": ["123", "456"]})
        self.assertEqual(ids, ["123", "456"])

    def test_notification_chat_ids_do_not_fall_back_to_known_chats(self):
        with tempfile.TemporaryDirectory() as tmp:
            chat_path = Path(tmp) / "telegram_chats.toml"
            with patch.object(telegram_notifier, "TELEGRAM_CHATS_PATH", str(chat_path)):
                telegram_notifier.remember_chat_id(456)
                ids = telegram_notifier.notification_chat_ids({"notification_chat_ids": []})
        self.assertEqual(ids, [])

    def test_allowed_chat_ids_fall_back_to_notification_chat_ids(self):
        self.assertEqual(
            telegram_notifier.allowed_chat_ids({"allowed_chat_ids": [], "notification_chat_ids": ["123"]}),
            ["123"],
        )

    def test_notify_refuses_multiple_chats_by_default(self):
        settings = {
            "enabled": True,
            "bot_token": "token",
            "notification_chat_ids": ["123", "456"],
            "allow_multiple_notification_chat_ids": False,
            "send_match_summary": True,
            "include_screenshot": False,
        }
        with patch.object(telegram_notifier, "load_telegram_settings", return_value=settings):
            sent = asyncio.run(telegram_notifier.async_notify_user("test", details={"state": "x"}))

        self.assertFalse(sent)

    def test_chat_ids_from_updates_extracts_unique_message_chats(self):
        updates = [
            {"message": {"chat": {"id": 123}}},
            {"message": {"chat": {"id": "123"}}},
            {"edited_message": {"chat": {"id": 456}}},
            {"message": {"text": "/start"}},
        ]

        self.assertEqual(telegram_notifier.chat_ids_from_updates(updates), ["123", "456"])

    def test_missing_config_defaults_are_ready_except_master_enable(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing_telegram_config.toml"
            missing_local = Path(tmp) / "missing_telegram_config.local.toml"
            with patch.object(telegram_notifier, "TELEGRAM_CONFIG_PATH", str(missing)), \
                    patch.object(telegram_notifier, "LOCAL_TELEGRAM_CONFIG_PATH", str(missing_local)):
                settings = telegram_notifier.load_telegram_settings()

        self.assertFalse(settings["enabled"])
        self.assertTrue(settings["send_match_summary"])
        self.assertTrue(settings["include_screenshot"])
        self.assertFalse(settings["allow_multiple_notification_chat_ids"])
        self.assertTrue(settings["remote_control_enabled"])

    def test_set_runtime_state_writes_pause_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "runtime.state"
            self.assertEqual(set_runtime_state(state_path, paused=True), PAUSED)
            self.assertEqual(read_state(state_path), PAUSED)
            self.assertEqual(set_runtime_state(state_path, paused=False), RUNNING)
            self.assertEqual(read_state(state_path), RUNNING)


if __name__ == "__main__":
    unittest.main()
