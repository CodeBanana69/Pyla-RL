import unittest
from pathlib import Path


class SetupBootstrapTests(unittest.TestCase):
    def test_setup_bootstrap_uses_modern_pyla_install_command(self):
        source = Path("tools/setup_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn('"--pyla-install"', source)
        self.assertNotIn('["setup.py", "install"]', source)
        self.assertNotIn('"install"]', source)

    def test_setup_py_supports_direct_pyla_install_mode(self):
        source = Path("setup.py").read_text(encoding="utf-8")

        pyla_install_index = source.index('if "--pyla-install" in sys.argv:')
        setup_function_index = source.index("def setup_pyla():")
        setuptools_setup_index = source.index("setup(")
        legacy_redirect_index = source.index('if any(cmd in sys.argv for cmd in ["install", "develop"]):', pyla_install_index)

        self.assertGreater(pyla_install_index, setup_function_index)
        self.assertLess(pyla_install_index, setuptools_setup_index)
        self.assertLess(legacy_redirect_index, setuptools_setup_index)
        self.assertIn("Redirecting to PylaAi setup mode", source)
        self.assertIn("sys.exit(0)", source)

    def test_setup_bootstrap_handles_subprocess_errors_without_pyi_traceback(self):
        source = Path("tools/setup_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn("except subprocess.CalledProcessError", source)
        self.assertIn("Command failed with exit code", source)
        self.assertIn("raise SystemExit(exc.returncode)", source)

    def test_setup_bootstrap_has_certificate_download_fallbacks(self):
        source = Path("tools/setup_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn("download_with_powershell", source)
        self.assertIn("certificate fallback", source)
        self.assertIn("verify_windows_signature", source)
        self.assertIn("ssl._create_unverified_context", source)

    def test_gpu_repair_installs_qml_dependency(self):
        source = Path("tools/fix_gpu_runtime.py").read_text(encoding="utf-8")

        self.assertIn('"PySide6>=6.7.0"', source)

    def test_setup_repairs_numpy_before_importing_utils(self):
        source = Path("setup.py").read_text(encoding="utf-8")

        numpy_repair_index = source.index('force_install(["numpy<2.0.0"], no_deps=True)')
        utils_import_index = source.find("from utils import")
        self.assertEqual(utils_import_index, -1)
        self.assertLess(numpy_repair_index, source.index("force_install(base_reqs)"))
        self.assertIn('"numpy<2.0.0"', source)

    def test_direct_setup_creates_run_bat(self):
        source = Path("setup.py").read_text(encoding="utf-8")

        self.assertIn("def create_run_file", source)
        self.assertIn('"Run Pyla-RL.bat"', source)
        self.assertIn("create_run_file()", source)

    def test_main_repairs_numpy_before_importing_cv2(self):
        source = Path("main.py").read_text(encoding="utf-8")

        repair_index = source.index("repair_numpy_before_cv2_import()")
        cv2_index = source.index("import cv2")
        self.assertLess(repair_index, cv2_index)
        self.assertIn('"numpy<2.0.0"', source)
        self.assertIn("PYLAAI_NUMPY_REPAIR", source)


if __name__ == "__main__":
    unittest.main()
