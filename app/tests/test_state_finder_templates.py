import os
import unittest

import cv2
import numpy as np

from state_finder import find_game_result, get_state, load_template


class StateFinderTemplateTests(unittest.TestCase):
    def test_showdown_template_files_exist(self):
        root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "images", "end_results")
        for name in ("sd1st.png", "sd2nd.png", "sd3rd.png", "sd4th.png", "victory.png", "defeat.png", "draw.png"):
            self.assertTrue(os.path.exists(os.path.join(root, name)), f"missing {name}")

    def test_load_template_reads_showdown_first_place(self):
        path = os.path.join("images", "end_results", "sd1st.png")
        template = load_template(path, 960, 544)
        self.assertIsNotNone(template)
        self.assertEqual(len(template.shape), 3)

    def test_get_state_does_not_crash_on_blank_frame(self):
        frame = np.zeros((544, 960, 3), dtype=np.uint8)
        state = get_state(frame)
        self.assertEqual(state, "match")


if __name__ == "__main__":
    unittest.main()
