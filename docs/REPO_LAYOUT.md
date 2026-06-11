# Repository layout

[![Pyla-RL](https://img.shields.io/badge/repo-Pyla--RL-8E8E93)](https://github.com/CodeBanana69/Pyla-RL)
[![CI](https://github.com/CodeBanana69/Pyla-RL/actions/workflows/ci.yml/badge.svg)](https://github.com/CodeBanana69/Pyla-RL/actions/workflows/ci.yml)

Quick map of where code and data live in Pyla-RL. Project overview: [README](../README.md).

## Install root (what you see after extract)

| Path | Purpose |
|------|---------|
| `setup.exe` | One-click Windows setup |
| `updater.exe` | GitHub update installer |
| `pyla-rl.bat` | Canonical launcher |
| [`README.md`](../README.md) | GitHub landing page and project overview |
| [`app/`](../app/) | Runtime Python modules (`main.py`, `play.py`, …) |
| [`bin/`](../bin/) | Bundled `adb.exe` and DLLs |
| [`cfg/`](../cfg/) | Config templates and machine settings |
| [`data/`](../data/) | Single-instance farm plan (`latest_brawler_data.json`) |
| [`gui/`](../gui/) | Hub UI and instance management |
| [`instances/`](../instances/) | Per-bot farm plans (multi-instance) |
| [`tools/`](../tools/) | Setup helpers, diagnostics, dev scripts |
| [`tests/`](../tests/) | Unit tests |
| [`docs/`](.) | Tutorials, changelog, assets |

## Entry points

| Path | Purpose |
|------|---------|
| [`app/main.py`](../app/main.py) | Bot worker and game loop |
| [`pyla-rl.bat`](../pyla-rl.bat) | Windows launcher (sets `PYTHONPATH=app`) |
| [`app/setup.py`](../app/setup.py) | Dependency install helper |
| [`gui/qml_hub.py`](../gui/qml_hub.py) | Hub UI (QML) |

## Runtime modules (`app/`)

- [`play.py`](../app/play.py) — movement, combat, match loop
- [`stage_manager.py`](../app/stage_manager.py) — lobby, rewards, farm plan flow
- [`state_finder.py`](../app/state_finder.py) — screen/state detection
- [`lobby_automation.py`](../app/lobby_automation.py) — brawler picker automation
- [`window_controller.py`](../app/window_controller.py) — emulator / scrcpy / ADB
- [`runtime_control.py`](../app/runtime_control.py) — pause state, remote command IPC, F8 control window

## Remote control

| Path | Purpose |
|------|---------|
| [`discord_control.py`](../app/discord_control.py) | Discord slash commands |
| [`telegram_control.py`](../app/telegram_control.py) | Telegram bot commands |
| [`discord_notifier.py`](../app/discord_notifier.py) | Discord webhook notifications |
| [`telegram_notifier.py`](../app/telegram_notifier.py) | Telegram notifications |
| [`gui/remote_formatting.py`](../gui/remote_formatting.py) | Shared status/stats/queue text |
| [`gui/remote_command_router.py`](../gui/remote_command_router.py) | Multi-instance command routing |
| [`gui/remote_queue_commands.py`](../gui/remote_queue_commands.py) | Farm plan mutations for remote commands |

## Configuration and data tiers

| Tier | Location | Notes |
|------|----------|-------|
| Shipped defaults | [`cfg/*.toml`](../cfg/) | Versioned templates |
| Machine secrets | `cfg/*.local.toml` | Gitignored (API tokens, Telegram bot token) |
| Single-instance queue | [`data/latest_brawler_data.json`](../data/) | Default farm plan |
| Per-bot runtime | [`instances/<id>/`](../instances/) | Farm plan JSON, instance overrides |
| Session logs | `logs/` | Gitignored (metrics, match journal, remote replies) |

Multi-instance mode uses `instances/<id>/latest_brawler_data.json`.

## Tests

Run from the install root:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

`tests/conftest.py` adds `app/` to `PYTHONPATH` automatically.

## Docs

- [`TUTORIAL.md`](TUTORIAL.md) — index of feature tutorials
- [`tutorials/`](tutorials/) — step-by-step guides
