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
    original_front_target_reached = stage_manager._front_target_reached
    original_refresh_push_all = stage_manager.refresh_push_all_trophies_from_api
    original_should_use_play_again = stage_manager.should_use_play_again

    def _front_progress_numbers(self):
        if not getattr(self, "brawlers_pick_data", None):
            return 0, 1000, 0, ""
        front = self.brawlers_pick_data[0]
        target = _safe_int(front.get("push_until", 1000), 1000)
        row_trophies = _safe_int(front.get("trophies", 0), 0)
        observer_trophies = _safe_int(
            getattr(self.Trophy_observer, "current_trophies", row_trophies),
            row_trophies,
        )
        return row_trophies, target, observer_trophies, str(front.get("brawler", "") or "")

    def _local_match_after_is_below_target(self, target: int) -> bool:
        after = getattr(self, "last_match_trophy_after", None)
        if after is None:
            return False
        after = _safe_int(after, 0)
        return after < target and (target - after) > 20

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
        local_after = getattr(self, "last_match_trophy_after", None)
        if local_after is not None:
            observer_trophies = min(observer_trophies, _safe_int(local_after, observer_trophies))

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
        local_after = getattr(self, "last_match_trophy_after", None)
        if local_after is not None:
            observer_trophies = min(observer_trophies, _safe_int(local_after, observer_trophies))

        if row_trophies >= target and observer_trophies < target and row_trophies - observer_trophies > 80:
            print(
                "Using local trophy progress instead of suspicious API value: "
                f"{row.get('brawler', 'current')} API={row_trophies}, local={observer_trophies}, target={target}."
            )
            return observer_trophies
        return value

    def front_target_reached_guarded(self):
        row_trophies, target, observer_trophies, brawler = _front_progress_numbers(self)
        if _local_match_after_is_below_target(self, target):
            print(
                "Push All target guard: keeping current brawler because the last local match "
                f"ended below target ({brawler} {getattr(self, 'last_match_trophy_after', None)}/{target})."
            )
            return False
        if row_trophies >= target and observer_trophies < target and row_trophies - observer_trophies > 80:
            _restore_front_trophies_if_suspicious(self, reason="front target check")
            return False
        return original_front_target_reached(self)

    def refresh_push_all_trophies_from_api_guarded(self):
        old_front = dict(self.brawlers_pick_data[0]) if getattr(self, "brawlers_pick_data", None) else {}
        old_name = str(old_front.get("brawler", "") or "")
        old_target = _safe_int(old_front.get("push_until", 1000), 1000)
        old_row_trophies = _safe_int(old_front.get("trophies", 0), 0)
        old_observer = _safe_int(
            getattr(getattr(self, "Trophy_observer", None), "current_trophies", old_row_trophies),
            old_row_trophies,
        )
        local_before = min(old_row_trophies, old_observer)

        changed = original_refresh_push_all(self)

        if not old_name or not getattr(self, "brawlers_pick_data", None):
            return changed
        still_present = any(_same_brawler(row.get("brawler", ""), old_name) for row in self.brawlers_pick_data)
        if still_present:
            return changed

        # If the current brawler was below its target before the API refresh,
        # never let a refresh silently remove it. This protects against wrong
        # player tags, stale API rows, or OCR/API desync causing 380/408 -> next.
        if local_before < old_target and (old_target - local_before) > 20:
            restored_row = dict(old_front)
            restored_row["trophies"] = max(0, local_before)
            print(
                "Push All API refresh tried to remove the active brawler before local target: "
                f"restoring {old_name} at {local_before}/{old_target}."
            )
            self.brawlers_pick_data = [restored_row] + [
                row for row in self.brawlers_pick_data
                if not _same_brawler(row.get("brawler", ""), old_name)
            ]
            self.push_all_needs_selection = False
            try:
                self.Trophy_observer.change_trophies(local_before)
            except Exception:
                pass
            try:
                module.save_brawler_data(self.brawlers_pick_data)
            except Exception as exc:
                print(f"Could not save queue after restoring active brawler: {exc}")
            return True
        return changed

    def should_use_play_again_guarded(self, value=0, target=0, active_brawler=None):
        target_int = _safe_int(target, 0)
        value_int = _safe_int(value, 0)
        if target_int and value_int >= target_int and _local_match_after_is_below_target(self, target_int):
            print(
                "Play Again guard: API/queue value says target reached, but local match "
                f"is still {getattr(self, 'last_match_trophy_after', None)}/{target_int}. Continuing."
            )
            if getattr(self, "post_match_action", "") != "play_again":
                return False
            if self.requires_brawler_reselection(active_brawler):
                return False
            return True
        return original_should_use_play_again(self, value, target, active_brawler)

    stage_manager.sync_trophies_from_api_after_match = sync_trophies_from_api_after_match_guarded
    stage_manager._trophy_progress_value = trophy_progress_value_guarded
    stage_manager._front_target_reached = front_target_reached_guarded
    stage_manager.refresh_push_all_trophies_from_api = refresh_push_all_trophies_from_api_guarded
    stage_manager.should_use_play_again = should_use_play_again_guarded
    stage_manager._pyla_runtime_safety_patched = True


def _import_hook(name, globals=None, locals=None, fromlist=(), level=0):
    module = _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)
    if name == "lobby_automation":
        _patch_lobby_automation(module)
    elif name == "stage_manager":
        _patch_stage_manager(module)
    return module


builtins.__import__ = _import_hook
