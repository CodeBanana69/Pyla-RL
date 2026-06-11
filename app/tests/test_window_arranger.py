import unittest

from gui.window_arranger import compute_grid_rects


class WindowArrangerTests(unittest.TestCase):
    def test_compute_grid_rects_single(self):
        rects = compute_grid_rects(1, area=(0, 0, 1920, 1080))
        self.assertEqual(len(rects), 1)
        x, y, w, h = rects[0]
        self.assertGreaterEqual(w, 360)
        self.assertGreaterEqual(h, 240)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)

    def test_compute_grid_rects_four(self):
        rects = compute_grid_rects(4, area=(0, 0, 1920, 1080))
        self.assertEqual(len(rects), 4)
        self.assertEqual(len({rect[:2] for rect in rects}), 4)


if __name__ == "__main__":
    unittest.main()
