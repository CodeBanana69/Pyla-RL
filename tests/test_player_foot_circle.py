import unittest

from play import Play


class PlayerFootCircleTests(unittest.TestCase):
    def test_foot_circle_touches_box_sides_and_sits_on_bottom(self):
        player = [100, 50, 160, 110]
        foot_x, foot_y, radius = Play.get_player_foot_circle(player)

        self.assertEqual(foot_x, 130.0)
        self.assertEqual(radius, 30.0)
        self.assertEqual(foot_y, 80.0)
        self.assertEqual(foot_x - radius, 100.0)
        self.assertEqual(foot_x + radius, 160.0)
        self.assertEqual(foot_y + radius, 110.0)

    def test_get_player_pos_uses_foot_center(self):
        player = [100, 50, 160, 110]
        pos = Play.get_player_pos(player)
        foot_x, foot_y, _ = Play.get_player_foot_circle(player)
        self.assertEqual(pos, (foot_x, foot_y))

    def test_minimum_radius_for_tiny_boxes(self):
        player = [10, 10, 14, 30]
        _, _, radius = Play.get_player_foot_circle(player)
        self.assertEqual(radius, 4.0)


if __name__ == "__main__":
    unittest.main()
