"""PyInstaller entry for updater.exe — delegates to app/tools/updater.py."""

from tools.frozen_exe_launcher import launch_updater

if __name__ == "__main__":
    raise SystemExit(launch_updater())
