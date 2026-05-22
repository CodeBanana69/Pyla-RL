import os
import unittest
from unittest.mock import patch

from gui.brand import FREE_NOTICE, OFFICIAL_GITHUB
from gui.official_source import verify_official_source
from pathlib import Path


class OfficialSourceTests(unittest.TestCase):
    def test_license_is_noncommercial(self):
        license_text = Path("LICENSE").read_text(encoding="utf-8")
        self.assertIn("NonCommercial", license_text)

    def test_qml_contains_free_notice(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")
        self.assertIn("hubBrand", qml)
        self.assertIn("footerNotice", qml)
        self.assertIn("UNOFFICIAL COPY", qml)
        self.assertIn("accept-license", qml)

    @patch.dict(os.environ, {}, clear=True)
    @patch("gui.official_source.detect_git_remote")
    @patch("gui.official_source.read_build_info")
    def test_official_when_build_info_matches(self, mock_build_info, mock_remote):
        mock_build_info.return_value = {
            "repo_url": OFFICIAL_GITHUB,
            "commit": "abc1234",
        }
        mock_remote.return_value = ""

        result = verify_official_source()

        self.assertTrue(result["official"])
        self.assertEqual(result["commit"], "abc1234")

    @patch.dict(os.environ, {}, clear=True)
    @patch("gui.official_source.detect_git_remote")
    @patch("gui.official_source.read_build_info")
    def test_official_when_git_remote_matches(self, mock_build_info, mock_remote):
        mock_build_info.return_value = {}
        mock_remote.return_value = "https://github.com/CodeBanana69/Pyla-RL.git"

        result = verify_official_source()

        self.assertTrue(result["official"])

    @patch.dict(os.environ, {}, clear=True)
    @patch("gui.official_source.detect_git_remote")
    @patch("gui.official_source.read_build_info")
    def test_unofficial_when_no_provenance(self, mock_build_info, mock_remote):
        mock_build_info.return_value = {"repo_url": "https://github.com/scammer/resold-pyla"}
        mock_remote.return_value = ""

        result = verify_official_source()

        self.assertFalse(result["official"])
        self.assertIn("Unofficial", result["reason"])

    @patch.dict(os.environ, {"PYLA_RL_DEV": "1"}, clear=True)
    def test_dev_mode_skips_unofficial_warning(self):
        result = verify_official_source()
        self.assertTrue(result["official"])
        self.assertIn("Developer mode", result["reason"])

    def test_brand_constants(self):
        self.assertIn("free", FREE_NOTICE.lower())
        self.assertIn("CodeBanana69", OFFICIAL_GITHUB)


if __name__ == "__main__":
    unittest.main()
