# Multi-Instance

Run multiple LDPlayer or MuMu bots in parallel.

## Enable

1. Open **Instances**.
2. Turn on **Enable Multi-Instance**.
3. Restart the Hub if Discord/Telegram remote control does not see instances.

## Add instances

1. Click **Add Instance**.
2. Set ID, name, emulator, and a **unique ADB port**.

| Emulator | Common ports |
|----------|----------------|
| LDPlayer | 5555, 5557, 5559 |
| MuMu | 16384, 16416, 16448 |

## Farm plans per instance

Each instance uses its own queue file:

```
instances/<id>/latest_brawler_data.json
```

Ways to populate:

1. Build a plan on **Farm Plan**, **Export**, then copy the JSON into each instance folder.
2. Edit the JSON files directly.
3. Use Discord/Telegram `/push` with an `instance:` argument while a worker is running.

## Start workers

Use **Start** on each instance row. Do **not** use Overview **START** in multi-instance mode.

## Remote control

Discord: `/status instance:ld-2`  
Telegram: `/status ld-2` (third argument)
