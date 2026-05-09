# Pyla-RL — Reinforcement Learning fork of PylaAi-XXZ

**Pyla-RL** is a reinforcement-learning fork of PylaAi-XXZ. It keeps every brawler-specific attack/super/gadget rule from the upstream bot and replaces only the **movement** layer with a Stable-Baselines3 PPO policy that learns to position, dodge, and rotate from live gameplay.

What's different in this fork:

- **PPO movement policy.** When `use_rl_movement = "yes"` in `cfg/bot_config.toml`, every approach / retreat / strafe / dodge call is produced by a neural policy instead of the heuristic movement code. Combat (attacks, supers, gadgets) is unchanged.
- **Online training on live frames.** With `enable_rl_movement_training = "yes"` the bridge submits one transition per frame to a Gym env and runs `model.learn()` on a worker thread, so the game loop never blocks on gradient steps. Weights are persisted to `models/rl_movement_policy.zip`.
- **Direction-gated projectile tracker.** A lightweight EMA tracker fuses YOLO projectile classes with residual detector keys and masked motion blobs, then keeps only tracks whose velocity is heading at the player. The strictness is exposed as the **Projectile Detection Confidence** slider in the hub (sits next to wall and entity confidence).
- **Live RL score in the terminal and in `logs/`.** The bridge prints a periodic `[RL] step=... ep_reward=... mean100ep=...` line; `logger_setup.py` mirrors all stdout to `logs/pyla_<timestamp>.log` so every score line is on disk.
- **Showdown-first focus.** The fork is tuned end-to-end for Showdown trio (analog joystick movement, teammate hysteresis, fog avoidance, wall-stuck escape, place-based trophy tracking).

See [`rl/README.md`](rl/README.md) for the full RL architecture, observation/action layout, reward shaping, and training tips.

---

What the bot does in Showdown:

- **Analog joystick movement.** Brawlers are moved by a continuous angle, not WASD taps, so pathing and dodging are smoother than in the stock client-agnostic modes.
- **Follows teammates in trio** when there's no enemy to chase, with hysteresis so it doesn't ping-pong between two nearby teammates.
- **Trio team spacing.** The bot avoids stacking directly on teammates, orbits when grouped, and biases back toward the team instead of chasing too far alone.
- **Passive roam** when alone and safe — slow rotation of standing still.
- **Poison fog avoidance.** Detects the fog and when a trusted fog mass enters the flee radius around the player, overrides movement to run the opposite way.
- **Wall-based unstuck detector + semicircle escape.** If surrounding walls stop moving while the bot is commanding movement, it's pressed against something — the bot retreats from the obstacle and then sweeps a semicircular arc around it. The arc side alternates between triggers.
- **Place-based trophy tracking.** Recognizes 1st/2nd/3rd/4th-place end screens and updates the trophy count accordingly.

---

PylaAi-XXZ is currently the best external Brawl Stars bot.
This repository is intended for devs and it's recommended for others to use the official version from the discord.

**Warning :** This is a source-code fork. It now includes a one-click Windows setup helper, but the official build and support are still linked in the Pyla Discord.

## Installation / How to run

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
8. Double-click the generated `Run PylaAi-XXZ.bat` file or run `python main.py`.
9. In the hub, choose your emulator, select your brawler setup, then press Start.

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
- Auto-refresh logs in to the official developer portal, detects the current public IP, deletes old PylaAi-XXZ-created keys, creates a fresh key for that IP, and saves the generated token locally.
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
- While the bot is running, a small `PylaAi-XXZ Control` window lets you pause and resume movement safely. By default it also shows a live IPS readout (bot iterations per second, smoothed) and a small green graph above a red threshold line, so you can spot performance issues at a glance. Turn it off with the `Pause Window IPS Tracker` toggle in the hub (or `pause_menu_ips_tracker = "no"` in `cfg/general_config.toml`); changes apply on the next bot start.

Discord webhook and remote control :
- Open `cfg/discord_config.toml`.
- Webhook notifications only need `webhook_url`.
- Discord `/start`, `/stop`, and `/status` need a Discord bot token, because normal webhooks cannot receive commands.
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
  4. Paste it into `discord_control_user_id`. If this is blank, PylaAi-XXZ uses `discord_id`.
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
- Restart PylaAi-XXZ after changing the Discord bot token or remote-control settings.

## AMD GPU on Windows (RX 7000 series / gfx1100)

Standard PyTorch ROCm wheels have a known issue on Windows where MIOpen’s JIT compiler fails to find C++ standard library headers, spamming errors such as `HIPRTC_ERROR_COMPILATION` or `fatal error: 'type_traits' file not found`.

**Quick fix:** before starting the bot, set:

```bat
set MIOPEN_FIND_MODE=5
```

This repository calls `configure_amd_windows()` from [`main.py`](main.py) before any ML stack loads PyTorch, which applies the same setting via `os.environ.setdefault` so you normally do not need to set it manually (shell overrides still win if you export a different value).

**Better fix for PyTorch-on-ROCm on Windows:** use the self-contained **TheRock** wheels (no HIP SDK install). Choose the release matching your GPU family, e.g. [rocm-TheRock releases](https://github.com/scottt/rocm-TheRock/releases) (look for tags such as `v6.5.0rc-pytorch-gfx110x` for RDNA3).

See [`requirements-rocm-windows.txt`](requirements-rocm-windows.txt) for optional pip notes. Your gameplay / RL code does not need changes — `torch.device("cuda")` still maps to ROCm when using the ROCm build.

Performance troubleshooting :
- Run `python tools/performance_check.py`.
- If it says `CPUExecutionProvider`, run `setup.exe` again or set `cfg/general_config.toml` `cpu_or_gpu = "directml"`.
- If the bot shows `1-2 IPS` while Python CPU usage is low, check the `scrcpy frame FPS` line from `tools/performance_check.py`. Low frame FPS means the emulator/ADB feed is slow, not the AI model.
- On laptops with two GPUs, set Windows Graphics settings for `python.exe` and the emulator to High performance.
- If DirectML is active but still very slow, try `directml_device_id = "1"` in `cfg/general_config.toml`, then restart the bot.
- Turn off Windows Efficiency mode for the emulator if Task Manager shows it. Efficiency mode can cap emulator frame delivery and make the bot look stuck at 2-5 IPS.
- For LDPlayer or MuMu, select the matching emulator in the hub or set `current_emulator = "LDPlayer"` / `"MuMu"` in `cfg/general_config.toml`, use 1920x1080 landscape, set emulator FPS to 60, and disable any low-FPS/eco mode.
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
- Please respect the "no selling" license as respect for our work.

Devs : 
- Iyordanov
- AngelFire

# Run tests
Run `python -m unittest discover` to check if your changes have made any regressions. 

# Performance profile
If the bot drops to 1-3 IPS while Python CPU usage is low, first apply the safe capture profile and restart:

`python tools/apply_performance_profile.py --profile balanced`

Use `--profile low-end` for older laptops that overheat or throttle. PylaAi-XXZ requires 64-bit Python; emulator 32-bit/GFX modes are optional emulator settings, not a Python requirement.

# If you want to contribute, don't hesitate to create an Issue, a Pull Request, or/and make a ticket on the Pyla discord server at :
https://discord.gg/xUusk3fw4A

Don't know what to do ? Check the To-Fix and Idea lists :
https://trello.com/b/SAz9J6AA/public-pyla-trello
