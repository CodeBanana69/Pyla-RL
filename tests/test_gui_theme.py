import unittest

from gui.theme import (
    DARK,
    LIGHT,
    THEME,
    normalize_theme_mode,
    qml_colors,
    qml_theme_payload,
    resolve_theme_mode,
)


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
        for palette in (DARK, LIGHT):
            for key, value in palette.items():
                with self.subTest(key=key):
                    self.assertIsInstance(value, str)
                    self.assertTrue(value.startswith("#"))

    def test_light_and_dark_palettes_share_keys_but_differ(self):
        self.assertEqual(set(DARK.keys()), set(LIGHT.keys()))
        self.assertNotEqual(DARK["bg"], LIGHT["bg"])
        self.assertNotEqual(DARK["text"], LIGHT["text"])

    def test_legacy_theme_alias_is_dark(self):
        self.assertIs(THEME, DARK)

    def test_normalize_theme_mode(self):
        self.assertEqual(normalize_theme_mode("LIGHT"), "light")
        self.assertEqual(normalize_theme_mode("dark"), "dark")
        self.assertEqual(normalize_theme_mode("system"), "system")
        self.assertEqual(normalize_theme_mode("bogus"), "system")
        self.assertEqual(normalize_theme_mode(None), "system")

    def test_resolve_theme_mode_returns_concrete_mode(self):
        self.assertIn(resolve_theme_mode("system"), ("light", "dark"))
        self.assertEqual(resolve_theme_mode("light"), "light")
        self.assertEqual(resolve_theme_mode("dark"), "dark")

    def test_qml_colors_provide_glass_tokens(self):
        for mode in ("light", "dark"):
            colors = qml_colors(mode)
            for key in (
                "bg",
                "chrome",
                "panel",
                "panel2",
                "panel3",
                "border",
                "borderSoft",
                "hover",
                "glassHighlight",
                "scrim",
                "text",
                "muted",
                "faint",
                "accent",
                "accentHover",
                "accentSoft",
                "accentBorder",
                "ok",
                "okSoft",
                "danger",
                "dangerSoft",
                "warnSoft",
                "knob",
                "disabled",
                "link",
                "glowA",
                "glowB",
                "glowC",
            ):
                with self.subTest(mode=mode, key=key):
                    self.assertIn(key, colors)
                    self.assertTrue(str(colors[key]).startswith("#"))
        # Glass surfaces carry an alpha channel for translucency.
        self.assertEqual(len(qml_colors("dark")["panel"]), 9)
        self.assertEqual(len(qml_colors("light")["panel"]), 9)

    def test_qml_theme_payload_structure(self):
        payload = qml_theme_payload("light", animations=False)
        self.assertEqual(payload["mode"], "light")
        self.assertEqual(payload["resolved"], "light")
        self.assertFalse(payload["animations"])
        self.assertIn("colors", payload)

        payload = qml_theme_payload("system", animations=True)
        self.assertEqual(payload["mode"], "system")
        self.assertIn(payload["resolved"], ("light", "dark"))
        self.assertTrue(payload["animations"])


if __name__ == "__main__":
    unittest.main()
