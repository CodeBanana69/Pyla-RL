import unittest
from pathlib import Path

import scrcpy


ROOT = Path(__file__).resolve().parents[1]


class ScrcpyVendorTests(unittest.TestCase):
    def test_vendored_scrcpy_uses_pyla_capture_path(self):
        core = (ROOT / "scrcpy" / "core.py").read_text(encoding="utf-8")

        self.assertTrue(getattr(scrcpy, "PYLA_RGB_FRAMES", False))
        self.assertIn("recv(0x100000)", core)
        self.assertIn('to_ndarray(format="rgb24")', core)

    def test_window_controller_skips_duplicate_color_conversion(self):
        source = (ROOT / "window_controller.py").read_text(encoding="utf-8")

        self.assertIn('getattr(scrcpy, "PYLA_RGB_FRAMES", False)', source)
        self.assertIn("cv2.COLOR_BGR2RGB", source)


if __name__ == "__main__":
    unittest.main()
