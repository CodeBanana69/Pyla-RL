# Farm Plan

## Build a queue

1. Open the **Farm Plan** tab.
2. Click **Add** to pick a brawler and trophy target.
3. Or use **Build Queue** (Push All) after configuring the **API** tab.

## Order

- Drag the grip on a row to reorder.
- The **first** brawler is active when the bot starts.

## Import / Export

- **Export** saves your queue as JSON for backup.
- **Import** loads a saved queue file.

## Empty queue

If the farm plan is empty, START opens the legacy brawler picker window instead.

## Queue file format

Single-instance mode uses `data/latest_brawler_data.json` in the project folder.

Example entry:

```json
{
  "brawler": "shelly",
  "push_until": 1000,
  "trophies": 0,
  "type": "trophies",
  "automatically_pick": true,
  "selection_method": "named_brawler"
}
```

See [Multi-Instance](multi-instance.md) for per-instance queue paths.
