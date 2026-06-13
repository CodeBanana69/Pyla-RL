import unittest

from gui.hub_action_runner import is_blocking_hub_action, pending_action_message


class HubActionRunnerTests(unittest.TestCase):
    def test_build_push_all_is_blocking(self):
        self.assertTrue(is_blocking_hub_action("build-push-all"))

    def test_clear_queue_is_not_blocking(self):
        self.assertFalse(is_blocking_hub_action("clear-queue"))

    def test_pending_message_for_start(self):
        self.assertEqual(pending_action_message("start-pyla"), "Checking pre-flight...")

    def test_preflight_fix_is_blocking(self):
        self.assertTrue(is_blocking_hub_action("preflight-fix"))
        self.assertEqual(pending_action_message("preflight-fix"), "Applying pre-flight fix...")


if __name__ == "__main__":
    unittest.main()
