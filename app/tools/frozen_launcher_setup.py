"""PyInstaller entry for setup.exe — delegates to app/tools/setup_bootstrap.py."""

from tools.frozen_exe_launcher import launch_setup

if __name__ == "__main__":
    raise SystemExit(launch_setup())
