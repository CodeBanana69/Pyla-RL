# Repository layout

Quick map of where code and data live in Pyla-RL. Project overview: [README](../../README.md).

## Install root (what you see after extract)

| Path | Purpose |
|------|---------|
| `setup.exe` | One-click Windows setup |
| `updater.exe` | GitHub update installer |
| `pyla-rl.bat` | Canonical launcher |
| [`README.md`](../../README.md) | GitHub landing page |
| [`app/`](../) | **Everything else** — code, cfg, tools, docs, assets |

## Inside `app/`

| Path | Purpose |
|------|---------|
| [`main.py`](../main.py) | Bot worker and game loop |
| [`setup.py`](../setup.py) | Dependency install helper |
| [`cfg/`](../cfg/) | Config templates and machine settings |
| [`bin/`](../bin/) | Bundled `adb.exe` |
| [`data/`](../data/) | Single-instance farm plan |
| [`gui/`](../gui/) | Hub UI |
| [`tools/`](../tools/) | Setup helpers and dev scripts |
| [`docs/`](.) | Tutorials, changelog, screenshots |
| [`tests/`](../tests/) | Unit tests |

## Tests

From the install root:

```bash
python -m unittest discover -s app/tests -t app -p "test_*.py"
```

Or set `PYTHONPATH=app` (CMD) / `$env:PYTHONPATH="app"` (PowerShell) before running unittest.
