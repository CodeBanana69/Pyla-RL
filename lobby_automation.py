from difflib import SequenceMatcher
import time

import cv2
import numpy as np

from state_finder import get_state
from utils import (
    extract_text_and_positions,
    extract_text_strings,
    count_hsv_pixels,
    load_toml_as_dict,
    load_brawlers_info,
    find_template_center,
    resolve_brawler_name_alias,
)

debug = load_toml_as_dict("cfg/general_config.toml")['super_debug'] == "yes"
gray_pixels_treshold = load_toml_as_dict("./cfg/bot_config.toml")['idle_pixels_minimum']
class LobbyAutomation:

    def __init__(self, window_controller):
        self.coords_cfg = load_toml_as_dict("./cfg/lobby_config.toml")
        self.window_controller = window_controller
        self.known_brawler_names = self._load_known_brawler_names()

    def _read_state(self):
        try:
            screenshot = self.window_controller.screenshot()
            if screenshot is None:
                return None
            return get_state(screenshot)
        except Exception as e:
            if debug:
                print(f"Could not read state while opening brawler menu: {e}")
            return None

    def open_brawler_selection(self, attempts=None):
        wr = self.window_controller.width_ratio
        hr = self.window_controller.height_ratio
        # Keep these clicks in the left-side BRAWLERS button band. Different
        # emulator scales and event layouts shift the safe center a bit; points
        # that are too low can open the pass/event panels instead.
        cfg_point = tuple(self.coords_cfg.get("lobby", {}).get("brawler_btn", (110, 490)))
        brawler_button_points = (
            (70, 500),
            (90, 500),
            (110, 490),
            (128, 500),
            (60, 535),
            (145, 505),
            cfg_point,
            (76, 420),
            (98, 420),
            (122, 420),
            (72, 455),
            (100, 455),
            (132, 455),
            (82, 385),
            (112, 385),
        )
        if attempts is None:
            attempts = len(brawler_button_points)

        state = self._read_state()
        if state == "brawler_selection":
            return True
        if state == "shop" and self.is_probably_brawler_selection_screen():
            return True

        if state == "lobby" and self.click_visible_brawler_menu_button():
            time.sleep(0.8)
            state = self._read_state()
            if state == "brawler_selection":
                return True
            if state == "shop" and self.is_probably_brawler_selection_screen():
                return True

        for attempt in range(attempts):
            if state == "shop":
                if self.is_probably_brawler_selection_screen():
                    return True
                print("Brawler menu click opened a lobby panel; backing out and retrying Brawlers.")
                self.press_back()
                time.sleep(0.8)
                state = self._read_state()
                if state == "brawler_selection":
                    return True
                if state == "shop" and self.is_probably_brawler_selection_screen():
                    return True
                if state == "lobby" and self.click_visible_brawler_menu_button():
                    time.sleep(0.8)
                    state = self._read_state()
                    if state == "brawler_selection":
                        return True
                    if state == "shop" and self.is_probably_brawler_selection_screen():
                        return True

            x, y = brawler_button_points[min(attempt, len(brawler_button_points) - 1)]
            self.window_controller.click(int(x * wr), int(y * hr))
            time.sleep(0.8)

            state = self._read_state()
            if state == "brawler_selection":
                return True
            if state == "shop" and self.is_probably_brawler_selection_screen():
                return True
            if state == "shop":
                continue
            if state is None:
                # Some tests/controllers cannot provide a state image here. Let
                # the OCR loop continue instead of failing selection up front.
                return True

        return False

    @staticmethod
    def _load_known_brawler_names():
        try:
            return {
                LobbyAutomation.normalize_ocr_name(name)
                for name in load_brawlers_info().keys()
                if name
            }
        except Exception:
            return set()

    def is_probably_brawler_selection_screen(self, screenshot=None):
        try:
            if screenshot is None:
                screenshot = self.window_controller.screenshot()
            if screenshot is None:
                return False
            results = extract_text_and_positions(screenshot)
        except Exception:
            return False

        known_names = getattr(self, "known_brawler_names", None)
        if known_names is None:
            known_names = self._load_known_brawler_names()
            self.known_brawler_names = known_names

        normalized_texts = {
            self.resolve_ocr_typos(self.normalize_ocr_name(text))
            for text in results.keys()
        }
        known_hits = len(normalized_texts & known_names)
        selection_words = {
            "brawlers",
            "brawler",
            "sortby",
            "leasttrophies",
            "mosttrophies",
            "trophies",
            "locked",
            "upgrade",
        }
        selection_word_hits = len(normalized_texts & selection_words)

        # Brawl Pass/shop panels can also be classified as "shop", but the
        # brawler selector exposes a grid/list of real brawler names. Trust OCR
        # only when it sees enough of that grid, so a single offer name does not
        # bypass the retry/back-out recovery.
        return known_hits >= 2 or (known_hits >= 1 and selection_word_hits >= 1)

    def click_visible_brawler_menu_button(self):
        try:
            screenshot = self.window_controller.screenshot()
            if screenshot is None:
                return False
            results = extract_text_and_positions(screenshot)
        except Exception:
            return False

        for text, box in results.items():
            normalized = self.normalize_ocr_name(text)
            if normalized not in {"brawlers", "brawler"}:
                continue
            center = box.get("center")
            if not center:
                continue
            x, y = center
            if x > screenshot.shape[1] * 0.35:
                continue
            self.window_controller.click(int(x), int(y))
            return True
        return False

    def check_for_idle(self, frame):
        general_config = load_toml_as_dict("cfg/general_config.toml")
        bot_config = load_toml_as_dict("./cfg/bot_config.toml")
        debug_enabled = str(general_config.get("super_debug", "no")).lower() in ("yes", "true", "1")
        gray_pixels_threshold = bot_config.get("idle_pixels_minimum", gray_pixels_treshold)
        wr = self.window_controller.width_ratio
        hr = self.window_controller.height_ratio
        # Tight ROI centered on the Idle Disconnect dialog body, so we don't
        # pick up dark gameplay pixels outside the box. V range is wide enough
        # to cover both LDPlayer (bright overlay, V~82) and MuMu (dark overlay, V~28).
        x_start, x_end = int(700 * wr), int(1220 * wr)
        y_start, y_end = int(470 * hr), int(620 * hr)
        gray_pixels = count_hsv_pixels(frame[y_start:y_end, x_start:x_end], (0, 0, 18), (10, 20, 100))
        if debug_enabled: print(f"gray pixels (if > {gray_pixels_threshold} then bot will try to unidle) :", gray_pixels)
        if gray_pixels > gray_pixels_threshold:
            self.window_controller.click(int(535 * wr), int(615 * hr))

    def select_brawler(self, brawler):
        self.window_controller.screenshot()
        wr = self.window_controller.width_ratio
        hr = self.window_controller.height_ratio
        general_config = load_toml_as_dict("cfg/general_config.toml")
        debug_enabled = str(general_config.get("super_debug", "no")).lower() in ("yes", "true", "1")
        try:
            ocr_scale = float(general_config.get("ocr_scale_down_factor", 0.65))
        except (TypeError, ValueError):
            ocr_scale = 0.65
        ocr_scale = max(0.35, min(1.0, ocr_scale))
        target_key = self.normalize_ocr_name(brawler)

        if not self.open_brawler_selection():
            print(f"WARNING: Could not open brawler selection menu for '{brawler}'. "
                  "Continuing with the currently selected brawler instead of crashing.")
            self.press_back()
            return False
        c = 0
        found_brawler = False
        for i in range(50):
            screenshot_full = self.window_controller.screenshot()
            full_h = screenshot_full.shape[0]
            screenshot = cv2.resize(
                screenshot_full,
                (int(screenshot_full.shape[1] * ocr_scale), int(screenshot_full.shape[0] * ocr_scale)),
                interpolation=cv2.INTER_AREA,
            )

            if debug_enabled: print("extracting text on current screen...")
            results = extract_text_and_positions(screenshot)
            reworked_results = {}
            for key in results.keys():
                orig_key = key
                key = self.normalize_ocr_name(key)
                key = self.resolve_ocr_typos(key)
                reworked_results[key] = results[orig_key]
            if debug_enabled:
                print("All detected text while looking for brawler name:", reworked_results.keys())
                print()
            matches = []
            for detected_name, text_box in reworked_results.items():
                if self.names_match(detected_name, target_key):
                    score = self.name_match_score(detected_name, target_key)
                    matches.append((score, detected_name, text_box))
            if matches:
                matches.sort(key=lambda item: item[0], reverse=True)
                _, detected_name, text_box = matches[0]
                x, y = text_box['center']
                click_x = int(x / ocr_scale)
                # EasyOCR returns the text label center, not the card/icon center.
                # Tapping above the label avoids selecting the brawler in the row below.
                y_offset = int(full_h * 0.088)
                click_y = int((y / ocr_scale) - y_offset)
                click_y = max(0, min(full_h - 1, click_y))
                self.window_controller.click(click_x, click_y)
                print(f"Found brawler {brawler} (OCR: {detected_name}) clicking icon at ({click_x}, {click_y}), y_offset={y_offset}")
                time.sleep(1.0)

                verify_screenshot = self.window_controller.screenshot()
                verify_state = get_state(verify_screenshot)
                card_is_open = verify_state in ("brawler_selection", "shop")
                if not card_is_open:
                    try:
                        select_words = {"select", "selegt", "selec", "selct", "selert"}
                        card_is_open = any(
                            self.normalize_ocr_name(text) in select_words
                            for text in extract_text_strings(verify_screenshot)
                        )
                        if card_is_open:
                            print(f"Brawler card detected by SELECT text (state was {verify_state}).")
                    except Exception:
                        pass

                if not card_is_open:
                    print(f"Brawler card did not open after tap (state={verify_state}); retrying without scrolling.")
                    time.sleep(0.5)
                    continue

                card_crop = verify_screenshot[
                    int(full_h * 0.05):int(full_h * 0.22),
                    0:verify_screenshot.shape[1],
                ]
                try:
                    card_texts = extract_text_strings(card_crop)
                except Exception:
                    card_texts = []
                card_name_match = any(
                    self.names_match(self.normalize_ocr_name(text), target_key)
                    for text in card_texts
                ) if card_texts else True

                if not card_name_match:
                    print(f"Card OCR shows {card_texts} but expected '{brawler}'; re-tapping with adjusted offset.")
                    self.press_back()
                    time.sleep(0.5)
                    click_y = int((y / ocr_scale) - int(full_h * 0.04))
                    click_y = max(0, min(full_h - 1, click_y))
                    self.window_controller.click(click_x, click_y)
                    time.sleep(1.0)

                select_x, select_y = self.coords_cfg['lobby']['select_btn'][0], self.coords_cfg['lobby']['select_btn'][1]
                self.window_controller.click(select_x, select_y, already_include_ratio=False)
                time.sleep(0.5)
                print(f"Selected brawler {brawler}")
                found_brawler = True
                break
            if c == 0:
                wr = self.window_controller.width_ratio
                hr = self.window_controller.height_ratio
                self.window_controller.swipe(int(1700 * wr), int(900 * hr), int(1700 * wr), int(850 * hr), duration=0.8)
                c += 1
                continue

            self.window_controller.swipe(int(1700 * wr), int(900 * hr), int(1700 * wr), int(650 * hr), duration=0.8)
            time.sleep(1)
        if not found_brawler:
            print(f"WARNING: Brawler '{brawler}' was not found after 50 scroll attempts. "
                  f"The bot will continue with the currently selected brawler.")
            return False
        return True

    def select_lowest_trophy_brawler(self):
        wr = self.window_controller.width_ratio
        hr = self.window_controller.height_ratio

        def tap(x, y, wait=0.6):
            self.window_controller.click(int(x * wr), int(y * hr))
            time.sleep(wait)

        print("Selecting next brawler by sorting lowest trophies.")
        tap(128, 500, 1.4)   # left Brawlers button in lobby
        tap(1210, 45, 0.6)   # sort dropdown
        tap(1210, 426, 1.0)  # Least Trophies
        tap(422, 359, 1.0)   # first brawler card after sorting
        tap(260, 991, 1.0)   # Select
        if self.ensure_lobby_after_selection():
            return True

        print("Lowest-trophy brawler selection did not return to lobby; trying one recovery pass.")
        self.press_back()
        time.sleep(0.8)
        tap(260, 991, 1.0)   # Select again if the brawler details screen is still open
        return self.ensure_lobby_after_selection()

    def ensure_lobby_after_selection(self, timeout=6.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                state = get_state(self.window_controller.screenshot())
            except Exception as e:
                print(f"Could not verify lobby after brawler selection: {e}")
                return False
            if state == "lobby":
                return True
            if state == "brawler_selection":
                # The card opened but Select may not have registered yet.
                self.window_controller.click(
                    int(260 * self.window_controller.width_ratio),
                    int(991 * self.window_controller.height_ratio),
                )
            elif state == "match":
                # Immediately after selecting a brawler, "match" usually means
                # an unrecognized brawler details/stats screen, not a real game.
                self.press_back()
            time.sleep(0.7)
        return False

    def press_back(self):
        if hasattr(self.window_controller, "android_back") and self.window_controller.android_back():
            return
        self.window_controller.click(
            int(100 * self.window_controller.width_ratio),
            int(60 * self.window_controller.height_ratio),
        )

    @staticmethod
    def resolve_ocr_typos(potential_brawler_name: str) -> str:
        """
        Matches well known 'typos' from OCR to the correct brawler's name
        or returns the original string
        """

        return resolve_brawler_name_alias(potential_brawler_name)

    @staticmethod
    def normalize_ocr_name(value: str) -> str:
        normalized = str(value).lower()
        for symbol in [' ', '-', '.', "&", "'", "`", "_"]:
            normalized = normalized.replace(symbol, "")
        return normalized

    @staticmethod
    def bounded_edit_distance(left: str, right: str, limit: int) -> int:
        if abs(len(left) - len(right)) > limit:
            return limit + 1
        previous = list(range(len(right) + 1))
        for i, left_char in enumerate(left, 1):
            current = [i]
            best = current[0]
            for j, right_char in enumerate(right, 1):
                cost = 0 if left_char == right_char else 1
                value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
                current.append(value)
                best = min(best, value)
            if best > limit:
                return limit + 1
            previous = current
        return previous[-1]

    @classmethod
    def names_match(cls, detected_name: str, target_name: str) -> bool:
        if detected_name == target_name:
            return True
        if len(target_name) >= 4 and (target_name in detected_name or detected_name in target_name):
            return True
        limit = 1 if len(target_name) <= 5 else 2
        if cls.bounded_edit_distance(detected_name, target_name, limit) <= limit:
            return True
        return SequenceMatcher(None, detected_name, target_name).ratio() >= 0.84

    @classmethod
    def name_match_score(cls, detected_name: str, target_name: str) -> float:
        if detected_name == target_name:
            return 2.0
        ratio = SequenceMatcher(None, detected_name, target_name).ratio()
        distance = cls.bounded_edit_distance(detected_name, target_name, 3)
        return ratio - (distance * 0.05)
