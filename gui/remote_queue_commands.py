from __future__ import annotations

from gui.brawler_queue import normalize_queue, normalize_queue_row
from utils import normalize_brawler_name


def _row_name(row: dict) -> str:
    return normalize_brawler_name(str(row.get("brawler", "") or ""))


def _find_row_index(queue: list[dict], brawler: str) -> int | None:
    target = normalize_brawler_name(brawler)
    if not target:
        return None
    for index, row in enumerate(queue):
        if _row_name(row) == target:
            return index
    return None


def format_queue_preview(queue, limit: int = 5) -> str:
    from gui.remote_formatting import format_queue_lines

    return format_queue_lines(queue, limit=limit)


def prioritize_brawler_in_queue(queue, brawler: str, push_until: int | None = None) -> tuple[list[dict], str]:
    queue = normalize_queue(list(queue or []))
    brawler = str(brawler or "").strip()
    if not brawler:
        return queue, "No brawler specified."

    if not queue:
        target = int(push_until if push_until is not None else 1000)
        row = normalize_queue_row({
            "brawler": brawler,
            "push_until": target,
            "trophies": 0,
            "selection_method": "named_brawler",
        })
        return [row], f"Created farm plan with {brawler.title()} (target {target})."

    front = dict(queue[0])
    if _row_name(front) == normalize_brawler_name(brawler):
        target = int(push_until if push_until is not None else front.get("push_until", 1000))
        front["push_until"] = target
        front["automatically_pick"] = True
        front["selection_method"] = "named_brawler"
        queue[0] = normalize_queue_row(front)
        return queue, f"Updated target for {brawler.title()} to {target}."

    existing_idx = _find_row_index(queue, brawler)
    former_front = dict(queue[0])
    if existing_idx is not None:
        pushed_row = dict(queue[existing_idx])
    else:
        pushed_row = normalize_queue_row({
            "brawler": brawler,
            "push_until": push_until if push_until is not None else former_front.get("push_until", 1000),
            "trophies": 0,
            "selection_method": "named_brawler",
        })

    if push_until is not None:
        pushed_row["push_until"] = int(push_until)
    pushed_row["brawler"] = brawler
    pushed_row["automatically_pick"] = True
    pushed_row["selection_method"] = "named_brawler"
    pushed_row = normalize_queue_row(pushed_row)

    rest = [
        dict(row)
        for index, row in enumerate(queue)
        if index not in {0, existing_idx}
    ]
    new_queue = normalize_queue([pushed_row, former_front, *rest])
    target = pushed_row["push_until"]
    return new_queue, f"Prioritized {brawler.title()} (target {target})."


def skip_current_brawler(queue) -> tuple[list[dict], str]:
    queue = normalize_queue(list(queue or []))
    if len(queue) < 2:
        return queue, "Need at least two brawlers in the farm plan to skip."

    skipped = queue[0].get("brawler", "?")
    next_brawler = queue[1].get("brawler", "?")
    new_queue = normalize_queue([queue[1], queue[0], *queue[2:]])
    return new_queue, f"Skipped {skipped}. Now playing {next_brawler}."


def remove_brawler_from_queue(queue, brawler: str) -> tuple[list[dict], str]:
    queue = normalize_queue(list(queue or []))
    brawler = str(brawler or "").strip()
    if not brawler:
        return queue, "No brawler specified."

    index = _find_row_index(queue, brawler)
    if index is None:
        return queue, f"{brawler.title()} is not in the farm plan."

    removed_name = queue[index].get("brawler", brawler)
    new_queue = normalize_queue(queue[:index] + queue[index + 1:])
    if not new_queue:
        return [], f"Removed {removed_name}. Farm plan is now empty."
    if index == 0:
        active = new_queue[0].get("brawler", "?")
        return new_queue, f"Removed {removed_name}. Now playing {active}."
    return new_queue, f"Removed {removed_name} from the farm plan."


def set_active_target(queue, push_until: int) -> tuple[list[dict], str]:
    queue = normalize_queue(list(queue or []))
    if not queue:
        return queue, "Farm plan is empty."

    target = int(push_until)
    queue[0] = normalize_queue_row({**queue[0], "push_until": target})
    brawler = queue[0].get("brawler", "?")
    return queue, f"Set target for {brawler} to {target}."
