# Pyla-RL

This fork focuses on **Showdown** (trio). Other game modes still run off the upstream logic, but development effort and tuning here go into making Showdown play well end-to-end.

What the bot does in Showdown:

- **Analog joystick movement.** Brawlers are moved by a continuous angle, not WASD taps, so pathing and dodging are smoother than in the stock client-agnostic modes.
- **Follows teammates in trio** when there's no enemy to chase, with hysteresis so it doesn't ping-pong between two nearby teammates.
- **Trio team spacing.** The bot avoids stacking directly on teammates, orbits when grouped, and biases back toward the team instead of chasing too far alone.
- **Passive roam** when alone and safe — slow rotation of standing still.
- **Poison fog avoidance.** Detects the fog and when a trusted fog mass enters the flee radius around the player, overrides movement to run the opposite way.
- **Wall-based unstuck detector + semicircle escape.** If surrounding walls stop moving while the bot is commanding movement, it's pressed against something — the bot retreats from the obstacle and then sweeps a semicircular arc around it. The arc side alternates between triggers.
- **Place-based trophy tracking.** Recognizes 1st/2nd/3rd/4th-place end screens and updates the trophy count accordingly.

---

Pyla-RL is currently the best external Brawl Stars bot.
This repository is intended for devs and it's recommended for others to use the official version from the discord.

**Warning :** This is a source-code fork. It now includes a one-click Windows setup helper, but the official build and support are still linked in the Pyla Discord.

## Installation / How to run

### Official download (free)

Pyla-RL is **free and open source**. Do not pay for copies, repacks, or "premium builds."

- **GitHub (source):** https://github.com/CodeBanana69/Pyla-RL
- **Pyla Discord (support/community):** https://discord.gg/xUusk3fw4A

See [docs/ANTI_RESELLING.md](docs/ANTI_RESELLING.md) for what is prohibited and how to report resellers.

For normal users, you only need `setup.exe`.

1. Download or clone this repository.
2. Open the project folder.
3. Run `setup.exe`.
4. Wait until setup finishes. It will:
   - install Python 3.11.9 if Python 3.11 64-bit is missing
   - install all required Python packages
   - install the best available ONNX Runtime option for your PC, including GPU acceleration when possible
5. Start your Android emulator.
6. Open Brawl Stars in the emulator.
7. Set the emulator resolution to `1920x1080` for best results.
8. Double-click the generated `Run Pyla-RL.bat` file or run `python main.py`.
9. In the hub, choose your emulator, select your brawler setup, then press Start.

Emulator and ADB troubleshooting:
- After setup, use **`Run Pyla-RL.bat`** only (older `Run PylaAi-XXZ.bat` launchers are removed automatically).
- On the Hub **Overview** tab, pick **LDPlayer** or **MuMu** first, then click **Run Checks**.
- **LDPlayer:** enable ADB in Settings → Other settings → ADB debugging, then restart the emulator. Default port is `5555` (instance 1 uses `5557`, instance 2 uses `5559`).
- **MuMu:** confirm ADB is enabled in emulator settings. Default port is `16384` (instance 1 uses `16416`).
- START is allowed once the **ADB device** check passes. Emulator process, Brawl Stars foreground, and resolution rows are warnings only.

Manual developer setup:
- Install Python 3.11 and Git.
- Run `python setup.py --pyla-install`.
- Run `python main.py`.

Brawl Stars API trophy autofill :
- Create a developer account at https://developer.brawlstars.com/
- Open `cfg/brawl_stars_api.toml`.
- Fill in:
  `player_tag = "#YOURTAG"`
  `developer_email = "YOUR_DEVELOPER_EMAIL"`
  `developer_password = "YOUR_DEVELOPER_PASSWORD"`
- You can also set the player tag in the Hub under Additional Settings.
- When you click a brawler in the brawler selection window, the Current Trophies field is filled from the API automatically.
- Auto-refresh logs in to the official developer portal, detects the current public IP, deletes old Pyla-RL-created keys, creates a fresh key for that IP, and saves the generated token locally.
- Keep `delete_all_tokens = false` unless you really want every key on the developer account deleted.
- Do not share a filled `cfg/brawl_stars_api.toml`; the committed file should keep tokens, email, and password blank.

Push All 1k :
- Fill `cfg/brawl_stars_api.toml` first.
- Start your emulator, open Brawl Stars, and leave the game on the lobby screen.
- Run `python main.py`.
- In the brawler selection window, press `Push All 1k`.
- The bot will sort the in-game brawler menu by Least Trophies, select the lowest trophy brawler, and build a queue for all known brawlers under 1000 trophies.

Recovery features :
- If Brawl Stars closes or another app is in front, the bot can relaunch Brawl Stars.
- If the Brawl Stars Idle Disconnect / Reload dialog appears, the bot presses Reload.
- If the scrcpy video feed freezes, the bot restarts the scrcpy feed instead of repeatedly restarting Brawl Stars.
- While the bot is running, a small `Pyla-RL Control` window lets you pause and resume movement safely.

Multi-instance mode (LDPlayer + MuMu):
- Enable **Multi-Instance** in the Hub **Instances** tab, then restart the Hub so the shared Discord/Telegram router starts.
- Each instance profile gets its own emulator port, farm plan (`instances/<id>/latest_brawler_data.json`), and worker process.
- Supported emulators: **LDPlayer** (5555/5557/5559) and **MuMu** (16384/16416/16448). Each running instance must use a unique ADB port.
- Use the Instances dashboard to start/stop workers while the Hub stays open.
- Discord/Telegram commands accept an optional `instance` argument (for example `/status instance:ld-1`). If only one instance is running, the argument is optional.
- With multi-instance disabled, Pyla-RL keeps the original single-process launch flow unchanged.

Discord webhook and remote control :
- Open `cfg/discord_config.toml`.
- Webhook notifications only need `webhook_url`.
- Discord `/pause`, `/start`, and `/status` need a Discord bot token, because normal webhooks cannot receive commands.
- Slash commands: `/pause`, `/start`, `/stop_all`, `/status`, `/stats`, `/queue`, `/screenshot`, `/push`, `/skip`, `/remove`, `/target`, `/pause_menu`, `/restart_game`, `/restart_scrcpy`, `/restart_emulator`, `/back`, `/press`, `/help`. `/stop` still pauses but is deprecated — use `/pause` instead. Command replies use formatted Discord embed cards.
- Create a bot token:
  1. Go to https://discord.com/developers/applications
  2. Click `New Application`.
  3. Open `Bot`.
  4. Click `Reset Token` or `View Token`, then copy it into `discord_bot_token`.
  5. Keep this token private. Anyone with it can control the Discord bot.
- Invite the bot to your server:
  1. In the same Discord Developer Portal app, open `OAuth2` -> `URL Generator`.
  2. Select scopes `bot` and `applications.commands`.
  3. Select basic bot permissions such as `Send Messages` and `Use Slash Commands`.
  4. Open the generated URL and invite it to your server.
- Enable remote control:
  `discord_control_enabled = true`
- Get your Discord user ID:
  1. In Discord, open `User Settings` -> `Advanced`.
  2. Enable `Developer Mode`.
  3. Right-click your Discord profile and click `Copy User ID`.
  4. Paste it into `discord_control_user_id`. If this is blank, Pyla-RL uses `discord_id`.
- Get a channel ID:
  1. With Developer Mode enabled, right-click the channel where commands should work.
  2. Click `Copy Channel ID`.
  3. Paste it into `discord_control_channel_id`.
  4. Leave it blank if commands should work in any channel where the bot is invited.
- Get a guild/server ID:
  1. With Developer Mode enabled, right-click the server icon.
  2. Click `Copy Server ID`.
  3. Paste it into `discord_control_guild_id`.
  4. Filling this makes slash commands appear faster because they sync to that server only.
- Restart Pyla-RL after changing the Discord bot token or remote-control settings.

Telegram notifications and remote control :
- Open `cfg/telegram_config.toml`.
- Create a bot with `@BotFather`, then paste the token into `bot_token`.
- Set `enabled = true`.
- Open the Telegram bot on your phone and send `/setup` or `/help` once. That chat is remembered for notifications.
- Commands:
  `/status`, `/stats`, `/pause`, `/resume`, `/quit`, `/queue`, `/push`, `/skip`, `/remove`, `/target`, `/pause_menu`, `/screenshot`, `/restart_game`, `/restart_scrcpy`, `/restart_emulator`, `/back`, `/press`, `/help`.
- Restart Pyla-RL after changing the Telegram token or remote-control settings.

Performance troubleshooting :
- Run `python tools/performance_check.py`.
- If it says `CPUExecutionProvider`, run `setup.exe` again or set `cfg/general_config.toml` `cpu_or_gpu = "directml"`.
- If the bot shows `1-2 IPS` while Python CPU usage is low, check the `scrcpy frame FPS` line from `tools/performance_check.py`. Low frame FPS means the emulator/ADB feed is slow, not the AI model.
- On laptops with two GPUs, set Windows Graphics settings for `python.exe` and the emulator to High performance.
- If DirectML is active but still very slow, try `directml_device_id = "1"` in `cfg/general_config.toml`, then restart the bot.
- Turn off Windows Efficiency mode for the emulator if Task Manager shows it. Efficiency mode can cap emulator frame delivery and make the bot look stuck at 2-5 IPS.
- For LDPlayer or MuMu, select the matching emulator in the hub or set `current_emulator = "LDPlayer"` / `"MuMu"` in `cfg/general_config.toml`, use 1920x1080 landscape, set emulator FPS to 60, and disable any low-FPS/eco mode.
- If MuMu black-screens or lags after a few matches, open `logs/recovery_events.jsonl` and look for repeated `display_repair` or `scrcpy_restart` events. Also check console lines containing `displayId=`. Lower `scrcpy_max_fps` to 30 and `scrcpy_max_width` to 720 if the emulator video pipeline is struggling.
- Keep some free RAM. If memory is above about 85%, close Discord/browser/other games before running the bot.
- Enable `Debug Screen` in Additional Settings to open a live vision overlay while the bot runs. It shows player, teammate, enemy, wall, fog, and range overlays.

Wall model improvement :
- The active wall/bush model is `models/tileDetector.onnx`.
- Capture wall-model frames:
  `python tools/capture_wall_samples.py --seconds 300 --start-match`
- Build the wall YOLO dataset:
  `python tools/create_wall_dataset.py`
- Label the images in YOLO format with:
  `0 wall`
  `1 bush`
  `2 close_bush`
- Train/export on GPU:
  `python tools/train_wall_model.py --device 0`
- After testing, install the exported wall model:
  `python tools/install_vision_model.py --source runs/wall_train/pylaai_wall/weights/best.onnx --target models/tileDetector.onnx`

Notes :
- This is the "localhost" version which means everything API related isn't enabled (login, online stats tracking, auto brawler list updating, auto icon updating, auto wall model updating). 
You can make it "online" by changing the base api url in utils.py and recoding the app to answer to the different endpoints. Site's code might become opensource but currently isn't.
- You can get the .pt version of the ai vision model at https://github.com/AngelFireLA/BrawlStarsBotMaking
- This repository won't contain early access features before they are released to the public.
- Please respect the CC BY-NC license: Pyla-RL must not be sold or resold. See [docs/ANTI_RESELLING.md](docs/ANTI_RESELLING.md).

Devs : 
- Iyordanov
- AngelFire

# Run tests
Run `python -m unittest discover` to check if your changes have made any regressions. 

# Performance profile
If the bot drops to 1-3 IPS while Python CPU usage is low, first apply the safe capture profile and restart:

`python tools/apply_performance_profile.py --profile balanced`

Use `--profile low-end` for older laptops that overheat or throttle. Pyla-RL requires 64-bit Python; emulator 32-bit/GFX modes are optional emulator settings, not a Python requirement.

# If you want to contribute, don't hesitate to create an Issue, a Pull Request, or/and make a ticket on the Pyla discord server at :
https://discord.gg/xUusk3fw4A

Don't know what to do ? Check the To-Fix and Idea lists :
https://trello.com/b/SAz9J6AA/public-pyla-trello
