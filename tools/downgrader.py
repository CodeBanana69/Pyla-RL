import sys

try:
    from updater import (
        app_dir,
        download_url_for_ref,
        install_from_zip,
        newest_ref,
        previous_ref,
        print_recent_versions,
        recent_commits,
        resolve_ref_sha,
        selected_ref_from_choice,
        wait_for_enter,
    )
except ModuleNotFoundError:
    from tools.updater import (
        app_dir,
        download_url_for_ref,
        install_from_zip,
        newest_ref,
        previous_ref,
        print_recent_versions,
        recent_commits,
        resolve_ref_sha,
        selected_ref_from_choice,
        wait_for_enter,
    )


def selected_ref_from_args_or_prompt(commits):
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        return selected_ref_from_choice(arg, commits)

    print("")
    latest_ref = newest_ref(commits)
    previous = previous_ref(commits)
    if latest_ref:
        print(f"Type 1 to install the newest version: {latest_ref[:8]}")
    if previous:
        print(f"Type 0 to install the previous version: {previous[:8]}")
    print("Or paste a commit/tag/branch.")
    print("Type cancel to quit.")
    choice = input("Version to install: ").strip()
    if not choice:
        return previous
    if choice.lower() in ("cancel", "quit", "exit"):
        return ""
    return selected_ref_from_choice(choice, commits)


def main() -> int:
    if "--help" in sys.argv or "-h" in sys.argv:
        print("PylaAi-XXZ version picker")
        print("Choose 1 for newest or 0 for previous/rollback.")
        print("Fast newest: updater.exe 1")
        print("Fast rollback: updater.exe 0")
        print("Advanced: updater.exe <commit/tag/branch>")
        return 0

    project_dir = app_dir()
    print("=" * 50)
    print("PylaAi-XXZ Version Picker")
    print("=" * 50)
    print(f"Project folder: {project_dir}")

    if not (project_dir / "main.py").exists():
        print("downgrader.exe must be inside the PylaAi-XXZ project folder next to main.py.")
        wait_for_enter()
        return 1

    try:
        commits = print_recent_versions()
    except Exception as exc:
        print(f"Could not load recent versions: {exc}")
        commits = []

    selected_ref = selected_ref_from_args_or_prompt(commits)
    if not selected_ref:
        print("Cancelled.")
        wait_for_enter()
        return 0

    marker_sha = resolve_ref_sha(selected_ref)
    url, label = download_url_for_ref(selected_ref)
    print("")
    print(f"Installing version: {selected_ref}")
    try:
        install_from_zip(project_dir, url, label, marker_sha=marker_sha, selected_ref=selected_ref)
    except Exception as exc:
        print("")
        print(f"Downgrade failed: {exc}")
        wait_for_enter()
        return 1

    print("")
    print(f"Version switch completed: {selected_ref}")
    print("Your cfg settings were kept, with new config keys added.")
    print("Run setup.exe if the selected version needs different dependencies.")
    wait_for_enter()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
