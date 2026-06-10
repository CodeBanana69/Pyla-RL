import math
import unittest

from play import Play


class CombatLosDodgeTests(unittest.TestCase):
    def _make_play(self):
        play = Play.__new__(Play)
        play.combat_los_dodge_enabled = True
        play.combat_dodge_blend = 0.5
        play.combat_dodge_jitter_degrees = 0.0
        play.is_there_enemy = lambda enemies: bool(enemies)
        play.find_closest_enemy = lambda *_args, **_kwargs: ((300, 100), 250.0)
        play.is_enemy_hittable = lambda *_args, **_kwargs: True
        play.is_path_blocked = lambda *_args, **_kwargs: False
        play.get_entity_pos = Play.get_entity_pos
        play.get_random_movement = lambda: (10, -10)
        play._evasion_active = False
        play._spacing_action = None
        return play

    def test_disabled_returns_base_movement(self):
        play = self._make_play()
        play.combat_los_dodge_enabled = False
        base = (50.0, 0.0)
        data = {"player": [[0, 0, 100, 100]], "enemy": [[250, 50, 350, 150]], "wall": []}
        self.assertEqual(play.apply_los_evasion_movement("shelly", data, base), base)
        self.assertFalse(play._evasion_active)

    def test_no_dodge_when_line_of_sight_blocked(self):
        play = self._make_play()
        play.is_enemy_hittable = lambda *_args, **_kwargs: False
        base = (50.0, 0.0)
        data = {"player": [[0, 0, 100, 100]], "enemy": [[250, 50, 350, 150]], "wall": [[200, 0, 220, 200]]}
        result = play.apply_los_evasion_movement("shelly", data, base)
        self.assertEqual(result, base)
        self.assertFalse(play._evasion_active)

    def test_dodge_changes_movement_when_hittable(self):
        play = self._make_play()
        base = (80.0, 0.0)
        data = {"player": [[0, 0, 100, 100]], "enemy": [[250, 50, 350, 150]], "wall": []}
        result = play.apply_los_evasion_movement("shelly", data, base)
        self.assertNotEqual(result, base)
        self.assertTrue(play._evasion_active)
        self.assertEqual(play._spacing_action, "dodge")
        perpendicularish = abs(result[1]) > 5 or abs(result[0] - base[0]) > 5
        self.assertTrue(perpendicularish)

    def test_wall_blocked_fallback_returns_base(self):
        play = self._make_play()
        play.is_path_blocked = lambda *_args, **_kwargs: True
        base = (80.0, 0.0)
        data = {"player": [[0, 0, 100, 100]], "enemy": [[250, 50, 350, 150]], "wall": []}
        result = play.apply_los_evasion_movement("shelly", data, base)
        self.assertEqual(result, base)
        self.assertFalse(play._evasion_active)

    def test_blend_zero_skips_dodge(self):
        play = self._make_play()
        play.combat_dodge_blend = 0.0
        base = (80.0, 0.0)
        data = {"player": [[0, 0, 100, 100]], "enemy": [[250, 50, 350, 150]], "wall": []}
        self.assertEqual(play.apply_los_evasion_movement("shelly", data, base), base)


if __name__ == "__main__":
    unittest.main()
