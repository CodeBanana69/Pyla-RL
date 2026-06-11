import argparse
import csv
import json
import zipfile
from collections import Counter
from io import TextIOWrapper
from pathlib import Path


TILES_CSV = "assets/csv_logic/tiles.csv"
MAPS_CSV = "assets/csv_logic/maps.csv"
LOCATIONS_CSV = "assets/csv_logic/locations.csv"


def truthy(value):
    return str(value or "").strip().lower() in {"true", "yes", "1"}


def int_or_none(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def read_csv_from_apk(apk_path, member):
    with zipfile.ZipFile(apk_path) as apk:
        with apk.open(member) as raw:
            yield from csv.DictReader(TextIOWrapper(raw, encoding="utf-8-sig", newline=""))


def load_tiles(apk_path):
    rows = list(read_csv_from_apk(apk_path, TILES_CSV))
    tiles = {}
    for row in rows[1:]:
        code = (row.get("TileCode") or "").strip()
        dynamic_code = int_or_none(row.get("DynamicCode"))
        key = code if dynamic_code is None else f"{code}:{dynamic_code}"
        if not code:
            continue
        tiles[key] = {
            "name": row.get("Name", ""),
            "tile_code": code,
            "dynamic_code": dynamic_code,
            "blocks_movement": truthy(row.get("BlocksMovement")),
            "blocks_projectiles": truthy(row.get("BlocksProjectiles")),
            "destructible": truthy(row.get("IsDestructible")),
            "destructible_normal_weapon": truthy(row.get("IsDestructibleNormalWeapon")),
            "destructible_overtime": truthy(row.get("IsDestructibleOvertime")),
            "bouncer": truthy(row.get("IsBouncer")),
            "forest": truthy(row.get("IsForest")),
            "damage": int_or_none(row.get("Damage")) or 0,
            "speed_change": int_or_none(row.get("SpeedChange")) or 0,
            "health": int_or_none(row.get("Health")),
            "map_editor_visible": truthy(row.get("MapEditorVisible")),
        }

    # Grid maps use the base TileCode character, while dynamic/spawn variants
    # share symbols. Keep a compact base lookup for movement/path planning.
    base_tiles = {}
    for tile in tiles.values():
        code = tile["tile_code"]
        current = base_tiles.get(code)
        if current is None or tile["dynamic_code"] is None:
            base_tiles[code] = tile
    return tiles, base_tiles


def load_maps(apk_path):
    maps = {}
    current_name = None
    current_rows = []
    for row in list(read_csv_from_apk(apk_path, MAPS_CSV))[1:]:
        name = (row.get("Map") or "").strip()
        data = row.get("Data") or ""
        if name:
            if current_name is not None:
                maps[current_name] = current_rows
            current_name = name
            current_rows = []
        if current_name is not None and data:
            current_rows.append(data)

    if current_name is not None:
        maps[current_name] = current_rows
    return maps


def load_locations(apk_path):
    locations = {}
    for row in list(read_csv_from_apk(apk_path, LOCATIONS_CSV))[1:]:
        name = (row.get("Name") or "").strip()
        map_name = (row.get("Map") or "").strip()
        if name and map_name:
            locations[name] = {
                "map": map_name,
                "mode": row.get("GameModeVariation", ""),
                "theme": row.get("LocationTheme", ""),
                "disabled": truthy(row.get("Disabled")),
            }
    return locations


def summarize_map(grid, base_tiles):
    counts = Counter("".join(grid))
    blocking = set()
    projectile_blocking = set()
    forest = set()
    damaging = set()
    for code in counts:
        tile = base_tiles.get(code)
        if not tile:
            continue
        if tile["blocks_movement"]:
            blocking.add(code)
        if tile["blocks_projectiles"]:
            projectile_blocking.add(code)
        if tile["forest"]:
            forest.add(code)
        if tile["damage"]:
            damaging.add(code)
    return {
        "width": max((len(row) for row in grid), default=0),
        "height": len(grid),
        "tile_counts": dict(sorted(counts.items())),
        "blocking_codes": sorted(blocking),
        "projectile_blocking_codes": sorted(projectile_blocking),
        "forest_codes": sorted(forest),
        "damaging_codes": sorted(damaging),
    }


def map_objects(grid, base_tiles):
    objects = []
    for y, row in enumerate(grid):
        for x, code in enumerate(row):
            if code == ".":
                continue
            tile = base_tiles.get(code, {})
            objects.append({
                "x": x,
                "y": y,
                "code": code,
                "name": tile.get("name", "Unknown"),
                "blocks_movement": bool(tile.get("blocks_movement")),
                "blocks_projectiles": bool(tile.get("blocks_projectiles")),
                "destructible": bool(tile.get("destructible")),
                "forest": bool(tile.get("forest")),
                "damage": int(tile.get("damage") or 0),
                "speed_change": int(tile.get("speed_change") or 0),
            })
    return objects


def filter_locations(locations, modes=None, active_only=False):
    mode_set = {mode.strip() for mode in modes or [] if mode.strip()}
    filtered = {}
    for name, location in locations.items():
        if mode_set and location["mode"] not in mode_set:
            continue
        if active_only and location["disabled"]:
            continue
        filtered[name] = location
    return filtered


def build_filtered_index(index, modes=None, active_only=False, include_objects=False):
    locations = filter_locations(index["locations"], modes=modes, active_only=active_only)
    map_names = sorted({location["map"] for location in locations.values()})
    maps = {
        name: index["maps"][name]
        for name in map_names
        if name in index["maps"]
    }
    result = {
        "source_apk": index["source_apk"],
        "mode_filter": sorted({mode for mode in (modes or []) if mode}),
        "active_only": active_only,
        "tile_count": index["tile_count"],
        "map_count": len(maps),
        "location_count": len(locations),
        "tiles": index["tiles"],
        "base_tiles": index["base_tiles"],
        "maps": maps,
        "map_summaries": {
            name: index["map_summaries"][name]
            for name in maps
            if name in index["map_summaries"]
        },
        "locations": locations,
    }
    if include_objects:
        result["map_objects"] = {
            name: map_objects(grid, index["base_tiles"])
            for name, grid in maps.items()
        }
    return result


def build_index(apk_path):
    tiles, base_tiles = load_tiles(apk_path)
    maps = load_maps(apk_path)
    locations = load_locations(apk_path)
    map_summaries = {
        name: summarize_map(grid, base_tiles)
        for name, grid in maps.items()
    }
    return {
        "source_apk": str(Path(apk_path).resolve()),
        "tile_count": len(tiles),
        "map_count": len(maps),
        "location_count": len(locations),
        "tiles": tiles,
        "base_tiles": {code: tile for code, tile in sorted(base_tiles.items())},
        "maps": maps,
        "map_summaries": map_summaries,
        "locations": locations,
    }


def print_summary(index):
    blocking = [
        f"{code}={tile['name']}"
        for code, tile in index["base_tiles"].items()
        if tile["blocks_movement"]
    ]
    projectile = [
        f"{code}={tile['name']}"
        for code, tile in index["base_tiles"].items()
        if tile["blocks_projectiles"]
    ]
    forest = [
        f"{code}={tile['name']}"
        for code, tile in index["base_tiles"].items()
        if tile["forest"]
    ]

    print(f"Tiles: {index['tile_count']}")
    print(f"Maps: {index['map_count']}")
    print(f"Locations: {index['location_count']}")
    if index.get("mode_filter"):
        print(f"Mode filter: {', '.join(index['mode_filter'])}")
    if index.get("active_only"):
        print("Active locations only: yes")
    print("Movement-blocking tile codes:")
    print(", ".join(blocking))
    print("Projectile-blocking tile codes:")
    print(", ".join(projectile))
    print("Forest/bush tile codes:")
    print(", ".join(forest))


def main():
    parser = argparse.ArgumentParser(
        description="Extract Brawl Stars map grids and tile blocking metadata from an APK."
    )
    parser.add_argument("apk", help="Path to the Brawl Stars APK")
    parser.add_argument("--output", help="Optional JSON output path")
    parser.add_argument("--summary", action="store_true", help="Print a compact summary")
    parser.add_argument(
        "--mode",
        action="append",
        default=[],
        help="Filter locations by exact GameModeVariation. Can be repeated.",
    )
    parser.add_argument(
        "--trio-showdown",
        action="store_true",
        help="Shortcut for --mode TrioShowdown.",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Only include locations not marked Disabled in locations.csv.",
    )
    parser.add_argument(
        "--include-objects",
        action="store_true",
        help="Include every non-open map tile with coordinates and object flags.",
    )
    args = parser.parse_args()

    index = build_index(args.apk)
    modes = list(args.mode)
    if args.trio_showdown:
        modes.append("TrioShowdown")
    if modes or args.active_only or args.include_objects:
        index = build_filtered_index(
            index,
            modes=modes,
            active_only=args.active_only,
            include_objects=args.include_objects,
        )
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Wrote {output}")
    if args.summary or not args.output:
        print_summary(index)


if __name__ == "__main__":
    main()
