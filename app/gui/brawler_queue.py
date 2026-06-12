import json
from pathlib import Path

from utils import (
    DEFAULT_QUEUE_PATH,
    fetch_brawl_stars_player,
    get_brawler_list,
    load_brawl_stars_api_config,
    normalize_brawler_name,
    resolve_project_path,
    save_brawler_data,
)

QUEUE_PATH = Path(resolve_project_path(DEFAULT_QUEUE_PATH))
PUSH_ORDER_PATH = Path(resolve_project_path("cfg/push_order.json"))

QUEUE_SORT_MODES = {
    "cups_desc": "Cups high to low",
    "cups_asc": "Cups low to high",
    "gap_asc": "Closest to target",
    "gap_desc": "Furthest from target",
    "target_desc": "Target high to low",
    "target_asc": "Target low to high",
    "name_asc": "Name A to Z",
    "name_desc": "Name Z to A",
    "efficiency": "Best trophies/hour (analytics)",
}


def _active_queue_path(path=None):
    if path is not None:
        queue_path = Path(path)
        if not queue_path.is_absolute():
            return Path(resolve_project_path(path))
        return queue_path
    try:
        from gui.instance_config import get_queue_path

        return get_queue_path()
    except Exception:
        return QUEUE_PATH


def normalize_queue_row(row):
    if not isinstance(row, dict):
        return {}
    normalized = dict(row)
    normalized["brawler"] = str(normalized.get("brawler", "") or "")
    normalized["push_until"] = int(normalized.get("push_until", 1000) or 1000)
    normalized["trophies"] = int(normalized.get("trophies", 0) or 0)
    wins = normalized.get("wins", 0)
    normalized["wins"] = int(wins) if wins not in ("", None) else 0
    normalized["type"] = str(normalized.get("type", "trophies") or "trophies")
    normalized["automatically_pick"] = True
    normalized["selection_method"] = str(normalized.get("selection_method", "named_brawler") or "named_brawler")
    normalized["win_streak"] = int(normalized.get("win_streak", 0) or 0)
    sort_mode = str(normalized.get("queue_sort_mode", "") or "").strip()
    if sort_mode in QUEUE_SORT_MODES:
        normalized["queue_sort_mode"] = sort_mode
    return normalized


def normalize_queue(queue):
    if not isinstance(queue, list):
        return []
    normalized = []
    for row in queue:
        if not isinstance(row, dict):
            continue
        item = normalize_queue_row(row)
        if item.get("brawler"):
            normalized.append(item)
    return normalized


def load_queue(path=None):
    queue_path = _active_queue_path(path)
    if not queue_path.exists():
        return []
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return normalize_queue(data if isinstance(data, list) else [])


def save_queue(data, path=None):
    queue_path = _active_queue_path(path)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_queue(data if isinstance(data, list) else [])
    queue_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return str(queue_path.resolve())


def load_push_order(path=None):
    order_path = Path(path) if path else PUSH_ORDER_PATH
    if path:
        order_path = Path(resolve_project_path(path)) if not order_path.is_absolute() else order_path
    if not order_path.exists():
        return []
    try:
        data = json.loads(order_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_push_order(order, path=None):
    order_path = Path(path) if path else PUSH_ORDER_PATH
    if path:
        order_path = Path(resolve_project_path(path)) if not order_path.is_absolute() else order_path
    order_path.parent.mkdir(parents=True, exist_ok=True)
    order_path.write_text(json.dumps(list(order), indent=2), encoding="utf-8")
    return str(order_path.resolve())


def normalize_brawler_icon_name(brawler_name):
    return (
        str(brawler_name or "")
        .lower()
        .replace(" ", "")
        .replace("-", "")
        .replace(".", "")
        .replace("&", "")
    )


def brawler_icon_path(brawler_name):
    safe_name = normalize_brawler_icon_name(brawler_name)
    return Path(resolve_project_path(f"api/assets/brawler_icons/{safe_name}.png"))


def brawler_icon_uri(brawler_name):
    icon_path = brawler_icon_path(brawler_name)
    return icon_path.resolve().as_uri() if icon_path.exists() else ""


def queue_item_icon_uri(brawler):
    return brawler_icon_uri(brawler)


def _queue_progress_values(row):
    row_type = str(row.get("type", "trophies") or "trophies")
    if row_type == "wins":
        current = int(row.get("wins", 0) or 0)
        target = int(row.get("push_until", 0) or 0)
    else:
        current = int(row.get("trophies", 0) or 0)
        target = int(row.get("push_until", 0) or 0)
    gap = max(0, target - current)
    return current, target, gap


def sort_queue(queue, *, mode="cups_desc"):
    """Order farm-plan rows using a named sort mode."""
    normalized = normalize_queue(queue if isinstance(queue, list) else [])
    sort_mode = mode if mode in QUEUE_SORT_MODES else "cups_desc"

    def sort_key(row):
        brawler = str(row.get("brawler", "") or "").lower()
        trophies, target, gap = _queue_progress_values(row)
        if sort_mode == "cups_desc":
            return (-trophies, brawler)
        if sort_mode == "cups_asc":
            return (trophies, brawler)
        if sort_mode == "target_desc":
            return (-target, -trophies, brawler)
        if sort_mode == "target_asc":
            return (target, trophies, brawler)
        if sort_mode == "gap_asc":
            return (gap, -trophies, brawler)
        if sort_mode == "gap_desc":
            return (-gap, trophies, brawler)
        if sort_mode == "name_asc":
            return (brawler, -trophies)
        if sort_mode == "efficiency":
            from farm_analytics import efficiency_sort_key

            return efficiency_sort_key(row)
        return (brawler,)

    if sort_mode == "name_desc":
        normalized.sort(key=lambda row: str(row.get("brawler", "") or "").lower(), reverse=True)
    else:
        normalized.sort(key=sort_key)
    apply_push_all_sort_metadata(normalized, sort_mode)
    return normalized


def selection_method_for_sort_mode(mode):
    if mode == "cups_asc":
        return "lowest_trophies"
    if mode == "cups_desc":
        return "highest_trophies"
    return "named_brawler"


def get_queue_sort_mode(queue):
    for row in queue or []:
        mode = str(row.get("queue_sort_mode", "") or "").strip()
        if mode in QUEUE_SORT_MODES:
            return mode
    return None


def infer_queue_sort_mode(queue):
    stored = get_queue_sort_mode(queue)
    if stored:
        return stored
    if not queue:
        return None
    methods = {
        str(row.get("selection_method", "named_brawler") or "named_brawler")
        for row in queue
    }
    if "highest_trophies" in methods:
        return "cups_desc"
    if "lowest_trophies" in methods:
        return "cups_asc"
    return None


def resolve_queue_sort_mode(queue):
    return get_queue_sort_mode(queue) or infer_queue_sort_mode(queue)


def apply_push_all_sort_metadata(queue, mode):
    """Remember Hub sort mode so post-match API refresh re-sorts the same way."""
    sort_mode = mode if mode in QUEUE_SORT_MODES else "cups_asc"
    method = selection_method_for_sort_mode(sort_mode)
    for row in queue:
        row["queue_sort_mode"] = sort_mode
        current = str(row.get("selection_method", "named_brawler") or "named_brawler")
        if current in ("lowest_trophies", "highest_trophies"):
            row["selection_method"] = method
            row["automatically_pick"] = True
    return queue


def sort_push_all_rows(rows, *, mode=None):
    sort_mode = mode or resolve_queue_sort_mode(rows) or "cups_asc"
    sorted_rows = sort_queue(rows, mode=sort_mode)
    apply_push_all_sort_metadata(sorted_rows, sort_mode)
    return sorted_rows


def sort_queue_by_trophies(queue, *, descending=True):
    """Order farm-plan rows by current trophy count."""
    return sort_queue(queue, mode="cups_desc" if descending else "cups_asc")


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

    # Lowest cups first so Push All always farms the lowest remaining brawler next.
    rows.sort(key=lambda item: (item[0], item[1]))
    data = []
    for idx, (trophies, _, brawler) in enumerate(rows):
        data.append({
            "brawler": brawler,
            "push_until": target_trophies,
            "trophies": trophies,
            "wins": 0,
            "type": "trophies",
            "automatically_pick": True,
            "selection_method": "lowest_trophies",
            "win_streak": 0,
        })
    apply_push_all_sort_metadata(data, "cups_asc")
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
        row["automatically_pick"] = True
        if row.get("brawler") in priority_index:
            row["selection_method"] = "named_brawler"
    return ordered


def build_push_all_queue(target_trophies=1000, brawlers=None, priority_order=None):
    data = get_push_all_data(target_trophies, brawlers=brawlers)
    if priority_order:
        data = apply_push_all_priority_order(data, priority_order)
    return data


def persist_queue(data, path=None):
    if path is None:
        save_brawler_data(data)
    return save_queue(data, path)
