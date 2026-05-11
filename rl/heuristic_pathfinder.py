"""Local grid A* pathfinding for heuristic showdown movement."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

Point = Tuple[float, float]
WallBox = Sequence[float]


@dataclass
class PathPlanDebug:
    desired_angle: float
    step_angle: Optional[float]
    tile_px: float
    grid_cells: List[Tuple[float, float, bool]]
    path_world: List[Tuple[float, float]]
    goal_world: Optional[Tuple[float, float]]


def _angle_from_direction(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dy, dx)) % 360.0


def _snap_angle(angle: float, step_deg: float) -> float:
    if step_deg <= 0:
        return angle % 360.0
    snapped = round(angle / step_deg) * step_deg
    return snapped % 360.0


class LocalGridPlanner:
    """Plan a single movement step on a small tile grid around the player."""

    def __init__(self, step_deg: float = 5.0) -> None:
        self.step_deg = float(step_deg)

    def plan_step_angle(
        self,
        player_pos: Point,
        desired_angle: float,
        walls: Sequence[WallBox],
        tile_px: float,
        padding_px: float,
        radius_tiles: int,
        max_iters: int,
        blocked_fn: Optional[Callable[[Point, Point, Sequence[WallBox], float], bool]] = None,
    ) -> Optional[float]:
        return self.plan_step_debug(
            player_pos,
            desired_angle,
            walls,
            tile_px=tile_px,
            padding_px=padding_px,
            radius_tiles=radius_tiles,
            max_iters=max_iters,
            blocked_fn=blocked_fn,
        ).step_angle

    def plan_step_debug(
        self,
        player_pos: Point,
        desired_angle: float,
        walls: Sequence[WallBox],
        tile_px: float,
        padding_px: float,
        radius_tiles: int,
        max_iters: int,
        blocked_fn: Optional[Callable[[Point, Point, Sequence[WallBox], float], bool]] = None,
    ) -> PathPlanDebug:
        empty = PathPlanDebug(
            desired_angle=float(desired_angle) % 360.0,
            step_angle=None,
            tile_px=float(tile_px),
            grid_cells=[],
            path_world=[],
            goal_world=None,
        )
        if tile_px <= 0:
            return empty

        radius = max(1, int(radius_tiles))
        size = 2 * radius + 1
        center = radius
        px, py = float(player_pos[0]), float(player_pos[1])
        tile = float(tile_px)
        padding = float(max(0.0, padding_px))

        if blocked_fn is None:
            raise ValueError("blocked_fn is required")
        blocked = blocked_fn

        def cell_blocked(gx: int, gy: int) -> bool:
            if gx == center and gy == center:
                return False
            wx = px + (gx - center) * tile
            wy = py + (gy - center) * tile
            return bool(blocked((px, py), (wx, wy), walls, padding))

        def cell_world(gx: int, gy: int) -> Tuple[float, float]:
            return px + (gx - center) * tile, py + (gy - center) * tile

        grid = [[cell_blocked(x, y) for y in range(size)] for x in range(size)]
        grid_cells = [
            (cell_world(gx, gy)[0], cell_world(gx, gy)[1], grid[gx][gy])
            for gx in range(size)
            for gy in range(size)
        ]
        if grid[center][center]:
            return PathPlanDebug(
                desired_angle=float(desired_angle) % 360.0,
                step_angle=None,
                tile_px=tile,
                grid_cells=grid_cells,
                path_world=[],
                goal_world=None,
            )

        goal = self._pick_goal_cell(grid, center, desired_angle)
        if goal is None:
            return PathPlanDebug(
                desired_angle=float(desired_angle) % 360.0,
                step_angle=None,
                tile_px=tile,
                grid_cells=grid_cells,
                path_world=[],
                goal_world=None,
            )

        path = self._astar(grid, (center, center), goal, max_iters)
        path_world = [cell_world(gx, gy) for gx, gy in path] if path else []
        goal_world = cell_world(goal[0], goal[1])
        if not path or len(path) < 2:
            return PathPlanDebug(
                desired_angle=float(desired_angle) % 360.0,
                step_angle=None,
                tile_px=tile,
                grid_cells=grid_cells,
                path_world=path_world,
                goal_world=goal_world,
            )

        nx, ny = path[1]
        dx = (nx - center) * tile
        dy = (ny - center) * tile
        if math.hypot(dx, dy) < 1e-6:
            step_angle = None
        else:
            step_angle = _snap_angle(_angle_from_direction(dx, dy), self.step_deg)
        return PathPlanDebug(
            desired_angle=float(desired_angle) % 360.0,
            step_angle=step_angle,
            tile_px=tile,
            grid_cells=grid_cells,
            path_world=path_world,
            goal_world=goal_world,
        )

    def _pick_goal_cell(
        self,
        grid: List[List[bool]],
        center: int,
        desired_angle: float,
    ) -> Optional[Tuple[int, int]]:
        size = len(grid)
        rad = math.radians(desired_angle)
        ux = math.cos(rad)
        uy = math.sin(rad)

        best: Optional[Tuple[float, Tuple[int, int]]] = None
        for gx in range(size):
            for gy in range(size):
                if gx == center and gy == center:
                    continue
                if grid[gx][gy]:
                    continue
                dx = gx - center
                dy = gy - center
                dist = math.hypot(dx, dy)
                if dist < 1e-6:
                    continue
                alignment = (dx * ux + dy * uy) / dist
                score = (-alignment, -dist)
                if best is None or score < best[0]:
                    best = (score, (gx, gy))

        if best is not None:
            return best[1]

        for gx in range(size):
            for gy in range(size):
                if gx == center and gy == center:
                    continue
                if not grid[gx][gy]:
                    return gx, gy
        return None

    def _astar(
        self,
        grid: List[List[bool]],
        start: Tuple[int, int],
        goal: Tuple[int, int],
        max_iters: int,
    ) -> Optional[List[Tuple[int, int]]]:
        size = len(grid)
        sx, sy = start
        gx, gy = goal
        if grid[sx][sy] or grid[gx][gy]:
            return None

        neighbors = (
            (-1, 0, 1.0),
            (1, 0, 1.0),
            (0, -1, 1.0),
            (0, 1, 1.0),
            (-1, -1, math.sqrt(2.0)),
            (-1, 1, math.sqrt(2.0)),
            (1, -1, math.sqrt(2.0)),
            (1, 1, math.sqrt(2.0)),
        )

        def heuristic(ax: int, ay: int) -> float:
            return max(abs(ax - gx), abs(ay - gy))

        open_heap: List[Tuple[float, int, Tuple[int, int]]] = []
        counter = 0
        g_score = {start: 0.0}
        came_from: dict[Tuple[int, int], Tuple[int, int]] = {}
        heapq.heappush(open_heap, (heuristic(sx, sy), counter, start))

        iters = 0
        while open_heap and iters < max(1, int(max_iters)):
            iters += 1
            _, _, current = heapq.heappop(open_heap)
            if current == goal:
                return self._reconstruct_path(came_from, current)

            cx, cy = current
            for dx, dy, step_cost in neighbors:
                nx, ny = cx + dx, cy + dy
                if nx < 0 or ny < 0 or nx >= size or ny >= size:
                    continue
                if grid[nx][ny]:
                    continue
                if dx != 0 and dy != 0:
                    if grid[cx + dx][cy] or grid[cx][cy + dy]:
                        continue

                tentative = g_score[current] + step_cost
                nxt = (nx, ny)
                if tentative >= g_score.get(nxt, float("inf")):
                    continue
                came_from[nxt] = current
                g_score[nxt] = tentative
                counter += 1
                f_score = tentative + heuristic(nx, ny)
                heapq.heappush(open_heap, (f_score, counter, nxt))

        return None

    @staticmethod
    def _reconstruct_path(
        came_from: dict[Tuple[int, int], Tuple[int, int]],
        current: Tuple[int, int],
    ) -> List[Tuple[int, int]]:
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path
