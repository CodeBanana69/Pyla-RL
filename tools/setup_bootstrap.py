import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


TARGET_PYTHON_VERSION = "3.11.9"
PYTHON_MAJOR_MINOR = "3.11"
PYTHON_INSTALLER_URL = (
    "https://www.python.org/ftp/python/"
    f"{TARGET_PYTHON_VERSION}/python-{TARGET_PYTHON_VERSION}-amd64.exe"
)
VC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"


def app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def run(command, cwd=None, env=None):
    print("> " + " ".join(str(part) for part in command))
    subprocess.check_call(command, cwd=str(cwd) if cwd else None, env=env)


def ensure_supported_windows():
    if platform.system() != "Windows":
        print("This setup.exe is for Windows only.")
        input("Press Enter to close...")
        return False
    if platform.machine().lower() not in ("amd64", "x86_64"):
        print("This setup.exe requires 64-bit Windows.")
        input("Press Enter to close...")
        return False
    return True


def download_file(url, destination, label):
    if destination.exists() and destination.stat().st_size > 1_000_000:
        return destination

    print(f"Downloading {label}...")
    try:
        with urllib.request.urlopen(url, timeout=45) as response, destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except Exception as exc:
        print("")
        print(f"Could not download {label}.")
        print("Check your internet connection, antivirus/firewall, or try again later.")
        print(f"Error: {exc}")
        input("Press Enter to close...")
        raise SystemExit(1)
    return destination


def python_info(command):
    try:
        output = subprocess.check_output(
            command + [
                "-c",
                "import platform,sys; "
                "print(sys.executable); "
                "print(platform.python_version()); "
                "print(platform.architecture()[0])",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip().splitlines()
    except Exception:
        return None

    if len(output) < 3:
        return None
    executable, version, arch = output[:3]
    if version.startswith(PYTHON_MAJOR_MINOR + ".") and arch == "64bit":
        return executable
    return None


def find_python():
    candidates = [
        ["py", f"-{PYTHON_MAJOR_MINOR}-64"],
        ["py", f"-{PYTHON_MAJOR_MINOR}"],
        ["python"],
    ]
    for command in candidates:
        executable = python_info(command)
        if executable:
            return command, executable

    common_roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
        Path(os.environ.get("ProgramFiles", "")),
    ]
    for root in common_roots:
        if not root.exists():
            continue
        for python_exe in root.glob("Python311/python.exe"):
            executable = python_info([str(python_exe)])
            if executable:
                return [str(python_exe)], executable
    return None, None


def download_python_installer():
    destination = Path(tempfile.gettempdir()) / f"pylaai-python-{TARGET_PYTHON_VERSION}-amd64.exe"
    return download_file(PYTHON_INSTALLER_URL, destination, f"Python {TARGET_PYTHON_VERSION}")


def install_python():
    installer = download_python_installer()
    print(f"Installing Python {TARGET_PYTHON_VERSION}...")
    run([
        str(installer),
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=1",
        "Include_launcher=1",
        "Include_test=0",
        "SimpleInstall=1",
    ])


def install_vc_redist():
    installer = download_file(
        VC_REDIST_URL,
        Path(tempfile.gettempdir()) / "pylaai-vc_redist.x64.exe",
        "Microsoft Visual C++ Redistributable x64",
    )
    print("Installing Microsoft Visual C++ Redistributable x64...")
    result = subprocess.run([
        str(installer),
        "/install",
        "/quiet",
        "/norestart",
    ])
    # 0 = installed, 1638 = another version already installed, 3010 = reboot required.
    if result.returncode not in (0, 1638, 3010):
        print("")
        print("Visual C++ Redistributable did not install cleanly.")
        print("If setup fails later with a DLL error, install it manually:")
        print(VC_REDIST_URL)
        print(f"Installer exit code: {result.returncode}")


def create_run_file(project_dir, python_command):
    python_invocation = " ".join(f'"{part}"' if " " in part else part for part in python_command)
    run_bat = project_dir / "Run PylaAi-XXZ.bat"
    run_bat.write_text(
        "@echo off\n"
        "cd /d %~dp0\n"
        "REM MIOpen: reduce HIPRTC JIT failures on Windows+AMD (README; requirements-rocm-windows.txt)\n"
        "set MIOPEN_FIND_MODE=5\n"
        "set MIOPEN_DEBUG_DISABLE_FIND_DB=0\n"
        "set OMP_NUM_THREADS=2\n"
        "set OPENBLAS_NUM_THREADS=2\n"
        "set MKL_NUM_THREADS=2\n"
        "set NUMEXPR_NUM_THREADS=2\n"
        f"{python_invocation} main.py\n"
        "pause\n",
        encoding="ascii",
    )
    print(f"Created {run_bat.name}")


def main():
    if not ensure_supported_windows():
        return 1

    project_dir = app_dir()
    setup_py = project_dir / "setup.py"
    main_py = project_dir / "main.py"
    if not setup_py.exists() or not main_py.exists():
        print("setup.exe must be placed in the PylaAi-XXZ project folder next to setup.py and main.py.")
        input("Press Enter to close...")
        return 1

    python_command, python_executable = find_python()
    if not python_command:
        install_python()
        python_command, python_executable = find_python()

    if not python_command:
        print("Could not find Python 3.11 after installation.")
        input("Press Enter to close...")
        return 1

    print(f"Using Python: {python_executable}")
    if "--smoke-test" in sys.argv:
        print("Smoke test passed. Python and project files are available.")
        return 0

    install_vc_redist()
    run(python_command + ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])

    env = os.environ.copy()
    env["PYLAAI_SETUP_AUTO"] = "1"
    run(python_command + ["setup.py", "--pyla-install"], cwd=project_dir, env=env)
    create_run_file(project_dir, python_command)

    print("")
    print("PylaAi-XXZ setup completed.")
    print("Start your emulator, open Brawl Stars, then run Run PylaAi-XXZ.bat or python main.py.")
    input("Press Enter to close...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
