from pathlib import Path

import toml

HUB_LICENSE_MARKER = ".hub_license_acknowledged"


def _default_cfg_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "cfg"


def _to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "yes", "true", "on"}


def _cfg_dir(project_dir=None):
    if project_dir and str(project_dir) not in {"", "."}:
        return Path(project_dir) / "cfg"
    return _default_cfg_dir()


def _marker_path(project_dir=None):
    return _cfg_dir(project_dir) / HUB_LICENSE_MARKER


def hub_license_acknowledged(project_dir=None):
    return _marker_path(project_dir).exists()


def mark_hub_license_acknowledged(project_dir=None):
    marker = _marker_path(project_dir)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("1", encoding="utf-8")


def ensure_hub_first_run_wizard(project_dir):
    """Ensure setup presents the license wizard before first hub use."""
    if hub_license_acknowledged(project_dir):
        return False

    config_path = _cfg_dir(project_dir) / "general_config.toml"
    config = toml.load(config_path) if config_path.exists() else {}
    config.setdefault("ui_language", "en")
    config.setdefault("ui_language_selected", "no")
    config["first_run_wizard"] = "yes"
    config["license_accepted"] = "no"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(toml.dumps(config), encoding="utf-8")
    return True
