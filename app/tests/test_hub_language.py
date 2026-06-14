import unittest
from unittest import mock

from gui.hub_state import HubStateStore


class TestHubLanguage(unittest.TestCase):
    def test_static_meta_exposes_language_fields(self):
        store = HubStateStore()
        store.general_config = {
            "ui_language": "ru",
            "ui_language_selected": "no",
            "first_run_wizard": "yes",
            "license_accepted": "no",
        }
        meta = store._static_ui_meta()
        self.assertEqual(meta["uiLanguage"], "ru")
        self.assertFalse(meta["uiLanguageSelected"])
        self.assertIn("navTabIds", meta)
        self.assertIn("navItems", meta)
        self.assertEqual(len(meta["navTabIds"]), len(meta["navItems"]))
        self.assertEqual(meta["navItems"][0], "Обзор")

    def test_wizard_needs_language_when_unset(self):
        store = HubStateStore()
        store.general_config = {
            "ui_language": "en",
            "ui_language_selected": "no",
            "license_accepted": "no",
        }
        meta = store._static_ui_meta()
        self.assertFalse(meta["uiLanguageSelected"])

    def test_qml_has_language_wizard_and_tr(self):
        from pathlib import Path

        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")
        self.assertIn('function tr(key', qml)
        self.assertIn("wizard.language.title", qml)
        self.assertIn("setLanguage", qml)
        self.assertIn("wizardStep === 0", qml)


if __name__ == "__main__":
    unittest.main()
