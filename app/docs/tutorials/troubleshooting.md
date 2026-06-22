# Troubleshooting

## ADB / emulator

1. On **Overview**, pick the correct emulator and click **Run Checks**.
2. **LDPlayer:** Settings → Other settings → enable ADB debugging, restart emulator. Port **5555** (instance 1: **5557**).
3. **MuMu:** confirm ADB enabled. Port **16384** (instance 1: **16416**).
4. If you see dual devices (`127.0.0.1:5555` + `emulator-5554`), restart emulator ADB or reconnect from Overview.

## Low IPS

1. Run `python tools/performance_check.py`.
2. If provider is CPU, rerun `setup.cmd` or set `cpu_or_gpu = "directml"` in `cfg/general_config.toml`.
3. Set emulator to 1920x1080, 60 FPS, disable eco/low-FPS modes.
4. ~60 IPS is normal when `scrcpy_max_fps = 60`.

## Multi-instance empty list

Open **Instances**, enable multi-instance, click **Refresh Instances**. Each instance needs a farm plan at `instances/<id>/latest_brawler_data.json`.

## Recovery spam

Read **Recovery Log** on Overview and `logs/recovery_events.jsonl`. Increase low IPS thresholds on the **Timers** tab if recovery triggers too often.

## GPU / DirectML

On hybrid laptops, set Windows Graphics settings for Python and the emulator to **High performance**. Try `directml_device_id = "1"` if device 0 is slow.

## More help

- Hub **Help** tab for quick guides
- [Full tutorial index](../TUTORIAL.md)
- [Pyla Discord](https://discord.gg/xUusk3fw4A)
