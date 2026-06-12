import os
import sys
import time
import cv2
import numpy as np

from state_finder import (
    get_prestige_next_button_center,
    get_skin_reward_continue_button_center,
    get_skin_reward_equip_button_center,
    get_state,
    is_in_prestige_reward,
)
from trophy_observer import TrophyObserver
from core.integration import get_webhook_settings, on_queue_file_changed
from runtime_log import log_debug, log_info, log_warn
from utils import (
    _config_bool,
    _extract_api_token,
    extract_text_strings,
    fetch_brawl_stars_player,
    find_template_center,
    load_brawl_stars_api_config,
    load_toml_as_dict,
    normalize_brawler_name,
    notify_user,
    resolve_project_path,
    save_brawler_data,
)

try:
    from early_access.early_access import get_brawler_stats, get_player_info
    early_access = True
except (ImportError, ModuleNotFoundError):
    early_access = False

    def get_brawler_stats(_player_info, _brawler_name, _power_level=False):
        return None, None

    def get_player_info(_tag):
        return None


def load_image(image_path, scale_factor):
    image = cv2.imread(resolve_project_path(image_path))
    orig_height, orig_width = image.shape[:2]

    new_width = int(orig_width * scale_factor)
    new_height = int(orig_height * scale_factor)

    resized_image = cv2.resize(image, (new_width, new_height))
    return resized_image


class StageManager:
    def __init__(self, brawlers_data, lobby_automator, window_controller, playstyle_info, state_getting, runtime_control=None):
        self.Lobby_automation = lobby_automator
        self.lobby_config = load_toml_as_dict("./cfg/lobby_config.toml")
        self.close_popup_icon = None
        self.brawlers_pick_data = brawlers_data
        self.Trophy_observer = TrophyObserver()
        self.time_since_last_stat_change = time.time()
        bot_config = load_toml_as_dict("./cfg/bot_config.toml")
        self.play_again_on_win = bot_config.get("play_again_on_win", "no") == "yes"
        self.post_match_action = str(bot_config.get("post_match_action", "lobby")).strip().lower()
        if self.post_match_action not in ("lobby", "play_again"):
            self.post_match_action = "lobby"
        self.window_controller = window_controller
        self.states = {
            'shop': self.quit_shop,
            'brawler_selection': self.quit_shop,
            'popup': self.close_pop_up,
            'match': lambda: 0,
            'match_making': lambda: 0,
            'lobby': self.start_game,
            'star_drop_regular': lambda: self.click_star_drop("regular"),
            'star_drop_angelic': lambda: self.click_star_drop("angelic"),
            'star_drop_demonic': lambda: self.click_star_drop("demonic"),
            'star_drop_starr_nova': lambda: self.click_star_drop("starr_nova"),
            'prestige_reward': self.handle_prestige_reward,
            'trophy_reward': self.handle_trophy_reward,
            'reward_unlock': self.handle_reward_unlock,
            'starr_nova_event': lambda: self.window_controller.press("middle_got_it"),
            'end_draw': self.end_game,
            'end_victory': self.end_game,
            'end_defeat': self.end_game,
            'end_trio_showdown_0': self.end_game,
            'end_trio_showdown_1': self.end_game,
            'end_trio_showdown_2': self.end_game,
            'end_trio_showdown_3': self.end_game
        }
        self.runtime_control = runtime_control
        webhook_settings = get_webhook_settings()
        if early_access:
            self.player_tag = load_toml_as_dict("./cfg/general_config.toml")['player_tag']
        self.ping_when_stuck = _config_bool(webhook_settings.get("ping_when_stuck"), False)
        self.ping_when_target_is_reached = _config_bool(
            webhook_settings.get("ping_when_target_is_reached"),
            False,
        )
        self._queue_file_mtime = None
        self.playstyle_info = playstyle_info
        self.get_latest_state = state_getting
        self.last_match_trophy_before = None
        self.last_match_trophy_after = None
        self.last_match_trophy_delta = 0
        self.last_match_crossed_1000 = False
        self.last_match_api_sync_ok = None
        self.last_recorded_result_time = 0.0
        self.stop_after_post_match_rewards = False
        self._stuck_nudge_sent: set[str] = set()

    def _should_stop(self):
        return bool(self.runtime_control and self.runtime_control.should_stop())

    def _should_pause(self):
        return bool(self.runtime_control and self.runtime_control.should_pause())

    def _sleep_interruptible(self, duration, allow_pause=True, poll_interval=0.1):
        end_time = time.time() + duration
        while time.time() < end_time:
            if self._should_stop():
                return True
            if allow_pause and self._should_pause():
                return True
            time.sleep(min(poll_interval, max(end_time - time.time(), 0)))
        return False

    @staticmethod
    def validate_trophies(trophies_string):
        trophies_string = trophies_string.lower()
        while "s" in trophies_string:
            trophies_string = trophies_string.replace("s", "5")
        numbers = ''.join(filter(str.isdigit, trophies_string))

        if not numbers:
            return False

        trophy_value = int(numbers)
        return trophy_value

    @staticmethod
    def _number_or_default(value, default=0):
        try:
            if value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    def _match_row_progress(self, match_brawler=None):
        if not self.brawlers_pick_data:
            return 0, 1000, "trophies"

        active_name = normalize_brawler_name(
            match_brawler or getattr(self, "active_match_brawler", "")
        )
        row = self.brawlers_pick_data[0]
        for candidate in self.brawlers_pick_data:
            if active_name and normalize_brawler_name(candidate.get("brawler", "")) == active_name:
                row = candidate
                break

        type_of_push = row.get("type", "trophies")
        if type_of_push not in ("trophies", "wins"):
            type_of_push = "trophies"
        if type_of_push == "trophies":
            value = self._number_or_default(
                row.get("trophies", getattr(self.Trophy_observer, "current_trophies", 0)),
                getattr(self.Trophy_observer, "current_trophies", 0),
            )
            default_target = 1000
        else:
            value = self._number_or_default(
                getattr(self.Trophy_observer, "current_wins", row.get("wins", 0)),
                row.get("wins", 0),
            )
            default_target = 300
        target = self._number_or_default(row.get("push_until", default_target), default_target)
        return value, target, type_of_push

    def _front_push_progress(self):
        if not self.brawlers_pick_data:
            return 0, 1000, "trophies"
        row = self.brawlers_pick_data[0]
        type_of_push = row.get("type", "trophies")
        if type_of_push not in ("trophies", "wins"):
            type_of_push = "trophies"
        if type_of_push == "trophies":
            value = self._number_or_default(
                row.get("trophies", getattr(self.Trophy_observer, "current_trophies", 0)),
                getattr(self.Trophy_observer, "current_trophies", 0),
            )
            default_target = 1000
        else:
            value = self._number_or_default(
                getattr(self.Trophy_observer, "current_wins", row.get("wins", 0)),
                row.get("wins", 0),
            )
            default_target = 300
        target = self._number_or_default(row.get("push_until", default_target), default_target)
        return value, target, type_of_push

    def _front_target_reached(self):
        value, target, _ = self._front_push_progress()
        return value >= target

    @staticmethod
    def _log_api_info(message):
        log_info("api", message)

    @staticmethod
    def _log_api_warn(message):
        log_warn("api", message)

    @staticmethod
    def _log_api_debug(message):
        log_debug("api", message)

    def _match_trophy_api_sync_enabled(self, log_skips=True):
        if not self.brawlers_pick_data:
            if log_skips:
                self._log_api_info("Post-match sync skipped: no brawler queue loaded")
            return False
        if self.brawlers_pick_data[0].get("type", "trophies") != "trophies":
            if log_skips:
                self._log_api_info("Post-match sync skipped: wins push mode does not use API trophies")
            return False
        try:
            api_config = load_brawl_stars_api_config("cfg/brawl_stars_api.toml")
        except Exception as exc:
            if log_skips:
                self._log_api_warn(f"Post-match sync skipped: could not load API config ({exc})")
            return False
        if not _config_bool(api_config.get("sync_trophies_after_match"), True):
            if log_skips:
                self._log_api_info("Post-match sync skipped: sync_trophies_after_match is disabled")
            return False
        tag = str(api_config.get("player_tag", "")).strip().upper()
        if not tag or tag == "#YOURTAG":
            if log_skips:
                self._log_api_warn("Post-match sync skipped: player_tag is missing or still #YOURTAG")
            return False
        token = _extract_api_token(api_config.get("api_token", ""))
        if token:
            return True
        if (
            _config_bool(api_config.get("auto_refresh_token"), False)
            and str(api_config.get("developer_email", "")).strip()
            and str(api_config.get("developer_password", "")).strip()
        ):
            return True
        if log_skips:
            self._log_api_warn(
                "Post-match sync skipped: no API token and auto-refresh credentials are incomplete"
            )
        return False

    def _fetch_api_trophies_map(self, force_token_refresh=False):
        player_data = self.fetch_push_all_player_data(force_token_refresh=force_token_refresh)
        return {
            normalize_brawler_name(brawler.get("name", "")): int(brawler.get("trophies", 0))
            for brawler in player_data.get("brawlers", [])
        }

    def _fetch_api_trophies_with_retry(self):
        try:
            return self._fetch_api_trophies_map(force_token_refresh=False)
        except RuntimeError as e:
            if "accessDenied" not in str(e):
                raise
            self._log_api_warn("Token rejected; refreshing for current public IP and retrying...")
            return self._fetch_api_trophies_map(force_token_refresh=True)

    def _active_push_target(self):
        if not self.brawlers_pick_data:
            return 1000
        row = self.brawlers_pick_data[0]
        default_target = 1000 if row.get("type", "trophies") == "trophies" else 300
        return self._number_or_default(row.get("push_until", default_target), default_target)

    @staticmethod
    def fetch_push_all_player_data(force_token_refresh=False):
        if force_token_refresh:
            StageManager._log_api_info("Refreshing API token, then fetching player profile...")
        started = time.time()
        api_config = load_brawl_stars_api_config(
            "cfg/brawl_stars_api.toml",
            force_refresh=force_token_refresh,
        )
        player_tag = str(api_config.get("player_tag", "")).strip().upper()
        data = fetch_brawl_stars_player(
            api_config.get("api_token", "").strip(),
            api_config.get("player_tag", "").strip(),
            int(api_config.get("timeout_seconds", 15)),
        )
        elapsed = time.time() - started
        brawler_count = len(data.get("brawlers", []))
        StageManager._log_api_info(
            f"Fetched {player_tag} ({brawler_count} brawlers, {elapsed:.1f}s)"
        )
        return data

    @classmethod
    def fetch_push_all_player_data_with_retry(cls):
        try:
            return cls.fetch_push_all_player_data(force_token_refresh=False)
        except RuntimeError as e:
            if "accessDenied" not in str(e):
                raise
            cls._log_api_warn("Token rejected; refreshing for current public IP and retrying...")
            return cls.fetch_push_all_player_data(force_token_refresh=True)

    def sync_trophies_from_api_after_match(self, current_brawler):
        result = {"attempted": False, "updated": False, "reason": "disabled"}
        self.last_match_api_sync_ok = None
        if not self._match_trophy_api_sync_enabled():
            self.last_match_api_sync_ok = False
            return result

        local_trophies = self._number_or_default(
            getattr(self.Trophy_observer, "current_trophies", 0),
            0,
        )
        push_target = self._active_push_target()
        result["attempted"] = True
        self._log_api_info(
            f"Post-match sync for {current_brawler}: OCR {local_trophies}, target {push_target}"
        )
        try:
            trophies_by_brawler = self._fetch_api_trophies_with_retry()
        except Exception as e:
            result["reason"] = f"api_error: {e}"
            self.last_match_api_sync_ok = False
            self._log_api_warn(f"Post-match sync failed; keeping local trophies ({e})")
            return result

        current_key = normalize_brawler_name(current_brawler)
        changed = False
        updates = []
        for idx, row in enumerate(self.brawlers_pick_data):
            if row.get("type", "trophies") != "trophies":
                continue
            key = normalize_brawler_name(row.get("brawler", ""))
            brawler_name = row.get("brawler", key)
            if key not in trophies_by_brawler:
                self._log_api_warn(f"  {brawler_name}: not found in API response")
                continue
            before = self._number_or_default(row.get("trophies", 0), 0)
            api_trophies = trophies_by_brawler[key]
            if before != api_trophies:
                self.brawlers_pick_data[idx]["trophies"] = api_trophies
                changed = True
                detail = f"{brawler_name}: {before} -> {api_trophies}"
                if key == current_key and local_trophies != api_trophies:
                    detail += f" (OCR was {local_trophies})"
                updates.append(detail)
                self._log_api_info(f"  {detail}")
            else:
                self._log_api_debug(f"  {brawler_name}: unchanged at {before}")

        if not changed:
            result["reason"] = "unchanged"
            self.last_match_api_sync_ok = True
            self._log_api_info(
                f"Post-match sync complete: queue already matches API "
                f"({current_brawler} {local_trophies}/{push_target})"
            )
            return result

        front_trophies = self._number_or_default(self.brawlers_pick_data[0].get("trophies", 0), 0)
        if getattr(self.Trophy_observer, "current_trophies", None) != front_trophies:
            self.Trophy_observer.change_trophies(front_trophies)
        if self.last_match_trophy_after is not None and front_trophies != self.last_match_trophy_after:
            before = self._number_or_default(self.last_match_trophy_before, front_trophies)
            self.last_match_trophy_after = front_trophies
            self.last_match_trophy_delta = front_trophies - before
            self.last_match_crossed_1000 = before < 1000 <= front_trophies and front_trophies > before
        save_brawler_data(self.brawlers_pick_data)
        result["updated"] = True
        result["reason"] = "updated"
        self.last_match_api_sync_ok = True
        self._log_api_info(
            f"Post-match sync complete: {len(updates)} brawler(s) updated, "
            f"active {current_brawler} now {front_trophies}/{push_target}"
        )
        return result

    def can_handle_prestige_reward_screen(self):
        current = self.brawlers_pick_data[0] if getattr(self, "brawlers_pick_data", None) else {}
        if str(current.get("type", "trophies")).strip().lower() != "trophies":
            return False

        return self.had_recent_trophy_change(seconds=45.0) or bool(
            getattr(self, "last_match_crossed_1000", False)
        )

    def had_recent_trophy_change(self, seconds=30.0):
        changed_at = max(
            float(getattr(self, "last_recorded_result_time", 0.0) or 0.0),
            float(getattr(self, "time_since_last_stat_change", 0.0) or 0.0),
        )
        if changed_at <= 0:
            return False
        if time.time() - changed_at > seconds:
            return False
        return int(getattr(self, "last_match_trophy_delta", 0) or 0) != 0

    def reset_prestige_reward_gate(self):
        self.last_match_trophy_before = None
        self.last_match_trophy_after = None
        self.last_match_trophy_delta = 0
        self.last_match_crossed_1000 = False

    def advance_to_next_brawler_after_prestige(self):
        if not self.brawlers_pick_data:
            return False
        current_brawler = self.brawlers_pick_data[0].get("brawler", "current")
        print(f"Prestige reward detected for {current_brawler}; treating current brawler as completed.")
        self.brawlers_pick_data[0]["trophies"] = max(1000, int(self.brawlers_pick_data[0].get("trophies") or 0))
        self.brawlers_pick_data[0]["push_until"] = max(1000, int(self.brawlers_pick_data[0].get("push_until") or 1000))

        if len(self.brawlers_pick_data) <= 1:
            print("Prestige reward reached, but no next brawler is queued.")
            self.stop_after_post_match_rewards = True
            save_brawler_data(self.brawlers_pick_data)
            return False

        self.brawlers_pick_data.pop(0)
        next_data = self.brawlers_pick_data[0]
        self.Trophy_observer.change_trophies(next_data.get("trophies", 0))
        self.Trophy_observer.current_wins = next_data.get("wins", 0) if next_data.get("wins", "") != "" else 0
        self.Trophy_observer.win_streak = next_data.get("win_streak", 0)
        save_brawler_data(self.brawlers_pick_data)
        return True

    def read_lobby_trophies_from_screenshot(self, screenshot):
        height, width = screenshot.shape[:2]
        width_ratio = width / 1920
        height_ratio = height / 1080
        x1 = int(700 * width_ratio)
        y1 = int(58 * height_ratio)
        x2 = int(990 * width_ratio)
        y2 = int(165 * height_ratio)
        crop = screenshot[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        try:
            crop = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            texts = extract_text_strings(crop)
        except Exception as e:
            print(f"Could not OCR lobby trophies after reward: {e}")
            return None

        for text in texts:
            value = self.validate_trophies(text)
            if value is not False and 0 <= value <= 5000:
                return value
        print(f"Could not read lobby trophies after reward from OCR: {texts}")
        return None

    def wait_for_lobby_after_reward(self, max_attempts=30):
        screenshot = self.window_controller.screenshot()
        current_state = get_state(screenshot)
        attempts = 0
        while current_state != "lobby" and attempts < max_attempts:
            self.window_controller.press_key("Q")
            time.sleep(1.0)
            screenshot = self.window_controller.screenshot()
            current_state = get_state(screenshot)
            attempts += 1
        return screenshot if current_state == "lobby" else None

    def click_skin_reward_button(self):
        screenshot = self.window_controller.screenshot()
        screenshot_bgr = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
        equip_center = get_skin_reward_equip_button_center(screenshot_bgr)
        if equip_center is not None:
            print("Skin reward unlock detected; clicking EQUIP NOW.")
            self.window_controller.keys_up(list("wasd"))
            self.window_controller.click(*equip_center, delay=0.08)
            return True

        continue_center = get_skin_reward_continue_button_center(screenshot_bgr)
        if continue_center is not None:
            print("Skin reward unlock detected; clicking CONTINUE.")
            self.window_controller.keys_up(list("wasd"))
            self.window_controller.click(*continue_center, delay=0.08)
            return True
        return False

    def handle_trophy_reward(self):
        if self.click_skin_reward_button():
            return
        self.window_controller.press_key("Q")

    def handle_reward_unlock(self):
        if self.click_skin_reward_button():
            return
        print("Reward unlock detected; pressing continue.")
        self.window_controller.press_key("Q")

    def handle_prestige_reward(self):
        if not self.can_handle_prestige_reward_screen():
            print("Prestige reward ignored; no recent recorded trophy result allows this reward screen.")
            return
        screenshot = self.window_controller.screenshot()
        screenshot_bgr = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
        next_button_center = get_prestige_next_button_center(screenshot_bgr)
        if next_button_center is None or not is_in_prestige_reward(screenshot_bgr):
            print("Prestige reward state ignored; NEXT button was not confirmed.")
            return

        print("Prestige reward screen detected; clicking NEXT.")
        self.window_controller.keys_up(list("wasd"))
        self.window_controller.click(*next_button_center)
        time.sleep(1.0)

        lobby_screenshot = self.wait_for_lobby_after_reward()
        if lobby_screenshot is None:
            print("Could not reach lobby after reward; will retry from normal state loop.")
            return

        lobby_trophies = self.read_lobby_trophies_from_screenshot(lobby_screenshot)
        if lobby_trophies is not None and self.brawlers_pick_data:
            print(f"Lobby trophies after reward: {lobby_trophies}")
            self.Trophy_observer.change_trophies(lobby_trophies)
            self.brawlers_pick_data[0]["trophies"] = lobby_trophies
            save_brawler_data(self.brawlers_pick_data)

        push_target = self._active_push_target()
        if lobby_trophies is None:
            if push_target > 1000:
                print(
                    f"Prestige at 1k milestone while pushing to {push_target}; "
                    "keeping current brawler in queue."
                )
                return
            print("Could not read lobby trophies after prestige; trusting confirmed prestige reward screen.")
        elif lobby_trophies > 20:
            print("Reward screen did not confirm a 1k trophy reset; not forcing brawler switch.")
            return
        elif push_target > 1000:
            print(
                f"Prestige at 1k milestone while pushing to {push_target}; "
                "keeping current brawler in queue."
            )
            return

        if not self.advance_to_next_brawler_after_prestige():
            self.window_controller.press_key("Q")
            return

        self.Lobby_automation.select_lowest_trophy_brawler()

    def start_game(self):
        on_queue_file_changed(self)
        if self._should_stop() or self._should_pause():
            return

        if getattr(self, "stop_after_post_match_rewards", False):
            print("Post-match rewards cleared; stopping after completed target.")
            from utils import LEGACY_QUEUE_PATH, default_queue_path, resolve_project_path

            queue_path = default_queue_path()
            if os.path.exists(queue_path):
                os.remove(queue_path)
            legacy_queue = resolve_project_path(LEGACY_QUEUE_PATH)
            if os.path.exists(legacy_queue):
                os.remove(legacy_queue)
            self.window_controller.release_movement()
            self.window_controller.close()
            sys.exit(0)

        if early_access and self.player_tag:
            print("Waiting 3 seconds for API to update with latest data...")
            time.sleep(3)
            player_info = get_player_info(self.player_tag)
            if not player_info:
                print("Player tag is incorrect. Use your Brawl Stars player tag, not your Supercell ID. Skipping API stat refresh.")
            else:
                current_brawler = self.brawlers_pick_data[0]['brawler']
                trophies, win_streak = get_brawler_stats(player_info, current_brawler)
                if trophies is not None and win_streak is not None:
                    if trophies != self.Trophy_observer.current_trophies or win_streak != self.Trophy_observer.win_streak:
                        print(f"Warning: Trophies or win streak from API do not match current values. This may indicate a desync. API values: trophies={trophies}, win_streak={win_streak}. Current values: trophies={self.Trophy_observer.current_trophies}, win_streak={self.Trophy_observer.win_streak}")
                    self.Trophy_observer.current_trophies = trophies
                    self.Trophy_observer.win_streak = win_streak
        print("state is lobby, starting game")
        values = {
            "trophies": self.Trophy_observer.current_trophies,
            "wins": self.Trophy_observer.current_wins
        }

        type_of_push = self.brawlers_pick_data[0]['type']
        value = values[type_of_push]
        push_current_brawler_till = self.brawlers_pick_data[0]['push_until']

        if value >= push_current_brawler_till:
            if len(self.brawlers_pick_data) <= 1:
                print("Brawler reached required trophies/wins. No more brawlers selected for pushing in the menu. "
                      "Bot will now pause itself until closed.", value, push_current_brawler_till)
                screenshot = self.window_controller.screenshot()
                notify_user("completed", screenshot, self)
                print("Bot stopping: all targets completed with no more brawlers.")
                self.window_controller.release_movement()
                self.window_controller.close()
                sys.exit(0)
            if self.ping_when_target_is_reached:
                screenshot = self.window_controller.screenshot()
                notify_user("brawler_goal", screenshot, self)
            print(f'Bot has reached the target trophies/wins for {self.brawlers_pick_data[0]["brawler"]}, moving on to the next one in the list.', value, push_current_brawler_till)
            self.brawlers_pick_data.pop(0)
            self._clear_instance_session_state()

            next_brawler_name = self.brawlers_pick_data[0]['brawler']
            if self.brawlers_pick_data[0]["automatically_pick"]:
                self.Lobby_automation.selecting_brawler = True
                try:
                    selected = self.Lobby_automation.select_brawler(next_brawler_name)
                    attempts = 0
                    while not selected and attempts < len(self.brawlers_pick_data):
                        if self.ping_when_stuck:
                            screenshot = self.window_controller.screenshot()
                            notify_user("bot_failed_brawler_selection", screenshot, self)
                            print(f"Skipping {next_brawler_name}")
                        if self._should_stop() or self._should_pause():
                            return
                        if len(self.brawlers_pick_data) < 1:
                            print("No more brawlers selected for pushing in the menu. Bot will now pause itself until closed.")
                            screenshot = self.window_controller.screenshot()
                            notify_user("completed", screenshot, self)
                            print("Bot stopping: all targets completed with no more brawlers.")
                            self.window_controller.release_movement()
                            self.window_controller.close()
                            sys.exit(0)
                        current_brawler = self.brawlers_pick_data.pop(0)
                        self.brawlers_pick_data.append(current_brawler)
                        next_brawler_name = self.brawlers_pick_data[0]['brawler']
                        self.quit_shop()
                        selected = self.Lobby_automation.select_brawler(next_brawler_name)
                        attempts += 1
                finally:
                    self.Lobby_automation.selecting_brawler = False
                if not selected:
                    return
                self.Trophy_observer.change_trophies(self.brawlers_pick_data[0]['trophies'])
                self.Trophy_observer.current_wins = self.brawlers_pick_data[0]['wins'] if self.brawlers_pick_data[0]['wins'] != "" else 0
                self.Trophy_observer.win_streak = self.brawlers_pick_data[0]['win_streak']
            else:
                self.Trophy_observer.change_trophies(self.brawlers_pick_data[0]['trophies'])
                self.Trophy_observer.current_wins = self.brawlers_pick_data[0]['wins'] if self.brawlers_pick_data[0]['wins'] != "" else 0
                self.Trophy_observer.win_streak = self.brawlers_pick_data[0]['win_streak']
                print("Next brawler is in manual mode, waiting 10 seconds to let user switch.")
                if self._sleep_interruptible(10):
                    return
        save_brawler_data(self.brawlers_pick_data)

        if self._should_stop() or self._should_pause():
            return
        self.window_controller.release_movement()
        self.window_controller.press("proceed")
        print("Pressed to start a match")
        time.sleep(2)

    def click_star_drop(self, drop_type="regular"):
        if hasattr(self, '_star_drop_thread') and self._star_drop_thread.is_alive():
            return

        def _handle_drop():
            if drop_type in ["angelic", "demonic", "starr_nova"]:
                self.window_controller.press("proceed", 8)
            else:
                for _ in range(8):
                    self.window_controller.press("proceed", 0.05)
                    time.sleep(0.1)
        
        import threading
        self._star_drop_thread = threading.Thread(target=_handle_drop, daemon=True)
        self._star_drop_thread.start()

    def _notify_match_summary(self, screenshot):
        match_record = getattr(self.Trophy_observer, "last_match_record", None)
        if not match_record:
            return
        notify_user("match", screenshot, self, match_record=match_record)
        self._maybe_notify_stuck_brawler(screenshot)

    def _maybe_notify_stuck_brawler(self, screenshot):
        queue = getattr(self, "brawlers_pick_data", None) or []
        if not queue:
            return
        brawler = normalize_brawler_name(queue[0].get("brawler", "")).lower()
        if not brawler or brawler in self._stuck_nudge_sent:
            return
        try:
            from farm_analytics import brawler_stats, stuck_brawlers

            if brawler not in stuck_brawlers():
                return
            stats = brawler_stats().get(brawler, {})
            win_rate = float(stats.get("win_rate", 0) or 0)
            target = queue[0].get("push_until", 1000)
            notify_user(
                "recovery_alert",
                screenshot,
                {
                    "brawler": brawler,
                    "detail": f"{brawler} win rate is {win_rate * 100:.0f}% over recent matches.",
                    "notice": f"Consider skipping {brawler} or lowering push target ({target}).",
                    "event_type": "stuck_brawler",
                },
            )
            self._stuck_nudge_sent.add(brawler)
        except Exception:
            pass

    def _clear_instance_session_state(self):
        try:
            import os

            instance_id = str(os.environ.get("PYLA_INSTANCE_ID", "") or "").strip()
            if instance_id:
                from gui.session_state import clear_session_state

                clear_session_state(instance_id)
        except Exception:
            pass

    @staticmethod
    def _is_win_result(result):
        if not result:
            return False
        normalized = str(result).strip().lower()
        if normalized == "victory":
            return True
        if normalized.startswith("trio_showdown_"):
            try:
                place = int(normalized.rsplit("_", 1)[-1])
            except (TypeError, ValueError):
                return False
            return place <= 1
        return False

    def requires_brawler_reselection(self, active_brawler=None):
        brawlers_pick_data = getattr(self, "brawlers_pick_data", None)
        if not brawlers_pick_data:
            return False
        active_name = normalize_brawler_name(active_brawler or getattr(self, "active_match_brawler", ""))
        front_name = normalize_brawler_name(brawlers_pick_data[0].get("brawler", ""))
        return bool(active_name and front_name and active_name != front_name)

    def should_return_to_lobby_after_match(self, active_brawler=None):
        if getattr(self, "pending_brawler_reselection", False):
            return True
        if getattr(self, "brawlers_pick_data", None) and getattr(self, "Trophy_observer", None):
            type_to_push = self.brawlers_pick_data[0].get("type", "trophies")
            value = getattr(self.Trophy_observer, f"current_{type_to_push}", None)
            if value is None and type_to_push == "trophies":
                value = getattr(self.Trophy_observer, "current_trophies", 0)
            target = self.brawlers_pick_data[0].get("push_until", 1000)
            try:
                if int(value) >= int(target):
                    return True
            except (TypeError, ValueError):
                pass
        return self.requires_brawler_reselection(active_brawler)

    def should_use_play_again(self, value=0, target=0, active_brawler=None):
        if self.post_match_action != "play_again":
            return False
        try:
            if int(value) >= int(target):
                return False
        except (TypeError, ValueError):
            pass
        if self.should_return_to_lobby_after_match(active_brawler):
            return False
        try:
            return int(value) < int(target)
        except (TypeError, ValueError):
            return True

    def _should_press_play_again(self, result, value, target):
        if not self.should_use_play_again(value, target):
            return False
        if self.play_again_on_win and not self._is_win_result(result):
            return False
        return not self._should_pause() and not self._should_stop()

    def dismiss_end_screen(self, use_play_again=False):
        self.window_controller.keys_up(list("wasd"))
        if use_play_again:
            screenshot = self.window_controller.screenshot()
            if self.is_play_again_button_visually_available(screenshot):
                print("Post-match action: clicking PLAY AGAIN.")
                self.click_play_again_button()
                return

            exit_center = self.get_play_again_missing_exit_center(screenshot, allow_ocr=False)
            if exit_center is not None:
                print("Play Again unavailable; clicking EXIT to requeue from lobby.")
                self.window_controller.click(*exit_center, delay=0.08)
                return

            text_state = self.get_play_again_text_state(screenshot)
            if text_state == "play_again":
                print("Post-match action: clicking PLAY AGAIN.")
                self.click_play_again_button()
                return
            if text_state == "exit":
                print("Play Again unavailable; clicking EXIT to requeue from lobby.")
                self.window_controller.click(
                    int(1660 * self.window_controller.width_ratio),
                    int(980 * self.window_controller.height_ratio),
                    delay=0.08,
                )
                return

            print("Play Again button is not enabled; pressing continue instead.")
            self.window_controller.press_key("Q")
            return
        self.window_controller.press_key("Q")

    def click_play_again_button(self):
        self.window_controller.click(
            int(1215 * self.window_controller.width_ratio),
            int(935 * self.window_controller.height_ratio),
            delay=0.08,
        )

    def _scaled_crop(self, image, region):
        if image is None or image.size == 0:
            return None
        height, width = image.shape[:2]
        x, y, w, h = region
        x1 = max(0, int(x * width / 1920))
        y1 = max(0, int(y * height / 1080))
        x2 = min(width, int((x + w) * width / 1920))
        y2 = min(height, int((y + h) * height / 1080))
        crop = image[y1:y2, x1:x2]
        return crop if crop.size else None

    @staticmethod
    def _button_color_ratios(crop):
        hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
        blue = cv2.inRange(hsv, np.array((95, 80, 100), dtype=np.uint8), np.array((125, 255, 255), dtype=np.uint8))
        green = cv2.inRange(hsv, np.array((42, 70, 100), dtype=np.uint8), np.array((82, 255, 255), dtype=np.uint8))
        yellow = cv2.inRange(hsv, np.array((18, 70, 110), dtype=np.uint8), np.array((38, 255, 255), dtype=np.uint8))
        dark = cv2.inRange(hsv, np.array((0, 0, 0), dtype=np.uint8), np.array((179, 255, 90), dtype=np.uint8))
        total = max(1, crop.shape[0] * crop.shape[1])
        return {
            "button": (cv2.countNonZero(blue) + cv2.countNonZero(green) + cv2.countNonZero(yellow)) / total,
            "dark": cv2.countNonZero(dark) / total,
        }

    def is_play_again_button_visually_available(self, screenshot):
        play_crop = self._scaled_crop(screenshot, [1030, 850, 360, 150])
        if play_crop is None:
            return False
        ratios = self._button_color_ratios(play_crop)
        return ratios["button"] > 0.18 and ratios["dark"] > 0.035

    def get_play_again_missing_exit_center(self, screenshot, allow_ocr=True):
        if screenshot is None or screenshot.size == 0:
            return None

        play_crop = self._scaled_crop(screenshot, [1030, 850, 360, 150])
        exit_crop = self._scaled_crop(screenshot, [1480, 850, 380, 170])
        if exit_crop is None:
            return None
        exit_ratios = self._button_color_ratios(exit_crop)
        play_ratios = self._button_color_ratios(play_crop) if play_crop is not None else {"button": 0.0, "dark": 0.0}
        if exit_ratios["button"] > 0.20 and exit_ratios["dark"] > 0.035 and play_ratios["button"] < 0.12:
            return (
                int(1660 * self.window_controller.width_ratio),
                int(980 * self.window_controller.height_ratio),
            )

        if not allow_ocr:
            return None

        text_state = self.get_play_again_text_state(screenshot)
        if text_state != "exit":
            return None

        return (
            int(1660 * self.window_controller.width_ratio),
            int(980 * self.window_controller.height_ratio),
        )

    def get_play_again_text_state(self, screenshot):
        try:
            height, width = screenshot.shape[:2]
            button_crop = screenshot[int(height * 0.78):height, int(width * 0.72):width]
            texts = extract_text_strings(button_crop)
        except Exception:
            return ""

        normalized_words = [normalize_brawler_name(text) for text in texts]
        normalized_text = " ".join(normalized_words)
        compact_text = "".join(normalized_words)
        play_again_visible = (
            "play" in normalized_text and "again" in normalized_text
        ) or "playagain" in compact_text
        if play_again_visible:
            return "play_again"
        if "exit" in normalized_text:
            return "exit"
        return ""

    def end_game(self):
        screenshot = self.window_controller.screenshot()

        found_game_result = False
        match_notified = False
        current_state = get_state(screenshot)
        use_play_again = False
        end_screen_time = time.time()
        stats_recorded = False

        while current_state.startswith("end") and time.time() - end_screen_time < 35:
            if not stats_recorded:
                found_game_result = '_'.join(current_state.split("_")[1:])
                current_brawler = self.brawlers_pick_data[0]['brawler']
                power_level = None
                if early_access and getattr(self, "player_tag", None):
                    player_info = get_player_info(self.player_tag)
                    power_level = get_brawler_stats(player_info, current_brawler, power_level=True)[2]
                trophies_before = self._number_or_default(
                    getattr(self.Trophy_observer, "current_trophies", 0),
                    0,
                )
                self.Trophy_observer.add_trophies(found_game_result, current_brawler, self.playstyle_info, power_level)
                self.Trophy_observer.add_win(found_game_result)
                trophies_after = self._number_or_default(
                    getattr(self.Trophy_observer, "current_trophies", trophies_before),
                    trophies_before,
                )
                self.last_match_trophy_before = trophies_before
                self.last_match_trophy_after = trophies_after
                self.last_match_trophy_delta = trophies_after - trophies_before
                self.last_match_crossed_1000 = (
                    trophies_before < 1000 <= trophies_after and trophies_after > trophies_before
                )
                self.time_since_last_stat_change = time.time()
                self.last_recorded_result_time = time.time()
                values = {
                    "trophies": self.Trophy_observer.current_trophies,
                    "wins": self.Trophy_observer.current_wins
                }
                type_to_push = self.brawlers_pick_data[0]['type']
                value = values[type_to_push]
                target = self.brawlers_pick_data[0].get("push_until", 1000)
                self.brawlers_pick_data[0][type_to_push] = value
                self.brawlers_pick_data[0]['win_streak'] = self.Trophy_observer.win_streak
                save_brawler_data(self.brawlers_pick_data)
                self.sync_trophies_from_api_after_match(current_brawler)
                value, target, type_to_push = self._match_row_progress(current_brawler)
                if type_to_push in values:
                    self.brawlers_pick_data[0][type_to_push] = value
                    save_brawler_data(self.brawlers_pick_data)
                stats_recorded = True
                if not match_notified:
                    self._notify_match_summary(screenshot)
                    match_notified = True
                use_play_again = self._should_press_play_again(found_game_result, value, target)

            if use_play_again:
                print("Post-match action: Play Again.")
            else:
                print("Game has ended, proceeding")
            self.dismiss_end_screen(use_play_again=use_play_again)

            time.sleep(3)
            screenshot = self.window_controller.screenshot()
            current_state = get_state(screenshot)

        if use_play_again and not self._should_pause():
            print("Waiting for match to start...")
            start_wait_time = time.time()
            while time.time() - start_wait_time < 25:
                if self._should_stop() or self._should_pause():
                    break
                screenshot = self.window_controller.screenshot()
                current_state = get_state(screenshot)
                if current_state == "match":
                    print("Match started successfully!")
                    return
                if self._sleep_interruptible(0.5):
                    break

            print("Match did not start within 25s, proceeding to return to lobby.")
            self.window_controller.press("proceed")
            time.sleep(2)

        print("Game has ended", current_state)

    def quit_shop(self):
        if getattr(getattr(self, "Lobby_automation", None), "selecting_brawler", False):
            return
        now = time.time()
        last_escape = getattr(self, "_last_shop_escape_at", 0.0)
        if now - last_escape < 1.0:
            return
        self._last_shop_escape_at = now
        if hasattr(self.window_controller, "press_escape") and self.window_controller.press_escape():
            time.sleep(0.35)
            return
        if hasattr(self.window_controller, "android_back") and self.window_controller.android_back():
            time.sleep(0.35)
            return
        self.window_controller.click(
            100 * self.window_controller.width_ratio,
            60 * self.window_controller.height_ratio,
        )
        time.sleep(0.35)

    def close_pop_up(self):
        screenshot = self.window_controller.screenshot()
        if self.close_popup_icon is None:
            self.close_popup_icon = load_image("images/states/close_popup.png", self.window_controller.scale_factor)
        popup_location = find_template_center(screenshot, self.close_popup_icon)
        if popup_location:
            self.window_controller.click(*popup_location)

    def stage_queue_update(self, new_queue, reason="", reselect_brawler=""):
        from core.integration import normalize_queue, save_queue_data

        normalized = normalize_queue(new_queue)
        if not normalized:
            return False
        self.brawlers_pick_data = normalized
        save_queue_data(normalized)
        self._queue_file_mtime = None
        return True

    def do_state(self, state, data=None):
        if data is not None:
            self.states[state](data)
            return
        self.states[state]()
