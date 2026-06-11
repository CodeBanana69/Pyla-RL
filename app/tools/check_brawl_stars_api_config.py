import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import (  # noqa: E402
    brawl_stars_api_config_status,
    load_brawl_stars_api_config,
    resolve_project_path,
)


def main():
    config_path = "cfg/brawl_stars_api.toml"
    resolved_path = resolve_project_path(config_path)
    print("Brawl Stars API config check")
    print(f"Reading: {resolved_path}")
    try:
        config = load_brawl_stars_api_config(config_path)
    except Exception as exc:
        print(f"FAILED: {exc}")
        return 1

    print(brawl_stars_api_config_status(config, config_path))
    if not config.get("api_token"):
        print("No API token is saved yet. If auto_refresh_token is enabled, Push All will try to create one.")
    else:
        print("API token is present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
