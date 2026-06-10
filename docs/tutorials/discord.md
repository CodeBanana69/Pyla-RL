# Discord Notifications

## Webhook (notifications only)

1. Open **Discord** tab or `cfg/discord_config.toml`.
2. Paste your channel **webhook URL**.
3. Enable **Send Match Summary** to post a report after every finished match.
4. Set **Ping Every X Matches** to `1` if you want a `@mention` on every match summary (`0` = summaries without mention).

Match summaries include brawler, result, trophy change, and optional screenshot.

**Heartbeat Every X Minutes** is optional. Leave it at `0` unless you want a separate still-running ping. It does not replace match summaries.

Webhooks cannot receive commands.

## Remote control (optional)

Slash commands need a **bot token** and restricted user/channel IDs.

See [Discord Remote Control](discord-remote-control.md) for full setup.

## Restart

Restart Pyla-RL after changing Discord settings.
