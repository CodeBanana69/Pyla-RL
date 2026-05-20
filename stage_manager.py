import os.path
import sys

import asyncio
import time

import cv2
import numpy as np

from state_finder import (
    get_state,
    find_game_result,
    is_in_prestige_reward,
    get_prestige_next_button_center,
    get_star_drop_type,
    get_skin_reward_equip_button_center,
    get_skin_reward_continue_button_center,
)
from trophy_observer import TrophyObserver
from utils import find_template_center, load_toml_as_dict, async_notify_user, \
    save_brawler_data, extract_text_strings, load_brawl_stars_api_config, fetch_brawl_stars_player, normalize_brawler_name

debug = load_toml_as_dict("cfg/general_config.toml")['super_debug'] == "yes"


def load_image(image_path, scale_factor):
    # Load the image
    image = cv2.imread(image_path)
    orig_height, orig_width = image.shape[:2]

    # Calculate the new dimensions based on the scale factor
    new_width = int(orig_width * scale_factor)
    new_height = int(orig_height * scale_factor)

    # Resize the image
    resized_image = cv2.resize(image, (new_width, new_height))
    return resized_image

class StageManager:

    def __init__(self, brawlers_data, lobby_automator, window_controller):
        self.Lobby_automation = lobby_automator
        self.lobby_config = load_toml_as_dict("./cfg/lobby_config.toml")
        self.close_popup_icon = None
        self.brawlers_pick_data = brawlers_data
        self.started_trophies_by_brawler = {}
        for brawler in brawlers_data:
            name = str(brawler.get("brawler", "")).lower()
            if name:
                self.started_trophies_by_brawler[name] = brawler.get("trophies", 0)
        brawler_list = [brawler["brawler"] for brawler in brawlers_data]
        self.Trophy_observer = TrophyObserver(brawler_list)
        bot_config = load_toml_as_dict("cfg/bot_config.toml")
        self.post_match_action = str(bot_config.get("post_match_action", "lobby")).strip().lower()
        if self.post_match_action not in ("lobby", "play_again"):
            self.post_match_action = "lobby"
        self.time_since_last_stat_change = time.time()
        # Guards against recording trophies twice when end_game() is re-entered
        # on the same end-of-match screen (e.g. because the dismiss button
        # didn't clear the screen before the outer loop called us again).
        self.last_recorded_result_time = 0.0
        self.last_recorded_result = None
        self.active_end_result = None
        self.last_match_trophy_before = None
        self.last_match_trophy_after = None
        self.last_match_trophy_delta = 0
        self.last_match_crossed_1000 = False
        self.last_player_total_trophies = None
        self.stop_after_post_match_rewards = False
        self.completion_notification_sent = False
        time_thresholds = load_toml_as_dict("./cfg/time_tresholds.toml")
        self.end_screen_dismiss_delay = float(time_thresholds.get("end_screen_dismiss_delay", 0.35))
        self.window_controller = window_controller
        self.states = {
            'shop': self.quit_shop,
            'brawler_selection': self.quit_shop,
            'popup': self.close_pop_up,
            'match': lambda: 0,
            'match_making': lambda: self.window_controller.keys_up(list("wasd")),
            'end_draw': self.end_game,
            'end_victory': self.end_game,
            'end_defeat': self.end_game,
            # Showdown trio: finishing places 1-4
            'end_1st': self.end_game,
            'end_2nd': self.end_game,
            'end_3rd': self.end_game,
            'end_4th': self.end_game,
            'lobby': self.start_game,
            'star_drop': self.handle_star_drop,
            'daily_star_drop': self.handle_star_drop,
            'nova_star_drop': self.handle_star_drop,
            'prestige_reward': self.handle_prestige_reward,
            'trophy_reward': self.handle_trophy_reward,
            'reward_unlock': self.handle_reward_unlock,
        }

    def should_use_play_again(self, value=0, target=0):
        if self.post_match_action != "play_again":
            return False
        try:
            return int(value) < int(target)
        except (TypeError, ValueError):
            return True

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
        # Fast path: avoid OCR when the expected Play Again button is plainly
        # present. The region is intentionally narrow so the far-right EXIT
        # button does not make this look like Play Again.
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

    def restart_and_select_next_after_target(self, target, type_of_push):
        print("Target reached in Play Again mode; restarting Brawl Stars before selecting next brawler.")
        if not self._prepare_next_push_all_brawler(target, type_of_push):
            print("No remaining brawlers are below the target after restart preparation.")
            self.stop_after_post_match_rewards = True
            return False

        self.window_controller.keys_up(list("wasd"))
        if not self.window_controller.restart_brawl_stars():
            print("Brawl Stars restart failed after target completion; falling back to normal lobby flow.")
            return False
        if hasattr(self.window_controller, "restart_scrcpy_client"):
            self.window_controller.restart_scrcpy_client()

        lobby_screenshot = self.wait_for_lobby_after_reward(max_attempts=45)
        if lobby_screenshot is None:
            print("Could not confirm lobby after target-completion restart; delaying next selection.")
            return False

        selection_method = self.brawlers_pick_data[0].get("selection_method", "named_brawler")
        if selection_method == "lowest_trophies":
            selected = self.Lobby_automation.select_lowest_trophy_brawler()
        else:
            selected = self.Lobby_automation.select_brawler(self.brawlers_pick_data[0]["brawler"])
        if not selected:
            print("Could not confirm next brawler selection after restart.")
            return False

        self.window_controller.press_key("Q")
        print("Target-completion restart finished; selected next brawler and started matchmaking.")
        return True

    def send_webhook_notification(self, event_type, screenshot=None, details=None):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(async_notify_user(event_type, screenshot, details=details or {}))
        finally:
            loop.run_until_complete(asyncio.sleep(0.25))
            loop.run_until_complete(loop.shutdown_asyncgens())
            asyncio.set_event_loop(None)
            loop.close()

    def current_target_details(self, extra=None):
        current = self.brawlers_pick_data[0] if self.brawlers_pick_data else {}
        type_to_push = current.get("type", "trophies")
        values = {
            "trophies": self.Trophy_observer.current_trophies,
            "wins": self.Trophy_observer.current_wins,
        }
        details = {
            "brawler": current.get("brawler", ""),
            "started_trophies": self.started_trophies_by_brawler.get(
                str(current.get("brawler", "")).lower(),
                current.get("trophies", 0),
            ),
            "trophies": values.get(type_to_push, self.Trophy_observer.current_trophies),
            "target": current.get("push_until", ""),
            "wins": self.Trophy_observer.current_wins,
            "win_streak": self.Trophy_observer.win_streak,
            "brawlers_left": len(self.brawlers_pick_data),
        }
        total_trophies = self.player_total_trophies()
        if total_trophies is not None:
            details["total_trophies"] = total_trophies
        trophy_delta = getattr(self, "last_match_trophy_delta", 0) or 0
        if trophy_delta:
            details["trophy_delta"] = trophy_delta
        if extra:
            details.update(extra)
        return details

    def player_total_trophies(self):
        config = dict(load_toml_as_dict("cfg/brawl_stars_api.toml"))
        config.update(load_toml_as_dict("cfg/brawl_stars_api.local.toml"))
        player_tag = str(config.get("player_tag") or "").strip()
        has_token = bool(str(config.get("api_token") or "").strip())
        has_refresh_login = bool(
            config.get("auto_refresh_token")
            and str(config.get("developer_email") or "").strip()
            and str(config.get("developer_password") or "").strip()
        )
        if not player_tag or player_tag == "#YOURTAG" or not (has_token or has_refresh_login):
            return getattr(self, "last_player_total_trophies", None)
        try:
            player = self.fetch_push_all_player_data()
            total = player.get("trophies")
            if total is not None:
                self.last_player_total_trophies = int(total)
        except Exception as e:
            print(f"Could not fetch player total trophies for webhook: {e}")
        return getattr(self, "last_player_total_trophies", None)

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

    def _sync_observer_to_current_row(self):
        if not self.brawlers_pick_data:
            return
        current = self.brawlers_pick_data[0]
        self.Trophy_observer.change_trophies(
            self._number_or_default(current.get("trophies", 0), 0)
        )
        self.Trophy_observer.current_wins = self._number_or_default(current.get("wins", 0), 0)
        self.Trophy_observer.win_streak = self._number_or_default(current.get("win_streak", 0), 0)

    def _prepare_next_push_all_brawler(self, target, type_of_push="trophies"):
        """Remove completed Push All rows and choose the current lowest remaining row.

        Push All queues are built from API trophies at launch, but the queue can
        become stale after each match. Re-sorting here keeps all trophy targets
        targets on the same "least trophies next" behavior the player sees in
        the Brawl Stars brawler menu.
        """
        if not self.brawlers_pick_data:
            return False

        target = self._number_or_default(target, 1000 if type_of_push == "trophies" else 300)
        current_row = self.brawlers_pick_data[0]
        current_row[type_of_push] = self._number_or_default(
            getattr(self.Trophy_observer, f"current_{type_of_push}", current_row.get(type_of_push, 0)),
            current_row.get(type_of_push, 0),
        )
        current_row["win_streak"] = self.Trophy_observer.win_streak

        remaining = self.brawlers_pick_data[1:]
        if type_of_push == "trophies":
            remaining = [
                dict(row)
                for row in remaining
                if self._number_or_default(row.get("trophies", 0), 0)
                < self._number_or_default(row.get("push_until", target), target)
            ]
        else:
            remaining = [
                dict(row)
                for row in remaining
                if self._number_or_default(row.get("wins", 0), 0)
                < self._number_or_default(row.get("push_until", target), target)
            ]

        if not remaining:
            self.brawlers_pick_data = []
            save_brawler_data(self.brawlers_pick_data)
            return False

        if any(row.get("selection_method") == "lowest_trophies" for row in remaining):
            remaining.sort(
                key=lambda row: (
                    self._number_or_default(row.get(type_of_push, 0), 0),
                    str(row.get("brawler", "")),
                )
            )
            for row in remaining:
                row["selection_method"] = "lowest_trophies"
                row["automatically_pick"] = True

        self.brawlers_pick_data = remaining
        self._sync_observer_to_current_row()
        save_brawler_data(self.brawlers_pick_data)
        return True

    def refresh_push_all_trophies_from_api(self):
        if not self.brawlers_pick_data:
            return False
        if self.brawlers_pick_data[0].get("type", "trophies") != "trophies":
            return False
        if not any(row.get("selection_method") == "lowest_trophies" for row in self.brawlers_pick_data):
            return False

        old_front_brawler = self.brawlers_pick_data[0].get("brawler")
        try:
            player_data = self.fetch_push_all_player_data(force_token_refresh=False)
        except RuntimeError as e:
            if "accessDenied" not in str(e):
                print(f"Push All API trophy refresh failed; using local trophies. {e}")
                return False
            try:
                print("Push All API token was rejected; refreshing token for current public IP and retrying.")
                player_data = self.fetch_push_all_player_data(force_token_refresh=True)
            except Exception as retry_error:
                print(f"Push All API trophy refresh failed after token refresh; using local trophies. {retry_error}")
                return False
        except Exception as e:
            print(f"Push All API trophy refresh failed; using local trophies. {e}")
            return False

        trophies_by_brawler = {
            normalize_brawler_name(brawler.get("name", "")): int(brawler.get("trophies", 0))
            for brawler in player_data.get("brawlers", [])
        }
        default_target = self._number_or_default(self.brawlers_pick_data[0].get("push_until", 1000), 1000)
        changed = False
        refreshed_rows = []
        for row in self.brawlers_pick_data:
            key = normalize_brawler_name(row.get("brawler", ""))
            refreshed_row = dict(row)
            if key in trophies_by_brawler:
                api_trophies = trophies_by_brawler[key]
                if refreshed_row.get("brawler") == old_front_brawler:
                    local_trophies = self._number_or_default(
                        getattr(self.Trophy_observer, "current_trophies", refreshed_row.get("trophies", 0)),
                        refreshed_row.get("trophies", 0),
                    )
                    api_trophies = max(api_trophies, local_trophies)
                if refreshed_row.get("trophies") != api_trophies:
                    refreshed_row["trophies"] = api_trophies
                    changed = True
            row_target = self._number_or_default(refreshed_row.get("push_until", default_target), default_target)
            if self._number_or_default(refreshed_row.get("trophies", 0), 0) < row_target:
                refreshed_rows.append(refreshed_row)

        current_row = next(
            (row for row in refreshed_rows if row.get("brawler") == old_front_brawler),
            None,
        )
        remaining_rows = [
            row for row in refreshed_rows
            if row.get("brawler") != old_front_brawler
        ]

        if current_row is not None:
            remaining_rows.sort(
                key=lambda row: (
                    self._number_or_default(row.get("trophies", 0), 0),
                    str(row.get("brawler", "")),
                )
            )
            refreshed_rows = [current_row] + remaining_rows
            self.push_all_needs_selection = False
        else:
            refreshed_rows = remaining_rows
            self.push_all_needs_selection = bool(refreshed_rows)

        if refreshed_rows:
            refreshed_rows[0]["automatically_pick"] = bool(self.push_all_needs_selection)
            refreshed_rows[0]["selection_method"] = "lowest_trophies"
            for row in refreshed_rows[1:]:
                if row.get("automatically_pick") is not True:
                    changed = True
                row["automatically_pick"] = True
                row["selection_method"] = "lowest_trophies"

        old_order = [row.get("brawler") for row in self.brawlers_pick_data]
        new_order = [row.get("brawler") for row in refreshed_rows]
        if new_order != old_order:
            changed = True

        if not refreshed_rows:
            self.brawlers_pick_data = []
            save_brawler_data(self.brawlers_pick_data)
            print("Push All API trophies refreshed: all brawlers reached target.")
            return True

        if len(refreshed_rows) != len(self.brawlers_pick_data):
            changed = True

        self.brawlers_pick_data = refreshed_rows

        new_front_brawler = self.brawlers_pick_data[0].get("brawler")
        if new_front_brawler != old_front_brawler:
            self._sync_observer_to_current_row()
            changed = True
        else:
            current_trophies = self._number_or_default(self.brawlers_pick_data[0].get("trophies", 0), 0)
            if getattr(self.Trophy_observer, "current_trophies", None) != current_trophies:
                self.Trophy_observer.change_trophies(current_trophies)
                changed = True
            current_wins = self._number_or_default(
                getattr(self.Trophy_observer, "current_wins", self.brawlers_pick_data[0].get("wins", 0)),
                self.brawlers_pick_data[0].get("wins", 0),
            )
            current_streak = self._number_or_default(
                getattr(self.Trophy_observer, "win_streak", self.brawlers_pick_data[0].get("win_streak", 0)),
                self.brawlers_pick_data[0].get("win_streak", 0),
            )
            if self.brawlers_pick_data[0].get("wins") != current_wins:
                self.brawlers_pick_data[0]["wins"] = current_wins
                changed = True
            if self.brawlers_pick_data[0].get("win_streak") != current_streak:
                self.brawlers_pick_data[0]["win_streak"] = current_streak
                changed = True

        if changed:
            if self.push_all_needs_selection:
                print("Push All API trophies refreshed; current brawler reached target, selecting next lowest.")
            else:
                print("Push All API trophies refreshed; keeping current brawler until target.")
            save_brawler_data(self.brawlers_pick_data)
        return changed

    @staticmethod
    def fetch_push_all_player_data(force_token_refresh=False):
        api_config = load_brawl_stars_api_config(
            "cfg/brawl_stars_api.toml",
            force_refresh=force_token_refresh,
        )
        return fetch_brawl_stars_player(
            api_config.get("api_token", "").strip(),
            api_config.get("player_tag", "").strip(),
            int(api_config.get("timeout_seconds", 15)),
        )

    def start_game(self):
        print("state is lobby, starting game")
        if getattr(self, "stop_after_post_match_rewards", False):
            print("Post-match rewards cleared; stopping after completed target.")
            if os.path.exists("latest_brawler_data.json"):
                os.remove("latest_brawler_data.json")
            self.window_controller.keys_up(list("wasd"))
            self.window_controller.close()
            sys.exit(0)
        self.push_all_needs_selection = False
        self.refresh_push_all_trophies_from_api()
        if not self.brawlers_pick_data:
            print("Bot stopping: all Push All targets completed.")
            self.window_controller.keys_up(list("wasd"))
            self.window_controller.close()
            sys.exit(0)
        values = {
            "trophies": self.Trophy_observer.current_trophies,
            "wins": self.Trophy_observer.current_wins
        }

        type_of_push = self.brawlers_pick_data[0]['type']
        if type_of_push not in values:
            type_of_push = "trophies"
        value = values[type_of_push]
        saved_value = self._number_or_default(self.brawlers_pick_data[0].get(type_of_push, 0), 0)
        if value == "" and type_of_push == "wins":
            value = 0
        push_current_brawler_till = self.brawlers_pick_data[0]['push_until']
        if push_current_brawler_till == "" and type_of_push == "wins":
            push_current_brawler_till = 300
        if push_current_brawler_till == "" and type_of_push == "trophies":
            push_current_brawler_till = 1000
        push_current_brawler_till = self._number_or_default(
            push_current_brawler_till,
            1000 if type_of_push == "trophies" else 300,
        )
        value = self._number_or_default(value, 0)
        value = max(value, saved_value)

        if value >= push_current_brawler_till:
            if len(self.brawlers_pick_data) <= 1:
                print("Brawler reached required trophies/wins. No more brawlers selected for pushing in the menu. "
                      "Bot will now pause itself until closed.", value, push_current_brawler_till)
                screenshot = self.window_controller.screenshot()
                self.send_webhook_notification(
                    "completed",
                    screenshot,
                    self.current_target_details({"target": push_current_brawler_till}),
                )
                print("Bot stopping: all targets completed with no more brawlers.")
                self.window_controller.keys_up(list("wasd"))
                self.window_controller.close()
                sys.exit(0)
            completed_brawler = self.brawlers_pick_data[0]["brawler"]
            screenshot = self.window_controller.screenshot()
            self.send_webhook_notification(
                "brawler_complete",
                screenshot,
                self.current_target_details({
                    "brawler": completed_brawler,
                    "target": push_current_brawler_till,
                    "brawlers_left": max(0, len(self.brawlers_pick_data) - 1),
                }),
            )
            if not self._prepare_next_push_all_brawler(push_current_brawler_till, type_of_push):
                print("Brawler reached required trophies/wins. No remaining brawlers are below the Push All target.")
                self.send_webhook_notification(
                    "completed",
                    screenshot,
                    self.current_target_details({"target": push_current_brawler_till}),
                )
                print("Bot stopping: all Push All targets completed.")
                self.window_controller.keys_up(list("wasd"))
                self.window_controller.close()
                sys.exit(0)
            if self.brawlers_pick_data[0]["automatically_pick"]:
                print("Picking next automatically picked brawler")
                screenshot = self.window_controller.screenshot()
                current_state = get_state(screenshot)
                if current_state != "lobby":
                    print("Trying to reach the lobby to switch brawler")

                max_attempts = 30
                attempts = 0
                while current_state != "lobby" and attempts < max_attempts:
                    self.window_controller.press_key("Q")
                    print("Pressed Q to return to lobby")
                    time.sleep(1)
                    screenshot = self.window_controller.screenshot()
                    current_state = get_state(screenshot)
                    attempts += 1
                if attempts >= max_attempts:
                    print("Failed to reach lobby after max attempts")
                else:
                    selection_method = self.brawlers_pick_data[0].get("selection_method", "named_brawler")
                    if selection_method == "lowest_trophies":
                        selected = self.Lobby_automation.select_lowest_trophy_brawler()
                    else:
                        next_brawler_name = self.brawlers_pick_data[0]['brawler']
                        selected = self.Lobby_automation.select_brawler(next_brawler_name)
                    if not selected:
                        print("Could not confirm the next brawler selection reached lobby; delaying match start.")
                        self.window_controller.keys_up(list("wasd"))
                        return
            else:
                print("Next brawler is in manual mode, waiting 10 seconds to let user switch.")

        elif self.push_all_needs_selection:
            print("Push All queue changed from API; selecting the new lowest trophy brawler.")
            selected = self.Lobby_automation.select_lowest_trophy_brawler()
            if not selected:
                print("Could not confirm the API-refreshed brawler selection reached lobby; delaying match start.")
                self.window_controller.keys_up(list("wasd"))
                return

        # q btn is over the start btn
        self.window_controller.keys_up(list("wasd"))
        self.window_controller.press_key("Q")
        print("Pressed Q to start a match")
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

    def handle_star_drop(self):
        screenshot = self.window_controller.screenshot()
        screenshot_bgr = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
        drop_type = get_star_drop_type(screenshot_bgr)
        if drop_type is None:
            return

        label = {
            "daily_hold": "Daily Wins hold",
            "starr_nova_hold": "Starr Nova hold",
            "angelic": "Angelic",
            "demonic": "Demonic",
            "standard": "Standard",
        }.get(drop_type, str(drop_type).replace("_", " ").title())
        print(f"{label} star drop detected; opening by template.")
        self.window_controller.keys_up(list("wasd"))
        current_height, current_width = screenshot.shape[:2]
        width_ratio = current_width / 1920
        height_ratio = current_height / 1080
        x = int(965 * width_ratio)
        y = int(525 * height_ratio)
        if drop_type == "starr_nova_hold":
            for duration in (5.0, 10.0):
                if hasattr(self.window_controller, "long_press"):
                    self.window_controller.long_press(x, y, duration=duration)
                else:
                    self.window_controller.click(x, y, delay=duration)
                time.sleep(0.25)

                followup = self.window_controller.screenshot()
                followup_bgr = cv2.cvtColor(followup, cv2.COLOR_RGB2BGR)
                if get_star_drop_type(followup_bgr) != "starr_nova_hold":
                    break
                if duration == 5.0:
                    print("Starr Nova hold still detected after 5s; trying 10s hold.")
        elif drop_type in ("angelic", "demonic", "daily_hold"):
            for _ in range(2):
                if hasattr(self.window_controller, "long_press"):
                    self.window_controller.long_press(x, y, duration=1.15)
                else:
                    self.window_controller.click(x, y, delay=1.15)
                time.sleep(0.25)
        else:
            for _ in range(5):
                self.window_controller.click(x, y, delay=0.04)
                time.sleep(0.08)

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

        if lobby_trophies is None:
            print("Could not read lobby trophies after prestige; trusting confirmed prestige reward screen.")
        elif lobby_trophies > 20:
            print("Reward screen did not confirm a 1k trophy reset; not forcing brawler switch.")
            return

        if not self.advance_to_next_brawler_after_prestige():
            self.window_controller.press_key("Q")
            return

        self.Lobby_automation.select_lowest_trophy_brawler()

    def end_game(self):
        screenshot = self.window_controller.screenshot()

        found_game_result = False
        current_state = get_state(screenshot)
        button_pressed = False
        end_screen_time = time.time()

        # If this is a re-entry on the same lingering end-of-match screen,
        # skip recording and just keep trying to dismiss it.
        current_result = current_state.split("_", 1)[1] if current_state.startswith("end_") else None
        already_recorded = current_result is not None and self.active_end_result == current_result
        stats_recorded = already_recorded
        use_play_again = False
        if already_recorded:
            found_game_result = current_result
            print(f"end_game: re-entry on '{current_state}', skipping trophy update")

        while current_state.startswith("end") and time.time() - end_screen_time < 25:
            if not stats_recorded:
                found_game_result = current_state.split("_")[1]
                current_brawler = self.brawlers_pick_data[0]['brawler']
                trophies_before = self._number_or_default(
                    getattr(self.Trophy_observer, "current_trophies", 0),
                    0,
                )
                self.Trophy_observer.add_trophies(found_game_result, current_brawler)
                self.Trophy_observer.add_win(found_game_result)
                trophies_after = self._number_or_default(
                    getattr(self.Trophy_observer, "current_trophies", trophies_before),
                    trophies_before,
                )
                self.last_match_trophy_before = trophies_before
                self.last_match_trophy_after = trophies_after
                self.last_match_trophy_delta = trophies_after - trophies_before
                self.last_match_crossed_1000 = trophies_before < 1000 <= trophies_after and trophies_after > trophies_before
                self.time_since_last_stat_change = time.time()
                self.last_recorded_result = found_game_result
                self.last_recorded_result_time = time.time()
                self.active_end_result = found_game_result
                stats_recorded = True
                values = {
                    "trophies": self.Trophy_observer.current_trophies,
                    "wins": self.Trophy_observer.current_wins
                }
                type_to_push = self.brawlers_pick_data[0]['type']
                if type_to_push not in values:
                    type_to_push = "trophies"
                value = values[type_to_push]
                self.brawlers_pick_data[0][type_to_push] = value
                self.brawlers_pick_data[0]['win_streak'] = self.Trophy_observer.win_streak
                save_brawler_data(self.brawlers_pick_data)
                self.send_webhook_notification(
                    "match",
                    screenshot,
                    self.current_target_details({
                        "result": found_game_result,
                        "target": self.brawlers_pick_data[0].get("push_until", ""),
                    }),
                )
                push_current_brawler_till = self.brawlers_pick_data[0]['push_until']

                if value == "" and type_to_push == "wins":
                    value = 0
                if push_current_brawler_till == "" and type_to_push == "wins":
                    push_current_brawler_till = 300
                if push_current_brawler_till == "" and type_to_push == "trophies":
                    push_current_brawler_till = 1000
                push_current_brawler_till = self._number_or_default(
                    push_current_brawler_till,
                    1000 if type_to_push == "trophies" else 300,
                )
                value = self._number_or_default(value, 0)
                use_play_again = self.should_use_play_again(value, push_current_brawler_till)

                if value >= push_current_brawler_till:
                    use_play_again = False
                    if len(self.brawlers_pick_data) <= 1:
                        print(
                            "Brawler reached required trophies/wins. No more brawlers selected for pushing in the menu. "
                            "Bot will finish reward screens before stopping.")
                        self.stop_after_post_match_rewards = True
                        if not self.completion_notification_sent:
                            screenshot = self.window_controller.screenshot()
                            self.send_webhook_notification(
                                "completed",
                                screenshot,
                                self.current_target_details({
                                    "result": found_game_result,
                                    "target": push_current_brawler_till,
                                }),
                            )
                            self.completion_notification_sent = True
                    else:
                        print(
                            "Brawler reached required trophies/wins. "
                            "Will switch brawler as soon as lobby is reached.",
                            value,
                            push_current_brawler_till,
                        )
                        if self.post_match_action == "play_again":
                            if self.restart_and_select_next_after_target(push_current_brawler_till, type_to_push):
                                return
            
            # Keep pressing the dismiss key on every iteration until the
            # end-of-match screens give way. One press is rarely enough in
            # showdown: after the place screen there can be star drops,
            # trophy rewards, and offers to dismiss.
            self.dismiss_end_screen(use_play_again=use_play_again)
            button_pressed = True

            time.sleep(self.end_screen_dismiss_delay)
            screenshot = self.window_controller.screenshot()
            current_state = get_state(screenshot)

        print("Game has ended", current_state)

    def quit_shop(self):
        if hasattr(self.window_controller, "android_back") and self.window_controller.android_back():
            return
        self.window_controller.click(100*self.window_controller.width_ratio, 60*self.window_controller.height_ratio)

    def close_pop_up(self):
        screenshot = self.window_controller.screenshot()
        if self.close_popup_icon is None:
            self.close_popup_icon = load_image("images/states/close_popup.png", self.window_controller.scale_factor)
        popup_location = find_template_center(screenshot, self.close_popup_icon)
        if popup_location:
            self.window_controller.click(*popup_location)

    def tap_with_adb_fallback(self, x, y, screenshot_shape=None):
        try:
            device = getattr(self.window_controller, "device", None)
            if device is None:
                return False
            target_x = x
            target_y = y
            if screenshot_shape is not None:
                frame_h, frame_w = screenshot_shape[:2]
                size = device.window_size()
                target_x = x * (size.width / max(1, frame_w))
                target_y = y * (size.height / max(1, frame_h))
            device.shell(f"input tap {int(target_x)} {int(target_y)}")
            return True
        except Exception as e:
            print(f"ADB fallback tap failed: {e}")
            return False

    def do_state(self, state, data=None):
        if not str(state).startswith("end"):
            self.active_end_result = None
        if data is not None:
            self.states[state](data)
            return
        self.states[state]()
