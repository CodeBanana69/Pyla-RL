import argparse
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from performance_profile import PERFORMANCE_PROFILES, apply_performance_profile, get_performance_profile_summary


def main():
    parser = argparse.ArgumentParser(
        description="Apply known-good PylaAi-XXZ performance settings without editing emulator internals."
    )
    parser.add_argument(
        "--profile",
        choices=["balanced", "low-end", "low_end", "quality"],
        default="balanced",
        help="Performance profile to apply.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be applied without saving.")
    args = parser.parse_args()

    print("PylaAi-XXZ performance profile")
    print(f"Python: {platform.python_version()} {platform.architecture()[0]}")
    if platform.architecture()[0] != "64bit":
        print("WARNING: 32-bit Python is not supported. Run setup.exe to install Python 3.11 64-bit.")

    print(get_performance_profile_summary(args.profile))
    result = apply_performance_profile(args.profile, save=not args.dry_run)

    action = "Would apply" if args.dry_run else "Applied"
    print(f"{action} profile: {result['profile']}")
    print("Updated cfg/general_config.toml keys:")
    for key in result["changed_general_keys"]:
        print(f"- {key} = {result['general_config'][key]}")
    print("Updated cfg/bot_config.toml keys:")
    for key in result["changed_bot_keys"]:
        print(f"- {key} = {result['bot_config'][key]}")

    if not args.dry_run:
        print("\nRestart the bot after applying this profile.")
    print("Keep emulator graphics at 1920x1080 landscape, 280 DPI, 60 FPS, and disable eco/low-FPS mode.")
    print("Use local ADB only. If the device is 192.168.x.x, fix the emulator ADB port first.")
    print("Do not use 32-bit Python; emulator 32-bit Android/GFX mode is optional and depends on the user's PC.")


if __name__ == "__main__":
    main()
