# README screenshot assets

Images used on the main [README](../../README.md) gallery.

| File | Shows | Re-capture when |
|------|--------|-----------------|
| `hub-overview.png` | Hub **Overview** tab — pre-flight checks, header **update pill**, performance profile | Hub layout, Overview tab, or header chrome changes |
| `hub-farm-plan.png` | Hub **Farm Plan** tab — queue builder and presets | Farm Plan UI changes |
| `control-window.png` | **Pyla-RL Control** — status pill, pause/resume, IPS graph, session strip | Control window layout, chrome, or metrics strip changes |

## Capture

From the repo root on Windows:

```bash
python tools/capture_readme_assets.py
```

Options:

- `--target hub-overview` / `hub-farm-plan` / `control-window` — single asset
- `--no-launch` — capture from already-open windows
- `--wait 25` — seconds to wait for each window

Farm Plan uses `gui.qml_hub --initial-tab "Farm Plan"` and temporarily seeds `data/latest_brawler_data.json` with demo brawlers for the screenshot.

Prerequisites for clean Hub shots: `license_accepted = "yes"` and `first_run_wizard = "no"` in local `cfg/general_config.toml` (do not commit local config).
