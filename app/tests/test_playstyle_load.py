import unittest

from utils import get_playstyles_list, load_pyla_script


class PlaystyleLoadTests(unittest.TestCase):
    def test_team_showdown_loads(self):
        metadata, code = load_pyla_script("team_showdown.pyla")
        self.assertIn("name", metadata)
        self.assertIn("movement", code.lower())
        self.assertIn("get_multi_enemy_spacing_movement", code)

    def test_playstyles_list_not_empty(self):
        playstyles = get_playstyles_list()
        filenames = {item["filename"] for item in playstyles}
        self.assertIn("team_showdown.pyla", filenames)
        self.assertIn("default_up.pyla", filenames)


if __name__ == "__main__":
    unittest.main()
