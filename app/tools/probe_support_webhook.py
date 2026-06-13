"""Send a one-off support report to verify webhook configuration."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from support_reporter import (  # noqa: E402
    async_send_support_report,
    ensure_support_reporting_defaults,
    load_support_settings,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Send a real test message to the maintainer support webhook.",
    )
    parser.add_argument(
        "--message",
        default="",
        help="Custom probe message (default: timestamped auto message)",
    )
    args = parser.parse_args(argv)

    ensure_support_reporting_defaults()
    settings = load_support_settings()
    if not settings.get("enabled", True):
        print("Support reporting is disabled in cfg/support_reporting.local.toml")
        return 1

    message = args.message.strip() or (
        f"Manual support webhook probe at {time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    ok = asyncio.run(
        async_send_support_report(
            "support_probe",
            message,
            extra={"probe": True, "source": "probe_support_webhook.py"},
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
