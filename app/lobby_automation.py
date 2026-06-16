from difflib import SequenceMatcher
import time

import cv2
import numpy as np

from state_finder import (
    get_state,
    get_starr_nova_hub_back_button_center,
    is_in_brawl_pass,
    is_in_brawler_selection,
    is_in_star_road,
    is_starr_nova_hub_screen,
)
from utils import (
    extract_text_and_positions,
    extract_all_text_boxes,
    extract_text_strings,
    count_hsv_pixels,
    load_toml_as_dict,
    load_brawlers_info,
    normalize_brawler_name,
    resolve_brawler_name_alias,
    resolve_project_path,
)

debug = load_toml_as_dict("cfg/general_config.toml")['super_debug'] == "yes"
gray_pixels_treshold = load_toml_as_dict("./cfg/bot_config.toml")['idle_pixels_minimum']
GRID_OCR_MIN_CONFIDENCE = 0.2


class LobbyAutomation:

    def __init__(self, window_controller):
        self.coords_cfg = load_toml_as_dict("./cfg/lobby_config.toml")
        self.window_controller = window_controller
        self.known_brawler_names = self._load_known_brawler_names()
        self.selecting_brawler = False

    def _timing(self, key, default):
        section = self.coords_cfg.get("lobby_timing") or {}
        try:
            return float(section.get(key, default))
        except (TypeError, ValueError):
            return default

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

    def _screenshot_bgr(self, screenshot=None):
        if screenshot is None:
            screenshot = self.window_controller.screenshot()
        if screenshot is None:
            return None
        return cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)

    def _confirm_brawler_menu_open(self, screenshot=None):
        screenshot_bgr = self._screenshot_bgr(screenshot)
        if screenshot_bgr is None:
            return False
        if is_starr_nova_hub_screen(screenshot_bgr):
            return False
        return is_in_brawler_selection(screenshot_bgr)

    def _dismiss_starr_nova_hub_if_present(self, max_attempts=5):
        dismissed = False
        for _ in range(max_attempts):
            screenshot = self.window_controller.screenshot()
            if screenshot is None:
                break
            screenshot_bgr = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
            if not is_starr_nova_hub_screen(screenshot_bgr):
                break
            back_center = get_starr_nova_hub_back_button_center(screenshot_bgr)
            print("Starr Nova hub open during brawler selection; backing out.")
            self.window_controller.keys_up(list("wasd"))
            if back_center is not None:
                self.window_controller.click(*back_center, delay=0.08)
            else:
                self.press_back()
            time.sleep(self._timing("starr_nova_dismiss_delay", 0.35))
            dismissed = True
        return dismissed

    def _brawlers_label_click_is_safe(self, x, y, screenshot):
        height, width = screenshot.shape[:2]
        if width <= 0 or height <= 0:
            return False
        if x > width * 0.22:
            return False
        y_on_1080 = y * (1080.0 / height)
        # Keep OCR clicks above the bottom-left Brawl Pass banner band.
        return 360.0 <= y_on_1080 <= 500.0

    def _is_pass_panel(self, screenshot_bgr):
        if screenshot_bgr is None:
            return False
        return is_in_brawl_pass(screenshot_bgr) or is_in_star_road(screenshot_bgr)

    def _back_out_of_lobby_panel(self):
        self.press_back()
        time.sleep(self._timing("back_panel_delay", 0.35))

    def _brawler_button_points(self):
        cfg_x, cfg_y = tuple(self.coords_cfg.get("lobby", {}).get("brawler_btn", (110, 490)))
        if cfg_y < 400:
            cfg_x, cfg_y = cfg_x, 430
        return (
            (96, 430),
            (112, 420),
            (122, 420),
            (132, 455),
            (100, 455),
            (98, 420),
            (76, 420),
            (cfg_x, cfg_y),
            (110, 490),
            (128, 500),
        )

    def _ensure_lobby_before_brawler_click(self, max_attempts=4):
        for _ in range(max_attempts):
            state = self._read_state()
            screenshot = self.window_controller.screenshot()
            if state in (None, "lobby"):
                return True
            if state == "brawler_selection" or self._confirm_brawler_menu_open(screenshot):
                return True
            if state == "shop" and self.is_probably_brawler_selection_screen(screenshot):
                return True
            self._back_out_of_lobby_panel()
        return self._read_state() in (None, "lobby")

    def _try_open_brawler_via_ocr(self):
        if not self.click_visible_brawler_menu_button():
            return False
        time.sleep(self._timing("menu_open_delay", 0.35))
        self._dismiss_starr_nova_hub_if_present()
        state = self._read_state()
        if state == "brawler_selection" or self._confirm_brawler_menu_open():
            return True
        if state == "shop" and self.is_probably_brawler_selection_screen():
            return True
        if state == "shop":
            self._back_out_of_lobby_panel()
        return False

    def open_brawler_selection(self, attempts=None):
        wr = self.window_controller.width_ratio
        hr = self.window_controller.height_ratio
        brawler_button_points = self._brawler_button_points()
        if attempts is None:
            attempts = len(brawler_button_points)
        menu_retry_delay = self._timing("menu_retry_delay", 0.35)

        self._dismiss_starr_nova_hub_if_present()

        state = self._read_state()
        if state == "brawler_selection" or self._confirm_brawler_menu_open():
            return True
        if state == "shop" and self.is_probably_brawler_selection_screen():
            return True
        if state == "shop":
            self._back_out_of_lobby_panel()
            state = self._read_state()

        if state in (None, "lobby") and self._try_open_brawler_via_ocr():
            return True

        for attempt in range(attempts):
            if not self._ensure_lobby_before_brawler_click():
                continue

            x, y = brawler_button_points[min(attempt, len(brawler_button_points) - 1)]
            click_x = int(x * wr)
            click_y = int(y * hr)
            self.window_controller.click(click_x, click_y)
            time.sleep(menu_retry_delay)

            state = self._read_state()
            screenshot = self.window_controller.screenshot()
            screenshot_bgr = self._screenshot_bgr(screenshot)
            nova_hub = screenshot_bgr is not None and is_starr_nova_hub_screen(screenshot_bgr)
            brawler_open = self._confirm_brawler_menu_open(screenshot)
            probably_brawler = self.is_probably_brawler_selection_screen(screenshot)
            if nova_hub:
                self._dismiss_starr_nova_hub_if_present()
                continue
            if brawler_open or state == "brawler_selection":
                return True
            if state == "shop" and probably_brawler:
                return True
            if state == "shop":
                time.sleep(self._timing("menu_open_delay", 0.35))
                if self._confirm_brawler_menu_open():
                    return True
                if self.is_probably_brawler_selection_screen():
                    return True
                panel_kind = "pass" if self._is_pass_panel(screenshot_bgr) else "shop"
                print(
                    f"Brawler menu click opened lobby {panel_kind} panel; "
                    "backing out and retrying Brawlers."
                )
                self._back_out_of_lobby_panel()
                continue
            if state is None:
                continue

        if self._read_state() in (None, "lobby") and self._try_open_brawler_via_ocr():
            return True

        return False

    @staticmethod
    def _load_known_brawler_names():
        try:
            names = {
                LobbyAutomation.normalize_ocr_name(name)
                for name in load_brawlers_info().keys()
                if name
            }
            from utils import load_brawler_name_aliases

            load_brawler_name_aliases()
            try:
                import json
                from pathlib import Path

                raw_aliases = json.loads(
                    Path(resolve_project_path("cfg/names.json")).read_text(encoding="utf-8")
                )
            except Exception:
                raw_aliases = {}
            for canonical, aliases in raw_aliases.items():
                if canonical:
                    names.add(LobbyAutomation.normalize_ocr_name(canonical))
                if isinstance(aliases, list):
                    for alias in aliases:
                        if alias:
                            names.add(LobbyAutomation.normalize_ocr_name(alias))
            return names
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
            if not self._brawlers_label_click_is_safe(x, y, screenshot):
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

    @staticmethod
    def _ocr_digit_fixes():
        return str.maketrans({
            "0": "o",
            "1": "l",
            "8": "b",
            "5": "s",
            "|": "l",
        })

    def _normalize_grid_label(self, raw_text):
        normalized = self.resolve_ocr_typos(self.normalize_ocr_name(raw_text))
        normalized = self._ocr_name_from_brawler_ref(normalized)
        if len(normalized) <= 8:
            fixed = normalized.translate(self._ocr_digit_fixes())
            fixed = self.resolve_ocr_typos(fixed)
            fixed = self._ocr_name_from_brawler_ref(fixed)
            if fixed in self.known_brawler_names:
                return fixed
        return normalized

    def _detected_name_closer_to_other_brawler(self, detected_name, target_name):
        known = getattr(self, "known_brawler_names", None)
        if not known:
            return False
        target_norm = normalize_brawler_name(target_name)
        target_score = self.name_match_score(detected_name, target_name)
        for known_name in known:
            if known_name == target_name:
                continue
            if normalize_brawler_name(known_name) == target_norm:
                continue
            if self.name_match_score(detected_name, known_name) > target_score + 0.08:
                return True
        return False

    def _is_confident_grid_name_match(self, detected_name, target_name):
        if not self.names_match(detected_name, target_name):
            return False
        return not self._detected_name_closer_to_other_brawler(detected_name, target_name)

    @staticmethod
    def _grid_page_signature(entries):
        labels = [str(entry.get("text", "")).strip().lower() for entry in entries if entry.get("text")]
        return tuple(sorted(labels[:24]))

    @staticmethod
    def _is_brawler_grid_end(ocr_labels):
        blob = LobbyAutomation.normalize_ocr_name(" ".join(ocr_labels))
        return "comingsoon" in blob or "brawlerscoming" in blob

    def _collect_easyocr_grid_matches(self, screenshot_full, target_key, ocr_scale, debug_enabled=False, entries=None):
        if entries is None:
            entries = self._run_easyocr_on_brawler_grid(screenshot_full, ocr_scale)
        if debug_enabled:
            print(
                "EasyOCR grid texts:",
                [f"{entry['text']} ({entry['confidence']:.2f})" for entry in entries],
            )
        full_h, full_w = screenshot_full.shape[:2]
        matches = []
        for entry in entries:
            raw_text = str(entry.get("text", "")).strip()
            if not raw_text:
                continue
            if float(entry.get("confidence", 0) or 0) < GRID_OCR_MIN_CONFIDENCE:
                continue
            detected_name = self._normalize_grid_label(raw_text)
            if not detected_name:
                continue
            if not self._is_confident_grid_name_match(detected_name, target_key):
                continue
            if not self._is_probable_grid_label(entry["box"], full_h, full_w):
                continue
            score = self.name_match_score(detected_name, target_key) + min(entry["confidence"], 0.99) * 0.05
            matches.append((score, detected_name, entry["box"], entry["text"]))

        if not matches and len(target_key) <= 6:
            for entry in entries:
                raw_text = str(entry.get("text", "")).strip()
                if not raw_text:
                    continue
                if float(entry.get("confidence", 0) or 0) < GRID_OCR_MIN_CONFIDENCE:
                    continue
                detected_name = self._normalize_grid_label(raw_text)
                if not detected_name:
                    continue
                if self.bounded_edit_distance(detected_name, target_key, 1) > 1:
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
                    time.sleep(self._timing("detail_back_delay", 0.25))

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
                time.sleep(self._timing("pick_tap_delay", 0.35))

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
                    time.sleep(self._timing("pick_verify_delay", 0.35))
                    print(f"Selected brawler {brawler}")
                    return True

                card_texts = self._detail_card_texts(verify_screenshot)
                print(
                    f"EasyOCR detail texts {card_texts} did not confirm '{brawler}' "
                    f"(matched label {detected_name!r})."
                )

        if opened_detail:
            self.press_back()
            time.sleep(self._timing("detail_back_delay", 0.25))
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
            time.sleep(self._timing("detail_back_delay", 0.25))
            return True
        return False

    def _wait_for_grid_settle(self, stable_frames=1, delay=None, diff_threshold=6.5, timeout=None):
        if delay is None:
            delay = self._timing("grid_settle_delay", 0.06)
        if timeout is None:
            timeout = self._timing("grid_settle_timeout", 0.45)
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

    def _scroll_brawler_grid(self, wr, hr, direction="down"):
        scroll_x = int(320 * wr)
        if direction == "up":
            start_y = int(570 * hr)
            end_y = int(790 * hr)
        else:
            start_y = int(790 * hr)
            end_y = int(570 * hr)
        swipe_duration = self._timing("scroll_swipe_duration", 0.22)
        self.window_controller.swipe(
            scroll_x, start_y, scroll_x, end_y, duration=swipe_duration
        )
        self._wait_for_grid_settle()

    def _apply_brawler_sort(self, mode="lowest"):
        wr = self.window_controller.width_ratio
        hr = self.window_controller.height_ratio
        sort_y = 426 if str(mode).lower() == "lowest" else 368
        self.window_controller.click(int(1210 * wr), int(45 * hr))
        time.sleep(self._timing("sort_open_delay", 0.25))
        self.window_controller.click(int(1210 * wr), int(sort_y * hr))
        time.sleep(self._timing("sort_apply_delay", 0.35))

    def _select_brawler_on_open_grid(self, brawler, *, max_scrolls=None, sort_applied=False):
        if max_scrolls is None:
            max_scrolls = int(self._timing("default_max_scrolls", 90))
        general_config = load_toml_as_dict("cfg/general_config.toml")
        debug_enabled = str(general_config.get("super_debug", "no")).lower() in ("yes", "true", "1")
        try:
            ocr_scale = float(general_config.get("ocr_scale_down_factor", 0.65))
        except (TypeError, ValueError):
            ocr_scale = 0.65
        ocr_scale = max(0.35, min(1.0, ocr_scale))
        target_key = self._brawler_target_key(brawler)
        grid_ocr_scale = max(ocr_scale, 0.75)
        if len(target_key) <= 5:
            grid_ocr_scale = max(grid_ocr_scale, 0.95)
        if sort_applied:
            max_scrolls = min(max_scrolls, int(self._timing("sorted_max_scrolls", 90)))

        same_screen_attempts = 0
        max_same_screen_attempts = 3
        scroll_direction = "down"
        previous_page_signature = None
        unchanged_pages = 0
        for scroll_index in range(max_scrolls):
            self._dismiss_open_detail_card()

            screenshot_full = self.window_controller.screenshot()
            entries = self._run_easyocr_on_brawler_grid(screenshot_full, grid_ocr_scale)
            page_signature = self._grid_page_signature(entries)
            page_labels = [entry["text"] for entry in entries]

            matches = self._collect_easyocr_grid_matches(
                screenshot_full,
                target_key,
                grid_ocr_scale,
                debug_enabled=debug_enabled,
                entries=entries,
            )

            if matches:
                scroll_reason = "pick_failed"
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
                scroll_reason = "no_matches"
                if debug_enabled:
                    print(f"EasyOCR did not find '{brawler}' on the current brawler grid page.")

            wr = self.window_controller.width_ratio
            hr = self.window_controller.height_ratio
            if page_signature == previous_page_signature:
                unchanged_pages += 1
            else:
                unchanged_pages = 0
            previous_page_signature = page_signature

            if self._is_brawler_grid_end(page_labels):
                if scroll_direction == "down":
                    scroll_direction = "up"
                    unchanged_pages = 0
                    previous_page_signature = None
                else:
                    break

            if unchanged_pages >= 2:
                if scroll_direction == "down":
                    scroll_direction = "up"
                    unchanged_pages = 0
                    previous_page_signature = None
                else:
                    break

            self._scroll_brawler_grid(wr, hr, direction=scroll_direction)

        print(
            f"WARNING: Brawler '{brawler}' was not found after {max_scrolls} scroll attempts. "
            "The bot will continue with the currently selected brawler."
        )
        return False

    def select_brawler(self, brawler):
        self.window_controller.screenshot()
        if not self.open_brawler_selection():
            print(f"WARNING: Could not open brawler selection menu for '{brawler}'. "
                  "Continuing with the currently selected brawler instead of crashing.")
            self.press_back()
            return False
        return self._select_brawler_on_open_grid(brawler)

    def _select_sorted_trophy_brawler(self, *, sort_y, sort_label, recovery_label):
        wr = self.window_controller.width_ratio
        hr = self.window_controller.height_ratio

        tap_delay = self._timing("pick_tap_delay", 0.35)
        confirm_delay = self._timing("select_confirm_delay", 0.35)

        def tap(x, y, wait=None):
            if wait is None:
                wait = tap_delay
            self.window_controller.click(int(x * wr), int(y * hr))
            time.sleep(wait)

        print(f"Selecting next brawler by sorting {sort_label}.")
        self._dismiss_starr_nova_hub_if_present()
        if not self.open_brawler_selection():
            print(f"WARNING: Could not open brawler selection menu for {recovery_label.lower()} pick.")
            self.press_back()
            return False
        self._dismiss_starr_nova_hub_if_present()
        tap(1210, 45)   # sort dropdown
        tap(1210, sort_y, self._timing("sort_apply_delay", 0.35))
        tap(422, 359, confirm_delay)   # first brawler card after sorting
        tap(260, 991, confirm_delay)   # Select
        if self.ensure_lobby_after_selection():
            return True

        print(f"{recovery_label} brawler selection did not return to lobby; trying one recovery pass.")
        self.press_back()
        time.sleep(self._timing("menu_retry_delay", 0.35))
        tap(260, 991, confirm_delay)   # Select again if the brawler details screen is still open
        return self.ensure_lobby_after_selection()

    def _select_sorted_queue_brawler(self, brawler, *, mode="lowest"):
        brawler_name = str(brawler or "").strip()
        if not brawler_name:
            if mode == "highest":
                return self._select_sorted_trophy_brawler(
                    sort_y=368,
                    sort_label="most trophies",
                    recovery_label="Highest-trophy",
                )
            return self._select_sorted_trophy_brawler(
                sort_y=426,
                sort_label="lowest trophies",
                recovery_label="Lowest-trophy",
            )

        sort_label = "lowest trophies" if mode == "lowest" else "most trophies"
        print(f"Selecting queued brawler {brawler_name} after {sort_label} sort.")
        self._dismiss_starr_nova_hub_if_present()
        if not self.open_brawler_selection():
            print(f"WARNING: Could not open brawler selection menu for '{brawler_name}'.")
            self.press_back()
            return False
        self._dismiss_starr_nova_hub_if_present()
        self._apply_brawler_sort(mode)
        if self._select_brawler_on_open_grid(brawler_name, sort_applied=True):
            return True
        self.press_back()
        return False

    def select_highest_trophy_brawler(self, brawler=None):
        if brawler:
            return self._select_sorted_queue_brawler(brawler, mode="highest")
        return self._select_sorted_trophy_brawler(
            sort_y=368,
            sort_label="most trophies",
            recovery_label="Highest-trophy",
        )

    def select_lowest_trophy_brawler(self, brawler=None):
        if brawler:
            return self._select_sorted_queue_brawler(brawler, mode="lowest")
        return self._select_sorted_trophy_brawler(
            sort_y=426,
            sort_label="lowest trophies",
            recovery_label="Lowest-trophy",
        )

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
            time.sleep(self._timing("lobby_return_poll", 0.35))
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

    def _ocr_name_from_brawler_ref(self, brawler: str) -> str:
        requested = normalize_brawler_name(str(brawler or ""))
        if not requested:
            return self.normalize_ocr_name(brawler)
        for name in load_brawlers_info().keys():
            if normalize_brawler_name(name) == requested:
                return self.normalize_ocr_name(name)
        return self.normalize_ocr_name(brawler)

    def _brawler_target_key(self, brawler: str) -> str:
        return self._ocr_name_from_brawler_ref(brawler)

    @staticmethod
    def normalize_ocr_name(value: str) -> str:
        normalized = str(value).lower().strip()
        for symbol in (" ", ".", "&", "'", "`", "_", "[", "]", "(", ")", "@", "#", "|", "!", "·"):
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
        detected_name = str(detected_name or "").strip()
        target_name = str(target_name or "").strip()
        if not detected_name or not target_name:
            return False
        if detected_name == target_name:
            return True
        if normalize_brawler_name(detected_name) == normalize_brawler_name(target_name):
            return True
        if len(target_name) <= 2 or len(detected_name) <= 2:
            return False
        shorter, longer = (
            (target_name, detected_name)
            if len(target_name) <= len(detected_name)
            else (detected_name, target_name)
        )
        if len(shorter) >= 4 and shorter in longer and len(shorter) / len(longer) >= 0.72:
            return True
        if len(target_name) <= 4:
            limit = 1
            if cls.bounded_edit_distance(detected_name, target_name, limit) > limit:
                return False
            return detected_name[0] == target_name[0]
        limit = 2 if len(target_name) >= 8 else 1
        if cls.bounded_edit_distance(detected_name, target_name, limit) <= limit:
            return True
        return len(target_name) >= 5 and SequenceMatcher(None, detected_name, target_name).ratio() >= 0.84

    @classmethod
    def name_match_score(cls, detected_name: str, target_name: str) -> float:
        if detected_name == target_name:
            return 2.0
        ratio = SequenceMatcher(None, detected_name, target_name).ratio()
        distance = cls.bounded_edit_distance(detected_name, target_name, 3)
        return ratio - (distance * 0.05)
