import time
import unittest
from unittest.mock import patch

from play import Play


class CombatLosDodgeTests(unittest.TestCase):
    def _make_play(self):
        play = Play.__new__(Play)
        play.combat_los_dodge_enabled = True
        play.combat_dodge_blend = 0.5
        play.combat_dodge_jitter_degrees = 0.0
        play.combat_dodge_commit_seconds = 0.6
        play._dodge_side = 1
        play._dodge_committed_until = 0.0
        play._dodge_vector = None
        play._dodge_jitter_rad = 0.0
        play.is_there_enemy = lambda enemies: bool(enemies)
        play.find_closest_enemy = lambda *_args, **_kwargs: ((300, 100), 250.0)
        play.is_enemy_hittable = lambda *_args, **_kwargs: True
        play.is_path_blocked = lambda *_args, **_kwargs: False
        play.get_entity_pos = Play.get_entity_pos
        play._evasion_active = False
        play._spacing_action = None
        return play

    def _data(self):
        return {"player": [[0, 0, 100, 100]], "enemy": [[250, 50, 350, 150]], "wall": []}

    def test_disabled_returns_base_movement(self):
        play = self._make_play()
        play.combat_los_dodge_enabled = False
        base = (50.0, 0.0)
        self.assertEqual(play.apply_los_evasion_movement("shelly", self._data(), base), base)
        self.assertFalse(play._evasion_active)

    def test_no_dodge_when_line_of_sight_blocked(self):
        play = self._make_play()
        play.is_enemy_hittable = lambda *_args, **_kwargs: False
        base = (50.0, 0.0)
        result = play.apply_los_evasion_movement("shelly", self._data(), base)
        self.assertEqual(result, base)
        self.assertFalse(play._evasion_active)

    def test_dodge_changes_movement_when_hittable(self):
        play = self._make_play()
        base = (80.0, 0.0)
        result = play.apply_los_evasion_movement("shelly", self._data(), base)
        self.assertNotEqual(result, base)
        self.assertTrue(play._evasion_active)
        self.assertEqual(play._spacing_action, "dodge")
        perpendicularish = abs(result[1]) > 5 or abs(result[0] - base[0]) > 5
        self.assertTrue(perpendicularish)

    def test_wall_blocked_fallback_returns_base(self):
        play = self._make_play()
        play.is_path_blocked = lambda *_args, **_kwargs: True
        base = (80.0, 0.0)
        result = play.apply_los_evasion_movement("shelly", self._data(), base)
        self.assertEqual(result, base)
        self.assertFalse(play._evasion_active)

    def test_blend_zero_skips_dodge(self):
        play = self._make_play()
        play.combat_dodge_blend = 0.0
        base = (80.0, 0.0)
        self.assertEqual(play.apply_los_evasion_movement("shelly", self._data(), base), base)

    def test_dodge_vector_stays_committed_within_window(self):
        play = self._make_play()
        base = (80.0, 0.0)
        first = play.apply_los_evasion_movement("shelly", self._data(), base)
        second = play.apply_los_evasion_movement("shelly", self._data(), base)
        self.assertEqual(first, second)

    def test_dodge_side_alternates_between_commitments(self):
        play = self._make_play()
        base = (80.0, 0.0)
        first = play.apply_los_evasion_movement("shelly", self._data(), base)
        first_side = play._dodge_side
        play._dodge_committed_until = 0.0
        play._dodge_vector = None
        second = play.apply_los_evasion_movement("shelly", self._data(), base)
        self.assertNotEqual(first_side, play._dodge_side)
        self.assertNotEqual(first, second)

    def test_wall_blocked_committed_side_flips_and_recommits(self):
        play = self._make_play()
        blocked = {0}

        def path_blocked(_player, move, _walls):
            if blocked:
                blocked.clear()
                return True
            return False

        play.is_path_blocked = path_blocked
        base = (80.0, 0.0)
        play._dodge_vector = (10.0, 75.0)
        play._dodge_committed_until = time.time() + 1.0
        result = play.apply_los_evasion_movement("shelly", self._data(), base)
        self.assertTrue(play._evasion_active)
        self.assertNotEqual(result, base)

    @patch("play.time.time")
    def test_commitment_expires(self, mock_time):
        play = self._make_play()
        mock_time.return_value = 1000.0
        base = (80.0, 0.0)
        play.apply_los_evasion_movement("shelly", self._data(), base)
        self.assertTrue(play._dodge_is_committed(1000.0))
        mock_time.return_value = 1001.0
        play.is_enemy_hittable = lambda *_args, **_kwargs: False
        result = play.apply_los_evasion_movement("shelly", self._data(), base)
        self.assertEqual(result, base)
        self.assertFalse(play._dodge_is_committed(1001.0))


if __name__ == "__main__":
    unittest.main()
