import tempfile
import unittest
from pathlib import Path

import toml

from gui.hub_state import HubStateStore
from play import Play
from utils import load_pyla_script


class FakeWindow:
    scale_factor = 1.0
    width_ratio = 1.0
    height_ratio = 1.0
    width = 1920
    height = 1080


class EnemySpacingTests(unittest.TestCase):
    def setUp(self):
        self.play = Play.__new__(Play)
        self.play.window_controller = FakeWindow()
        self.play.brawler_ranges = {"shelly": (301, 490, 490)}
        self.play.brawlers_info = {"shelly": {"safe_range": 301.0, "attack_range": 490.0, "super_range": 490}}
        self.play.get_brawler_range = lambda brawler: self.play.brawler_ranges[brawler]
        self.play.is_path_blocked = lambda *_args, **_kwargs: False
        self.play._spacing_strafe_side = 1

    def test_effective_range_blend_values(self):
        self.play.enemy_spacing_enabled = True
        self.play.enemy_spacing_blend = 0.0
        self.assertEqual(self.play.get_effective_enemy_range("shelly"), 301)
        self.play.enemy_spacing_blend = 0.5
        self.assertEqual(self.play.get_effective_enemy_range("shelly"), 395)
        self.play.enemy_spacing_blend = 1.0
        self.assertEqual(self.play.get_effective_enemy_range("shelly"), 490)

    def test_disabled_mode_uses_safe_range(self):
        self.play.enemy_spacing_enabled = False
        self.play.enemy_spacing_blend = 1.0
        self.assertEqual(self.play.get_effective_enemy_range("shelly"), 301)

    def test_spacing_action_hysteresis(self):
        target = 400
        tolerance = 40
        self.assertEqual(Play.get_enemy_spacing_action(450, target, tolerance), "approach")
        self.assertEqual(Play.get_enemy_spacing_action(350, target, tolerance), "retreat")
        self.assertEqual(Play.get_enemy_spacing_action(410, target, tolerance), "hold")
        self.assertEqual(Play.get_enemy_spacing_action(390, target, tolerance), "hold")

    def test_disabled_spacing_uses_legacy_threshold(self):
        self.play.enemy_spacing_enabled = False
        movement_far = self.play.get_enemy_spacing_movement(
            [0, 0, 100, 100],
            (50, 50),
            (500, 50),
            450,
            "shelly",
            [],
        )
        movement_near = self.play.get_enemy_spacing_movement(
            [0, 0, 100, 100],
            (50, 50),
            (200, 50),
            150,
            "shelly",
            [],
        )
        self.assertGreater(movement_far[0], 0)
        self.assertLess(movement_near[0], 0)

    def test_team_showdown_references_spacing_helper(self):
        _, code = load_pyla_script("team_showdown.pyla")
        self.assertIn("get_enemy_spacing_movement", code)

    def test_hub_roundtrip_persists_spacing_settings(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        bot_path = root / "bot_config.toml"
        general_path = root / "general_config.toml"
        timer_path = root / "time_tresholds.toml"
        history_path = root / "match_history.toml"
        discord_path = root / "discord_config.toml"
        telegram_base_path = root / "telegram_config.toml"
        telegram_local_path = root / "telegram_config.local.toml"
        api_base_path = root / "brawl_stars_api.toml"
        api_local_path = root / "brawl_stars_api.local.toml"
        for path in (
            bot_path,
            general_path,
            timer_path,
            history_path,
            discord_path,
            telegram_base_path,
            telegram_local_path,
            api_base_path,
            api_local_path,
        ):
            path.write_text(toml.dumps({}), encoding="utf-8")

        store = HubStateStore(
            str(bot_path),
            str(general_path),
            str(timer_path),
            str(history_path),
            str(discord_path),
            str(telegram_base_path),
            str(telegram_local_path),
            str(api_base_path),
            str(api_local_path),
        )
        store.update_config("settings", "enemy_spacing_enabled", True)
        store.update_config("settings", "enemy_spacing_blend", 0.6)
        store.update_config("settings", "enemy_spacing_tolerance", 55)
        store.update_config("settings", "enemy_spacing_hold_strafe", False)

        saved = toml.loads(bot_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["enemy_spacing_enabled"], "yes")
        self.assertAlmostEqual(float(saved["enemy_spacing_blend"]), 0.6)
        self.assertAlmostEqual(float(saved["enemy_spacing_tolerance"]), 55.0)
        self.assertEqual(saved["enemy_spacing_hold_strafe"], "no")


if __name__ == "__main__":
    unittest.main()
