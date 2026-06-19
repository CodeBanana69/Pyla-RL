import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui.brand import OFFICIAL_GITHUB
from subprocess_text import run_text


def _git_value(args):
    try:
        result = run_text(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def main():
    output_path = ROOT / "cfg" / "build_info.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "repo_url": OFFICIAL_GITHUB,
        "commit": _git_value(["rev-parse", "--short", "HEAD"]) or "unknown",
        "built_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
