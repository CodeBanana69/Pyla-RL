import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.parse
import zipfile
import ctypes
from pathlib import Path

from core.toml_merge import merge_toml_text


REPO_OWNER = "CodeBanana69"
REPO_NAME = "Pyla-RL"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
MAIN_BRANCH_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/main"
COMMITS_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits"
MAIN_BRANCH_ZIP = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/main.zip"
UPDATE_INFO_PATH = Path("cfg") / "update_info.json"

SKIPPED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "logs",
    "build",
    "dist",
}

SKIPPED_FILES = {
    "adb.exe",
    "adbwinapi.dll",
    "adbwinusbapi.dll",
    "brawl_stars_api.local.toml",
    "downgrader.exe",
    "telegram_chats.toml",
    "telegram_config.local.toml",
    "support_reporting.local.toml",
}

OBSOLETE_FILES = {
    "downgrader.exe",
    "setup.exe",
    "updater.exe",
}


def copy_root_launcher_files(source_install: Path, project_install: Path) -> list[str]:
    """Refresh root launchers from the update zip."""
    updated: list[str] = []
    for name in (
        "pyla-rl.bat",
        "readme.md",
        "README.md",
        "setup.cmd",
        "update.cmd",
    ):
        source = source_install / name
        if not source.is_file():
            continue
        destination = project_install / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        updated.append(name)
        print(f"Updated {name}")
    return updated


def wait_for_enter(prompt="Press Enter to close...") -> None:
    try:
        input(prompt)
    except EOFError:
        pass


def print_green(message: str) -> None:
    if os.name != "nt":
        print(f"\033[92m{message}\033[0m")
        return
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        # Bright green on the default black console background.
        kernel32.SetConsoleTextAttribute(handle, 0x0A)
        print(message)
        kernel32.SetConsoleTextAttribute(handle, 0x07)
    except Exception:
        print(message)


BUNDLE_DIR_NAMES = (
    "api",
    "bin",
    "cfg",
    "core",
    "data",
    "docs",
    "gui",
    "images",
    "instances",
    "models",
    "playstyles",
    "scrcpy",
    "tests",
    "tools",
)


def install_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def bundle_path(install: Path | None = None) -> Path:
    root = install or install_dir()
    return root / "app"


def app_dir() -> Path:
    return install_dir()


def _cfg_dir(install: Path) -> Path:
    bundled = bundle_path(install) / "cfg"
    if bundled.is_dir():
        return bundled
    legacy = install / "cfg"
    return legacy


def request_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "Pyla-RL-Updater",
    })
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def choose_release_download(release: dict) -> tuple[str, str]:
    assets = release.get("assets") or []
    zip_assets = [
        asset for asset in assets
        if str(asset.get("browser_download_url", "")).lower().endswith(".zip")
    ]
    if zip_assets:
        asset = zip_assets[0]
        return asset["browser_download_url"], asset.get("name") or "release asset"
    if release.get("zipball_url"):
        return release["zipball_url"], "GitHub source zip"
    return MAIN_BRANCH_ZIP, "main branch zip"


def latest_download_url() -> tuple[str, str]:
    # Hotfixes are pushed to main first. Using a GitHub release asset here can
    # install old code while the updater records the newest main SHA, making
    # future updater runs incorrectly say "You're on the latest version!".
    return MAIN_BRANCH_ZIP, "main branch zip"


def download_url_for_ref(ref: str) -> tuple[str, str]:
    ref = str(ref or "").strip()
    if not ref:
        return latest_download_url()
    encoded_ref = urllib.parse.quote(ref, safe="")
    return f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/{encoded_ref}.zip", f"GitHub ref {ref}"


def latest_main_sha() -> str | None:
    try:
        data = request_json(MAIN_BRANCH_API)
        sha = str(data.get("sha") or "").strip()
        return sha or None
    except Exception:
        return None


def resolve_ref_sha(ref: str) -> str | None:
    ref = str(ref or "").strip()
    if not ref:
        return latest_main_sha()
    try:
        data = request_json(f"{COMMITS_API}/{urllib.parse.quote(ref, safe='')}")
        sha = str(data.get("sha") or "").strip()
        return sha or None
    except Exception:
        # A tag/branch archive can still be downloadable even if the commit API
        # cannot resolve it, so install can continue without the local marker.
        return None


def recent_commits(limit=10) -> list[dict]:
    limit = max(1, min(int(limit), 30))
    data = request_json(f"{COMMITS_API}?sha=main&per_page={limit}")
    if not isinstance(data, list):
        return []
    return data


def previous_ref(commits: list[dict]) -> str:
    if len(commits) >= 2:
        return str(commits[1].get("sha", "")).strip()
    if commits:
        return str(commits[0].get("sha", "")).strip()
    return ""


def newest_ref(commits: list[dict]) -> str:
    if commits:
        return str(commits[0].get("sha", "")).strip()
    return ""


def print_recent_versions(limit=12) -> list[dict]:
    print("Recent versions from main:")
    commits = recent_commits(limit)
    for index, commit in enumerate(commits):
        sha = str(commit.get("sha", "")).strip()
        details = commit.get("commit") or {}
        message = str(details.get("message") or "").splitlines()[0]
        date = ((details.get("committer") or {}).get("date") or "")[:10]
        number = "1" if index == 0 else "0" if index == 1 else str(index)
        label = "newest" if index == 0 else "previous" if index == 1 else "older"
        print(f"  {number:>2}. {sha[:8]}  {date}  {label:<8}  {message}")
    return commits


def selected_ref_from_choice(choice: str, commits: list[dict]) -> str:
    choice = str(choice or "").strip()
    if not choice:
        return newest_ref(commits)
    lowered = choice.lower()
    if lowered in ("latest", "newest"):
        return newest_ref(commits)
    if lowered in ("--previous", "previous", "prev", "rollback"):
        return previous_ref(commits)
    if choice == "1":
        return newest_ref(commits)
    if choice == "0":
        return previous_ref(commits)
    if choice.isdigit():
        index = int(choice)
        if 2 <= index < len(commits):
            return str(commits[index].get("sha", "")).strip()
    return choice


def selected_ref_from_args_or_prompt(commits: list[dict]) -> str:
    plain_args = [
        arg for arg in sys.argv[1:]
        if not arg.startswith("--")
    ]
    if plain_args:
        return selected_ref_from_choice(plain_args[0], commits)

    print("")
    print("Type 1 for newest, 0 for previous/rollback, or paste a commit/tag/branch.")
    print("Press Enter for newest. Type cancel to quit.")
    choice = input("Version to install: ").strip()
    if choice.lower() in ("cancel", "quit", "exit"):
        return ""
    return selected_ref_from_choice(choice, commits)


def read_local_update_sha(project_dir: Path) -> str | None:
    info_path = bundle_path(project_dir) / UPDATE_INFO_PATH
    if not info_path.exists():
        info_path = project_dir / UPDATE_INFO_PATH
    if not info_path.exists():
        return None
    try:
        data = json.loads(info_path.read_text(encoding="utf-8-sig"))
        sha = str(data.get("main_sha") or "").strip()
        return sha or None
    except Exception:
        return None


def write_local_update_info(project_dir: Path, sha: str | None, selected_ref: str | None = None) -> None:
    if not sha:
        return
    info_path = bundle_path(project_dir) / UPDATE_INFO_PATH
    info_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "main_sha": sha,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "repo": f"{REPO_OWNER}/{REPO_NAME}",
    }
    if selected_ref:
        data["selected_ref"] = selected_ref
    info_path.write_text(json.dumps(data, indent=4), encoding="utf-8")


def download_file(url: str, destination: Path, label: str) -> Path:
    print(f"Downloading latest Pyla-RL update ({label})...")
    request = urllib.request.Request(url, headers={"User-Agent": "Pyla-RL-Updater"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    return destination


def merge_json_data(new_data, old_data):
    if isinstance(new_data, dict) and isinstance(old_data, dict):
        merged = dict(new_data)
        for key, old_value in old_data.items():
            if key in merged:
                merged[key] = merge_json_data(merged[key], old_value)
            else:
                merged[key] = old_value
        return merged
    return old_data


def is_valid_install(path: Path) -> bool:
    bundle = bundle_path(path)
    return (bundle / "main.py").is_file() and _cfg_dir(path).is_dir()


def find_project_root(extracted_dir: Path) -> Path:
    if is_valid_install(extracted_dir):
        return extracted_dir
    candidates: list[Path] = []
    for main_py in extracted_dir.rglob("main.py"):
        parent = main_py.parent
        if parent.name == "app":
            install = parent.parent
            if is_valid_install(install) or _cfg_dir(install).is_dir():
                candidates.append(install)
        elif (parent / "cfg").is_dir():
            candidates.append(parent)
    if not candidates:
        raise FileNotFoundError("Downloaded update does not look like a Pyla-RL project.")
    candidates.sort(key=lambda path: len(path.parts))
    return candidates[0]


def migrate_legacy_layout(install: Path) -> None:
    """Normalize flat or partial layouts into install-root + app/ bundle."""
    install = Path(install)
    bundle = bundle_path(install)
    bundle.mkdir(parents=True, exist_ok=True)
    migrated = False

    if (install / "main.py").is_file() and not (bundle / "main.py").is_file():
        migrated = True
        print("Migrating flat install into app/...")
        for py_file in install.glob("*.py"):
            destination = bundle / py_file.name
            if destination.exists():
                continue
            shutil.move(str(py_file), str(destination))
            print(f"Moved {py_file.name} -> app/{py_file.name}")
        for name in ("qt.conf",):
            source = install / name
            if source.is_file() and not (bundle / name).exists():
                shutil.move(str(source), str(bundle / name))
                print(f"Moved {name} -> app/{name}")

    for name in BUNDLE_DIR_NAMES:
        source = install / name
        destination = bundle / name
        if not source.exists() or source.resolve() == bundle.resolve():
            continue
        migrated = True
        if destination.exists() and source.is_dir():
            for child in source.iterdir():
                target = destination / child.name
                if target.exists():
                    continue
                shutil.move(str(child), str(target))
                print(f"Moved {name}/{child.name} -> app/{name}/{child.name}")
            if not any(source.iterdir()):
                source.rmdir()
        elif not destination.exists():
            shutil.move(str(source), str(destination))
            print(f"Moved {name}/ -> app/{name}/")

    for name in ("adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll"):
        source = install / name
        if source.is_file():
            destination = bundle / "bin" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                migrated = True
                shutil.move(str(source), str(destination))
                print(f"Moved {name} -> app/bin/{name}")

    legacy_queue = install / "latest_brawler_data.json"
    if legacy_queue.is_file():
        destination = bundle / "data" / "latest_brawler_data.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            migrated = True
            shutil.move(str(legacy_queue), str(destination))
            print("Moved latest_brawler_data.json -> app/data/latest_brawler_data.json")

    if migrated:
        print("Bundle layout migration complete.")


def backup_preserved_files(project_dir: Path, backup_dir: Path) -> None:
    cfg_dir = _cfg_dir(project_dir)
    if not cfg_dir.exists():
        return
    cfg_prefix = Path("app/cfg") if cfg_dir.parent.name == "app" else Path("cfg")
    for source in cfg_dir.iterdir():
        if source.suffix.lower() not in (".toml", ".json") or not source.is_file():
            continue
        relative_path = cfg_prefix / source.name
        destination = backup_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        print(f"Preserved {relative_path}")


def restore_preserved_files(project_dir: Path, backup_dir: Path) -> None:
    cfg_backup = backup_dir / "app" / "cfg"
    cfg_prefix = Path("app")
    if not cfg_backup.exists():
        cfg_backup = backup_dir / "cfg"
        cfg_prefix = Path(".")
    if not cfg_backup.exists():
        return
    for old_config in cfg_backup.iterdir():
        if old_config.suffix.lower() not in (".toml", ".json") or not old_config.is_file():
            continue
        relative_path = cfg_prefix / "cfg" / old_config.name
        if relative_path.as_posix().lower() == "cfg/webhook_config.toml":
            relative_path = cfg_prefix / "cfg" / "discord_config.toml"
        if relative_path.as_posix().lower() == "app/cfg/webhook_config.toml":
            relative_path = Path("app/cfg/discord_config.toml")
        destination = bundle_path(project_dir) / "cfg" / old_config.name
        if cfg_prefix == Path("."):
            destination = project_dir / "cfg" / old_config.name
        if destination.exists() and old_config.suffix.lower() == ".toml":
            merged = merge_toml_text(
                destination.read_text(encoding="utf-8-sig"),
                old_config.read_text(encoding="utf-8-sig"),
            )
            destination.write_text(merged, encoding="utf-8")
            print(f"Merged {relative_path}")
        elif destination.exists() and old_config.suffix.lower() == ".json":
            try:
                new_data = json.loads(destination.read_text(encoding="utf-8-sig"))
                old_data = json.loads(old_config.read_text(encoding="utf-8-sig"))
                merged = merge_json_data(new_data, old_data)
                destination.write_text(json.dumps(merged, indent=4), encoding="utf-8")
                print(f"Merged {relative_path}")
            except Exception:
                shutil.copy2(old_config, destination)
                print(f"Restored {relative_path}")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_config, destination)
            print(f"Restored {relative_path}")


def should_skip(relative_path: Path, source: Path) -> bool:
    parts = set(relative_path.parts)
    if parts & SKIPPED_DIRS:
        return True
    if source.is_file() and relative_path.name.lower() in SKIPPED_FILES:
        return True
    if (
            len(relative_path.parts) >= 2
            and relative_path.parts[0] == "cfg"
            and relative_path.suffix.lower() in (".toml", ".json")
    ):
        return False
    return False


def copy_update_files(source_install: Path, project_install: Path) -> None:
    migrate_legacy_layout(source_install)
    source_bundle = bundle_path(source_install)
    target_bundle = bundle_path(project_install)
    target_bundle.mkdir(parents=True, exist_ok=True)
    for source in source_bundle.rglob("*"):
        relative_path = source.relative_to(source_bundle)
        if should_skip(relative_path, source):
            continue
        destination = target_bundle / relative_path
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source, destination)
        except PermissionError:
            print(f"Skipped locked file: {relative_path}")


def remove_obsolete_files(project_dir: Path) -> None:
    for relative in OBSOLETE_FILES:
        target = project_dir / relative
        if not target.exists() or not target.is_file():
            continue
        try:
            target.unlink()
            print(f"Removed obsolete file: {relative}")
        except PermissionError:
            print(f"Could not remove locked obsolete file: {relative}")


def install_from_zip(project_dir: Path, url: str, label: str, marker_sha: str | None = None, selected_ref: str | None = None) -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="pyla_update_"))
    backup_dir = temp_dir / "preserved_user_files"
    zip_path = temp_dir / "pylaai_update.zip"

    try:
        migrate_legacy_layout(project_dir)
        backup_preserved_files(project_dir, backup_dir)
        download_file(url, zip_path, label)
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        print("Extracting update...")
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(extract_dir)
        source_root = find_project_root(extract_dir)
        print(f"Installing update from: {source_root}")
        copy_update_files(source_root, project_dir)
        copy_root_launcher_files(source_root, project_dir)
        remove_obsolete_files(project_dir)
        restore_preserved_files(project_dir, backup_dir)
        write_local_update_info(project_dir, marker_sha, selected_ref=selected_ref)
    except Exception:
        if backup_dir.exists():
            try:
                restore_preserved_files(project_dir, backup_dir)
            except Exception:
                pass
        raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def option_value(name: str) -> str | None:
    if name not in sys.argv:
        return None
    index = sys.argv.index(name)
    if index + 1 >= len(sys.argv):
        raise ValueError(f"{name} requires a value.")
    return sys.argv[index + 1]


def main() -> int:
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Pyla-RL updater")
        print("Downloads a GitHub update and keeps your cfg settings.")
        print("Run update.cmd, then choose 1 for newest or 0 for previous.")
        print("Use --ref <commit/tag/branch> to install or downgrade to a specific version.")
        print("Use --list-versions to show recent main commits you can pass to --ref.")
        print("Use --force to reinstall even when this folder is already current.")
        print("Use --smoke-test to verify that update.cmd starts.")
        print("Use --skip-setup to install files only without dependency repair.")
        return 0

    project_dir = app_dir()
    print("=" * 50)
    print("Pyla-RL Updater")
    print("=" * 50)
    print(f"Project folder: {project_dir}")

    if not is_valid_install(project_dir):
        print("update.cmd must be inside the Pyla-RL install folder next to app/main.py and app/cfg/.")
        wait_for_enter()
        return 1

    remove_obsolete_files(project_dir)

    if "--smoke-test" in sys.argv:
        print("Smoke test passed. Updater can see the Pyla-RL project folder.")
        return 0

    if "--list-versions" in sys.argv:
        try:
            count_arg = option_value("--list-versions")
            count = int(count_arg) if count_arg and not count_arg.startswith("--") else 10
        except Exception:
            count = 10
        try:
            print("Recent versions from main:")
            for commit in recent_commits(count):
                sha = str(commit.get("sha", ""))[:8]
                details = commit.get("commit") or {}
                message = str(details.get("message") or "").splitlines()[0]
                date = ((details.get("committer") or {}).get("date") or "")[:10]
                print(f"  {sha}  {date}  {message}")
            wait_for_enter()
            return 0
        except Exception as exc:
            print(f"Could not list versions: {exc}")
            wait_for_enter()
            return 1

    try:
        selected_ref = option_value("--ref")
    except ValueError as exc:
        print(exc)
        wait_for_enter()
        return 1

    if selected_ref is None:
        try:
            commits = print_recent_versions()
            selected_ref = selected_ref_from_args_or_prompt(commits)
        except Exception as exc:
            print(f"Could not load recent versions: {exc}")
            selected_ref = None
        if selected_ref == "":
            print("Cancelled.")
            wait_for_enter()
            return 0

    latest_sha = resolve_ref_sha(selected_ref) if selected_ref else latest_main_sha()
    local_sha = read_local_update_sha(project_dir)
    if latest_sha and local_sha == latest_sha and "--force" not in sys.argv:
        print_green("You're on the latest version!")
        wait_for_enter()
        return 0

    try:
        url, label = download_url_for_ref(selected_ref) if selected_ref else latest_download_url()
        install_from_zip(project_dir, url, label, marker_sha=latest_sha, selected_ref=selected_ref)
        setup_result = None
        if "--skip-setup" not in sys.argv:
            from tools.post_update_setup import run_post_update_setup

            setup_result = run_post_update_setup(project_dir)
        print("")
        if selected_ref:
            print(f"Version switch completed: {selected_ref}")
        else:
            print("Update completed.")
        print("Your cfg settings were kept, with new config keys added.")
        if setup_result is not None:
            print(setup_result.message)
            if not setup_result.ok:
                wait_for_enter()
                return 1
        wait_for_enter()
        return 0
    except Exception as exc:
        print("")
        print(f"Update failed: {exc}")
        wait_for_enter()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
