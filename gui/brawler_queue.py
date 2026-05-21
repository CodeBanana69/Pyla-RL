import json
from pathlib import Path

from utils import (
    fetch_brawl_stars_player,
    get_brawler_list,
    load_brawl_stars_api_config,
    normalize_brawler_name,
    save_brawler_data,
)

QUEUE_PATH = Path("latest_brawler_data.json")
PUSH_ORDER_PATH = Path("cfg/push_order.json")


def load_queue(path=None):
    queue_path = Path(path or QUEUE_PATH)
    if not queue_path.exists():
        return []
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_queue(data, path=None):
    queue_path = Path(path or QUEUE_PATH)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return str(queue_path.resolve())


def load_push_order(path=None):
    order_path = Path(path or PUSH_ORDER_PATH)
    if not order_path.exists():
        return []
    try:
        data = json.loads(order_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_push_order(order, path=None):
    order_path = Path(path or PUSH_ORDER_PATH)
    order_path.parent.mkdir(parents=True, exist_ok=True)
    order_path.write_text(json.dumps(list(order), indent=2), encoding="utf-8")
    return str(order_path.resolve())


def queue_item_icon_uri(brawler):
    icon_path = Path("api") / "assets" / "brawler_icons" / f"{brawler}.png"
    return icon_path.resolve().as_uri() if icon_path.exists() else ""


def queue_state_items(queue):
    items = []
    for index, row in enumerate(queue):
        if not isinstance(row, dict):
            continue
        brawler = str(row.get("brawler", "") or "")
        items.append({
            "index": index,
            "brawler": brawler,
            "target": row.get("push_until", row.get("wins", "")),
            "type": str(row.get("type", "trophies") or "trophies"),
            "autoPick": bool(row.get("automatically_pick", False)),
            "trophies": row.get("trophies", ""),
            "icon": queue_item_icon_uri(brawler),
        })
    return items


def get_push_all_data(target_trophies=1000, brawlers=None):
    target_trophies = int(target_trophies)
    brawlers = brawlers or get_brawler_list()
    api_config = load_brawl_stars_api_config("cfg/brawl_stars_api.toml")
    player_data = fetch_brawl_stars_player(
        api_config.get("api_token", "").strip(),
        api_config.get("player_tag", "").strip(),
        int(api_config.get("timeout_seconds", 15)),
    )
    known_by_normalized_name = {
        normalize_brawler_name(brawler): brawler
        for brawler in brawlers
    }
    rows = []
    for index, api_brawler in enumerate(player_data.get("brawlers", [])):
        brawler = known_by_normalized_name.get(normalize_brawler_name(api_brawler.get("name", "")))
        if not brawler:
            continue
        trophies = int(api_brawler.get("trophies", 0))
        if trophies < target_trophies:
            rows.append((trophies, index, brawler))

    rows.sort(key=lambda item: (item[0], item[1]))
    data = []
    for idx, (trophies, _, brawler) in enumerate(rows):
        data.append({
            "brawler": brawler,
            "push_until": target_trophies,
            "trophies": trophies,
            "wins": 0,
            "type": "trophies",
            "automatically_pick": idx != 0,
            "selection_method": "lowest_trophies",
            "win_streak": 0,
        })
    return data


def apply_push_all_priority_order(data, priority_order):
    priority_order = [
        brawler
        for brawler in priority_order
        if any(row.get("brawler") == brawler for row in data)
    ]
    if not priority_order:
        return data

    priority_index = {brawler: index for index, brawler in enumerate(priority_order)}
    priority_rows = []
    remaining_rows = []
    for row in data:
        if row.get("brawler") in priority_index:
            priority_rows.append(dict(row))
        else:
            remaining_rows.append(dict(row))

    priority_rows.sort(key=lambda row: priority_index[row.get("brawler")])
    ordered = priority_rows + remaining_rows
    for index, row in enumerate(ordered):
        row["automatically_pick"] = True if priority_rows else index != 0
        if row.get("brawler") in priority_index:
            row["selection_method"] = "named_brawler"
    return ordered


def build_push_all_queue(target_trophies=1000, brawlers=None, priority_order=None):
    data = get_push_all_data(target_trophies, brawlers=brawlers)
    if priority_order:
        data = apply_push_all_priority_order(data, priority_order)
    return data


def persist_queue(data):
    save_brawler_data(data)
    return save_queue(data)
