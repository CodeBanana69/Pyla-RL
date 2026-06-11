# Multi-Instance

Run multiple LDPlayer or MuMu bots in parallel from the Hub **Instances** tab.

## Enable

1. Open **Instances**.
2. Turn on **Enable Multi-Instance**.
3. Follow the **Quick Setup** panel (scan emulators, quick add unassigned).
4. Restart the Hub if Discord/Telegram remote control does not see instances.

## Add instances

**Easy path**

1. Click **Scan Emulators** or **Quick Add All Unassigned**.
2. Each detected emulator becomes an instance with a unique port and a copy of the Default farm plan.

**Manual path**

1. Click **Manual Add**, pick a detected emulator with **Use**, or expand **Advanced** to set port manually.
2. Optionally set a per-instance player tag for API trophy autofill.

## Farm plans per instance

1. Open **Farm Plan**.
2. Use the instance selector at the top (**Editing farm plan for**).
3. Build or import the queue for that instance.

Each instance stores its plan at `instances/<id>/latest_brawler_data.json` automatically — you do not need to edit paths by hand.

## Start workers

1. Use **Start** on each ready instance, or **Start All Ready**.
2. Click **Align Windows** to tile emulator windows.
3. Do **not** use Overview **START** in multi-instance mode.

## Remote control

One Discord/Telegram bot on the Hub controls all instances:

- Discord: `/status instance:ld-2`
- Telegram: `/status ld-2` (third argument)

## Per-instance match notifications (optional)

On each instance card, set a webhook URL and ping ID for match alerts. Control commands still use the global Discord/Telegram tabs.
