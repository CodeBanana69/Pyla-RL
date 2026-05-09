"""Reinforcement learning support for Pyla-RL hybrid movement.

This package implements:
  - projectile_tracker: per-frame matching/velocity for incoming projectiles
    and supers detected by the vision pipeline.
  - movement_env: a Gymnasium environment exposing observation/action/reward
    space for movement-only RL (heuristic combat stays separate).
  - policy_bridge: thin Stable-Baselines3 loader/runner used by Play.loop()
    when use_rl_movement is enabled. Handles inference and on-policy
    rollout collection + periodic learn() updates when training is on.

The combat layer (attack, super, gadget, lead_shot_angle, hold-attack) is
NOT touched by this package. It is run by Play.run_combat() after the RL
movement is selected.
"""

from rl.projectile_tracker import (
    ProjectileTrack,
    ProjectileTracker,
    extract_projectile_boxes,
)

__all__ = [
    "ProjectileTrack",
    "ProjectileTracker",
    "extract_projectile_boxes",
]
