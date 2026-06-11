import unittest
from unittest.mock import patch

from gui.remote_command_router import RemoteCommandRouter
from runtime_control import PAUSED, RUNNING, read_state, write_state


class RemoteCommandRouterTest(unittest.TestCase):
    def test_dispatch_state_action(self):
        router = RemoteCommandRouter()
        with patch.object(router, "resolve_target", return_value=({"id": "ld-1", "state_path": "logs/test.state"}, None)):
            with patch("gui.remote_command_router.write_state") as mock_write:
                ok, message = router.dispatch_state_action("ld-1", "pause")
                self.assertTrue(ok)
                mock_write.assert_called_once()

    def test_require_resolved_instance_multiple(self):
        from gui.instance_registry import require_resolved_instance

        with patch("gui.instance_registry.list_instances", return_value=[
            {"id": "a", "running": True, "state_path": "logs/a.state"},
            {"id": "b", "running": True, "state_path": "logs/b.state"},
        ]):
            resolved, error = require_resolved_instance(None)
            self.assertIsNone(resolved)
            self.assertIn("Multiple instances", error or "")


if __name__ == "__main__":
    unittest.main()
