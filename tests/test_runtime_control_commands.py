import tempfile
import unittest
from pathlib import Path

from runtime_control import (
    control_command_path,
    read_and_clear_control_command,
    write_control_command,
)


class RuntimeControlCommandTests(unittest.TestCase):
    def test_command_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "runtime_control_12345.state"
            state_path.write_text("running", encoding="utf-8")
            write_control_command(state_path, "show")
            self.assertEqual(control_command_path(state_path).read_text(encoding="utf-8"), "show")
            self.assertEqual(read_and_clear_control_command(state_path), "show")
            self.assertFalse(control_command_path(state_path).exists())
            self.assertEqual(read_and_clear_control_command(state_path), "")


if __name__ == "__main__":
    unittest.main()
