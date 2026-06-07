"""Runtime guard for dismissing Brawl Stars team invite popups.

This module is imported automatically by Python when Pyla-RL is launched from
this repository. It patches LobbyAutomation.check_for_idle so invite popups do
not block lobby automation.
"""

from __future__ import annotations

import builtins
import time

_ORIGINAL_IMPORT = builtins.__import__


def _patch_lobby_automation(module) -> None:
    lobby_automation = getattr(module, "LobbyAutomation", None)
    if lobby_automation is None:
        return
    if getattr(lobby_automation, "_team_invite_guard_patched", False):
        return

    original_check_for_idle = lobby_automation.check_for_idle

    def _handle_team_invite(self, frame) -> bool:
        if frame is None:
            return False

        now = time.time()
        if now - getattr(self, "_last_team_invite_check", 0.0) < 0.8:
            return False
        self._last_team_invite_check = now

        height, width = frame.shape[:2]
        invite_crop = frame[
            int(height * 0.18):int(height * 0.86),
            int(width * 0.12):int(width * 0.88),
        ]

        try:
            from utils import extract_text_strings

            text = " ".join(extract_text_strings(invite_crop)).lower()
        except Exception:
            return False

        compact_text = "".join(ch for ch in text if ch.isalnum())
        looks_like_invite = (
            ("team" in text and "invite" in text)
            or ("wants" in text and "team" in text)
            or ("accept" in text and "reject" in text)
            or ("mute" in text and "reject" in text)
            or "teaminvite" in compact_text
        )
        if not looks_like_invite:
            return False

        if now - getattr(self, "_last_team_invite_action", 0.0) < 2.0:
            return True
        self._last_team_invite_action = now

        print("Team invite detected; muting inviter for 10 minutes and rejecting.")
        try:
            self.window_controller.keys_up(list("wasd"))
        except Exception:
            pass

        # Coordinates are based on the standard 1920x1080 Pyla-RL layout and are
        # scaled by WindowController when already_include_ratio=False.
        self.window_controller.click(1400, 830, delay=0.08, already_include_ratio=False)
        time.sleep(0.15)
        self.window_controller.click(675, 710, delay=0.08, already_include_ratio=False)
        time.sleep(0.25)
        return True

    def check_for_idle_with_team_invite_guard(self, frame):
        try:
            if _handle_team_invite(self, frame):
                return
        except Exception as exc:
            print(f"Team invite guard failed: {exc}")
        return original_check_for_idle(self, frame)

    lobby_automation.check_for_idle = check_for_idle_with_team_invite_guard
    lobby_automation._team_invite_guard_patched = True


def _import_hook(name, globals=None, locals=None, fromlist=(), level=0):
    module = _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)
    if name == "lobby_automation":
        _patch_lobby_automation(module)
    return module


builtins.__import__ = _import_hook
