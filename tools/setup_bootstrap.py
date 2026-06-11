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


def app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


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


def verify_windows_signature(path, label):
    if platform.system() != "Windows" or path.suffix.lower() != ".exe":
        return True
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                (
                    "$sig = Get-AuthenticodeSignature -LiteralPath $args[0]; "
                    "if ($sig.Status -eq 'Valid') { exit 0 } "
                    "Write-Host ('Signature status: ' + $sig.Status); exit 1"
                ),
                str(path),
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
    return False


def download_with_urllib(url, destination, timeout=45, insecure=False):
    context = ssl._create_unverified_context() if insecure else None
    with urllib.request.urlopen(url, timeout=timeout, context=context) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def download_with_powershell(url, destination):
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                "$ProgressPreference='SilentlyContinue'; "
                "Invoke-WebRequest -Uri $args[0] -OutFile $args[1] -UseBasicParsing"
            ),
            url,
            str(destination),
        ],
        text=True,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(message or f"PowerShell download failed with exit code {result.returncode}")


def download_file(url, destination, label):
    if destination.exists() and destination.stat().st_size > 1_000_000:
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
                if verify_windows_signature(destination, label):
                    return destination
                errors.append(f"{name}: downloaded file did not have a valid Windows signature")
            else:
                errors.append(f"{name}: downloaded file was empty or incomplete")
        except Exception as exc:
            errors.append(f"{name}: {exc}")

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


def ensure_project_venv(project_dir: Path, python_command: list[str]) -> tuple[list[str], str]:
    venv_dir = project_dir / ".venv"
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


def main():
    if not ensure_supported_windows():
        return 1

    project_dir = app_dir()
    bundle_dir = project_dir / "app"
    setup_py = bundle_dir / "setup.py"
    main_py = bundle_dir / "main.py"
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
    venv_command, venv_executable = ensure_project_venv(project_dir, python_command)
    print(f"Project venv: {venv_executable}")
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
    if progress_window:
        progress_window.update("Upgrading pip and setuptools...")
    run(venv_command + ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])

    env = os.environ.copy()
    env["PYLAAI_SETUP_AUTO"] = "1"
    if progress_window:
        progress_window.update("Installing Pyla-RL dependencies...")
    run(venv_command + ["setup.py", "--pyla-install"], cwd=bundle_dir, env=env)

    if progress_window:
        progress_window.update("Verifying EasyOCR runtime...")
    try:
        run(venv_command + ["-c", "import skimage; import easyocr"], cwd=project_dir)
    except SystemExit:
        print("")
        print("EasyOCR verification failed. Re-run setup or install missing packages with:")
        print(f'  "{venv_executable}" -m pip install scikit-image ninja pyclipper python-bidi Shapely')
        return 1

    from tools.hub_first_run import ensure_hub_first_run_wizard
    from tools.launcher_bat import create_run_file
    from tools.python_runtime import verify_runtime_imports, write_setup_status

    try:
        runtime_info = verify_runtime_imports(venv_command)
    except RuntimeError as exc:
        print("")
        print(str(exc))
        print("")
        print("Setup did not finish cleanly. Try running:")
        print(f'  "{venv_executable}" -m pip install pandas>=2.0.0')
        print(f'  "{venv_executable}" -m pip install --force-reinstall --no-deps opencv-python==4.8.0.76')
        print(f'  "{venv_executable}" tools\\check_runtime.py')
        input("Press Enter to close...")
        return 1

    versions = runtime_info.get("versions") or {}
    write_setup_status(
        project_dir,
        python_executable=venv_executable,
        cv2_version=str(versions.get("cv2", "")),
    )
    ensure_hub_first_run_wizard(project_dir)
    create_run_file(project_dir, python_executable=venv_executable)

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
