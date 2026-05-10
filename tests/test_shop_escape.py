import unittest

from stage_manager import StageManager


class DummyBackController:
    width_ratio = 1.0
    height_ratio = 1.0

    def __init__(self, back_result):
        self.back_result = back_result
        self.back_presses = 0
        self.clicks = []

    def android_back(self):
        self.back_presses += 1
        return self.back_result

    def click(self, x, y):
        self.clicks.append((x, y))


class ShopEscapeTests(unittest.TestCase):
    def test_quit_shop_uses_android_back_first(self):
        manager = object.__new__(StageManager)
        manager.window_controller = DummyBackController(True)

        manager.quit_shop()

        self.assertEqual(manager.window_controller.back_presses, 1)
        self.assertEqual(manager.window_controller.clicks, [])

    def test_quit_shop_falls_back_to_top_left_click(self):
        manager = object.__new__(StageManager)
        manager.window_controller = DummyBackController(False)

        manager.quit_shop()

        self.assertEqual(manager.window_controller.back_presses, 1)
        self.assertEqual(manager.window_controller.clicks, [(100.0, 60.0)])


if __name__ == "__main__":
    unittest.main()
