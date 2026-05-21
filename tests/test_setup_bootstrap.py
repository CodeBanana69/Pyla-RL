import unittest
from pathlib import Path


class SetupBootstrapTests(unittest.TestCase):
    def test_setup_bootstrap_uses_modern_pyla_install_command(self):
        source = Path("tools/setup_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn('"--pyla-install"', source)
        self.assertNotIn('["setup.py", "install"]', source)

    def test_setup_py_supports_direct_pyla_install_mode(self):
        source = Path("setup.py").read_text(encoding="utf-8")

        pyla_install_index = source.index('if "--pyla-install" in sys.argv:')
        setup_function_index = source.index("def setup_pyla():")
        setuptools_setup_index = source.index("setup(")

        self.assertGreater(pyla_install_index, setup_function_index)
        self.assertLess(pyla_install_index, setuptools_setup_index)

    def test_setup_bootstrap_has_certificate_download_fallbacks(self):
        source = Path("tools/setup_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn("download_with_powershell", source)
        self.assertIn("certificate fallback", source)
        self.assertIn("verify_windows_signature", source)
        self.assertIn("ssl._create_unverified_context", source)

    def test_gpu_repair_installs_qml_dependency(self):
        source = Path("tools/fix_gpu_runtime.py").read_text(encoding="utf-8")

        self.assertIn('"PySide6>=6.7.0"', source)


if __name__ == "__main__":
    unittest.main()
