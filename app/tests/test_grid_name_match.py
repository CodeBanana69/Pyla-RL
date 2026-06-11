import unittest

from lobby_automation import LobbyAutomation


class GridNameMatchTests(unittest.TestCase):
    def test_empty_label_does_not_match_nita(self):
        self.assertFalse(LobbyAutomation.names_match("", "nita"))

    def test_two_letter_fragment_does_not_match_nita(self):
        self.assertFalse(LobbyAutomation.names_match("ni", "nita"))

    def test_nit_typo_matches_nita_on_grid(self):
        automation = LobbyAutomation.__new__(LobbyAutomation)
        automation.known_brawler_names = {"nita", "barley", "colt"}
        self.assertTrue(automation._is_confident_grid_name_match("nit", "nita"))

    def test_barley_does_not_match_nita(self):
        automation = LobbyAutomation.__new__(LobbyAutomation)
        automation.known_brawler_names = {"nita", "barley", "colt"}
        self.assertFalse(automation._is_confident_grid_name_match("barley", "nita"))

    def test_box_does_not_match_bo(self):
        self.assertFalse(LobbyAutomation.names_match("box", "bo"))

    def test_hyphenated_r_t_matches(self):
        self.assertTrue(LobbyAutomation.names_match("r-t", "rt"))
        self.assertTrue(LobbyAutomation.names_match("rt", "r-t"))

    def test_ocr_junk_is_stripped(self):
        self.assertEqual(LobbyAutomation.normalize_ocr_name("[Leon]"), "leon")

    def test_ambiguous_known_name_rejected(self):
        automation = LobbyAutomation.__new__(LobbyAutomation)
        automation.known_brawler_names = {"nita", "barley", "colt"}
        self.assertFalse(automation._is_confident_grid_name_match("barley", "nita"))


if __name__ == "__main__":
    unittest.main()
