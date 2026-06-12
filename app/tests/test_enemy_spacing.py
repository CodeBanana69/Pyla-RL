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
        self.play.is_enemy_hittable = lambda *_args, **_kwargs: True
        self.play.get_tracked_enemy_velocity = lambda: (0.0, 0.0)
        self.play.enemy_spacing_enabled = True
        self.play.enemy_spacing_blend = 1.0
        self.play.enemy_spacing_tolerance = 40
        self.play.multi_enemy_flee_weight = 0.45
        self.play.approach_flank_blend = 0.12
        self.play.retreat_strafe_fraction = 0.0
        self.play.enemy_spacing_hold_strafe = False
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
        self.assertIn("get_multi_enemy_spacing_movement", code)

    def test_default_playstyle_references_multi_enemy_spacing(self):
        _, code = load_pyla_script("default.pyla")
        self.assertIn("get_multi_enemy_spacing_movement", code)

    def test_universal_smart_references_multi_enemy_spacing(self):
        _, code = load_pyla_script("universal_smart_v5_Slarckvul_Eddition.pyla")
        self.assertIn("get_multi_enemy_spacing_movement", code)

    def test_compute_multi_enemy_spacing_retreats_when_any_enemy_too_close(self):
        player_pos = (100.0, 100.0)
        enemies = [((140.0, 100.0), 40.0), ((710.0, 100.0), 610.0)]
        fx, fy, action, threat_count = Play.compute_multi_enemy_spacing_forces(
            player_pos,
            enemies,
            target=490,
            tolerance=40,
            flee_weight=0.45,
            approach_blend=0.12,
        )
        self.assertEqual(action, "retreat")
        self.assertEqual(threat_count, 2)
        self.assertLess(fx, 0.0)

    def test_compute_multi_enemy_spacing_approaches_when_all_too_far(self):
        player_pos = (100.0, 100.0)
        enemies = [((610.0, 100.0), 550.0), ((100.0, 620.0), 560.0)]
        fx, fy, action, _ = Play.compute_multi_enemy_spacing_forces(
            player_pos,
            enemies,
            target=490,
            tolerance=40,
            flee_weight=0.45,
            approach_blend=0.12,
        )
        self.assertEqual(action, "approach")
        self.assertGreater(abs(fx) + abs(fy), 0.0)

    def test_compute_multi_enemy_spacing_holds_when_all_in_band(self):
        player_pos = (100.0, 100.0)
        enemies = [((560.0, 100.0), 460.0), ((100.0, 570.0), 470.0)]
        _fx, _fy, action, _ = Play.compute_multi_enemy_spacing_forces(
            player_pos,
            enemies,
            target=490,
            tolerance=40,
            flee_weight=0.45,
            approach_blend=0.12,
        )
        self.assertEqual(action, "hold")

    def test_multi_enemy_spacing_movement_retreats_from_close_flank_enemy(self):
        player_pos = (100.0, 100.0)
        player_data = [70, 70, 130, 130]
        enemy_data = [
            [120, 90, 160, 110],
            [680, 90, 720, 110],
        ]
        movement = self.play.get_multi_enemy_spacing_movement(
            player_data,
            player_pos,
            enemy_data,
            "shelly",
            [],
        )
        self.assertEqual(self.play._spacing_action, "retreat")
        self.assertLess(movement[0], 0.0)

    def test_multi_enemy_flee_weight_increases_flank_retreat_force(self):
        player_pos = (0.0, 0.0)
        enemies = [((50.0, 0.0), 50.0), ((80.0, 0.0), 80.0)]
        low_fx, _, action_low, _ = Play.compute_multi_enemy_spacing_forces(
            player_pos, enemies, 490, 40, flee_weight=0.0, approach_blend=0.12
        )
        high_fx, _, action_high, _ = Play.compute_multi_enemy_spacing_forces(
            player_pos, enemies, 490, 40, flee_weight=1.0, approach_blend=0.12
        )
        self.assertEqual(action_low, "retreat")
        self.assertEqual(action_high, "retreat")
        self.assertLess(high_fx, low_fx)

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
        store.update_config("settings", "multi_enemy_flee_weight", 0.7)

        saved = toml.loads(bot_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["enemy_spacing_enabled"], "yes")
        self.assertAlmostEqual(float(saved["enemy_spacing_blend"]), 0.6)
        self.assertAlmostEqual(float(saved["enemy_spacing_tolerance"]), 55.0)
        self.assertEqual(saved["enemy_spacing_hold_strafe"], "no")
        self.assertAlmostEqual(float(saved["multi_enemy_flee_weight"]), 0.7)


if __name__ == "__main__":
    unittest.main()
