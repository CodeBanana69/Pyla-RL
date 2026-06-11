import importlib
import unittest
from unittest.mock import patch


class ConfigDefaultTests(unittest.TestCase):
    def test_missing_api_base_url_defaults_to_localhost(self):
        import utils

        original_api_base_url = utils.api_base_url
        original_cfg_api_base_url = utils.cfg_api_base_url
        try:
            with patch("utils.load_toml_as_dict", return_value={}):
                importlib.reload(utils)
            self.assertEqual(utils.api_base_url, "localhost")
        finally:
            utils.api_base_url = original_api_base_url
            utils.cfg_api_base_url = original_cfg_api_base_url


if __name__ == "__main__":
    unittest.main()
