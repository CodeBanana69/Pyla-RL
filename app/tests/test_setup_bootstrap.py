import unittest
from pathlib import Path


class SetupBootstrapTests(unittest.TestCase):
    def test_setup_bootstrap_uses_modern_pyla_install_command(self):
        source = Path("app/tools/setup_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn('"--pyla-install"', source)
        self.assertNotIn('["setup.py", "install"]', source)
        self.assertNotIn('"install"]', source)

    def test_setup_py_supports_direct_pyla_install_mode(self):
        source = Path("app/setup.py").read_text(encoding="utf-8")

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
        source = Path("app/tools/setup_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn("except subprocess.CalledProcessError", source)
        self.assertIn("Command failed with exit code", source)
        self.assertIn("raise SystemExit(exc.returncode)", source)

    def test_setup_bootstrap_has_certificate_download_fallbacks(self):
        source = Path("app/tools/setup_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn("download_with_powershell", source)
        self.assertIn("certificate fallback", source)
        self.assertIn("verify_windows_signature", source)
        self.assertIn("ssl._create_unverified_context", source)

    def test_gpu_repair_installs_qml_dependency(self):
        source = Path("app/tools/fix_gpu_runtime.py").read_text(encoding="utf-8")

        self.assertIn('"PySide6>=6.7.0"', source)

    def test_setup_repairs_numpy_before_importing_utils(self):
        source = Path("app/setup.py").read_text(encoding="utf-8")

        numpy_repair_index = source.index("repair_numpy(verbose=True)")
        utils_import_index = source.find("from utils import")
        self.assertEqual(utils_import_index, -1)
        self.assertLess(numpy_repair_index, source.index("force_install(base_reqs)"))
        self.assertIn("repair_numpy", source)

    def test_direct_setup_does_not_create_run_bat(self):
        source = Path("app/setup.py").read_text(encoding="utf-8")

        self.assertNotIn("def create_run_file", source)
        self.assertNotIn("create_run_file()", source)

    def test_setup_bootstrap_uses_shared_launcher_helper(self):
        source = Path("app/tools/setup_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn("from tools.launcher_bat import create_run_file", source)
        self.assertIn("create_run_file(project_dir", source)

    def test_launcher_helper_removes_legacy_bat(self):
        source = Path("app/tools/launcher_bat.py").read_text(encoding="utf-8")

        self.assertIn("Run PylaAi-XXZ.bat", source)
        self.assertIn("pyla-xxz.bat", source)
        self.assertIn("Run Pyla-RL.bat", source)
        self.assertIn("pyla-rl.bat", source)
        self.assertIn('import cv2', source)
        self.assertIn("onnxruntime", source)
        self.assertIn("get_available_providers", source)
        self.assertIn("pyla_python.txt", source)
        self.assertIn("setup.exe", source)
        self.assertIn("fix_gpu_runtime.py auto", source)
        self.assertIn("legacy_path.unlink()", source)

    def test_setup_auto_installs_verified_gpu_runtime(self):
        source = Path("app/setup.py").read_text(encoding="utf-8")

        self.assertIn("auto_install_gpu_runtime", source)
        self.assertIn("verify=True", source)
        self.assertIn("PYLAAI_SETUP_AUTO", source)

    def test_setup_bootstrap_installs_into_project_venv(self):
        source = Path("app/tools/setup_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn("ensure_project_venv", source)
        self.assertIn("verify_runtime_imports", source)
        self.assertIn("bundle_dir / \"setup.py\"", source)
        self.assertIn("cwd=bundle_dir", source)
        self.assertIn("tools\\\\fix_gpu_runtime.py auto", source)

    def test_general_config_template_requires_first_run_wizard(self):
        source = Path("cfg/general_config.toml").read_text(encoding="utf-8")

        self.assertIn('first_run_wizard = "yes"', source)
        self.assertIn('license_accepted = "no"', source)

    def test_setup_bootstrap_prepares_hub_first_run_wizard(self):
        source = Path("app/tools/setup_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn("ensure_hub_first_run_wizard", source)

    def test_main_repairs_numpy_before_importing_cv2(self):
        source = Path("app/main.py").read_text(encoding="utf-8")

        repair_index = source.index("repair_numpy_before_cv2_import()")
        cv2_index = source.index("import cv2")
        self.assertLess(repair_index, cv2_index)
        self.assertIn('"numpy<2.0.0"', source)
        self.assertIn("PYLAAI_NUMPY_REPAIR", source)
        self.assertIn("ModuleNotFoundError", source)
        launcher = Path("pyla-rl.bat").read_text(encoding="utf-8")
        self.assertIn("setup.exe", launcher)
        self.assertIn("onnxruntime", launcher)

    def test_setup_verifies_onnxruntime_before_completion(self):
        source = Path("app/setup.py").read_text(encoding="utf-8")

        self.assertIn("import onnxruntime as ort", source)
        self.assertIn("ONNX Runtime verified", source)
        self.assertIn("ort.get_available_providers()", source)

    def test_setup_splits_easyocr_from_core_batch(self):
        source = Path("app/setup.py").read_text(encoding="utf-8")

        core_start = source.index("base_reqs = [")
        core_end = source.index("]", core_start)
        core_block = source[core_start:core_end]
        self.assertNotIn("easyocr", core_block)
        self.assertIn('"pandas>=2.0.0"', core_block)
        self.assertIn('force_install(["easyocr"], no_deps=True)', source)
        self.assertIn('"scikit-image"', source)


if __name__ == "__main__":
    unittest.main()
