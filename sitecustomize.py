"""Runtime safety patches for Pyla-RL.

Python imports this module automatically when the project is launched from the
repository root. The patches here are intentionally small and defensive: they
only wrap existing behavior and fall back to upstream logic when a condition is
not recognized.
"""

from __future__ import annotations

import builtins
import time
from typing import Any

_ORIGINAL_IMPORT = builtins.__import__


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _same_brawler(left: str, right: str) -> bool:
    left_norm = str(left or "").strip().lower().replace(" ", "").replace("-", "")
    right_norm = str(right or "").strip().lower().replace(" ", "").replace("-", "")
    return bool(left_norm and right_norm and left_norm == right_norm)


def _patch_lobby_automation(module) -> None:
    lobby_automation = getattr(module, "LobbyAutomation", None)
    if lobby_automation is None:
        return
    if getattr(lobby_automation, "_pyla_runtime_safety_patched", False):
        return

    original_check_for_idle = lobby_automation.check_for_idle
    original_resolve_ocr_typos = lobby_automation.resolve_ocr_typos
    original_select_button_words = lobby_automation._select_button_words

    ocr_aliases = {
        # EasyOCR often reads AMBER as AMBEP/AMBFR on the Brawl Stars card font.
        "ambep": "amber",
        "ambfr": "amber",
        "anber": "amber",
        "am8er": "amber",
        "arnber": "amber",
        # A few short names are easy to confuse with digits/punctuation.
        "8it": "bit",
        "r8it": "8bit",
    }

    @staticmethod
    def resolve_ocr_typos_with_aliases(potential_brawler_name: str) -> str:
        normalized = lobby_automation.normalize_ocr_name(potential_brawler_name)
        if normalized in ocr_aliases:
            return ocr_aliases[normalized]
        return original_resolve_ocr_typos(potential_brawler_name)

    @staticmethod
    def select_button_words_with_selected():
        words = set(original_select_button_words())
        words.update({
            "selected",
            "selectd",
            "seleted",
            "choose",
            "chosen",
        })
        return words

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

    def check_for_idle_with_popup_guard(self, frame):
        try:
            if _handle_team_invite(self, frame):
                return
        except Exception as exc:
            print(f"Team invite guard failed: {exc}")
        return original_check_for_idle(self, frame)

    lobby_automation.resolve_ocr_typos = resolve_ocr_typos_with_aliases
    lobby_automation._select_button_words = select_button_words_with_selected
    lobby_automation.check_for_idle = check_for_idle_with_popup_guard
    lobby_automation._pyla_runtime_safety_patched = True


def _patch_stage_manager(module) -> None:
    stage_manager = getattr(module, "StageManager", None)
    if stage_manager is None:
        return
    if getattr(stage_manager, "_pyla_runtime_safety_patched", False):
        return

    original_sync_after_match = stage_manager.sync_trophies_from_api_after_match
    original_trophy_progress = stage_manager._trophy_progress_value

    def _restore_front_trophies_if_suspicious(self, *, reason: str) -> bool:
        if not getattr(self, "brawlers_pick_data", None):
            return False
        front = self.brawlers_pick_data[0]
        if front.get("type", "trophies") != "trophies":
            return False

        target = _safe_int(front.get("push_until", 1000), 1000)
        row_trophies = _safe_int(front.get("trophies", 0), 0)
        observer_trophies = _safe_int(
            getattr(self.Trophy_observer, "current_trophies", row_trophies),
            row_trophies,
        )

        # A normal Showdown match cannot add hundreds of trophies. This usually
        # means the Brawl Stars API tag points to a different account or returned
        # stale data, which can make Push All skip a brawler at low trophies.
        suspicious_jump = row_trophies - observer_trophies > 80
        if row_trophies >= target and observer_trophies < target and suspicious_jump:
            restored = max(0, observer_trophies)
            print(
                "Suspicious API trophy jump ignored for Push All: "
                f"{front.get('brawler', 'current')} {row_trophies}->{restored} "
                f"while target is {target}. Reason: {reason}."
            )
            front["trophies"] = restored
            try:
                self.Trophy_observer.change_trophies(restored)
            except Exception:
                pass
            self.last_match_api_sync_ok = False
            try:
                module.save_brawler_data(self.brawlers_pick_data)
            except Exception as exc:
                print(f"Could not save queue after suspicious trophy correction: {exc}")
            return True
        return False

    def sync_trophies_from_api_after_match_guarded(self, current_brawler):
        before_front = dict(self.brawlers_pick_data[0]) if getattr(self, "brawlers_pick_data", None) else {}
        before_observer = _safe_int(
            getattr(getattr(self, "Trophy_observer", None), "current_trophies", before_front.get("trophies", 0)),
            _safe_int(before_front.get("trophies", 0), 0),
        )

        result = original_sync_after_match(self, current_brawler)

        if before_front and getattr(self, "brawlers_pick_data", None):
            front = self.brawlers_pick_data[0]
            if _same_brawler(front.get("brawler", ""), current_brawler):
                corrected = _restore_front_trophies_if_suspicious(
                    self,
                    reason=f"post-match API sync; local OCR before sync was {before_observer}",
                )
                if corrected and isinstance(result, dict):
                    result = dict(result)
                    result["updated"] = False
                    result["reason"] = "suspicious_api_jump_ignored"
        return result

    def trophy_progress_value_guarded(self, row):
        value = original_trophy_progress(self, row)
        row_trophies = _safe_int(row.get("trophies", 0), 0)
        observer_trophies = _safe_int(
            getattr(self.Trophy_observer, "current_trophies", row_trophies),
            row_trophies,
        )
        target = _safe_int(row.get("push_until", 1000), 1000)

        if row_trophies >= target and observer_trophies < target and row_trophies - observer_trophies > 80:
            print(
                "Using local trophy progress instead of suspicious API value: "
                f"{row.get('brawler', 'current')} API={row_trophies}, local={observer_trophies}, target={target}."
            )
            return observer_trophies
        return value

    stage_manager.sync_trophies_from_api_after_match = sync_trophies_from_api_after_match_guarded
    stage_manager._trophy_progress_value = trophy_progress_value_guarded
    stage_manager._pyla_runtime_safety_patched = True


def _import_hook(name, globals=None, locals=None, fromlist=(), level=0):
    module = _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)
    if name == "lobby_automation":
        _patch_lobby_automation(module)
    elif name == "stage_manager":
        _patch_stage_manager(module)
    return module


builtins.__import__ = _import_hook
