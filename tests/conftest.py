"""Shared unittest fixtures for config and instance path tests."""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1] / "app"
if _APP_ROOT.is_dir() and str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


@contextmanager
def temp_repo_layout():
    """Create an isolated cfg/ + instances/ tree for tests that touch disk paths."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg_dir = root / "cfg"
        instances_dir = root / "instances" / "default"
        cfg_dir.mkdir(parents=True)
        instances_dir.mkdir(parents=True)
        (cfg_dir / "general_config.toml").write_text('pyla_version = "test"\n', encoding="utf-8")
        (instances_dir / "latest_brawler_data.json").write_text("[]", encoding="utf-8")
        original_cwd = os.getcwd()
        try:
            os.chdir(root)
            yield root
        finally:
            os.chdir(original_cwd)
