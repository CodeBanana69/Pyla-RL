# Overview and START

## Pre-flight checks

On the **Overview** tab:

1. Select **LDPlayer** or **MuMu**.
2. Click **Run Checks** or **Test Connection**.
3. Fix **required** failures (usually ADB) before START.

| Check | Required? |
|-------|-----------|
| ADB device | Yes |
| Emulator process | Recommended |
| Brawl Stars foreground | Recommended |
| 1080p resolution | Recommended |

## Game mode

**Showdown Trio** is the primary tuned mode in this fork. **Brawl Ball** is also available in the Hub and uses `playstyles/default.pyla`.

## Performance profile

Choose **Balanced**, **Low-end**, or other profiles on Overview. Restart the bot after changing profiles.

## START

- **Single-instance:** press **START** on Overview after checks pass.
- **Multi-instance:** enable mode on **Instances**, build per-instance farm plans, then **Start** each worker there (Overview START is disabled).

## Updates

The Hub header shows an **update pill** next to the language toggle (EN/RU). It compares your installed `main`-branch commit to GitHub and opens a popover with:

- Installed version and local vs latest commit SHAs
- **Run updater** (launches `updater.exe` when present)
- **Refresh** status

Use `update.exe` / `update.cmd` from the install folder if the pill reports an update is available.

## While running

The **Pyla-RL Control** window lets you pause and resume safely (**F8**). It shows a running/paused status pill, a full-width pause button, IPS sparkline, and a session strip (click to copy). Use **Open Hub** or the compact bar if you need the window out of the way.
