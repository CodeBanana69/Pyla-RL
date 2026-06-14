# Discord Remote Control

Control your running Pyla-RL bot from Discord with slash commands. This is separate from webhook notifications.

## Safety

- Only enable remote control for **your** Discord user ID and **your** command channel.
- Never share your bot token.
- Use a private admin channel for `/screenshot`.

## Setup

1. Create a bot at https://discord.com/developers/applications
2. Copy the bot token into the Hub **Discord** tab (`discord_bot_token`).
3. Invite the bot with `bot` and `applications.commands` scopes.
4. Enable Developer Mode in Discord and copy:
   - Your user ID → `discord_control_user_id`
   - Command channel ID → `discord_control_channel_id`
   - Server ID → `discord_control_guild_id` (faster slash-command sync)
5. Set `discord_control_enabled = true` and restart Pyla-RL.

## Command reference

| Command | Description |
|---------|-------------|
| `/start` | Resume the bot |
| `/pause` | Pause the bot (`/stop` is deprecated) |
| `/status` | Live state, IPS, brawler, target |
| `/stats` | Session wins/losses/uptime |
| `/queue` | Show farm plan |
| `/push` | Prioritize a brawler |
| `/skip` | Play next brawler in queue |
| `/remove` | Remove a brawler from queue |
| `/target` | Set trophy target for active brawler |
| `/screenshot` | Send emulator screenshot |
| `/restart_game` | Restart Brawl Stars + scrcpy |
| `/restart_scrcpy` | Restart video feed only |
| `/restart_emulator` | Restart emulator profile |
| `/back` | Android Back |
| `/press` | Press q/e/f/g/h/m/back |
| `/help` | List commands |

## Multi-instance

Add `instance:your-id` to commands, e.g. `/status instance:ld-2`.

## Recovery order

1. `/back` for menus
2. `/restart_scrcpy` for frozen feed
3. `/restart_game` for crashed game
4. `/restart_emulator` for frozen emulator/ADB

## Troubleshooting

- **Commands missing:** restart Pyla-RL, verify guild ID and bot invite scopes.
- **Not allowed:** check user ID, channel ID, and guild ID.
- **Screenshot fails:** run `/status` first, then try `/restart_scrcpy`.
