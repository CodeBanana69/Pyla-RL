import os
import tempfile
import unittest
from unittest.mock import patch

import discord
import toml

from support_reporter import (
    DEFAULT_SUPPORT_WEBHOOK_ENC,
    _fingerprint,
    _should_send,
    build_support_embed,
    collect_support_context,
    decrypt_webhook_url,
    encrypt_webhook_url,
    install,
    load_support_settings,
    report_support_event,
    sanitize_text,
)


class SupportReporterTests(unittest.TestCase):
    def test_encrypt_decrypt_webhook_roundtrip(self):
        url = (
            "https://discord.com/api/webhooks/123456789012345678/"
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ab"
        )
        encrypted = encrypt_webhook_url(url)
        self.assertNotIn("discord.com", encrypted)
        self.assertEqual(decrypt_webhook_url(encrypted), url)

    def test_default_encrypted_constant_roundtrips(self):
        decrypted = decrypt_webhook_url(DEFAULT_SUPPORT_WEBHOOK_ENC)
        self.assertTrue(decrypted.startswith("https://discord.com/api/webhooks/"))

    @patch("support_reporter.resolve_project_path")
    def test_load_settings_decrypts_encrypted_config(self, mock_resolve):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "support_reporting.local.toml")
            plain_url = (
                "https://discord.com/api/webhooks/999999999999999999/"
                "testtokenabcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ01"
            )
            with open(config_path, "w", encoding="utf-8") as f:
                toml.dump(
                    {
                        "enabled": True,
                        "webhook_url_encrypted": encrypt_webhook_url(plain_url),
                        "username": "Test Bot",
                        "min_interval_seconds": 60,
                    },
                    f,
                )
            mock_resolve.return_value = config_path
            settings = load_support_settings()
            self.assertEqual(settings["webhook_url"], plain_url)
            self.assertEqual(settings["username"], "Test Bot")
            self.assertEqual(settings["min_interval_seconds"], 60.0)

    @patch("utils.resolve_project_path")
    @patch("support_reporter.resolve_project_path")
    def test_load_settings_migrates_plaintext_webhook(self, mock_resolve_sr, mock_resolve_utils):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "support_reporting.local.toml")
            plain_url = (
                "https://discord.com/api/webhooks/888888888888888888/"
                "legacytokenabcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ01"
            )
            with open(config_path, "w", encoding="utf-8") as f:
                toml.dump(
                    {
                        "enabled": False,
                        "webhook_url": plain_url,
                        "username": "Legacy",
                    },
                    f,
                )
            mock_resolve_sr.return_value = config_path
            mock_resolve_utils.return_value = config_path
            settings = load_support_settings()
            self.assertEqual(settings["webhook_url"], plain_url)
            migrated = toml.load(config_path)
            self.assertNotIn("webhook_url", migrated)
            self.assertIn("webhook_url_encrypted", migrated)
            self.assertEqual(decrypt_webhook_url(migrated["webhook_url_encrypted"]), plain_url)

    def test_sanitize_text_redacts_webhook_urls(self):
        url = "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ab"
        cleaned = sanitize_text(f"failed at {url}")
        self.assertIn("[REDACTED]", cleaned)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", cleaned)

    def test_fingerprint_dedupe_suppresses_repeat(self):
        fp = _fingerprint("log_warn:recovery", "same message")
        self.assertTrue(_should_send("log_warn:recovery", fp, 120))
        self.assertFalse(_should_send("log_warn:recovery", fp, 120))

    def test_critical_triggers_bypass_dedupe(self):
        fp = _fingerprint("startup_crash", "boom")
        self.assertTrue(_should_send("startup_crash", fp, 120))
        self.assertTrue(_should_send("startup_crash", fp, 120))

    def test_build_support_embed_includes_trigger_and_message(self):
        embed = build_support_embed(
            {
                "trigger": "brawler_pick_failed",
                "message": "Automatic brawler pick failed for grom",
                "version": "0.8.1",
                "game_state": "lobby",
            }
        )
        self.assertIsInstance(embed, discord.Embed)
        self.assertIn("brawler_pick_failed", embed.title)
        self.assertIn("grom", embed.description)

    @patch("support_reporter.load_toml_as_dict", return_value={})
    @patch("support_reporter._build_info", return_value={})
    def test_collect_support_context_sanitizes_extra(self, _mock_build, _mock_toml):
        context = collect_support_context(
            "test",
            "hello",
            extra={
                "webhook_url": (
                    "https://discord.com/api/webhooks/123456789012345678/"
                    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ab"
                )
            },
        )
        self.assertIn("[REDACTED]", context["webhook_url"])

    @patch("support_reporter._dispatch_report")
    def test_report_support_event_dispatches(self, mock_dispatch):
        report_support_event("test_trigger", "hello world")
        mock_dispatch.assert_called_once()

    def test_install_sets_excepthook_once(self):
        import sys

        before = sys.excepthook
        install()
        first = sys.excepthook
        install()
        self.assertIs(sys.excepthook, first)
        self.assertIsNot(first, before)

    @patch("runtime_log._emit")
    def test_runtime_log_warn_still_emits(self, mock_emit):
        import runtime_log

        runtime_log.log_warn("recovery", "test warning")
        mock_emit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
