import unittest

import cv2
import numpy as np

from rl.universal_projectiles import (
    box_iou,
    extract_residual_projectile_boxes,
    greedy_nms_xyxy,
    grayscale_small,
    merge_projectile_candidates,
    motion_blob_boxes,
    raster_fog_roi_to_small_mask,
)


class UniversalProjectileHelpersTests(unittest.TestCase):
    def test_box_iou_overlap(self):
        a = [0.0, 0.0, 10.0, 10.0]
        b = [5.0, 5.0, 15.0, 15.0]
        iou = box_iou(a, b)
        self.assertGreater(iou, 0.1)
        self.assertLessEqual(iou, 1.0)

    def test_residual_skips_excluded_keys_and_entity_overlap(self):
        data = {
            "player": [[0, 0, 40, 40]],
            "enemy": [[500, 500, 560, 560]],
            "odd_class": [[200, 200, 230, 235]],
            "junk": "not_a_list",
        }
        ref = [[0, 0, 40, 40], [500, 500, 560, 560]]
        ex = {"player", "enemy", "wall", "teammate", "bush"}
        boxes = extract_residual_projectile_boxes(
            data,
            ex,
            ref,
            frame_size=(1920, 1080),
            max_box_area_frac=1.0,
            max_side_frac=1.0,
            iou_exclude_thresh=0.01,
        )
        self.assertEqual(len(boxes), 1)
        self.assertAlmostEqual(boxes[0][0], 200.0)

    def test_greedy_nms_drops_duplicate_boxes(self):
        a = [10.0, 10.0, 30.0, 30.0]
        b = [12.0, 12.0, 28.0, 28.0]
        kept = greedy_nms_xyxy([a, b], iou_thresh=0.3)
        self.assertEqual(len(kept), 1)

    def test_merge_prioritizes_spread_via_nms(self):
        labeled = [[100, 100, 120, 120]]
        residual = [[800, 800, 830, 830]]
        merged = merge_projectile_candidates(labeled, residual, [], nms_iou=0.05)
        self.assertEqual(len(merged), 2)

    def test_raster_fog_roi_to_small_mask(self):
        roi = np.zeros((20, 20), dtype=np.uint8)
        roi[5:15, 5:15] = 255
        small = raster_fog_roi_to_small_mask(roi, (100, 80), (200, 320), (50, 80))
        self.assertEqual(small.shape, (50, 80))
        self.assertGreater(int(small.sum()), 0)

    def test_motion_detects_moving_blob_masked_entity(self):
        sh, sw = 64, 64
        prev = np.zeros((sh, sw), dtype=np.uint8)
        curr = np.zeros((sh, sw), dtype=np.uint8)
        cv2.rectangle(prev, (38, 28), (50, 40), 255, thickness=-1)
        cv2.rectangle(curr, (42, 28), (54, 40), 255, thickness=-1)
        entity = [[0.0, 0.0, 20.0, 64.0]]
        frame_wh = (640, 640)
        boxes = motion_blob_boxes(
            prev,
            curr,
            entity,
            frame_wh,
            diff_threshold=8,
            exclude_dilate_px=2,
            min_area_px=3,
            max_area_px=5000,
            morph_kernel=1,
        )
        self.assertGreaterEqual(len(boxes), 1)


class GrayscaleSmallTests(unittest.TestCase):
    def test_grayscale_small_aspect(self):
        rgb = np.zeros((1080, 1920, 3), dtype=np.uint8)
        rgb[100:120, 400:420] = (255, 255, 255)
        g = grayscale_small(rgb, scale_width=480)
        self.assertEqual(g.shape[1], 480)
        self.assertEqual(g.dtype, np.uint8)


if __name__ == "__main__":
    unittest.main()
