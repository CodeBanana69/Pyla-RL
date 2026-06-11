import unittest

from main import config_bool, parse_max_ips


class MaxIpsTest(unittest.TestCase):
    def test_zero_means_unlimited(self):
        self.assertIsNone(parse_max_ips(0))
        self.assertIsNone(parse_max_ips("0"))

    def test_positive_value_is_loop_cap(self):
        self.assertEqual(parse_max_ips(24), 24)
        self.assertEqual(parse_max_ips("45"), 45)
        self.assertEqual(parse_max_ips(999), 999)

    def test_invalid_value_falls_back_to_unlimited(self):
        self.assertIsNone(parse_max_ips("auto"))
        self.assertIsNone(parse_max_ips(""))
        self.assertIsNone(parse_max_ips(None))

    def test_config_bool_accepts_common_enabled_values(self):
        self.assertTrue(config_bool("yes"))
        self.assertTrue(config_bool("1"))
        self.assertFalse(config_bool("no"))
        self.assertTrue(config_bool(None, default=True))


if __name__ == "__main__":
    unittest.main()
