# Telegram

## Notifications

1. Create a bot with [@BotFather](https://t.me/BotFather).
2. Paste the token in the **Telegram** tab (`bot_token`).
3. Set `enabled = true`.
4. Message your bot once with `/setup` to register the chat.

## Remote commands

Send these to your bot:

| Command | Description |
|---------|-------------|
| `/status` | Bot state and metrics |
| `/stats` | Session stats |
| `/pause` | Pause movement |
| `/resume` | Resume |
| `/queue` | Farm plan preview |
| `/push` | Prioritize brawler |
| `/skip` | Next brawler |
| `/remove` | Remove from queue |
| `/target` | Set trophy target |
| `/screenshot` | Emulator screenshot |
| `/restart_game` | Restart game |
| `/restart_scrcpy` | Restart feed |
| `/restart_emulator` | Restart emulator |
| `/back` | Android Back |
| `/press` | Game button |
| `/help` | Command list |

## Multi-instance

Add the instance ID as an extra argument, e.g. `/push shelly 1000 ld-2`.

## Restart

Restart Pyla-RL after changing Telegram settings.
