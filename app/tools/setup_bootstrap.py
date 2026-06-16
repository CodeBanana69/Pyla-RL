import os
import platform
import shutil
import subprocess
import ssl
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


def install_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundle_dir():
    return install_dir() / "app"


app_dir = install_dir


def run(command, cwd=None, env=None):
    print("> " + " ".join(str(part) for part in command))
    try:
        subprocess.check_call(command, cwd=str(cwd) if cwd else None, env=env)
    except subprocess.CalledProcessError as exc:
        print("")
        print(f"Command failed with exit code {exc.returncode}:")
        print("  " + " ".join(str(part) for part in command))
        print("")
        print("Setup could not finish. Most setup failures are fixed by running this inside the project folder:")
        print('  py -3.11-64 setup.py --pyla-install')
        print("")
        input("Press Enter to close...")
        raise SystemExit(exc.returncode) from exc


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


def _powershell_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def verify_windows_signature(path, label, *, required=True):
    if platform.system() != "Windows" or path.suffix.lower() != ".exe":
        return True
    path_literal = _powershell_literal(str(path))
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                (
                    f"$sig = Get-AuthenticodeSignature -LiteralPath {path_literal}; "
                    "if ($sig.Status -eq 'Valid') { exit 0 } "
                    "Write-Host ('Signature status: ' + $sig.Status); exit 1"
                ),
            ],
            text=True,
            capture_output=True,
            timeout=20,
        )
        if result.returncode == 0:
            return True
        print(f"{label} signature check failed.")
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.stderr.strip():
            print(result.stderr.strip())
    except Exception as exc:
        print(f"Could not verify {label} signature: {exc}")
    if not required:
        print(f"WARNING: Continuing without verified signature for {label}.")
        return True
    return False


def download_with_urllib(url, destination, timeout=45, insecure=False):
    context = ssl._create_unverified_context() if insecure else None
    with urllib.request.urlopen(url, timeout=timeout, context=context) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def download_with_powershell(url, destination):
    url_literal = _powershell_literal(url)
    dest_literal = _powershell_literal(str(destination))
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                "$ProgressPreference='SilentlyContinue'; "
                f"Invoke-WebRequest -Uri {url_literal} -OutFile {dest_literal} -UseBasicParsing"
            ),
        ],
        text=True,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(message or f"PowerShell download failed with exit code {result.returncode}")


def download_file(url, destination, label, *, required=True, require_signature=True):
    if destination.exists() and destination.stat().st_size > 1_000_000:
        if not require_signature or verify_windows_signature(destination, label, required=required):
            return destination

    print(f"Downloading {label}...")
    errors = []
    attempts = [
        ("Python HTTPS", lambda: download_with_urllib(url, destination)),
        ("Windows downloader", lambda: download_with_powershell(url, destination)),
        ("certificate fallback", lambda: download_with_urllib(url, destination, insecure=True)),
    ]
    for name, action in attempts:
        try:
            if destination.exists():
                destination.unlink()
            action()
            if destination.exists() and destination.stat().st_size > 1_000_000:
                if not require_signature or verify_windows_signature(destination, label, required=required):
                    return destination
                errors.append(f"{name}: downloaded file did not have a valid Windows signature")
            else:
                errors.append(f"{name}: downloaded file was empty or incomplete")
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    if destination.exists() and destination.stat().st_size > 1_000_000 and not required:
        print(f"WARNING: Using {label} without a verified signature.")
        return destination

    print("")
    print(f"Could not download {label}.")
    print("This is usually a broken Windows/Python certificate store, antivirus HTTPS scanning, proxy/VPN filtering, or the wrong PC date/time.")
    print("Setup tried Python HTTPS, Windows PowerShell download, and a signed-installer fallback.")
    print("")
    print("What to try:")
    print("- Check Windows date/time.")
    print("- Run Windows Update, then restart.")
    print("- Temporarily disable antivirus HTTPS/SSL scanning or try another network/VPN.")
    print("- Download this file manually in a browser and place it here:")
    print(f"  {destination}")
    print(f"  {url}")
    print("")
    print("Download errors:")
    for error in errors:
        print(f"- {error}")
    if not required:
        return None
    input("Press Enter to close...")
    raise SystemExit(1)


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


def _venv_pip_usable(venv_python: Path) -> bool:
    try:
        result = subprocess.run(
            [str(venv_python), "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def ensure_project_venv(project_dir: Path, python_command: list[str]) -> tuple[list[str], str]:
    venv_dir = project_dir / ".venv"
    venv_python = venv_dir / "Scripts" / "python.exe"
    if venv_python.exists() and not _venv_pip_usable(venv_python):
        print("Project .venv has a broken pip install. Recreating it...")
        shutil.rmtree(venv_dir, ignore_errors=True)
        venv_python = venv_dir / "Scripts" / "python.exe"
    if not venv_python.exists():
        print(f"Creating project virtual environment at {venv_dir}...")
        run(python_command + ["-m", "venv", str(venv_dir)])
    if not venv_python.exists():
        print("Could not create .venv for Pyla-RL.")
        input("Press Enter to close...")
        raise SystemExit(1)
    return [str(venv_python)], str(venv_python)


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
    destination = Path(tempfile.gettempdir()) / "pylaai-vc_redist.x64.exe"
    installer = download_file(
        VC_REDIST_URL,
        destination,
        "Microsoft Visual C++ Redistributable x64",
        required=False,
        require_signature=False,
    )
    if installer is None:
        print("")
        print("WARNING: Visual C++ Redistributable could not be downloaded automatically.")
        print("Setup will continue. If you later see missing DLL errors, install it manually:")
        print(VC_REDIST_URL)
        return
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


def main():
    if not ensure_supported_windows():
        return 1

    project_dir = install_dir()
    app_bundle = bundle_dir()
    setup_py = app_bundle / "setup.py"
    main_py = app_bundle / "main.py"
    if not setup_py.exists() or not main_py.exists():
        print("setup.exe must be placed in the Pyla-RL project folder next to app/setup.py and app/main.py.")
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
    progress_window = None
    if os.environ.get("PYLAAI_SETUP_GUI", "").strip().lower() in {"1", "yes", "true", "on"}:
        try:
            from tools.setup_progress_window import SetupProgressWindow

            progress_window = SetupProgressWindow()
            progress_window.update("Checking Python and dependencies...")
        except Exception:
            progress_window = None
    if "--smoke-test" in sys.argv:
        print("Smoke test passed. Python and project files are available.")
        return 0

    install_vc_redist()
    from tools.post_update_setup import run_full_project_setup

    if not run_full_project_setup(
        project_dir,
        progress_callback=progress_window.update if progress_window else None,
        interactive=True,
        install_vc_redist=None,
    ):
        return 1

    print("")
    print("Pyla-RL setup completed.")
    print("Start your emulator, open Brawl Stars, then run pyla-rl.bat or python app/main.py.")
    if progress_window:
        progress_window.update("Setup completed.")
        progress_window.close()
    input("Press Enter to close...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
