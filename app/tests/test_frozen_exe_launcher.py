import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.frozen_exe_launcher import (
    bundle_dir_from_install,
    delegate_to_script,
    install_root_from_frozen_exe,
    resolve_python_for_launch,
)


class FrozenExeLauncherTest(unittest.TestCase):
    def test_install_root_from_frozen_exe(self):
        with patch("tools.frozen_exe_launcher.sys.executable", r"C:\Pyla-RL\setup.exe"):
            self.assertEqual(install_root_from_frozen_exe(), Path(r"C:\Pyla-RL"))

    def test_bundle_dir_from_install(self):
        install = Path(r"C:\Pyla-RL")
        self.assertEqual(bundle_dir_from_install(install), Path(r"C:\Pyla-RL\app"))

    def test_resolve_python_for_launch_prefers_pin_for_updater(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)
            (bundle / "cfg").mkdir(parents=True)
            (bundle / "cfg" / "pyla_python.txt").write_text("C:\\Python311\\python.exe\n", encoding="utf-8")
            with patch("tools.frozen_exe_launcher._python_info", return_value=r"C:\Python311\python.exe"):
                command = resolve_python_for_launch(bundle, prefer_venv=True)
            self.assertEqual(command, [r"C:\Python311\python.exe"])

    def test_resolve_python_for_setup_uses_system_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)
            with patch("tools.frozen_exe_launcher.resolve_system_python", return_value=["py", "-3.11-64"]):
                command = resolve_python_for_launch(bundle, prefer_venv=False)
            self.assertEqual(command, ["py", "-3.11-64"])

    def test_delegate_to_script_sets_pythonpath_and_forwards_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            bundle = install / "app"
            script = bundle / "tools" / "updater.py"
            script.parent.mkdir(parents=True)
            script.write_text("print('ok')\n", encoding="utf-8")
            with patch("tools.frozen_exe_launcher.resolve_python_for_launch", return_value=["py", "-3.11-64"]), patch(
                "tools.frozen_exe_launcher.subprocess.run"
            ) as run_mock, patch("tools.frozen_exe_launcher.sys.argv", ["updater.exe", "--smoke-test"]):
                run_mock.return_value = subprocess.CompletedProcess([], 0)
                code = delegate_to_script(bundle, install, Path("tools") / "updater.py")
            self.assertEqual(code, 0)
            command, kwargs = run_mock.call_args
            self.assertEqual(command[0], ["py", "-3.11-64", str(script), "--smoke-test"])
            self.assertEqual(kwargs["cwd"], str(install))
            self.assertEqual(kwargs["env"]["PYTHONPATH"], str(bundle))

    def test_delegate_to_script_missing_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            bundle = install / "app"
            bundle.mkdir()
            code = delegate_to_script(bundle, install, Path("tools") / "missing.py")
            self.assertEqual(code, 1)

    def test_launcher_sources_use_frozen_entrypoints(self):
        build_source = Path("app/tools/build_windows_exes.py").read_text(encoding="utf-8")
        self.assertIn("frozen_launcher_setup.py", build_source)
        self.assertIn("frozen_launcher_updater.py", build_source)
        self.assertNotIn("setup_bootstrap.py", build_source.split("TARGETS")[1])

    def test_frozen_exe_launcher_is_stdlib_only(self):
        source = Path("app/tools/frozen_exe_launcher.py").read_text(encoding="utf-8")
        self.assertNotIn("from tools.updater", source)
        self.assertNotIn("from tools.setup_bootstrap", source)


if __name__ == "__main__":
    unittest.main()
