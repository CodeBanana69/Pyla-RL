# Timers and Recovery

## Low IPS recovery

When image processing speed (IPS) stays low, Pyla-RL can automatically:

1. Restart the scrcpy feed
2. Restart Brawl Stars
3. Restart the emulator profile

Adjust thresholds on the **Timers** tab:

- **Low IPS Recovery Seconds** — how long IPS must stay low
- **Low IPS Cooldown** — minimum time between recovery attempts
- **App Restart Attempt** — after N attempts, restart game
- **Emulator Restart Attempt** — after N attempts, restart emulator

## Other timers

The Timers tab also controls menu delays, emulator restart cooldowns, and related watchdog values.

## Recovery log

On **Overview**, click **Recovery Log** to read recent auto-recovery events from `logs/recovery_events.jsonl`.

## Built-in recovery (no config)

Pyla-RL also handles:

- Brawl Stars closed or wrong app in foreground → relaunch game
- Idle disconnect dialog → press Reload
- Frozen scrcpy feed → restart feed
