import unittest

from state_finder import SHOWDOWN_PLACE_THRESHOLD, showdown_place_threshold


class ShowdownResultDetectionTests(unittest.TestCase):
    def test_first_place_uses_more_tolerant_template_threshold(self):
        self.assertLess(showdown_place_threshold("1st"), SHOWDOWN_PLACE_THRESHOLD)
        self.assertGreaterEqual(showdown_place_threshold("1st"), 0.84)

    def test_other_showdown_places_keep_strict_threshold(self):
        for place in ("2nd", "3rd", "4th"):
            with self.subTest(place=place):
                self.assertEqual(showdown_place_threshold(place), SHOWDOWN_PLACE_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
