import unittest
from pathlib import Path


class SetupBootstrapTests(unittest.TestCase):
    def test_setup_bootstrap_uses_modern_pyla_install_command(self):
        source = Path("tools/setup_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn('"--pyla-install"', source)
        self.assertNotIn('["setup.py", "install"]', source)

    def test_run_bat_sets_miopen_env_for_amd_rocm_workaround(self):
        source = Path("tools/setup_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn("MIOPEN_FIND_MODE", source)
        self.assertIn("MIOPEN_DEBUG_DISABLE_FIND_DB", source)

    def test_setup_py_supports_direct_pyla_install_mode(self):
        source = Path("setup.py").read_text(encoding="utf-8")

        pyla_install_index = source.index('if "--pyla-install" in sys.argv:')
        setup_function_index = source.index("def setup_pyla():")
        setuptools_setup_index = source.index("setup(")

        self.assertGreater(pyla_install_index, setup_function_index)
        self.assertLess(pyla_install_index, setuptools_setup_index)


if __name__ == "__main__":
    unittest.main()
