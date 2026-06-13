"""Send a real startup_crash support report for local end-to-end testing."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from support_reporter import (  # noqa: E402
    async_send_support_report,
    ensure_support_reporting_defaults,
    install,
    load_support_settings,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emulate a real startup_crash support report (same path as bot crash handler).",
    )
    parser.add_argument(
        "--excepthook",
        action="store_true",
        help="Install the global excepthook and raise an uncaught exception instead.",
    )
    args = parser.parse_args(argv)

    ensure_support_reporting_defaults()
    settings = load_support_settings()
    if not settings.get("enabled", True):
        print("Support reporting is disabled in cfg/support_reporting.local.toml")
        return 1

    if args.excepthook:
        install()
        raise RuntimeError("Intentional uncaught crash test - safe to ignore")

    exc = RuntimeError("Intentional local crash test - safe to ignore")
    ok = asyncio.run(
        async_send_support_report(
            "startup_crash",
            f"{type(exc).__name__}: {exc}",
            exc=exc,
            extra={"test": True, "source": "trigger_support_crash_test.py"},
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
