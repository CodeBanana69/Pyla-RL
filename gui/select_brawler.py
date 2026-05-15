import json
import time
import tkinter as tk
from difflib import SequenceMatcher
from math import ceil

import cv2
import customtkinter as ctk
import numpy as np
import pyautogui
from adbutils import adb
from PIL import Image
from customtkinter import CTkImage
from utils import (
    extract_text_strings,
    fetch_brawl_stars_player,
    load_brawl_stars_api_config,
    load_toml_as_dict,
    normalize_brawler_name,
    resolve_project_path,
    resolve_brawler_name_alias,
    save_brawler_icon,
    get_dpi_scale,
)
from tkinter import filedialog

from gui.main import install_tk_background_error_filter

orig_screen_width, orig_screen_height = 1920, 1080
width, height = pyautogui.size()
width_ratio = width / orig_screen_width
height_ratio = height / orig_screen_height
scale_factor = min(width_ratio, height_ratio)
scale_factor *= 96/get_dpi_scale()
pyla_version = load_toml_as_dict("./cfg/general_config.toml")['pyla_version']

class SelectBrawler:

    def __init__(self, data_setter, brawlers):
        self.app = ctk.CTk()
        install_tk_background_error_filter(self.app)
        tk._default_root = self.app

        square_size = int(75 * scale_factor)
        amount_of_rows = ceil(len(brawlers)/10) + 1
        necessary_height = (int(145 * scale_factor) + amount_of_rows*square_size + (amount_of_rows-1)*int(3 * scale_factor))
        window_height = min(necessary_height, int(820 * scale_factor))
        image_frame_height = max(int(240 * scale_factor), window_height - int(190 * scale_factor))
        self.app.title(f"PylaAi-XXZ v{pyla_version}")
        self.brawlers = brawlers

        self.app.geometry(f"{str(int(860 * scale_factor))}x{window_height}+{str(int(600 * scale_factor))}")
        self.data_setter = data_setter
        self.colors = {
            'gray': "#7d7777",
            'red': "#cd5c5c",
            'darker_white': '#c4c4c4',
            'dark gray': '#1c1c1c',
            'cherry red': '#960a00',
            'ui box gray': '#242424',
            'chess white': '#f0d9b5',
            'chess brown': '#b58863',
            'indian red': "#cd5c5c"
        }

        self.app.configure(fg_color=self.colors['ui box gray'])



        self.images = []
        self.visible_image_labels = []
        self.brawlers_data = []
        self.farm_type = ""
        self.api_trophies_by_brawler = None
        self.api_trophies_by_normalized_brawler = None
        self.api_trophy_error_reported = False
        self._filter_after_id = None
        self._image_render_after_id = None
        self._current_filter_text = None
        self._closing = False
        self._closed = False
        api_trophies = self.get_api_trophies_by_brawler()
        if api_trophies:
            self.brawlers = [brawler for brawler in self.brawlers if brawler in api_trophies]

        for brawler in self.brawlers:
            img_path = f"./api/assets/brawler_icons/{brawler}.png"
            try:
                img = Image.open(img_path)
            except FileNotFoundError:
                save_brawler_icon(brawler)
                img = Image.open(img_path)

            img_tk = CTkImage(img, size=(square_size, square_size))
            self.images.append((brawler, img_tk))  # Store tuple of brawler name and image

        # Entry widget for filtering
        self.filter_var = tk.StringVar()
        self.filter_entry = ctk.CTkEntry(
            self.app, textvariable=self.filter_var,
            placeholder_text="Type brawler name...", font=("", int(20 * scale_factor)), width=int(200 * scale_factor),
            fg_color=self.colors['ui box gray'], border_color=self.colors['cherry red'], text_color="white"
        )
        header_text = "Write brawler"
        search_x = int(330 * scale_factor)
        search_width = int(220 * scale_factor)
        search_label = ctk.CTkLabel(
            self.app,
            text=header_text,
            font=("Comic sans MS", int(20 * scale_factor)),
            text_color=self.colors['cherry red'],
            width=search_width,
            anchor="center",
        )
        search_label.place(x=search_x, y=int(scale_factor * 18))
        self.filter_entry.configure(width=search_width)
        self.filter_entry.place(x=search_x, y=int(scale_factor * 52))
        self.filter_var.trace_add("write", lambda *args: self.queue_image_filter_update())

        # Frame to hold the images
        self.image_frame = ctk.CTkScrollableFrame(
            self.app,
            fg_color=self.colors['ui box gray'],
            width=int(845 * scale_factor),
            height=image_frame_height,
        )
        self.image_frame.place(x=0, y=int(100 * scale_factor))

        self.update_images("")
        ctk.CTkButton(self.app, text="Start", command=self.start_bot, fg_color=self.colors['ui box gray'],
                      text_color="white",
                      font=("Comic sans MS", int(25 * scale_factor)), border_color=self.colors['cherry red'],
                      border_width=int(2 * scale_factor)).place(x=int(390 * scale_factor), y=int((window_height-60* scale_factor) ))

        ctk.CTkButton(self.app, text="Push All", command=self.open_push_all_target_window, fg_color=self.colors['ui box gray'],
                      text_color="white",
                      font=("Comic sans MS", int(25 * scale_factor)), border_color=self.colors['cherry red'],
                      border_width=int(2 * scale_factor)).place(x=int(10 * scale_factor),
                                                                y=int((window_height-60* scale_factor) ))

        self.app.mainloop()

    def queue_image_filter_update(self):
        if self._closing:
            return
        if self._filter_after_id is not None:
            try:
                self.app.after_cancel(self._filter_after_id)
            except Exception:
                pass
        self._filter_after_id = self.app.after(
            120,
            lambda: self.update_images(self.filter_var.get())
        )

    def set_farm_type(self, value):
        self.farm_type = value

    def start_bot(self):
        if self._closing:
            return
        brawlers_data = list(self.brawlers_data)
        self._closing = True
        self._cancel_queued_callbacks()
        self._hide_window()
        self.data_setter(brawlers_data)
        try:
            self.app.quit()
        except Exception:
            pass

    def _cancel_queued_callbacks(self):
        for after_id in (self._filter_after_id, self._image_render_after_id):
            if after_id is None:
                continue
            try:
                self.app.after_cancel(after_id)
            except Exception:
                pass
        self._filter_after_id = None
        self._image_render_after_id = None

    def _hide_window(self):
        try:
            self.app.withdraw()
        except Exception:
            pass
        try:
            self.app.update_idletasks()
        except Exception:
            pass
        try:
            self.app.update()
        except Exception:
            pass

    def close_app(self):
        if self._closed:
            return
        self._closing = True
        self._cancel_queued_callbacks()
        self._hide_window()

        try:
            self.app.quit()
        except Exception:
            pass
        try:
            self.app.destroy()
        except Exception:
            pass
        self._closed = True

    def load_brawler_config(self):
        # open file select dialog to select a json file
        file_path = filedialog.askopenfilename(
            title="Select Brawler Config File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'r') as file:
                    brawlers_data = json.load(file)
                    try:
                        brawlers_data = [
                            bd for bd in brawlers_data
                            if not (bd["push_until"] <= bd[bd["type"]])
                        ]
                        self.brawlers_data = brawlers_data
                        print("Brawler data loaded successfully :", brawlers_data)
                    except Exception as e:
                        print("Invalid data format. Expected a list of brawler data.", e)
            except Exception as e:
                print(f"Error loading brawler data: {e}")

    def get_push_all_data(self, target_trophies=1000):
        target_trophies = int(target_trophies)
        api_config = load_brawl_stars_api_config("cfg/brawl_stars_api.toml")
        player_data = fetch_brawl_stars_player(
            api_config.get("api_token", "").strip(),
            api_config.get("player_tag", "").strip(),
            int(api_config.get("timeout_seconds", 15)),
        )
        known_by_normalized_name = {
            normalize_brawler_name(brawler): brawler
            for brawler in self.brawlers
        }
        rows = []
        for index, api_brawler in enumerate(player_data.get("brawlers", [])):
            brawler = known_by_normalized_name.get(normalize_brawler_name(api_brawler.get("name", "")))
            if not brawler:
                continue
            trophies = int(api_brawler.get("trophies", 0))
            if trophies < target_trophies:
                rows.append((trophies, index, brawler))

        rows.sort(key=lambda item: (item[0], item[1]))
        data = []
        for idx, (trophies, _, brawler) in enumerate(rows):
            data.append({
                "brawler": brawler,
                "push_until": target_trophies,
                "trophies": trophies,
                "wins": 0,
                "type": "trophies",
                "automatically_pick": idx != 0,
                "selection_method": "lowest_trophies",
                "win_streak": 0,
            })
        return data

    def get_push_all_1k_data(self):
        return self.get_push_all_data(1000)

    @staticmethod
    def _match_brawler_from_ocr_texts(texts, known_brawlers):
        best_brawler = None
        best_score = 0.0
        known_names = [(brawler, normalize_brawler_name(brawler)) for brawler in known_brawlers]
        for raw_text in texts:
            normalized_text = resolve_brawler_name_alias(raw_text)
            if not normalized_text:
                continue
            for brawler, normalized_brawler in known_names:
                normalized_brawler = resolve_brawler_name_alias(normalized_brawler)
                if normalized_text == normalized_brawler:
                    return brawler
                if normalized_brawler in normalized_text or normalized_text in normalized_brawler:
                    score = min(len(normalized_text), len(normalized_brawler)) / max(
                        len(normalized_text), len(normalized_brawler)
                    )
                else:
                    score = SequenceMatcher(None, normalized_text, normalized_brawler).ratio()
                if score > best_score:
                    best_score = score
                    best_brawler = brawler
        return best_brawler if best_score >= 0.72 else None

    @staticmethod
    def _move_brawler_to_front(data, selected_brawler):
        if not selected_brawler:
            return data
        selected_normalized = normalize_brawler_name(selected_brawler)
        selected_index = None
        for index, row in enumerate(data):
            if normalize_brawler_name(row.get("brawler", "")) == selected_normalized:
                selected_index = index
                break
        if selected_index is None:
            return data
        reordered = [dict(row) for row in data]
        selected_row = reordered.pop(selected_index)
        reordered.insert(0, selected_row)
        for index, row in enumerate(reordered):
            row["automatically_pick"] = index != 0
        return reordered

    def detect_first_sorted_brawler(self, device):
        last_texts = []
        for attempt in range(3):
            try:
                screenshot = device.screenshot()
                frame = np.array(screenshot)
                if frame.ndim == 3 and frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2RGB)
            except Exception as e:
                print(f"Could not screenshot brawler screen for OCR: {e}")
                return None

            height, width = frame.shape[:2]
            crop = frame[
                int(height * 0.16):int(height * 0.56),
                int(width * 0.10):int(width * 0.36),
            ]
            try:
                texts = extract_text_strings(crop)
            except Exception as e:
                print(f"Could not OCR first sorted brawler card: {e}")
                return None

            last_texts = texts
            detected_brawler = self._match_brawler_from_ocr_texts(texts, self.brawlers)
            if detected_brawler:
                print(f"Detected first sorted brawler from game screen: {detected_brawler} (OCR: {texts})")
                return detected_brawler
            time.sleep(0.35 + attempt * 0.2)

        print(f"Could not match first sorted brawler from OCR: {last_texts}")
        return None

    def get_adb_device_for_quick_select(self):
        general_config = load_toml_as_dict("cfg/general_config.toml")
        configured_port = general_config.get("emulator_port", 0)
        selected_emulator = general_config.get("current_emulator", "LDPlayer")
        brawl_package = general_config.get("brawl_stars_package", "com.supercell.brawlstars").strip()
        emulator_ports = {
            "LDPlayer": [5555, 5557, 5559, 5554],
            "MuMu": [16384, 16416, 16448, 7555, 5558, 5557, 5556, 5555, 5554],
        }
        if selected_emulator not in emulator_ports:
            try:
                configured_port_int = int(configured_port)
            except (TypeError, ValueError):
                configured_port_int = 0
            selected_emulator = "MuMu" if configured_port_int in (16384, 16416, 16448, 7555) else "LDPlayer"
        try:
            configured_port = int(configured_port)
        except (TypeError, ValueError):
            configured_port = 0
        preferred_ports = []
        port_candidates = [configured_port] + emulator_ports[selected_emulator] + emulator_ports["LDPlayer"] + emulator_ports["MuMu"]
        for port in port_candidates:
            try:
                port = int(port)
            except (TypeError, ValueError):
                continue
            if port != 5037 and port not in preferred_ports:
                preferred_ports.append(port)
        configured_ports = []
        try:
            configured_ports = [int(configured_port)]
        except (TypeError, ValueError):
            pass

        def serial_port(serial):
            if serial.startswith("emulator-"):
                try:
                    return int(serial.rsplit("-", 1)[1])
                except ValueError:
                    return None
            if ":" in serial:
                try:
                    return int(serial.rsplit(":", 1)[1])
                except ValueError:
                    return None
            return None

        def online_devices():
            devices = []
            for dev in adb.device_list():
                try:
                    if dev.get_state() == "device":
                        devices.append(dev)
                except Exception:
                    pass
            return devices

        def choose_device(devices):
            best_device = None
            best_score = None
            for index, dev in enumerate(devices):
                port = serial_port(dev.serial)
                try:
                    opened_package = dev.app_current().package.strip()
                except Exception:
                    opened_package = ""
                score = (
                    opened_package == brawl_package,
                    port in configured_ports,
                    port in preferred_ports,
                    -index,
                )
                if best_score is None or score > best_score:
                    best_device = dev
                    best_score = score
            return best_device

        devices = online_devices()
        device = choose_device(devices)
        if device:
            return device

        for port in preferred_ports:
            if port == 5037:
                continue
            try:
                adb.connect(f"127.0.0.1:{port}")
            except Exception:
                pass

        devices = online_devices()
        device = choose_device(devices)
        if not device:
            raise ConnectionError("No ADB device found for Push All.")
        return device

    def quick_select_least_trophies_brawler(self):
        device = self.get_adb_device_for_quick_select()
        size = device.window_size()
        wr = size.width / 1920
        hr = size.height / 1080

        def tap(x, y, wait=0.8):
            device.shell(f"input tap {int(x * wr)} {int(y * hr)}")
            time.sleep(wait)

        print(f"Push All using ADB device: {device.serial}")
        tap(128, 500, 1.4)   # left Brawlers button in lobby
        tap(1210, 45, 0.6)   # sort dropdown
        tap(1210, 426, 1.0)  # Least Trophies
        selected_brawler = self.detect_first_sorted_brawler(device)
        tap(422, 359, 1.0)   # first brawler card
        tap(260, 991, 1.0)   # Select
        return device.serial, selected_brawler

    def open_push_all_target_window(self):
        top = ctk.CTkToplevel(self.app)
        top.configure(fg_color=self.colors['ui box gray'])
        top.title("Push All Target")
        top.attributes("-topmost", True)
        win_w = int(360 * scale_factor)
        win_h = int(300 * scale_factor)
        top.geometry(f"{win_w}x{win_h}+{str(int(950 * scale_factor))}+{str(int(260 * scale_factor))}")

        ctk.CTkLabel(
            top,
            text="Push all brawlers to:",
            font=("Comic sans MS", int(22 * scale_factor)),
            text_color=self.colors['red'],
        ).pack(pady=(int(18 * scale_factor), int(10 * scale_factor)))

        button_frame = ctk.CTkFrame(top, fg_color=self.colors['ui box gray'])
        button_frame.pack(pady=int(8 * scale_factor))

        def choose_target(target):
            try:
                top.destroy()
            except Exception:
                pass
            self.push_all(target)

        targets = [250, 500, 750, 1000, 1250, 1500]
        for index, target in enumerate(targets):
            row = index // 2
            col = index % 2
            ctk.CTkButton(
                button_frame,
                text=str(target),
                command=lambda t=target: choose_target(t),
                fg_color=self.colors['ui box gray'],
                hover_color=self.colors['cherry red'],
                text_color="white",
                font=("Comic sans MS", int(20 * scale_factor)),
                border_color=self.colors['cherry red'],
                border_width=int(2 * scale_factor),
                width=int(120 * scale_factor),
                height=int(42 * scale_factor),
            ).grid(row=row, column=col, padx=int(10 * scale_factor), pady=int(8 * scale_factor))

    def push_all(self, target_trophies=1000):
        if self._closing:
            return
        target_trophies = int(target_trophies)
        hidden_for_start = False
        try:
            self.app.withdraw()
            self.app.update_idletasks()
            self.app.update()
            hidden_for_start = True

            data = self.get_push_all_data(target_trophies)
            if not data:
                print(f"Push All: no brawlers below {target_trophies} trophies were found.")
                self.app.deiconify()
                return
            selected_serial, selected_brawler = self.quick_select_least_trophies_brawler()
            if selected_brawler:
                data = self._move_brawler_to_front(data, selected_brawler)
            print(f"Push All {target_trophies} first brawler:", data[0])
            self.brawlers_data = data
            self.start_bot()
        except Exception as e:
            print(f"Push All failed: {e}")
            print(
                f"Open {resolve_project_path('cfg/brawl_stars_api.toml')} and make sure player_tag, developer_email, "
                "developer_password, and auto_refresh_token are set correctly."
            )
            if hidden_for_start:
                try:
                    self.app.deiconify()
                except Exception:
                    pass

    def push_all_1k(self):
        self.push_all(1000)

    def get_api_trophies_by_brawler(self):
        if self.api_trophies_by_brawler is not None:
            return self.api_trophies_by_brawler

        config_path = "cfg/brawl_stars_api.toml"
        try:
            api_config = load_brawl_stars_api_config(config_path)
            if not api_config.get("api_token") or not api_config.get("player_tag"):
                self.api_trophies_by_brawler = {}
                return self.api_trophies_by_brawler
            player_data = fetch_brawl_stars_player(
                api_config.get("api_token", "").strip(),
                api_config.get("player_tag", "").strip(),
                int(api_config.get("timeout_seconds", 15)),
            )
            known_by_normalized_name = {
                normalize_brawler_name(brawler): brawler
                for brawler in self.brawlers
            }
            self.api_trophies_by_brawler = {}
            self.api_trophies_by_normalized_brawler = {}
            for api_brawler in player_data.get("brawlers", []):
                normalized_name = normalize_brawler_name(api_brawler.get("name", ""))
                brawler = known_by_normalized_name.get(normalized_name)
                if brawler:
                    trophies = int(api_brawler.get("trophies", 0))
                    self.api_trophies_by_brawler[brawler] = trophies
                    self.api_trophies_by_normalized_brawler[normalize_brawler_name(brawler)] = trophies
                    self.api_trophies_by_normalized_brawler[normalized_name] = trophies
            print(f"Loaded current trophies for {len(self.api_trophies_by_brawler)} brawlers from Brawl Stars API.")
        except Exception as e:
            self.api_trophies_by_brawler = {}
            self.api_trophies_by_normalized_brawler = {}
            if not self.api_trophy_error_reported:
                print(f"Could not auto-fill trophies. Check {resolve_project_path(config_path)}: {e}")
                self.api_trophy_error_reported = True
        return self.api_trophies_by_brawler

    def get_api_trophies_for_brawler(self, brawler):
        api_trophies = self.get_api_trophies_by_brawler()
        if brawler in api_trophies:
            return api_trophies[brawler]
        if self.api_trophies_by_normalized_brawler is None:
            self.api_trophies_by_normalized_brawler = {
                normalize_brawler_name(name): trophies
                for name, trophies in api_trophies.items()
            }
        return self.api_trophies_by_normalized_brawler.get(normalize_brawler_name(brawler))

    def on_image_click(self, brawler):
        self.open_brawler_entry(brawler)

    def open_brawler_entry(self, brawler):
        top = ctk.CTkToplevel(self.app)
        top.configure(fg_color=self.colors['ui box gray'])
        win_w = int(300 * scale_factor)
        win_h = int(400 * scale_factor)
        top.geometry(
            f"{win_w}x{win_h}+{str(int(1100 * scale_factor))}+{str(int(200 * scale_factor))}")
        top.title("Enter Brawler Data")
        top.attributes("-topmost", True)

        # --- Variables ---
        push_until_var = tk.StringVar()
        trophies_var = tk.StringVar()
        wins_var = tk.StringVar()
        current_win_streak_var = tk.StringVar(value="0")
        auto_pick_var = tk.BooleanVar(value=True) if self.brawlers_data else tk.BooleanVar(value=False)
        api_trophies = self.get_api_trophies_for_brawler(brawler)
        if api_trophies is not None:
            trophies_var.set(str(api_trophies))

        # --- Fixed Y positions for placed widgets ---
        y_title = int(7 * scale_factor)
        y_buttons = int(50 * scale_factor)
        y_field1_label = int(100 * scale_factor)
        y_field1_entry = int(125 * scale_factor)
        y_field2_label = int(165 * scale_factor)
        y_field2_entry = int(190 * scale_factor)
        y_field3_label = int(230 * scale_factor)
        y_field3_entry = int(255 * scale_factor)
        y_auto_pick = int(300 * scale_factor)
        y_submit = int(350 * scale_factor)
        x_center_label = int(70 * scale_factor)
        x_center_entry = int(60 * scale_factor)
        entry_width = int(170 * scale_factor)

        # --- Title ---
        ctk.CTkLabel(top, text=f"Brawler: {brawler}", font=("Comic sans MS", int(20 * scale_factor)),
                     text_color=self.colors['red']).place(x=x_center_label, y=y_title)

        # --- Push type buttons ---
        farm_type_button_frame = ctk.CTkFrame(top, width=int(210 * scale_factor), height=int(40 * scale_factor),
                                              fg_color=self.colors['ui box gray'])
        farm_type_button_frame.place(x=int(45 * scale_factor), y=y_buttons)

        # --- Entry widgets (created but NOT placed yet) ---
        push_until_label = ctk.CTkLabel(top, text="Target Amount", font=("Comic sans MS", int(15 * scale_factor)),
                     text_color=self.colors['chess white'])
        push_until_entry = ctk.CTkEntry(
            top, textvariable=push_until_var, fg_color=self.colors['ui box gray'], text_color="white",
            border_color=self.colors['cherry red'], border_width=int(2 * scale_factor),
            height=int(28 * scale_factor), width=entry_width
        )

        trophies_label = ctk.CTkLabel(top, text="Current Trophies", font=("Comic sans MS", int(15 * scale_factor)),
                     text_color=self.colors['chess white'])
        trophies_entry = ctk.CTkEntry(
            top, textvariable=trophies_var, fg_color=self.colors['ui box gray'], text_color="white",
            border_color=self.colors['cherry red'], border_width=int(2 * scale_factor),
            height=int(28 * scale_factor), width=entry_width
        )

        wins_label = ctk.CTkLabel(top, text="Current Wins", font=("Comic sans MS", int(15 * scale_factor)),
                     text_color=self.colors['chess white'])
        wins_entry = ctk.CTkEntry(
            top, textvariable=wins_var, fg_color=self.colors['ui box gray'], text_color="white",
            border_color=self.colors['cherry red'], border_width=int(2 * scale_factor),
            height=int(28 * scale_factor), width=entry_width
        )

        win_streak_label = ctk.CTkLabel(top, text="Current Brawler's Win Streak", font=("Comic sans MS", int(15 * scale_factor)),
                     text_color=self.colors['chess white'])
        current_win_streak_entry = ctk.CTkEntry(
            top, textvariable=current_win_streak_var, fg_color=self.colors['ui box gray'], text_color="white",
            border_color=self.colors['cherry red'], border_width=int(2 * scale_factor),
            height=int(28 * scale_factor), width=entry_width
        )

        auto_pick_checkbox = ctk.CTkCheckBox(
            top, text="Bot auto-selects brawler", variable=auto_pick_var,
            fg_color=self.colors['cherry red'], text_color="white", checkbox_height=int(24 * scale_factor)
        )

        def submit_data():
            push_until_raw = push_until_var.get()
            push_until_value = int(push_until_raw) if push_until_raw.isdigit() else 0
            trophies_raw = trophies_var.get()
            trophies_value = int(trophies_raw) if trophies_raw.isdigit() else 0
            wins_raw = wins_var.get()
            wins_value = int(wins_raw) if wins_raw.isdigit() else 0
            current_win_streak_raw = current_win_streak_var.get()
            current_win_streak_value = int(current_win_streak_raw) if current_win_streak_raw.isdigit() else 0
            data = {
                "brawler": brawler,
                "push_until": push_until_value,
                "trophies": trophies_value,
                "wins": wins_value,
                "type": self.farm_type,
                "automatically_pick": auto_pick_var.get(),
                "win_streak": current_win_streak_value
            }

            self.brawlers_data = [item for item in self.brawlers_data if item["brawler"] != data["brawler"]]
            self.brawlers_data.append(data)

            print("Selected Brawler Data :", self.brawlers_data)
            top.destroy()

        submit_button = ctk.CTkButton(
            top, text="Submit", command=submit_data, fg_color=self.colors['ui box gray'],
            border_color=self.colors['cherry red'],
            text_color="white", border_width=int(2 * scale_factor), width=int(80 * scale_factor)
        )

        # --- All dynamic widgets that can be shown/hidden ---
        all_dynamic_widgets = [
            push_until_label, push_until_entry,
            trophies_label, trophies_entry,
            wins_label, wins_entry,
            win_streak_label, current_win_streak_entry,
            auto_pick_checkbox, submit_button
        ]

        def hide_all_fields():
            for w in all_dynamic_widgets:
                w.place_forget()

        def check_submit_visibility():
            """Show submit only when push type is selected and required numeric fields are filled."""
            if self.farm_type == "":
                submit_button.place_forget()
                return
            target_ok = push_until_var.get().isdigit()
            if self.farm_type == "trophies":
                fields_ok = target_ok and trophies_var.get().isdigit() and current_win_streak_var.get().isdigit()
            else:  # wins
                fields_ok = target_ok and wins_var.get().isdigit()
            if fields_ok:
                submit_button.place(x=int(110 * scale_factor), y=y_submit)
            else:
                submit_button.place_forget()

        # Trace all entry vars to re-check submit visibility on every keystroke
        push_until_var.trace_add("write", lambda *a: check_submit_visibility())
        trophies_var.trace_add("write", lambda *a: check_submit_visibility())
        wins_var.trace_add("write", lambda *a: check_submit_visibility())
        current_win_streak_var.trace_add("write", lambda *a: check_submit_visibility())

        def show_trophies_fields():
            hide_all_fields()
            self.farm_type = "trophies"
            self.wins_button.configure(fg_color=self.colors['ui box gray'])
            self.trophies_button.configure(fg_color=self.colors['cherry red'])
            # Field 1: Target Amount
            push_until_label.place(x=x_center_label, y=y_field1_label)
            push_until_entry.place(x=x_center_entry, y=y_field1_entry)
            # Field 2: Current Trophies
            trophies_label.place(x=x_center_label, y=y_field2_label)
            trophies_entry.place(x=x_center_entry, y=y_field2_entry)
            # Field 3: Win Streak
            win_streak_label.place(x=int(40 * scale_factor), y=y_field3_label)
            current_win_streak_entry.place(x=x_center_entry, y=y_field3_entry)
            # Auto-pick checkbox
            auto_pick_checkbox.place(x=int(60 * scale_factor), y=y_auto_pick)
            check_submit_visibility()

        def show_wins_fields():
            hide_all_fields()
            self.farm_type = "wins"
            self.wins_button.configure(fg_color=self.colors['cherry red'])
            self.trophies_button.configure(fg_color=self.colors['ui box gray'])
            # Field 1: Target Amount
            push_until_label.place(x=x_center_label, y=y_field1_label)
            push_until_entry.place(x=x_center_entry, y=y_field1_entry)
            # Field 2: Current Wins
            wins_label.place(x=x_center_label, y=y_field2_label)
            wins_entry.place(x=x_center_entry, y=y_field2_entry)
            # Auto-pick checkbox
            auto_pick_checkbox.place(x=int(60 * scale_factor), y=y_auto_pick)
            check_submit_visibility()

        self.wins_button = ctk.CTkButton(farm_type_button_frame, text="Win Amount", width=int(90 * scale_factor),
                                            command=show_wins_fields,
                                            hover_color=self.colors['cherry red'],
                                            font=("", int(15 * scale_factor)),
                                            fg_color=self.colors["ui box gray"],
                                            border_color=self.colors['cherry red'],
                                            border_width=int(2 * scale_factor)
                                            )
        self.trophies_button = ctk.CTkButton(farm_type_button_frame, text="Trophies", width=int(85 * scale_factor),
                                             command=show_trophies_fields,
                                             hover_color=self.colors['cherry red'],
                                             font=("", int(15 * scale_factor)),
                                             fg_color=self.colors["ui box gray"],
                                             border_color=self.colors['cherry red'], border_width=int(2 * scale_factor)
                                             )

        self.trophies_button.place(x=int(10 * scale_factor))
        self.wins_button.place(x=int(110 * scale_factor))


    def update_images(self, filter_text):
        if self._closing:
            return
        filter_text = (filter_text or "").strip().lower()
        if filter_text == self._current_filter_text:
            return
        self._current_filter_text = filter_text
        if self._image_render_after_id is not None:
            try:
                self.app.after_cancel(self._image_render_after_id)
            except Exception:
                pass
            self._image_render_after_id = None
        self.visible_image_labels = []
        for widget in self.image_frame.winfo_children():
            widget.destroy()

        matches = [
            (brawler, img_tk)
            for brawler, img_tk in self.images
            if brawler.startswith(filter_text)
        ]

        def render_batch(start_index=0):
            if self._closing:
                return
            for index in range(start_index, min(start_index + 16, len(matches))):
                brawler, img_tk = matches[index]
                row_num = index // 10
                col_num = index % 10
                label = ctk.CTkLabel(self.image_frame, image=img_tk, text="")
                label._pyla_image_ref = img_tk
                self.visible_image_labels.append(label)
                label.bind("<Button-1>", lambda e, b=brawler: self.on_image_click(b))  # Bind click event
                label.grid(row=row_num, column=col_num, padx=int(5 * scale_factor), pady=int(3 * scale_factor))
            next_index = start_index + 16
            if next_index < len(matches):
                self._image_render_after_id = self.app.after(1, lambda: render_batch(next_index))
            else:
                self._image_render_after_id = None

        render_batch()

def dummy_data_setter(data):
    print("Data set:", data)
