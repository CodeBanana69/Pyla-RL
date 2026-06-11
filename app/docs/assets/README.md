# README screenshot assets

Images used on the main [README](../../README.md) gallery.

| File | Shows | Re-capture when |
|------|--------|-----------------|
| `hub-overview.png` | Hub **Overview** tab — pre-flight checks, performance profile, game mode | Hub layout or Overview tab changes |
| `hub-farm-plan.png` | Hub **Farm Plan** tab — queue builder and presets | Farm Plan UI changes |
| `control-window.png` | **Pyla-RL Control** — pause/stop, IPS graph, session strip | Control window chrome or metrics strip changes |

## Capture

From the repo root on Windows:

```bash
python tools/capture_readme_assets.py
```

Options:

- `--target hub-overview` / `hub-farm-plan` / `control-window` — single asset
- `--no-launch` — capture from already-open windows
- `--wait 25` — seconds to wait for each window

Prerequisites for clean Hub shots: `license_accepted = "yes"` and `first_run_wizard = "no"` in local `cfg/general_config.toml` (do not commit local config).
