import io
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import runtime_log


class RuntimeLogTests(unittest.TestCase):
    def setUp(self):
        runtime_log._once_times.clear()
        runtime_log._trace_times.clear()
        runtime_log._status_active = False
        runtime_log._last_status_len = 0

    def write_config(self, tmpdir, **values):
        path = f"{tmpdir}/general_config.toml"
        lines = [f'{key} = "{value}"' if not isinstance(value, (int, float)) else f"{key} = {value}" for key, value in values.items()]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        return path

    def test_startup_category_formats_banner(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_config(tmp, terminal_verbosity="normal")
            runtime_log.configure(path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                runtime_log.log_info("startup", "Pyla-RL is free, open source, and must not be sold.")
            self.assertIn("[Startup]", buffer.getvalue())

    def test_normal_verbosity_hides_movement_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_config(
                tmp,
                terminal_verbosity="normal",
                movement_debug="no",
                visual_debug="yes",
                super_debug="no",
                wall_stuck_debug="no",
            )
            runtime_log.configure(path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                runtime_log.log_trace("movement", "showdown movement angle=45.0")
            self.assertEqual(buffer.getvalue(), "")

    def test_movement_debug_enables_rate_limited_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_config(tmp, terminal_verbosity="normal", movement_debug="yes")
            runtime_log.configure(path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                runtime_log.log_trace("movement", "showdown movement angle=45.0", key="angle")
                runtime_log.log_trace("movement", "showdown movement angle=45.0", key="angle")
            output = buffer.getvalue()
            self.assertEqual(output.count("[Movement]"), 1)

    def test_log_once_suppresses_repeated_combat_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_config(tmp, terminal_verbosity="normal")
            runtime_log.configure(path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                runtime_log.log_once("combat:super", 5.0, runtime_log.LEVEL_INFO, "combat", "Using super")
                runtime_log.log_once("combat:super", 5.0, runtime_log.LEVEL_INFO, "combat", "Using super")
            self.assertEqual(buffer.getvalue().count("[Combat]"), 1)

    def test_quiet_mode_keeps_match_and_queue_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_config(tmp, terminal_verbosity="quiet")
            runtime_log.configure(path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                runtime_log.log_info("startup", "hidden startup")
                runtime_log.log_info("match", "Game has ended")
                runtime_log.log_warn("recovery", "Low IPS detected")
            output = buffer.getvalue()
            self.assertNotIn("[Startup]", output)
            self.assertIn("[Match]", output)
            self.assertIn("[Recovery]", output)

    def test_status_line_uses_carriage_return(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_config(tmp, terminal_verbosity="normal")
            runtime_log.configure(path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                runtime_log.log_status_line("IPS 12.3")
                runtime_log.log_info("match", "Post-match action: Play Again.")
            output = buffer.getvalue()
            self.assertTrue(output.startswith("\rIPS 12.3"))
            self.assertIn("\n[Match]", output)

    def test_wall_stuck_debug_enables_movement_debug_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_config(tmp, terminal_verbosity="quiet", wall_stuck_debug="yes")
            runtime_log.configure(path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                runtime_log.log_debug("movement", "unstuck triggered")
            self.assertIn("[Movement] unstuck triggered", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
