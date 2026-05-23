"""Shared unittest fixtures for config and instance path tests."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


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
