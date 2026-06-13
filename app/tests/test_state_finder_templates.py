import os
import tempfile
import unittest

import cv2
import numpy as np

from state_finder import find_game_result, get_state, load_template
from utils import imread_unicode, resolve_project_path


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

    def test_imread_unicode_loads_from_non_ascii_directory(self):
        source = resolve_project_path("images/end_results/sd1st.png")
        with tempfile.TemporaryDirectory(prefix="pyla-тест-") as temp_dir:
            target = os.path.join(temp_dir, "template.png")
            with open(source, "rb") as src, open(target, "wb") as dst:
                dst.write(src.read())
            image = imread_unicode(target)
        self.assertIsNotNone(image)
        self.assertEqual(len(image.shape), 3)

    def test_get_state_does_not_crash_on_blank_frame(self):
        frame = np.zeros((544, 960, 3), dtype=np.uint8)
        state = get_state(frame)
        self.assertEqual(state, "match")


if __name__ == "__main__":
    unittest.main()
