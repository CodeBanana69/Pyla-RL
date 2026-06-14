import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from i18n import (
    catalog_for_language,
    get_language,
    normalize_language,
    set_language,
    supported_languages,
    translate,
)


class TestI18n(unittest.TestCase):
    def setUp(self):
        import i18n

        i18n._current_language = "en"
        i18n._config_loader = None
        i18n.get_language.cache_clear()
        i18n._load_catalog.cache_clear()

    def test_supported_languages(self):
        self.assertEqual(supported_languages(), ("en", "ru"))

    def test_normalize_language(self):
        self.assertEqual(normalize_language("ru"), "ru")
        self.assertEqual(normalize_language("Russian"), "ru")
        self.assertEqual(normalize_language("en"), "en")
        self.assertEqual(normalize_language(None), "en")

    def test_translate_english(self):
        self.assertEqual(translate("nav.overview"), "Overview")

    def test_translate_russian(self):
        with mock.patch("i18n.get_language", return_value="ru"):
            self.assertEqual(translate("nav.overview"), "Обзор")

    def test_translate_interpolation(self):
        text = translate("nav.farmPlanCount", count=3)
        self.assertIn("3", text)

    def test_translate_fallback_to_english(self):
        with mock.patch("i18n.get_language", return_value="ru"):
            missing = translate("definitely.missing.key.xyz")
            self.assertEqual(missing, "definitely.missing.key.xyz")

    def test_translate_default(self):
        self.assertEqual(translate("missing.key", default="Fallback"), "Fallback")

    def test_catalog_for_language_merges_english(self):
        catalog = catalog_for_language("ru")
        self.assertEqual(catalog.get("nav.overview"), "Обзор")
        self.assertEqual(catalog.get("wizard.next"), "Далее")

    def test_set_language_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp) / "cfg"
            cfg_dir.mkdir()
            config_path = cfg_dir / "general_config.toml"
            config_path.write_text('ui_language = "en"\n', encoding="utf-8")

            with mock.patch("utils.load_toml_as_dict", return_value={"ui_language": "en"}):
                with mock.patch("utils.save_dict_as_toml") as save_mock:
                    set_language("ru", persist=True)
                    save_mock.assert_called_once()
                    saved = save_mock.call_args[0][0]
                    self.assertEqual(saved["ui_language"], "ru")
                    self.assertEqual(saved["ui_language_selected"], "yes")


if __name__ == "__main__":
    unittest.main()
