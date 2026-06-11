import tempfile
import unittest
from pathlib import Path

from core.integration import RuntimeControlBridge
from runtime_control import set_runtime_state


class RuntimeControlBridgeTests(unittest.TestCase):
    def test_external_resume_clears_stale_internal_pause_flag(self):
        """F8/control window writes RUNNING without calling mark_running()."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path = str(Path(tmp) / "runtime_control_test.state")
            bridge = RuntimeControlBridge(state_path)

            bridge.mark_paused()
            self.assertTrue(bridge.should_pause())

            set_runtime_state(state_path, False)
            self.assertFalse(bridge.should_pause())


if __name__ == "__main__":
    unittest.main()
