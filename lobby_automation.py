from difflib import SequenceMatcher
import time

import cv2
import numpy as np

from state_finder import get_state, is_starr_nova_hub_screen, get_starr_nova_hub_back_button_center
from utils import (
    extract_text_and_positions,
    extract_all_text_boxes,
    extract_text_strings,
    count_hsv_pixels,
    load_toml_as_dict,
    load_brawlers_info,
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

    def _dismiss_starr_nova_hub_if_present(self, max_attempts=3):
        dismissed = False
        for _ in range(max_attempts):
            screenshot = self.window_controller.screenshot()
            if screenshot is None:
                break
            screenshot_bgr = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
            if not is_starr_nova_hub_screen(screenshot_bgr):
                break
            back_center = get_starr_nova_hub_back_button_center(screenshot_bgr)
            if back_center is None:
                break
            print("Starr Nova hub open during brawler selection; clicking back.")
            self.window_controller.keys_up(list("wasd"))
            self.window_controller.click(*back_center, delay=0.08)
            time.sleep(0.8)
            dismissed = True
        return dismissed

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

        self._dismiss_starr_nova_hub_if_present()

        state = self._read_state()
        if state == "brawler_selection":
            return True
        if state == "shop" and self.is_probably_brawler_selection_screen():
            return True

        if state == "lobby" and self.click_visible_brawler_menu_button():
            time.sleep(0.8)
            self._dismiss_starr_nova_hub_if_present()
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
            screenshot = self.window_controller.screenshot()
            nova_hub = False
            if screenshot is not None:
                nova_hub = is_starr_nova_hub_screen(cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR))
            if nova_hub:
                self._dismiss_starr_nova_hub_if_present()
                state = self._read_state()
                continue
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

    @staticmethod
    def _select_button_words():
        return {"select", "selegt", "selec", "selct", "selert"}

    def _grid_region_bounds(self, full_h, full_w):
        # Brawler cards start around x=420 on a 1920-wide reference screen.
        return (
            int(full_w * 0.17),
            int(full_h * 0.12),
            int(full_w * 0.995),
            int(full_h * 0.92),
        )

    def _map_ocr_box_to_full_screen(self, box, ocr_scale, x0, y0):
        mapped = {}
        for corner in ("top_left", "top_right", "bottom_left", "bottom_right"):
            if corner in box:
                px, py = box[corner]
                mapped[corner] = (px / ocr_scale + x0, py / ocr_scale + y0)
        cx, cy = box["center"]
        mapped["center"] = (cx / ocr_scale + x0, cy / ocr_scale + y0)
        return mapped

    def _run_easyocr_on_brawler_grid(self, screenshot_full, ocr_scale):
        full_h, full_w = screenshot_full.shape[:2]
        x0, y0, x1, y1 = self._grid_region_bounds(full_h, full_w)
        crop = screenshot_full[y0:y1, x0:x1]
        scaled = cv2.resize(
            crop,
            (max(1, int(crop.shape[1] * ocr_scale)), max(1, int(crop.shape[0] * ocr_scale))),
            interpolation=cv2.INTER_CUBIC if ocr_scale > 1.0 else cv2.INTER_AREA,
        )
        entries = []
        for item in extract_all_text_boxes(scaled):
            entries.append({
                "text": item["text"],
                "confidence": item["confidence"],
                "box": self._map_ocr_box_to_full_screen(item["box"], ocr_scale, x0, y0),
            })
        return entries

    def _is_probable_grid_label(self, text_box, full_h, full_w):
        cx, cy = text_box["center"]
        gx0, gy0, gx1, gy1 = self._grid_region_bounds(full_h, full_w)
        return gx0 <= cx <= gx1 and gy0 <= cy <= gy1

    @classmethod
    def _is_confident_grid_name_match(cls, detected_name, target_name):
        if detected_name == target_name:
            return True
        if len(target_name) <= 3:
            return False
        return cls.names_match(detected_name, target_name)

    def _collect_easyocr_grid_matches(self, screenshot_full, target_key, ocr_scale, debug_enabled=False):
        entries = self._run_easyocr_on_brawler_grid(screenshot_full, ocr_scale)
        if debug_enabled:
            print(
                "EasyOCR grid texts:",
                [f"{entry['text']} ({entry['confidence']:.2f})" for entry in entries],
            )
        full_h, full_w = screenshot_full.shape[:2]
        matches = []
        for entry in entries:
            detected_name = self.resolve_ocr_typos(self.normalize_ocr_name(entry["text"]))
            if not self._is_confident_grid_name_match(detected_name, target_key):
                continue
            if not self._is_probable_grid_label(entry["box"], full_h, full_w):
                continue
            score = self.name_match_score(detected_name, target_key) + min(entry["confidence"], 0.99) * 0.05
            matches.append((score, detected_name, entry["box"], entry["text"]))
        matches.sort(key=lambda item: (-item[0], item[2]["center"][1], item[2]["center"][0]))
        return matches

    def _text_box_click_position(self, text_box, full_h, full_w, lift_factor=2.8):
        cx, cy = text_box["center"]
        click_x = int(cx)

        top_left = text_box.get("top_left")
        bottom_left = text_box.get("bottom_left")
        if top_left is not None and bottom_left is not None:
            top_right = text_box.get("top_right", top_left)
            bottom_right = text_box.get("bottom_right", bottom_left)
            tl_y = min(top_left[1], top_right[1])
            bl_y = max(bottom_left[1], bottom_right[1])
            label_h = max(bl_y - tl_y, full_h * 0.018)
            click_y = int(tl_y - label_h * lift_factor)
            click_y = max(int(full_h * 0.08), min(full_h - 1, click_y))
            return click_x, click_y

        click_y = int(cy - full_h * 0.09)
        click_y = max(0, min(full_h - 1, click_y))
        return click_x, click_y

    def _press_select_button(self):
        select_x, select_y = self.coords_cfg["lobby"]["select_btn"][0], self.coords_cfg["lobby"]["select_btn"][1]
        self.window_controller.click(select_x, select_y, already_include_ratio=False)

    def _attempt_easyocr_pick(self, brawler, target_key, screenshot_full, matches, debug_enabled=False):
        full_h, full_w = screenshot_full.shape[:2]
        lift_factors = (2.8, 3.5, 2.2, 4.0)
        opened_detail = False

        for _, detected_name, text_box, raw_text in matches[:3]:
            for lift_factor in lift_factors:
                if opened_detail:
                    self.press_back()
                    time.sleep(0.5)

                click_x, click_y = self._text_box_click_position(
                    text_box,
                    full_h,
                    full_w,
                    lift_factor=lift_factor,
                )
                self.window_controller.click(click_x, click_y)
                print(
                    f"EasyOCR found {raw_text!r} for {brawler}; "
                    f"clicking ({click_x}, {click_y}), lift={lift_factor}"
                )
                time.sleep(1.0)

                verify_screenshot = self.window_controller.screenshot()
                verify_state = get_state(verify_screenshot)
                card_is_open = verify_state in ("brawler_selection", "shop")
                if not card_is_open:
                    card_is_open = self._select_button_visible(verify_screenshot)
                    if card_is_open and debug_enabled:
                        print(f"Brawler card detected by EasyOCR SELECT text (state was {verify_state}).")

                if not card_is_open:
                    if debug_enabled:
                        print(f"Brawler card did not open after tap (state={verify_state}).")
                    continue

                opened_detail = True
                if self._verify_brawler_detail_card(verify_screenshot, target_key):
                    self._press_select_button()
                    time.sleep(0.5)
                    print(f"Selected brawler {brawler}")
                    return True

                card_texts = self._detail_card_texts(verify_screenshot)
                print(
                    f"EasyOCR detail texts {card_texts} did not confirm '{brawler}' "
                    f"(matched label {detected_name!r})."
                )

        if opened_detail:
            self.press_back()
            time.sleep(0.5)
        return False

    def _select_button_visible(self, screenshot):
        full_h = screenshot.shape[0]
        bottom = screenshot[int(full_h * 0.82):, :]
        try:
            texts = extract_text_strings(bottom)
        except Exception:
            return False
        select_words = self._select_button_words()
        return any(self.normalize_ocr_name(text) in select_words for text in texts)

    def _detail_card_texts(self, screenshot):
        full_h, full_w = screenshot.shape[:2]
        detail_regions = (
            (0.04, 0.38, 0.0, 0.72),
            (0.10, 0.62, 0.0, 0.52),
            (0.0, 0.25, 0.0, 1.0),
        )
        texts = []
        for y0, y1, x0, x1 in detail_regions:
            crop = screenshot[
                int(full_h * y0):int(full_h * y1),
                int(full_w * x0):int(full_w * x1),
            ]
            try:
                texts.extend(extract_text_strings(crop))
            except Exception:
                continue
        return texts

    def _verify_brawler_detail_card(self, screenshot, target_key):
        texts = self._detail_card_texts(screenshot)
        for text in texts:
            normalized = self.resolve_ocr_typos(self.normalize_ocr_name(text))
            if self.names_match(normalized, target_key):
                return True

        if not self._select_button_visible(screenshot):
            return False

        for text in texts:
            normalized = self.resolve_ocr_typos(self.normalize_ocr_name(text))
            if normalized in self.known_brawler_names and not self.names_match(normalized, target_key):
                return False

        return True

    def _dismiss_open_detail_card(self):
        screenshot = self.window_controller.screenshot()
        if screenshot is None:
            return False
        if self._select_button_visible(screenshot):
            self.press_back()
            time.sleep(0.55)
            return True
        return False

    def _wait_for_grid_settle(self, stable_frames=1, delay=0.1, diff_threshold=6.5, timeout=0.9):
        previous = None
        stable = 0
        deadline = time.time() + timeout
        while time.time() < deadline and stable < stable_frames:
            frame = self.window_controller.screenshot()
            if frame is None:
                time.sleep(delay)
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            crop = gray[int(frame.shape[0] * 0.16):int(frame.shape[0] * 0.92), :]
            if previous is not None:
                diff = float(np.mean(cv2.absdiff(previous, crop)))
                if diff <= diff_threshold:
                    stable += 1
                else:
                    stable = 0
            previous = crop
            time.sleep(delay)

    def _scroll_brawler_grid(self, wr, hr):
        scroll_x = int(320 * wr)
        start_y = int(790 * hr)
        end_y = int(570 * hr)
        self.window_controller.swipe(scroll_x, start_y, scroll_x, end_y, duration=0.28)
        self._wait_for_grid_settle()

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
        grid_ocr_scale = max(ocr_scale, 0.75)
        target_key = self.normalize_ocr_name(brawler)
        target_key = self.resolve_ocr_typos(target_key)

        if not self.open_brawler_selection():
            print(f"WARNING: Could not open brawler selection menu for '{brawler}'. "
                  "Continuing with the currently selected brawler instead of crashing.")
            self.press_back()
            return False

        same_screen_attempts = 0
        max_same_screen_attempts = 3
        for _scroll in range(50):
            self._dismiss_open_detail_card()

            screenshot_full = self.window_controller.screenshot()
            matches = self._collect_easyocr_grid_matches(
                screenshot_full,
                target_key,
                grid_ocr_scale,
                debug_enabled=debug_enabled,
            )

            if matches:
                if self._attempt_easyocr_pick(
                    brawler,
                    target_key,
                    screenshot_full,
                    matches,
                    debug_enabled=debug_enabled,
                ):
                    return True

                same_screen_attempts += 1
                if same_screen_attempts < max_same_screen_attempts:
                    print(
                        f"EasyOCR found {brawler} on screen; retrying pick "
                        f"({same_screen_attempts}/{max_same_screen_attempts}) before scrolling."
                    )
                    time.sleep(0.2)
                    continue

                print(
                    f"Could not pick {brawler} after {max_same_screen_attempts} EasyOCR attempts; scrolling."
                )
                same_screen_attempts = 0
            else:
                same_screen_attempts = 0
                if debug_enabled:
                    print(f"EasyOCR did not find '{brawler}' on the current brawler grid page.")

            wr = self.window_controller.width_ratio
            hr = self.window_controller.height_ratio
            self._scroll_brawler_grid(wr, hr)

        print(f"WARNING: Brawler '{brawler}' was not found after 50 scroll attempts. "
              f"The bot will continue with the currently selected brawler.")
        return False

    def select_highest_trophy_brawler(self):
        wr = self.window_controller.width_ratio
        hr = self.window_controller.height_ratio

        def tap(x, y, wait=0.6):
            self.window_controller.click(int(x * wr), int(y * hr))
            time.sleep(wait)

        print("Selecting next brawler by sorting most trophies.")
        self._dismiss_starr_nova_hub_if_present()
        tap(128, 500, 1.4)   # left Brawlers button in lobby
        self._dismiss_starr_nova_hub_if_present()
        tap(1210, 45, 0.6)   # sort dropdown
        tap(1210, 368, 1.0)  # Most Trophies
        tap(422, 359, 1.0)   # first brawler card after sorting
        tap(260, 991, 1.0)   # Select
        if self.ensure_lobby_after_selection():
            return True

        print("Highest-trophy brawler selection did not return to lobby; trying one recovery pass.")
        self.press_back()
        time.sleep(0.8)
        tap(260, 991, 1.0)   # Select again if the brawler details screen is still open
        return self.ensure_lobby_after_selection()

    def select_lowest_trophy_brawler(self):
        """Legacy alias kept for older saved queues."""
        return self.select_highest_trophy_brawler()

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
