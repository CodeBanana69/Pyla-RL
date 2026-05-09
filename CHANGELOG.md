# Changelog

## Unreleased

### Added
- Pause-window IPS tracker: the floating control window now shows a live `XX.X IPS` readout and a compact green sparkline with a dashed red line at the low-IPS recovery threshold. Toggle it from the hub (`Pause Window IPS Tracker`) or via `pause_menu_ips_tracker` in `cfg/general_config.toml`; default is on.

## v1.1.5 — 2026-04-20

### Added
- MuMu emulator support in the hub (new button, port list covering MuMu 12 and older builds).
- Wall-based unstuck detector for showdown
- Semicircle escape maneuver: on stuck, the bot retreats from the obstacle and then sweeps an arc around it

### Changed
- ADB device selection now respects the chosen emulator — a running LDPlayer no longer masks a MuMu connection.
- ADB connection time cut from ~54 s to ~2 s via fast 50 ms TCP probing before `adb.connect`.
- Idle Disconnect detection works on MuMu: tightened the gray-pixel ROI to the dialog body and widened the HSV V range so both LDPlayer (bright overlay) and MuMu (dark overlay) are covered. Threshold lowered to match.

### Removed
- Legacy analog angle-based unstuck (`unstuck_angle_if_needed`). Superseded by the wall-based detector + semicircle escape. String-based unstuck for non-showdown modes remains.
