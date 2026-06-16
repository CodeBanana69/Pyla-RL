import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.post_update_setup import (
    PostUpdateSetupResult,
    needs_full_setup,
    run_post_update_setup,
)


class PostUpdateSetupTest(unittest.TestCase):
    def test_needs_full_setup_when_venv_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "app").mkdir()
            needs, reason = needs_full_setup(project)
            self.assertTrue(needs)
            self.assertIn(".venv", reason)

    def test_needs_full_setup_when_runtime_probe_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            bundle = project / "app"
            venv_scripts = bundle / ".venv" / "Scripts"
            venv_scripts.mkdir(parents=True)
            (venv_scripts / "python.exe").write_text("", encoding="utf-8")
            with patch("tools.post_update_setup._venv_pip_usable", return_value=True), patch(
                "tools.post_update_setup.probe_runtime_imports",
                return_value={"ok": False, "error": "cv2: missing"},
            ):
                needs, reason = needs_full_setup(project)
            self.assertTrue(needs)
            self.assertIn("cv2", reason)

    def test_needs_full_setup_skips_when_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            bundle = project / "app"
            venv_scripts = bundle / ".venv" / "Scripts"
            venv_scripts.mkdir(parents=True)
            (venv_scripts / "python.exe").write_text("", encoding="utf-8")
            with patch("tools.post_update_setup._venv_pip_usable", return_value=True), patch(
                "tools.post_update_setup.probe_runtime_imports",
                return_value={"ok": True},
            ), patch("tools.post_update_setup._probe_pyside6", return_value=True):
                needs, reason = needs_full_setup(project)
            self.assertFalse(needs)
            self.assertEqual(reason, "")

    def test_run_post_update_setup_skips_when_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            with patch("tools.post_update_setup.needs_full_setup", return_value=(False, "")), patch(
                "tools.post_update_setup.run_full_project_setup"
            ) as full_mock:
                result = run_post_update_setup(project)
            full_mock.assert_not_called()
            self.assertTrue(result.skipped)
            self.assertTrue(result.ok)

    def test_run_post_update_setup_runs_full_when_unhealthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            with patch("tools.post_update_setup.needs_full_setup", return_value=(True, "broken pip")), patch(
                "tools.post_update_setup.run_full_project_setup",
                return_value=True,
            ) as full_mock:
                result = run_post_update_setup(project)
            full_mock.assert_called_once()
            self.assertFalse(result.skipped)
            self.assertTrue(result.ok)

    def test_post_update_setup_refreshes_launcher_and_hub_wizard(self):
        source = Path("app/tools/post_update_setup.py").read_text(encoding="utf-8")
        self.assertIn("ensure_hub_first_run_wizard", source)
        self.assertIn("create_run_file", source)
        self.assertIn("setup.py", source)
        self.assertIn("--pyla-install", source)

    def test_run_post_update_setup_reports_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            with patch("tools.post_update_setup.needs_full_setup", return_value=(True, "missing deps")), patch(
                "tools.post_update_setup.run_full_project_setup",
                return_value=False,
            ):
                result = run_post_update_setup(project)
            self.assertFalse(result.ok)
            self.assertIn("dependency setup failed", result.message)


if __name__ == "__main__":
    unittest.main()
