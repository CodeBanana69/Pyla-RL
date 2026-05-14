import unittest

import cv2
import numpy as np

from play import Play


class TestWallDetectionPostprocess(unittest.TestCase):
    def make_play(self):
        play = Play.__new__(Play)
        play.wall_box_min_size = 20
        play.wall_box_merge_iou = 0.25
        play.wall_box_merge_center_distance = 35
        play.wall_history_min_hits = 2
        play.wall_history = []
        play.wall_history_length = 3
        play.map_object_vision_enabled = True
        play.map_object_wall_color_detection = True
        play.map_object_water_detection = False
        play.map_object_min_area = 200
        play.wall_detection_retry_min_objects = 3
        play.TILE_SIZE = 60
        return play

    def test_merges_jittered_wall_boxes(self):
        play = self.make_play()
        boxes = [
            [100, 100, 160, 160],
            [105, 102, 163, 158],
            [500, 500, 560, 560],
            [10, 10, 20, 20],
        ]

        merged = play.merge_wall_boxes(boxes)

        self.assertEqual(len(merged), 2)
        self.assertTrue(any(abs(box[0] - 102) <= 4 and abs(box[1] - 101) <= 4 for box in merged))
        self.assertTrue(any(box[0] == 500 and box[1] == 500 for box in merged))

    def test_combines_history_without_exact_coordinate_duplicates(self):
        play = self.make_play()
        play.wall_history = [
            [[100, 100, 160, 160]],
            [[103, 98, 162, 161]],
            [[700, 700, 760, 760]],
        ]

        combined = play.combine_walls_from_history()

        self.assertEqual(len(combined), 2)

    def test_current_frame_walls_are_kept_before_history_votes(self):
        play = self.make_play()
        play.wall_history = [
            [[100, 100, 160, 160]],
            [[400, 400, 460, 460]],
        ]

        combined = play.combine_walls_from_history()

        self.assertTrue(any(box[0] == 400 and box[1] == 400 for box in combined))

    def test_process_tile_data_keeps_object_classes_without_color_water_by_default(self):
        play = self.make_play()
        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        teal_bush_rgb = cv2.cvtColor(np.array([[[88, 190, 210]]], dtype=np.uint8), cv2.COLOR_HSV2RGB)[0, 0]
        frame[80:125, 180:235] = teal_bush_rgb

        walls, objects = play.process_tile_data(
            {
                "wall": [[20, 20, 80, 80]],
                "bush": [[100, 20, 160, 80]],
                "close_bush": [[100, 100, 160, 160]],
            },
            frame,
        )

        self.assertIn("wall", objects)
        self.assertIn("bush", objects)
        self.assertIn("close_bush", objects)
        self.assertNotIn("water", objects)
        self.assertEqual(len(walls), 1)
        self.assertFalse(any(box[0] == 100 and box[1] == 20 for box in walls))

    def test_optional_water_detection_rejects_teal_bush_color(self):
        play = self.make_play()
        play.map_object_water_detection = True
        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        teal_bush_rgb = cv2.cvtColor(np.array([[[88, 190, 210]]], dtype=np.uint8), cv2.COLOR_HSV2RGB)[0, 0]
        frame[80:145, 180:245] = teal_bush_rgb

        self.assertEqual(play.detect_water_tiles(frame), [])

    def test_color_wall_fallback_detects_gray_blue_wall_and_rejects_teal_bush(self):
        play = self.make_play()
        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        wall_rgb = cv2.cvtColor(np.array([[[120, 105, 170]]], dtype=np.uint8), cv2.COLOR_HSV2RGB)[0, 0]
        bush_rgb = cv2.cvtColor(np.array([[[92, 230, 176]]], dtype=np.uint8), cv2.COLOR_HSV2RGB)[0, 0]
        frame[80:145, 80:145] = wall_rgb
        frame[80:145, 180:245] = bush_rgb

        walls = play.detect_wall_tiles_by_color(frame)

        self.assertTrue(any(80 <= (box[0] + box[2]) * 0.5 <= 145 for box in walls))
        self.assertFalse(any(180 <= (box[0] + box[2]) * 0.5 <= 245 for box in walls))

    def test_color_wall_fallback_rejects_green_vegetation_even_in_wall_hue_band(self):
        play = self.make_play()
        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        vegetation_rgb = np.array([95, 150, 120], dtype=np.uint8)
        frame[80:145, 80:145] = vegetation_rgb

        self.assertEqual(play.detect_wall_tiles_by_color(frame), [])

    def test_color_wall_fallback_fills_sparse_model_wall_detection(self):
        play = self.make_play()
        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        wall_rgb = cv2.cvtColor(np.array([[[120, 105, 170]]], dtype=np.uint8), cv2.COLOR_HSV2RGB)[0, 0]
        frame[80:145, 80:145] = wall_rgb

        walls, objects = play.process_tile_data({"wall": []}, frame)

        self.assertIn("wall", objects)
        self.assertTrue(walls)

    def test_color_wall_fallback_does_not_box_empty_corner_of_l_shape(self):
        play = self.make_play()
        frame = np.zeros((400, 400, 3), dtype=np.uint8)
        wall_rgb = cv2.cvtColor(np.array([[[120, 105, 170]]], dtype=np.uint8), cv2.COLOR_HSV2RGB)[0, 0]
        frame[40:160, 40:86] = wall_rgb
        frame[114:160, 40:160] = wall_rgb

        boxes = play.detect_wall_tiles_by_color(frame)

        self.assertTrue(boxes)
        self.assertFalse(
            any(box[0] < 120 and box[2] > 120 and box[1] < 80 and box[3] > 80 for box in boxes),
            boxes,
        )

    def test_normalize_map_object_class_accepts_apk_tile_names(self):
        self.assertEqual(Play.normalize_map_object_class("Wall1"), "wall")
        self.assertEqual(Play.normalize_map_object_class("RespawningForest"), "bush")
        self.assertEqual(Play.normalize_map_object_class("GravityPush"), "gravity_push")

    def test_get_tile_data_retries_when_primary_threshold_is_empty(self):
        play = self.make_play()
        play.wall_detection_confidence = 0.9
        play.wall_detection_retry_confidence = 0.20
        play.wall_detection_retry_min_objects = 3
        calls = []

        class Detector:
            def detect_objects(self, _frame, conf_tresh=0.6):
                calls.append(conf_tresh)
                if conf_tresh == 0.9:
                    return {}
                return {"wall": [[1, 2, 3, 4]]}

        play.Detect_tile_detector = Detector()

        data = play.get_tile_data(np.zeros((10, 10, 3), dtype=np.uint8))

        self.assertEqual(calls, [0.9, 0.20])
        self.assertEqual(data, {"wall": [[1, 2, 3, 4]]})

    def test_get_tile_data_retries_when_primary_detection_is_sparse(self):
        play = self.make_play()
        play.wall_detection_confidence = 0.9
        play.wall_detection_retry_confidence = 0.20
        play.wall_detection_retry_min_objects = 3

        class Detector:
            def detect_objects(self, _frame, conf_tresh=0.6):
                if conf_tresh == 0.9:
                    return {"wall": [[1, 2, 3, 4]]}
                return {"wall": [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]}

        play.Detect_tile_detector = Detector()

        data = play.get_tile_data(np.zeros((10, 10, 3), dtype=np.uint8))

        self.assertEqual(len(data["wall"]), 3)

    def test_water_does_not_block_movement_or_line_of_sight_until_map_alignment_is_safe(self):
        play = self.make_play()
        objects = {
            "wall": [[10, 10, 50, 50]],
            "water": [[60, 10, 100, 50]],
            "bush": [[110, 10, 150, 50]],
        }

        movement_boxes = play.map_object_boxes_for_classes(objects, play.blocking_map_object_classes())
        los_boxes = play.map_object_boxes_for_classes(objects, play.line_of_sight_map_object_classes())

        self.assertEqual(len(movement_boxes), 1)
        self.assertEqual(len(los_boxes), 1)
        self.assertEqual(los_boxes[0], [10, 10, 50, 50])


if __name__ == "__main__":
    unittest.main()
