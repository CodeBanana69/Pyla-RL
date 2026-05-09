"""Universal projectile candidates without dedicated YOLO classes.

Combines labeled detector boxes, residual detector keys, and masked frame
diff blobs. Shared between Play.update_projectile_tracker and unit tests."""

from __future__ import annotations

from typing import List, Optional, Sequence, Set, Tuple

import cv2
import numpy as np


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
            out.append(b)
    return out


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
) -> List[List[float]]:
    """Return full-resolution boxes from masked absdiff on downscaled grayscale."""
    if prev_gray_small is None or prev_gray_small.shape != curr_gray_small.shape:
        return []
    sh, sw = curr_gray_small.shape[:2]
    fh, fw = int(frame_size[1]), int(frame_size[0])

    diff = cv2.absdiff(curr_gray_small, prev_gray_small)
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
