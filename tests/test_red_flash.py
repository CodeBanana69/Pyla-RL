"""Unit tests for rl.red_flash.RedFlashDetector."""

from __future__ import annotations

import unittest

import numpy as np

from rl.red_flash import RedFlashDetector


class RedFlashDetectorTests(unittest.TestCase):
    def test_uniform_red_after_green_triggers_flash(self):
        green = np.zeros((80, 80, 3), dtype=np.uint8)
        green[:, :, 1] = 220
        red = np.zeros((80, 80, 3), dtype=np.uint8)
        red[:, :, 0] = 255

        det = RedFlashDetector(threshold=1.4, baseline_alpha=0.1)
        for _ in range(25):
            det.update(green)
        self.assertFalse(det.update(green))
        self.assertTrue(det.update(red))

    def test_steady_green_stays_false(self):
        green = np.zeros((80, 80, 3), dtype=np.uint8)
        green[:, :, 1] = 200
        det = RedFlashDetector(threshold=1.4, baseline_alpha=0.1)
        det.update(green)
        for _ in range(30):
            self.assertFalse(det.update(green))


if __name__ == "__main__":
    unittest.main()
