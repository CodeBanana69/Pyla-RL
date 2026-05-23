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

## Debug options

In **Settings**, you can enable visual debug, terminal logging, and related diagnostics.

## Reopen setup wizard

**Settings → About → Show Setup Wizard Again** reopens the first-run wizard.
