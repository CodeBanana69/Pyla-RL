import math
import unittest

from play import Play
from rl.heuristic_pathfinder import LocalGridPlanner


class LocalGridPlannerTests(unittest.TestCase):
    def setUp(self):
        self.planner = LocalGridPlanner(step_deg=5.0)
        self.tile_px = 60.0
        self.padding = 0.0
        self.blocked = Play.walls_block_line_of_sight

    def plan(self, player_pos, desired_angle, walls, radius_tiles=4):
        return self.planner.plan_step_angle(
            player_pos,
            desired_angle,
            walls,
            tile_px=self.tile_px,
            padding_px=self.padding,
            radius_tiles=radius_tiles,
            max_iters=256,
            blocked_fn=self.blocked,
        )

    def test_open_corridor_moves_toward_goal(self):
        angle = self.plan((300.0, 300.0), 0.0, [])
        self.assertIsNotNone(angle)
        self.assertAlmostEqual(angle, 0.0, delta=5.0)

    def test_plan_step_debug_returns_grid_and_path(self):
        detail = self.planner.plan_step_debug(
            (300.0, 300.0),
            0.0,
            [],
            tile_px=self.tile_px,
            padding_px=self.padding,
            radius_tiles=4,
            max_iters=256,
            blocked_fn=self.blocked,
        )
        self.assertGreater(len(detail.grid_cells), 0)
        self.assertGreaterEqual(len(detail.path_world), 2)
        self.assertIsNotNone(detail.step_angle)

    def test_single_wall_routes_around(self):
        walls = [[330.0, 270.0, 390.0, 330.0]]
        angle = self.plan((300.0, 300.0), 0.0, walls)
        self.assertIsNotNone(angle)
        self.assertNotAlmostEqual(angle, 0.0, delta=1.0)

    def test_l_shape_prefers_detour_over_direct_block(self):
        walls = [
            [330.0, 270.0, 390.0, 330.0],
            [330.0, 330.0, 390.0, 390.0],
        ]
        angle = self.plan((300.0, 300.0), 0.0, walls)
        self.assertIsNotNone(angle)
        self.assertNotAlmostEqual(angle, 0.0, delta=1.0)

    def test_fully_enclosed_returns_none(self):
        walls = [
            [240.0, 240.0, 360.0, 270.0],
            [240.0, 330.0, 360.0, 360.0],
            [240.0, 270.0, 270.0, 330.0],
            [330.0, 270.0, 360.0, 330.0],
        ]
        angle = self.plan((300.0, 300.0), 0.0, walls, radius_tiles=2)
        self.assertIsNone(angle)

    def test_diagonal_corner_clip_guard(self):
        grid = [
            [False, False],
            [True, False],
        ]
        path = self.planner._astar(grid, (0, 0), (1, 1), 64)
        self.assertIsNotNone(path)
        self.assertEqual(path[:2], [(0, 0), (0, 1)])


if __name__ == "__main__":
    unittest.main()
