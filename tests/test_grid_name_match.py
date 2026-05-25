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


if __name__ == "__main__":
    unittest.main()
