# Settings and Performance

## License

Accept the free-use license under **Settings → About** before START.

Pyla-RL is free and open source (CC BY-NC 4.0). Do not sell or resell it.

## cfg folder

**Open cfg Folder** opens `cfg/` for advanced TOML edits. Restart the bot after changes.

### Where settings live

| Tier | Path | Purpose |
|------|------|---------|
| Shipped defaults | `cfg/*.toml` | Versioned templates in the repo |
| Machine secrets | `cfg/*.local.toml` | API tokens, Telegram bot token (gitignored) |
| Per-bot runtime | `instances/<id>/` | Farm plan JSON and instance overrides |

See [REPO_LAYOUT.md](../REPO_LAYOUT.md) for the full folder map.

Note: `cfg/time_tresholds.toml` keeps a legacy filename spelling; do not rename it without a migration shim.

## Performance profile

Profiles on **Overview** adjust scrcpy capture, ONNX threads, and related runtime settings.

Run `python tools/performance_check.py` to diagnose low IPS or wrong GPU provider.

## Terminal output

Settings → **Terminal / Debug** controls how much appears in the console:

| Setting | Default | Purpose |
|---------|---------|---------|
| Terminal Verbosity | `normal` | `quiet`, `normal`, `verbose`, or `debug` |
| Console Status Line | on | Updates IPS in place instead of printing a new line every second |
| Status Summary Seconds | `5` | How often the status line also shows state and active brawler |
| Movement Debug | off | Rate-limited movement trace (independent of Debug Screen) |
| Debug Screen | off | Visual overlay only; does not flood the terminal |
| Save Terminal Log | off | Mirror stdout/stderr to timestamped files under `logs/` |
| Wall Stuck Debug | off | Escape/unstuck movement diagnostics |

Recommended everyday setup: **Terminal Verbosity = normal**, **Console Status Line = on**, **Debug Screen** only when you need the overlay.

## Debug options

You can still enable **Super Debug** for pixel-count diagnostics and deeper vision traces. That is separate from the normal terminal verbosity levels.

## Reopen setup wizard

**Settings → About → Show Setup Wizard Again** reopens the first-run wizard.
