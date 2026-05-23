# Repository layout

Quick map of where code and data live in Pyla-RL.

## Entry points

| Path | Purpose |
|------|---------|
| [`main.py`](../main.py) | Bot worker and game loop |
| [`pyla-rl.bat`](../pyla-rl.bat) | Windows launcher (canonical) |
| [`setup.py`](../setup.py) | One-click install helper |
| [`gui/qml_hub.py`](../gui/qml_hub.py) | Hub UI (QML) |

## Root runtime modules

Core gameplay and vision logic sit at the repo root for historical reasons:

- [`play.py`](../play.py) — movement, combat, match loop
- [`stage_manager.py`](../stage_manager.py) — lobby, rewards, farm plan flow
- [`state_finder.py`](../state_finder.py) — screen/state detection
- [`lobby_automation.py`](../lobby_automation.py) — brawler picker automation
- [`window_controller.py`](../window_controller.py) — emulator / scrcpy / ADB
- [`runtime_control.py`](../runtime_control.py) — pause state, remote command IPC, F8 control window

## Remote control

| Path | Purpose |
|------|---------|
| [`discord_control.py`](../discord_control.py) | Discord slash commands |
| [`telegram_control.py`](../telegram_control.py) | Telegram bot commands |
| [`discord_notifier.py`](../discord_notifier.py) | Discord webhook notifications |
| [`telegram_notifier.py`](../telegram_notifier.py) | Telegram notifications |
| [`gui/remote_formatting.py`](../gui/remote_formatting.py) | Shared status/stats/queue text |
| [`gui/remote_command_router.py`](../gui/remote_command_router.py) | Multi-instance command routing |
| [`gui/remote_queue_commands.py`](../gui/remote_queue_commands.py) | Farm plan mutations for remote commands |

Tutorials: [Discord remote control](tutorials/discord-remote-control.md), [Telegram](tutorials/telegram.md).

## GUI (`gui/`)

- [`qml_hub.py`](../gui/qml_hub.py) + [`qml/PylaHub.qml`](../gui/qml/PylaHub.qml) — active Hub
- [`hub_state.py`](../gui/hub_state.py) — Hub config store
- [`select_brawler.py`](../gui/select_brawler.py) — brawler selection window
- [`instance_config.py`](../gui/instance_config.py) — per-instance paths
- [`brawler_queue.py`](../gui/brawler_queue.py) — farm plan load/save

## Configuration and data tiers

| Tier | Location | Notes |
|------|----------|-------|
| Shipped defaults | [`cfg/*.toml`](../cfg/) | Versioned templates |
| Machine secrets | `cfg/*.local.toml` | Gitignored (API tokens, Telegram bot token) |
| Per-bot runtime | [`instances/<id>/`](../instances/) | Farm plan JSON, instance overrides |
| Session logs | `logs/` | Gitignored (metrics, match journal, remote replies) |

Single-instance mode still uses root [`latest_brawler_data.json`](../latest_brawler_data.json) when multi-instance is off; multi-instance uses `instances/<id>/latest_brawler_data.json`.

## Tools and tests

| Path | Purpose |
|------|---------|
| [`tools/`](../tools/) | Dev scripts (dataset, GPU fix, performance check, icon download) |
| [`tests/`](../tests/) | Unit tests — run with `python -m unittest discover -s tests -p "test_*.py"` |

## Docs

- [`TUTORIAL.md`](TUTORIAL.md) — index of feature tutorials
- [`tutorials/`](tutorials/) — step-by-step guides
