import unittest
from pathlib import Path


class SetupBootstrapTests(unittest.TestCase):
    def test_setup_bootstrap_uses_modern_pyla_install_command(self):
        bootstrap = Path("app/tools/setup_bootstrap.py").read_text(encoding="utf-8")
        post_update = Path("app/tools/post_update_setup.py").read_text(encoding="utf-8")

        self.assertIn("run_full_project_setup", bootstrap)
        self.assertIn('"--pyla-install"', post_update)
        self.assertNotIn('["setup.py", "install"]', post_update)

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
        self.assertIn("_powershell_literal", source)
        self.assertNotIn("$args[0]", source)
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
        source = Path("app/tools/post_update_setup.py").read_text(encoding="utf-8")

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
        source = Path("app/tools/post_update_setup.py").read_text(encoding="utf-8")

        self.assertIn("ensure_project_venv", source)
        self.assertIn("verify_runtime_imports", source)
        self.assertIn('["setup.py", "--pyla-install"]', source)
        self.assertIn("cwd=app_bundle", source)

    def test_general_config_template_requires_first_run_wizard(self):
        source = Path("app/gui/hub_state.py").read_text(encoding="utf-8")

        self.assertIn('setdefault("first_run_wizard", "yes")', source)
        self.assertIn('setdefault("license_accepted", "no")', source)

    def test_setup_bootstrap_delegates_to_post_update_setup(self):
        source = Path("app/tools/setup_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn("from tools.post_update_setup import run_full_project_setup", source)
        self.assertIn("run_full_project_setup(", source)

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
        easyocr_source = Path("app/tools/easyocr_runtime.py").read_text(encoding="utf-8")

        core_start = source.index("base_reqs = [")
        core_end = source.index("]", core_start)
        core_block = source[core_start:core_end]
        self.assertNotIn("easyocr", core_block)
        self.assertIn('"pandas>=2.0.0"', core_block)
        self.assertIn("install_easyocr_stack", source)
        self.assertIn('"scipy"', easyocr_source)
        self.assertIn('"PyYAML"', easyocr_source)

    def test_setup_verifies_easyocr_reader(self):
        source = Path("app/setup.py").read_text(encoding="utf-8")
        self.assertIn("verify_easyocr_runtime", source)
        self.assertIn("EasyOCR verified: Reader initialized (CPU)", source)

    def test_post_update_setup_verifies_easyocr_runtime(self):
        source = Path("app/tools/post_update_setup.py").read_text(encoding="utf-8")
        self.assertIn("verify_easyocr_runtime", source)
        self.assertNotIn('import skimage; import easyocr', source)

    def test_post_update_needs_full_setup_checks_easyocr(self):
        source = Path("app/tools/post_update_setup.py").read_text(encoding="utf-8")
        self.assertIn("probe_easyocr_runtime", source)

    def test_launcher_includes_easyocr_import_check(self):
        source = Path("app/tools/launcher_bat.py").read_text(encoding="utf-8")
        self.assertIn("import easyocr, scipy, skimage, torch", source)
        launcher = Path("pyla-rl.bat").read_text(encoding="utf-8")
        self.assertIn("import easyocr, scipy, skimage, torch", launcher)

    def test_fix_gpu_runtime_uses_shared_easyocr_install(self):
        source = Path("app/tools/fix_gpu_runtime.py").read_text(encoding="utf-8")
        self.assertIn("install_easyocr_stack", source)
        self.assertIn("verify_easyocr_runtime", source)
        base_start = source.index("BASE_REQUIREMENTS = [")
        base_end = source.index("]", base_start)
        base_block = source[base_start:base_end]
        self.assertNotIn('"easyocr"', base_block)


if __name__ == "__main__":
    unittest.main()
