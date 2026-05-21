import unittest

from gui.hub_validators import validate_config_value


class HubValidatorTests(unittest.TestCase):
    def test_pause_graph_samples_range(self):
        with self.assertRaises(ValueError):
            validate_config_value("settings", "pause_menu_graph_samples", "10")

    def test_webhook_url_validation(self):
        with self.assertRaises(ValueError):
            validate_config_value("discord", "webhook_url", "not-a-url")

    def test_player_tag_requires_hash(self):
        with self.assertRaises(ValueError):
            validate_config_value("api", "player_tag", "NOHASH")


if __name__ == "__main__":
    unittest.main()
