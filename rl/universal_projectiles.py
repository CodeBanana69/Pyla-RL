"""Universal projectile candidates without dedicated YOLO classes.

Combines labeled detector boxes, residual detector keys, and masked frame
diff blobs. Shared between Play.update_projectile_tracker and unit tests."""

from __future__ import annotations

from typing import List, Optional, Sequence, Set, Tuple, Union

import cv2
import numpy as np

# Reference 1920×1080 landscape — center x, center y, half_w, half_h
DEFAULT_UI_REFERENCE_RECTS: Tuple[Tuple[str, float, float, float, float], ...] = (
    ("joystick", 220.0, 870.0, 280.0, 280.0),
    ("attack", 1700.0, 870.0, 220.0, 220.0),
    ("super", 1500.0, 870.0, 160.0, 160.0),
    ("gadget", 1500.0, 720.0, 140.0, 140.0),
    ("hyper", 1700.0, 720.0, 140.0, 140.0),
    ("minimap", 1720.0, 130.0, 380.0, 240.0),
    ("score", 960.0, 60.0, 360.0, 110.0),
    ("ammo", 1500.0, 990.0, 360.0, 70.0),
)


def box_iou(a: Sequence[float], b: Sequence[float]) -> float:
    ax1, ay1, ax2, ay2 = map(float, a[:4])
    bx1, by1, bx2, by2 = map(float, b[:4])
    if ax2 < ax1:
        ax1, ax2 = ax2, ax1
    if ay2 < ay1:
        ay1, ay2 = ay2, ay1
    if bx2 < bx1:
        bx1, bx2 = bx2, bx1
    if by2 < by1:
        by1, by2 = by2, by1
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    iw = max(0.0, inter_x2 - inter_x1)
    ih = max(0.0, inter_y2 - inter_y1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _norm_xyxy(box: Sequence[float]) -> List[float]:
    x1, y1, x2, y2 = map(float, box[:4])
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return [x1, y1, x2, y2]


def _box_area(b: Sequence[float]) -> float:
    x1, y1, x2, y2 = _norm_xyxy(b)
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def collect_entity_wall_boxes(data: Optional[dict]) -> List[List[float]]:
    """Flatten player, teammate, enemy, wall boxes from a vision data dict."""
    if not data:
        return []
    out: List[List[float]] = []
    for key in ("player", "teammate", "enemy"):
        for box in data.get(key) or []:
            if len(box) >= 4:
                out.append([float(box[0]), float(box[1]), float(box[2]), float(box[3])])
    for box in data.get("wall") or []:
        if len(box) >= 4:
            out.append([float(box[0]), float(box[1]), float(box[2]), float(box[3])])
    return out


def extract_residual_projectile_boxes(
    data: dict,
    exclude_keys: Set[str],
    ref_boxes: Sequence[Sequence[float]],
    frame_size: Tuple[int, int],
    max_box_area_frac: float = 0.02,
    max_side_frac: float = 0.25,
    iou_exclude_thresh: float = 0.25,
    ui_exclude_boxes: Optional[Sequence[Sequence[float]]] = None,
) -> List[List[float]]:
    """Boxes from unknown detector keys, filtered by size and entity overlap."""
    fw, fh = max(1, int(frame_size[0])), max(1, int(frame_size[1]))
    frame_area = float(fw * fh)
    max_area = max(1.0, max_box_area_frac * frame_area)
    max_side = max(1.0, max_side_frac * max(fw, fh))
    out: List[List[float]] = []
    for key, val in data.items():
        if key in exclude_keys:
            continue
        if not isinstance(val, list) or not val:
            continue
        for box in val:
            if not isinstance(box, (list, tuple)) or len(box) < 4:
                continue
            x1, y1, x2, y2 = map(float, box[:4])
            if x2 < x1:
                x1, x2 = x2, x1
            if y2 < y1:
                y1, y2 = y2, y1
            w, h = x2 - x1, y2 - y1
            if w <= 0 or h <= 0:
                continue
            if w * h > max_area or max(w, h) > max_side:
                continue
            b = [x1, y1, x2, y2]
            if any(box_iou(b, r) >= iou_exclude_thresh for r in ref_boxes):
                continue
            cx = (x1 + x2) * 0.5
            cy = (y1 + y2) * 0.5
            if ui_exclude_boxes and _center_inside_any_rect(cx, cy, ui_exclude_boxes):
                continue
            out.append(b)
    return out


def _center_inside_any_rect(cx: float, cy: float, rects: Sequence[Sequence[float]]) -> bool:
    for r in rects:
        if len(r) < 4:
            continue
        x1, y1, x2, y2 = map(float, r[:4])
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            return True
    return False


def greedy_nms_xyxy(
    boxes: Sequence[Sequence[float]],
    iou_thresh: float,
) -> List[List[float]]:
    """Standard score-free NMS: keep larger boxes first when areas differ."""
    if not boxes:
        return []
    scored: List[Tuple[float, List[float]]] = []
    for b in boxes:
        x1, y1, x2, y2 = map(float, b[:4])
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        scored.append((area, [x1, y1, x2, y2]))
    scored.sort(key=lambda t: t[0], reverse=True)
    keep: List[List[float]] = []
    for _, b in scored:
        if any(box_iou(b, k) > iou_thresh for k in keep):
            continue
        keep.append(b)
    return keep


_SOURCE_PRIORITY = {"labeled": 3, "residual": 2, "motion": 1}


def merge_projectile_candidates(
    labeled: Sequence[Sequence[float]],
    residual: Sequence[Sequence[float]],
    motion: Sequence[Sequence[float]],
    nms_iou: float,
) -> List[List[float]]:
    merged: List[List[float]] = []
    for group in (labeled, residual, motion):
        for b in group:
            if len(b) >= 4:
                merged.append([float(b[0]), float(b[1]), float(b[2]), float(b[3])])
    return greedy_nms_xyxy(merged, nms_iou)


def merge_projectile_candidates_with_sources(
    labeled: Sequence[Sequence[float]],
    residual: Sequence[Sequence[float]],
    motion: Sequence[Sequence[float]],
    nms_iou: float,
) -> Tuple[List[List[float]], List[str]]:
    """NMS merging while preserving a per-box source label (labeled > residual > motion)."""
    items: List[Tuple[List[float], str]] = []
    for b in labeled:
        if len(b) >= 4:
            items.append((_norm_xyxy(b), "labeled"))
    for b in residual:
        if len(b) >= 4:
            items.append((_norm_xyxy(b), "residual"))
    for b in motion:
        if len(b) >= 4:
            items.append((_norm_xyxy(b), "motion"))
    if not items:
        return [], []

    def sort_key(it: Tuple[List[float], str]) -> Tuple[int, float]:
        box, src = it
        pr = _SOURCE_PRIORITY.get(src, 0)
        return (-pr, -_box_area(box))

    items.sort(key=sort_key)
    kept_boxes: List[List[float]] = []
    kept_sources: List[str] = []
    for box, src in items:
        if any(box_iou(box, k) > nms_iou for k in kept_boxes):
            continue
        kept_boxes.append(box)
        kept_sources.append(src)
    return kept_boxes, kept_sources


def _full_to_small_rect(
    box: Sequence[float],
    fw: int,
    fh: int,
    sw: int,
    sh: int,
) -> Tuple[int, int, int, int]:
    sx = sw / max(1, fw)
    sy = sh / max(1, fh)
    x1 = int(max(0, min(sw - 1, box[0] * sx)))
    y1 = int(max(0, min(sh - 1, box[1] * sy)))
    x2 = int(max(0, min(sw, box[2] * sx)))
    y2 = int(max(0, min(sh, box[3] * sy)))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return x1, y1, x2, y2


def raster_fog_roi_to_small_mask(
    fog_mask_roi: np.ndarray,
    origin: Tuple[int, int],
    frame_hw: Tuple[int, int],
    small_hw: Tuple[int, int],
) -> np.ndarray:
    """Map trusted fog ROI mask into motion-scale coordinates (full-frame raster)."""
    fh, fw = frame_hw
    sh, sw = small_hw
    out = np.zeros((sh, sw), dtype=np.uint8)
    ox, oy = int(origin[0]), int(origin[1])
    ys, xs = np.nonzero(fog_mask_roi)
    if ys.size == 0:
        return out
    fx = xs.astype(np.float64) + ox
    fy = ys.astype(np.float64) + oy
    sx_i = np.clip((fx * sw / max(1, fw)).astype(np.int32), 0, sw - 1)
    sy_i = np.clip((fy * sh / max(1, fh)).astype(np.int32), 0, sh - 1)
    out[sy_i, sx_i] = 255
    return out


def rgb_small(frame_rgb: np.ndarray, scale_width: int) -> np.ndarray:
    """Resize RGB to target width (same geometry as grayscale_small)."""
    h, w = frame_rgb.shape[:2]
    if w <= 0 or h <= 0:
        return np.zeros((1, 1, 3), dtype=np.uint8)
    sw = max(8, int(scale_width))
    sh = max(1, int(round(h * sw / max(1, w))))
    return cv2.resize(frame_rgb, (sw, sh), interpolation=cv2.INTER_AREA)


def align_prev_to_curr(
    prev_gray_small: np.ndarray,
    curr_gray_small: np.ndarray,
    *,
    min_response: float = 0.08,
) -> Tuple[np.ndarray, bool]:
    """Translate prev toward curr using phase correlation; reduces camera ego-motion in diff."""
    if prev_gray_small.shape != curr_gray_small.shape:
        return prev_gray_small, False
    sh, sw = prev_gray_small.shape[:2]
    if sh < 8 or sw < 8:
        return prev_gray_small, False

    p = prev_gray_small.astype(np.float32)
    c = curr_gray_small.astype(np.float32)
    try:
        (shift_x, shift_y), response = cv2.phaseCorrelate(p, c)
    except cv2.error:
        return prev_gray_small, False

    if not np.isfinite(shift_x) or not np.isfinite(shift_y):
        return prev_gray_small, False
    if float(response) < float(min_response):
        return prev_gray_small, False

    # Shift prev so its content aligns with curr (translate prev by +shift in image coords).
    M = np.array([[1.0, 0.0, float(shift_x)], [0.0, 1.0, float(shift_y)]], dtype=np.float32)
    aligned = cv2.warpAffine(
        prev_gray_small,
        M,
        (sw, sh),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return aligned, True


def trusted_fog_mask_small(
    frame_rgb: np.ndarray,
    *,
    fog_hsv_low: Tuple[int, int, int],
    fog_hsv_high: Tuple[int, int, int],
    scale_width: int,
    full_frame_area: int,
    full_min_blob_pixels: int,
    morph_kernel_size: int = 3,
    dilate_px: int = 2,
) -> np.ndarray:
    """Full-frame fog mask at motion resolution for excluding poison gas from motion diff."""
    rgb = rgb_small(frame_rgb, scale_width)
    sh, sw = rgb.shape[:2]
    small_area = max(1, sh * sw)
    scale_area = small_area / max(1, float(full_frame_area))
    min_blob_small = max(12, int(full_min_blob_pixels * scale_area))

    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    low = np.array(fog_hsv_low, dtype=np.uint8)
    high = np.array(fog_hsv_high, dtype=np.uint8)
    mask = cv2.inRange(hsv, low, high)

    ksz = max(1, int(morph_kernel_size)) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksz, ksz))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    trusted = np.zeros_like(mask)
    if num_labels > 1:
        for label in range(1, num_labels):
            if stats[label, cv2.CC_STAT_AREA] >= min_blob_small:
                trusted[labels == label] = 255

    if dilate_px > 0:
        dk = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (int(dilate_px) * 2 + 1, int(dilate_px) * 2 + 1),
        )
        trusted = cv2.dilate(trusted, dk)

    return trusted


def animated_terrain_mask_small(
    frame_rgb: np.ndarray,
    *,
    scale_width: int,
    hsv_ranges: Sequence[Tuple[Tuple[int, int, int], Tuple[int, int, int]]],
    dilate_px: int = 2,
) -> Optional[np.ndarray]:
    """Union of HSV ranges for water/lava/etc. Returns None if ranges empty."""
    if not hsv_ranges:
        return None
    rgb = rgb_small(frame_rgb, scale_width)
    sh, sw = rgb.shape[:2]
    out = np.zeros((sh, sw), dtype=np.uint8)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    for low_t, high_t in hsv_ranges:
        low = np.array(low_t, dtype=np.uint8)
        high = np.array(high_t, dtype=np.uint8)
        m = cv2.inRange(hsv, low, high)
        out = cv2.bitwise_or(out, m)
    if dilate_px > 0 and cv2.countNonZero(out) > 0:
        dk = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (int(dilate_px) * 2 + 1, int(dilate_px) * 2 + 1),
        )
        out = cv2.dilate(out, dk)
    return out


def scale_ui_reference_rects(
    frame_fw: int,
    frame_fh: int,
    *,
    ref_width: float = 1920.0,
    ref_height: float = 1080.0,
    definitions: Optional[Sequence[Sequence[Union[str, float, int]]]] = None,
) -> List[List[float]]:
    """Map reference UI rects (center + half extents) to frame pixel xyxy boxes."""
    defs: Sequence[Tuple[str, float, float, float, float]]
    if definitions:
        tup: List[Tuple[str, float, float, float, float]] = []
        for row in definitions:
            if len(row) < 5:
                continue
            name = str(row[0])
            cx, cy, hw, hh = float(row[1]), float(row[2]), float(row[3]), float(row[4])
            tup.append((name, cx, cy, hw, hh))
        defs = tup
    else:
        defs = DEFAULT_UI_REFERENCE_RECTS

    fw, fh = max(1, int(frame_fw)), max(1, int(frame_fh))
    out: List[List[float]] = []
    for _, cx, cy, hw, hh in defs:
        x1 = (cx - hw) * fw / ref_width
        y1 = (cy - hh) * fh / ref_height
        x2 = (cx + hw) * fw / ref_width
        y2 = (cy + hh) * fh / ref_height
        x1 = max(0.0, min(float(fw), x1))
        y1 = max(0.0, min(float(fh), y1))
        x2 = max(0.0, min(float(fw), x2))
        y2 = max(0.0, min(float(fh), y2))
        if x2 > x1 and y2 > y1:
            out.append([x1, y1, x2, y2])
    return out


def motion_blob_boxes(
    prev_gray_small: Optional[np.ndarray],
    curr_gray_small: np.ndarray,
    entity_boxes_fullres: Sequence[Sequence[float]],
    frame_size: Tuple[int, int],
    *,
    diff_threshold: int = 25,
    exclude_dilate_px: int = 8,
    min_area_px: int = 80,
    max_area_px: int = 8000,
    morph_kernel: int = 3,
    fog_exclude_small: Optional[np.ndarray] = None,
    ego_compensate: bool = False,
    ego_min_response: float = 0.08,
    skip_motion_on_low_ego_response: bool = False,
) -> List[List[float]]:
    """Return full-resolution boxes from masked absdiff on downscaled grayscale."""
    if prev_gray_small is None or prev_gray_small.shape != curr_gray_small.shape:
        return []
    sh, sw = curr_gray_small.shape[:2]
    fh, fw = int(frame_size[1]), int(frame_size[0])

    prev_use = prev_gray_small
    if ego_compensate:
        aligned, ok = align_prev_to_curr(prev_gray_small, curr_gray_small, min_response=ego_min_response)
        if skip_motion_on_low_ego_response and not ok:
            return []
        prev_use = aligned

    diff = cv2.absdiff(curr_gray_small, prev_use)
    _, th = cv2.threshold(diff, int(diff_threshold), 255, cv2.THRESH_BINARY)

    exclude = np.zeros((sh, sw), dtype=np.uint8)
    dil = max(1, int(exclude_dilate_px))
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (dil * 2 + 1, dil * 2 + 1))
    for box in entity_boxes_fullres:
        if len(box) < 4:
            continue
        x1, y1, x2, y2 = _full_to_small_rect(box, fw, fh, sw, sh)
        if x2 <= x1 or y2 <= y1:
            continue
        cv2.rectangle(exclude, (x1, y1), (x2, y2), 255, thickness=-1)
    exclude = cv2.dilate(exclude, k)

    if fog_exclude_small is not None and fog_exclude_small.shape == (sh, sw):
        exclude = cv2.bitwise_or(exclude, fog_exclude_small)

    th = cv2.bitwise_and(th, cv2.bitwise_not(exclude))

    mk = max(1, int(morph_kernel)) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (mk, mk))
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out: List[List[float]] = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area_px or area > max_area_px:
            continue
        x, y, w, h = cv2.boundingRect(c)
        if w <= 0 or h <= 0:
            continue
        # Map small → full resolution
        x1f = x * fw / max(1, sw)
        y1f = y * fh / max(1, sh)
        x2f = (x + w) * fw / max(1, sw)
        y2f = (y + h) * fh / max(1, sh)
        out.append([x1f, y1f, x2f, y2f])
    return out


def grayscale_small(frame_rgb: np.ndarray, scale_width: int) -> np.ndarray:
    """RGB frame → uint8 gray resized to target width (height preserves aspect)."""
    h, w = frame_rgb.shape[:2]
    if w <= 0 or h <= 0:
        return np.zeros((1, 1), dtype=np.uint8)
    sw = max(8, int(scale_width))
    sh = max(1, int(round(h * sw / max(1, w))))
    gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
    return cv2.resize(gray, (sw, sh), interpolation=cv2.INTER_AREA)


def parse_animated_terrain_hsv_ranges(
    raw: object,
) -> List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]]:
    """Parse TOML list of [low, high] HSV triples into typed tuples."""
    out: List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        lo, hi = item[0], item[1]
        if not isinstance(lo, (list, tuple)) or not isinstance(hi, (list, tuple)):
            continue
        if len(lo) < 3 or len(hi) < 3:
            continue
        out.append(
            (
                (int(lo[0]), int(lo[1]), int(lo[2])),
                (int(hi[0]), int(hi[1]), int(hi[2])),
            )
        )
    return out
