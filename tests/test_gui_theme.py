import unittest

from gui.theme import THEME


class GuiThemeTests(unittest.TestCase):
    def test_modern_theme_exposes_handoff_tokens(self):
        for key in (
            "bg",
            "surface",
            "surface_2",
            "surface_3",
            "hairline",
            "hairline_strong",
            "accent",
            "accent_soft",
            "accent_ring",
            "text",
            "muted",
            "muted_2",
        ):
            self.assertIn(key, THEME)

    def test_theme_values_are_tk_color_strings(self):
        for key, value in THEME.items():
            with self.subTest(key=key):
                self.assertIsInstance(value, str)
                self.assertTrue(value.startswith("#"))


if __name__ == "__main__":
    unittest.main()
