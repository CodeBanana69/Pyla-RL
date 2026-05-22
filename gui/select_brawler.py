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
from gui.theme import THEME

orig_screen_width, orig_screen_height = 1920, 1080
width, height = pyautogui.size()
width_ratio = width / orig_screen_width
height_ratio = height / orig_screen_height
scale_factor = min(width_ratio, height_ratio)
scale_factor *= 96/get_dpi_scale()

class SelectBrawler:

    def __init__(self, data_setter, brawlers):
        self.app = ctk.CTk()
        install_tk_background_error_filter(self.app)
        tk._default_root = self.app

        square_size = int(62 * scale_factor)
        amount_of_rows = ceil(len(brawlers) / 6) + 1
        necessary_height = int(230 * scale_factor) + amount_of_rows * int(118 * scale_factor)
        window_height = min(max(necessary_height, int(560 * scale_factor)), int(760 * scale_factor))
        self.content_width = int(720 * scale_factor)
        image_frame_height = max(int(250 * scale_factor), window_height - int(212 * scale_factor))
        self.app.title("Pyla-RL")
        self.brawlers = brawlers

        self.app.geometry(f"{str(int(820 * scale_factor))}x{window_height}+{str(int(600 * scale_factor))}")
        self._drag_offset = (0, 0)
        self.data_setter = data_setter
        self.colors = {
            "accent": "#ff9f0a",
            'gray': "#2f2f2f",
            'red': "#ffb23a",
            'darker_white': "#b8b8b8",
            'dark gray': "#0c0c0c",
            'cherry red': "#ff9f0a",
            'ui box gray': "#121212",
            'chess white': "#f4f4f4",
            'chess brown': "#202020",
            'indian red': "#ffb23a",
            'panel': "#181818",
            'panel2': "#1f1f1f",
            'border_soft': "#262626",
            'accent_soft': "#32220c",
            'accent_border': "#8f610e",
        }

        self.app.configure(fg_color=self.colors['ui box gray'])
        self._configure_frameless_window(self.app)

        self.images = []
        self.image_by_brawler = {}
        self.visible_image_labels = []
        self.push_all_priority_order = []
        self._push_order_drag_brawler = None
        self._push_order_queue_frames = []
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
            self.image_by_brawler[brawler] = img_tk

        self._create_window_chrome(self.app, "Brawler Select", self.close_app)

        header = ctk.CTkFrame(
            self.app,
            fg_color=self.colors['ui box gray'],
            border_color=self.colors['border_soft'],
            border_width=1,
            corner_radius=0,
            height=int(86 * scale_factor),
        )
        header.pack(fill="x")

        search_wrap = ctk.CTkFrame(
            header,
            fg_color=self.colors['panel'],
            border_color=self.colors['gray'],
            border_width=1,
            corner_radius=int(10 * scale_factor),
            width=int(380 * scale_factor),
            height=int(38 * scale_factor),
        )
        search_wrap.place(relx=0.5, y=int(24 * scale_factor), anchor="n")

        self.filter_var = tk.StringVar()
        self.filter_entry = ctk.CTkEntry(
            search_wrap,
            textvariable=self.filter_var,
            placeholder_text="Search brawler",
            font=("Segoe UI", int(13 * scale_factor), "bold"),
            width=int(348 * scale_factor),
            height=int(30 * scale_factor),
            fg_color=self.colors['panel'],
            border_color=self.colors['panel'],
            text_color=self.colors['chess white'],
            placeholder_text_color=self.colors['darker_white'],
        )
        self.filter_entry.place(relx=0.5, rely=0.5, anchor="center")
        self.filter_var.trace_add("write", lambda *args: self.queue_image_filter_update())

        body = ctk.CTkFrame(
            self.app,
            fg_color=self.colors['dark gray'],
            corner_radius=0,
        )
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=0)

        self.image_frame = ctk.CTkScrollableFrame(
            body,
            fg_color=self.colors['dark gray'],
            width=self.content_width,
            height=image_frame_height,
            scrollbar_button_color=self.colors['panel2'],
            scrollbar_button_hover_color=self.colors['gray'],
        )
        self.image_frame.grid(
            row=0,
            column=0,
            padx=int(30 * scale_factor),
            pady=(int(20 * scale_factor), int(8 * scale_factor)),
            sticky="nsew",
        )
        self.grid_frame = ctk.CTkFrame(self.image_frame, fg_color="transparent")
        self.grid_frame.pack(anchor="n", pady=(0, int(10 * scale_factor)))

        self.update_images("")

        actions_width = int(472 * scale_factor)
        actions_height = int(44 * scale_factor)
        actions = ctk.CTkFrame(
            body,
            fg_color="transparent",
            width=actions_width,
            height=actions_height,
            corner_radius=0,
        )
        actions.grid(row=1, column=0, pady=(int(4 * scale_factor), int(14 * scale_factor)))
        actions.pack_propagate(False)
        actions.grid_propagate(False)

        ctk.CTkButton(
            actions,
            text="Push All",
            command=self.open_push_all_target_window,
            fg_color=self.colors['panel'],
            hover_color=self.colors['panel2'],
            text_color=self.colors['chess white'],
            font=("Segoe UI", int(13 * scale_factor), "bold"),
            border_color=self.colors['gray'],
            border_width=1,
            corner_radius=int(9 * scale_factor),
            width=int(130 * scale_factor),
            height=int(38 * scale_factor),
        ).place(x=0, y=int(3 * scale_factor))
        self.start_button = ctk.CTkButton(
            actions,
            text="Start Pyla",
            command=self.start_bot,
            fg_color=self.colors['cherry red'],
            hover_color=self.colors['red'],
            text_color="white",
            font=("Segoe UI", int(13 * scale_factor), "bold"),
            border_color="#ffd18a",
            border_width=1,
            corner_radius=int(12 * scale_factor),
            width=int(148 * scale_factor),
            height=int(38 * scale_factor),
        )
        self.start_button.place(x=int(162 * scale_factor), y=int(3 * scale_factor))
        ctk.CTkButton(
            actions,
            text="Push Order",
            command=self.open_push_order_window,
            fg_color=self.colors['panel'],
            hover_color=self.colors['panel2'],
            text_color=self.colors['chess white'],
            font=("Segoe UI", int(13 * scale_factor), "bold"),
            border_color=self.colors['gray'],
            border_width=1,
            corner_radius=int(9 * scale_factor),
            width=int(130 * scale_factor),
            height=int(38 * scale_factor),
        ).place(x=int(342 * scale_factor), y=int(3 * scale_factor))

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

    def _configure_frameless_window(self, window):
        window.overrideredirect(True)
        window.configure(fg_color=self.colors['ui box gray'])

    def _create_window_chrome(self, window, title, close_command):
        chrome = ctk.CTkFrame(
            window,
            fg_color=self.colors['ui box gray'],
            border_color=self.colors['border_soft'],
            border_width=1,
            corner_radius=0,
            height=int(42 * scale_factor),
        )
        chrome.pack(fill="x")
        chrome.pack_propagate(False)

        def start_move(event):
            window._pyla_drag_offset = (event.x_root - window.winfo_x(), event.y_root - window.winfo_y())

        def drag_move(event):
            drag_x, drag_y = getattr(window, "_pyla_drag_offset", (0, 0))
            window.geometry(f"+{event.x_root - drag_x}+{event.y_root - drag_y}")

        chrome.bind("<ButtonPress-1>", start_move)
        chrome.bind("<B1-Motion>", drag_move)

        ctk.CTkLabel(
            chrome,
            text=f"Pyla  ·  {title}",
            font=("Segoe UI", int(13 * scale_factor), "bold"),
            text_color=self.colors['chess white'],
        ).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkButton(
            chrome,
            text="×",
            command=close_command,
            fg_color="transparent",
            hover_color=self.colors['panel2'],
            text_color=self.colors['darker_white'],
            font=("Segoe UI", int(13 * scale_factor), "bold"),
            width=int(34 * scale_factor),
            height=int(28 * scale_factor),
            corner_radius=int(6 * scale_factor),
        ).place(relx=0.985, rely=0.5, anchor="e")
        return chrome

    def _hub_button(self, parent, text, command, primary=False, width=None, height=None):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color=self.colors['cherry red'] if primary else self.colors['panel'],
            hover_color=self.colors['red'] if primary else self.colors['panel2'],
            text_color="white" if primary else self.colors['chess white'],
            font=("Segoe UI", int(13 * scale_factor), "bold"),
            border_color="#ffd18a" if primary else self.colors['gray'],
            border_width=1,
            corner_radius=int(10 * scale_factor),
            width=width or int(120 * scale_factor),
            height=height or int(36 * scale_factor),
        )

    def _modal_body(self, window, padx=18, pady=18):
        body = ctk.CTkFrame(window, fg_color=self.colors['dark gray'], corner_radius=0)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body._pyla_padx = int(padx * scale_factor)
        body._pyla_pady = int(pady * scale_factor)
        return body

    def _section_label(self, parent, text):
        return ctk.CTkLabel(
            parent,
            text=text.upper(),
            font=("Segoe UI", int(11 * scale_factor), "bold"),
            text_color=self.colors['darker_white'],
            anchor="w",
        )

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
        from gui.brawler_queue import get_push_all_data as build_push_all_data

        return build_push_all_data(target_trophies, brawlers=self.brawlers)

    def get_push_all_1k_data(self):
        return self.get_push_all_data(1000)

    def apply_push_all_priority_order(self, data):
        from gui.brawler_queue import apply_push_all_priority_order

        ordered = apply_push_all_priority_order(data, self.push_all_priority_order)
        print("Push All priority order:", [row.get("brawler") for row in ordered[: len(self.push_all_priority_order)]])
        return ordered

    def add_push_order_brawler(self, brawler):
        if brawler not in self.brawlers or brawler in self.push_all_priority_order:
            return
        self.push_all_priority_order.append(brawler)

    def remove_push_order_brawler(self, brawler):
        self.push_all_priority_order = [
            queued for queued in self.push_all_priority_order
            if queued != brawler
        ]

    def move_push_order_brawler(self, brawler, target_index):
        if brawler not in self.push_all_priority_order:
            return False
        self.push_all_priority_order.remove(brawler)
        target_index = max(0, min(int(target_index), len(self.push_all_priority_order)))
        self.push_all_priority_order.insert(target_index, brawler)
        return True

    def push_order_drop_index(self, pointer_x):
        if not self._push_order_queue_frames:
            return 0
        for index, frame in enumerate(self._push_order_queue_frames):
            try:
                midpoint = frame.winfo_rootx() + frame.winfo_width() / 2
            except Exception:
                continue
            if pointer_x < midpoint:
                return index
        return len(self._push_order_queue_frames)

    def open_push_order_window(self):
        top = ctk.CTkToplevel(self.app)
        self._configure_frameless_window(top)
        top.title("Push Order")
        top.attributes("-topmost", True)
        win_w = int(820 * scale_factor)
        win_h = int(570 * scale_factor)
        top.geometry(f"{win_w}x{win_h}+{str(int(820 * scale_factor))}+{str(int(180 * scale_factor))}")
        self._create_window_chrome(top, "Push Order", top.destroy)

        body = self._modal_body(top, padx=18, pady=14)

        top_bar = ctk.CTkFrame(body, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", padx=body._pyla_padx, pady=(body._pyla_pady, int(8 * scale_factor)))
        top_bar.grid_columnconfigure(0, weight=1)
        self._section_label(top_bar, "Priority").grid(row=0, column=0, sticky="w")

        selected_count_label = ctk.CTkLabel(
            top_bar,
            text="0 selected",
            font=("Segoe UI", int(12 * scale_factor), "bold"),
            text_color=self.colors['darker_white'],
        )
        selected_count_label.grid(row=0, column=1, sticky="e")

        queue_frame = ctk.CTkScrollableFrame(
            body,
            fg_color=self.colors['panel'],
            border_color=self.colors['gray'],
            border_width=1,
            corner_radius=int(10 * scale_factor),
            width=int(780 * scale_factor),
            height=int(88 * scale_factor),
            orientation="horizontal",
        )
        queue_frame.grid(row=1, column=0, sticky="ew", padx=body._pyla_padx, pady=(0, int(14 * scale_factor)))

        self._section_label(body, "Brawlers").grid(
            row=2,
            column=0,
            sticky="w",
            padx=body._pyla_padx,
            pady=(0, int(8 * scale_factor)),
        )

        grid_frame = ctk.CTkScrollableFrame(
            body,
            fg_color=self.colors['dark gray'],
            border_color=self.colors['gray'],
            border_width=1,
            corner_radius=int(10 * scale_factor),
            width=int(780 * scale_factor),
            height=int(300 * scale_factor),
            scrollbar_button_color=self.colors['panel2'],
            scrollbar_button_hover_color=self.colors['gray'],
        )
        grid_frame.grid(row=3, column=0, sticky="nsew", padx=body._pyla_padx)
        body.grid_rowconfigure(3, weight=1)

        action_frame = ctk.CTkFrame(
            body,
            fg_color="transparent",
            height=int(48 * scale_factor),
        )
        action_frame.grid(row=4, column=0, pady=(int(12 * scale_factor), int(14 * scale_factor)))
        action_frame.pack_propagate(False)

        grid_cards = {}

        def refresh_grid_state():
            queued_brawlers = set(self.push_all_priority_order)
            selected_count_label.configure(text=f"{len(queued_brawlers)} selected")
            for brawler, widgets in grid_cards.items():
                queued = brawler in queued_brawlers
                widgets["frame"].configure(
                    border_color=self.colors['cherry red'] if queued else self.colors['gray'],
                    border_width=int(2 * scale_factor) if queued else int(1 * scale_factor),
                )
                widgets["name"].configure(text=f"{brawler}{' *' if queued else ''}")

        def refresh_order_view():
            render_queue()
            refresh_grid_state()

        def render_queue():
            self._push_order_queue_frames = []
            for widget in queue_frame.winfo_children():
                widget.destroy()
            if not self.push_all_priority_order:
                ctk.CTkLabel(
                    queue_frame,
                    text="No priority order selected",
                    font=("Segoe UI", int(13 * scale_factor), "bold"),
                    text_color=self.colors['darker_white'],
                ).grid(row=0, column=0, padx=int(14 * scale_factor), pady=int(24 * scale_factor), sticky="w")
                return

            for index, brawler in enumerate(self.push_all_priority_order):
                frame = ctk.CTkFrame(
                    queue_frame,
                    fg_color=self.colors['accent_soft'],
                    border_color=self.colors['cherry red'],
                    border_width=1,
                    corner_radius=int(10 * scale_factor),
                    width=int(124 * scale_factor),
                    height=int(72 * scale_factor),
                )
                frame.grid(row=0, column=index, padx=int(6 * scale_factor), pady=int(7 * scale_factor))
                frame.grid_propagate(False)
                self._push_order_queue_frames.append(frame)

                img_tk = self.image_by_brawler.get(brawler)
                if img_tk is not None:
                    icon = ctk.CTkLabel(frame, image=img_tk, text="", width=int(44 * scale_factor), height=int(44 * scale_factor))
                    icon.place(x=int(4 * scale_factor), y=int(13 * scale_factor))
                    icon._pyla_image_ref = img_tk
                    drag_widgets = [frame, icon]
                else:
                    drag_widgets = [frame]

                label = ctk.CTkLabel(
                    frame,
                    text=f"{index + 1}. {brawler}",
                    font=("Segoe UI", int(11 * scale_factor), "bold"),
                    text_color="white",
                    width=int(60 * scale_factor),
                    anchor="w",
                )
                label.place(x=int(52 * scale_factor), y=int(18 * scale_factor))
                remove_btn = ctk.CTkButton(
                    frame,
                    text="X",
                    command=lambda b=brawler: (self.remove_push_order_brawler(b), refresh_order_view()),
                    fg_color=self.colors['panel2'],
                    hover_color=self.colors['gray'],
                    text_color=self.colors['darker_white'],
                    font=("Segoe UI", int(10 * scale_factor), "bold"),
                    width=int(20 * scale_factor),
                    height=int(20 * scale_factor),
                    corner_radius=int(6 * scale_factor),
                )
                remove_btn.place(x=int(92 * scale_factor), y=int(4 * scale_factor))

                for widget in drag_widgets + [label]:
                    widget.bind("<ButtonPress-1>", lambda event, b=brawler: self._start_push_order_drag(b))
                    widget.bind("<ButtonRelease-1>", lambda event: self._finish_push_order_drag(event, refresh_order_view))

        def render_grid():
            grid_cards.clear()
            for widget in grid_frame.winfo_children():
                widget.destroy()
            for index, (brawler, img_tk) in enumerate(self.images):
                frame = ctk.CTkFrame(
                    grid_frame,
                    fg_color=self.colors['panel'],
                    border_color=self.colors['gray'],
                    border_width=1,
                    corner_radius=int(10 * scale_factor),
                    width=int(86 * scale_factor),
                    height=int(102 * scale_factor),
                )
                frame.grid(row=index // 8, column=index % 8, padx=int(7 * scale_factor), pady=int(7 * scale_factor))
                frame.grid_propagate(False)
                label = ctk.CTkLabel(frame, image=img_tk, text="")
                label._pyla_image_ref = img_tk
                label.pack(pady=(int(5 * scale_factor), 0))
                name = ctk.CTkLabel(
                    frame,
                    text=brawler,
                    font=("Segoe UI", int(10 * scale_factor), "bold"),
                    text_color="white",
                    width=int(78 * scale_factor),
                )
                name.pack(pady=(0, int(4 * scale_factor)))
                grid_cards[brawler] = {"frame": frame, "name": name}
                for widget in (frame, label, name):
                    widget.bind("<ButtonPress-1>", lambda event, b=brawler: self._start_push_order_drag(b))
                    widget.bind("<ButtonRelease-1>", lambda event, b=brawler: self._finish_push_order_add(event, b, queue_frame, refresh_order_view))
                    widget.bind("<Double-Button-1>", lambda event, b=brawler: (self.add_push_order_brawler(b), refresh_order_view()))
            refresh_grid_state()

        self._hub_button(
            action_frame,
            "Clear Order",
            lambda: (self.push_all_priority_order.clear(), refresh_order_view()),
            width=int(120 * scale_factor),
        ).pack(side="left", padx=int(10 * scale_factor))
        self._hub_button(
            action_frame,
            "Done",
            top.destroy,
            primary=True,
            width=int(110 * scale_factor),
        ).pack(side="left", padx=int(10 * scale_factor))

        render_queue()
        render_grid()

    def _start_push_order_drag(self, brawler):
        self._push_order_drag_brawler = brawler

    def _finish_push_order_add(self, event, brawler, queue_frame, refresh_order_view):
        self._push_order_drag_brawler = None
        try:
            x = event.widget.winfo_pointerx()
            y = event.widget.winfo_pointery()
            inside_queue = (
                queue_frame.winfo_rootx() <= x <= queue_frame.winfo_rootx() + queue_frame.winfo_width()
                and queue_frame.winfo_rooty() <= y <= queue_frame.winfo_rooty() + queue_frame.winfo_height()
            )
        except Exception:
            inside_queue = False
        if inside_queue:
            self.add_push_order_brawler(brawler)
            refresh_order_view()

    def _finish_push_order_drag(self, event, refresh_order_view):
        brawler = self._push_order_drag_brawler
        self._push_order_drag_brawler = None
        if not brawler:
            return
        try:
            pointer_x = event.widget.winfo_pointerx()
        except Exception:
            return
        if self.move_push_order_brawler(brawler, self.push_order_drop_index(pointer_x)):
            refresh_order_view()

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
            row["automatically_pick"] = True
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
        self._configure_frameless_window(top)
        top.title("Push All Target")
        top.attributes("-topmost", True)
        win_w = int(390 * scale_factor)
        win_h = int(300 * scale_factor)
        top.geometry(f"{win_w}x{win_h}+{str(int(950 * scale_factor))}+{str(int(260 * scale_factor))}")
        self._create_window_chrome(top, "Push All Target", top.destroy)

        body = self._modal_body(top, padx=22, pady=18)
        self._section_label(body, "Target Trophies").grid(
            row=0,
            column=0,
            sticky="w",
            padx=body._pyla_padx,
            pady=(body._pyla_pady, int(12 * scale_factor)),
        )

        button_frame = ctk.CTkFrame(
            body,
            fg_color=self.colors['panel'],
            border_color=self.colors['gray'],
            border_width=1,
            corner_radius=int(10 * scale_factor),
        )
        button_frame.grid(row=1, column=0, padx=body._pyla_padx, sticky="ew")
        button_frame.grid_columnconfigure((0, 1), weight=1)

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
            self._hub_button(
                button_frame,
                str(target),
                lambda t=target: choose_target(t),
                width=int(120 * scale_factor),
                height=int(42 * scale_factor),
            ).grid(row=row, column=col, padx=int(10 * scale_factor), pady=int(10 * scale_factor))

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
            data = self.apply_push_all_priority_order(data)
            if not self.push_all_priority_order:
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
        self._configure_frameless_window(top)
        win_w = int(390 * scale_factor)
        win_h = int(470 * scale_factor)
        top.geometry(
            f"{win_w}x{win_h}+{str(int(1100 * scale_factor))}+{str(int(200 * scale_factor))}")
        top.title("Enter Brawler Data")
        top.attributes("-topmost", True)
        self._create_window_chrome(top, "Brawler Setup", top.destroy)

        # --- Variables ---
        push_until_var = tk.StringVar()
        trophies_var = tk.StringVar()
        wins_var = tk.StringVar()
        current_win_streak_var = tk.StringVar(value="0")
        auto_pick_var = tk.BooleanVar(value=True) if self.brawlers_data else tk.BooleanVar(value=False)
        api_trophies = self.get_api_trophies_for_brawler(brawler)
        if api_trophies is not None:
            trophies_var.set(str(api_trophies))

        body = self._modal_body(top, padx=22, pady=16)
        card = ctk.CTkFrame(
            body,
            fg_color=self.colors['panel'],
            border_color=self.colors['gray'],
            border_width=1,
            corner_radius=int(10 * scale_factor),
        )
        card.grid(row=0, column=0, padx=body._pyla_padx, pady=body._pyla_pady, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=brawler.title(),
            font=("Segoe UI", int(18 * scale_factor), "bold"),
            text_color=self.colors['chess white'],
        ).grid(row=0, column=0, pady=(int(16 * scale_factor), int(10 * scale_factor)))

        farm_type_button_frame = ctk.CTkFrame(card, fg_color="transparent")
        farm_type_button_frame.grid(row=1, column=0, pady=(0, int(14 * scale_factor)))

        fields_frame = ctk.CTkFrame(card, fg_color="transparent")
        fields_frame.grid(row=2, column=0, sticky="ew", padx=int(18 * scale_factor))
        fields_frame.grid_columnconfigure(0, weight=1)
        entry_width = int(230 * scale_factor)

        def form_label(text):
            return ctk.CTkLabel(
                fields_frame,
                text=text,
                font=("Segoe UI", int(12 * scale_factor), "bold"),
                text_color=self.colors['darker_white'],
                anchor="w",
            )

        push_until_label = form_label("Target Amount")
        push_until_entry = ctk.CTkEntry(
            fields_frame, textvariable=push_until_var, fg_color=self.colors['dark gray'], text_color="white",
            border_color=self.colors['gray'], border_width=1, corner_radius=int(8 * scale_factor),
            height=int(34 * scale_factor), width=entry_width
        )

        trophies_label = form_label("Current Trophies")
        trophies_entry = ctk.CTkEntry(
            fields_frame, textvariable=trophies_var, fg_color=self.colors['dark gray'], text_color="white",
            border_color=self.colors['gray'], border_width=1, corner_radius=int(8 * scale_factor),
            height=int(34 * scale_factor), width=entry_width
        )

        wins_label = form_label("Current Wins")
        wins_entry = ctk.CTkEntry(
            fields_frame, textvariable=wins_var, fg_color=self.colors['dark gray'], text_color="white",
            border_color=self.colors['gray'], border_width=1, corner_radius=int(8 * scale_factor),
            height=int(34 * scale_factor), width=entry_width
        )

        win_streak_label = form_label("Current Win Streak")
        current_win_streak_entry = ctk.CTkEntry(
            fields_frame, textvariable=current_win_streak_var, fg_color=self.colors['dark gray'], text_color="white",
            border_color=self.colors['gray'], border_width=1, corner_radius=int(8 * scale_factor),
            height=int(34 * scale_factor), width=entry_width
        )

        auto_pick_checkbox = ctk.CTkCheckBox(
            card, text="Auto select brawler", variable=auto_pick_var,
            fg_color=self.colors['cherry red'], hover_color=self.colors['red'],
            border_color=self.colors['gray'], text_color="white",
            font=("Segoe UI", int(12 * scale_factor), "bold"),
            checkbox_height=int(22 * scale_factor), checkbox_width=int(22 * scale_factor),
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

        submit_button = self._hub_button(card, "Submit", submit_data, primary=True, width=int(116 * scale_factor), height=int(38 * scale_factor))

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
                w.grid_forget()

        def add_field(row, label, entry):
            label.grid(row=row * 2, column=0, sticky="w", pady=(0, int(4 * scale_factor)))
            entry.grid(row=row * 2 + 1, column=0, pady=(0, int(12 * scale_factor)))

        def check_submit_visibility():
            """Show submit only when push type is selected and required numeric fields are filled."""
            if self.farm_type == "":
                submit_button.grid_forget()
                return
            target_ok = push_until_var.get().isdigit()
            if self.farm_type == "trophies":
                fields_ok = target_ok and trophies_var.get().isdigit() and current_win_streak_var.get().isdigit()
            else:  # wins
                fields_ok = target_ok and wins_var.get().isdigit()
            if fields_ok:
                submit_button.grid(row=4, column=0, pady=(int(10 * scale_factor), int(16 * scale_factor)))
            else:
                submit_button.grid_forget()

        # Trace all entry vars to re-check submit visibility on every keystroke
        push_until_var.trace_add("write", lambda *a: check_submit_visibility())
        trophies_var.trace_add("write", lambda *a: check_submit_visibility())
        wins_var.trace_add("write", lambda *a: check_submit_visibility())
        current_win_streak_var.trace_add("write", lambda *a: check_submit_visibility())

        def show_trophies_fields():
            hide_all_fields()
            self.farm_type = "trophies"
            self.wins_button.configure(fg_color=self.colors['panel'])
            self.trophies_button.configure(fg_color=self.colors['cherry red'])
            add_field(0, push_until_label, push_until_entry)
            add_field(1, trophies_label, trophies_entry)
            add_field(2, win_streak_label, current_win_streak_entry)
            auto_pick_checkbox.grid(row=3, column=0, pady=(0, int(4 * scale_factor)))
            check_submit_visibility()

        def show_wins_fields():
            hide_all_fields()
            self.farm_type = "wins"
            self.wins_button.configure(fg_color=self.colors['cherry red'])
            self.trophies_button.configure(fg_color=self.colors['panel'])
            add_field(0, push_until_label, push_until_entry)
            add_field(1, wins_label, wins_entry)
            auto_pick_checkbox.grid(row=3, column=0, pady=(int(8 * scale_factor), int(4 * scale_factor)))
            check_submit_visibility()

        self.wins_button = self._hub_button(farm_type_button_frame, "Win Amount", show_wins_fields, width=int(96 * scale_factor))
        self.trophies_button = self._hub_button(farm_type_button_frame, "Trophies", show_trophies_fields, width=int(88 * scale_factor))

        self.trophies_button.grid(row=0, column=0, padx=int(5 * scale_factor))
        self.wins_button.grid(row=0, column=1, padx=int(5 * scale_factor))


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
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        matches = [
            (brawler, img_tk)
            for brawler, img_tk in self.images
            if normalize_brawler_name(brawler).startswith(normalize_brawler_name(filter_text))
        ]

        def render_batch(start_index=0):
            if self._closing:
                return
            for index in range(start_index, min(start_index + 16, len(matches))):
                brawler, img_tk = matches[index]
                row_num = index // 6
                col_num = index % 6
                card = ctk.CTkFrame(
                    self.grid_frame,
                    fg_color=self.colors['panel'],
                    border_color=self.colors['border_soft'],
                    border_width=1,
                    corner_radius=int(12 * scale_factor),
                    width=int(112 * scale_factor),
                    height=int(108 * scale_factor),
                )
                card._pyla_role = "BrawlerCard"
                card.grid(row=row_num, column=col_num, padx=int(6 * scale_factor), pady=int(7 * scale_factor))
                card.grid_propagate(False)

                label = ctk.CTkLabel(card, image=img_tk, text="")
                label._pyla_image_ref = img_tk
                self.visible_image_labels.append(label)
                label.pack(pady=(int(9 * scale_factor), int(4 * scale_factor)))

                name = ctk.CTkLabel(
                    card,
                    text=brawler.replace("_", " ").title(),
                    font=("Segoe UI", int(11 * scale_factor), "bold"),
                    text_color=self.colors['chess white'],
                    width=int(96 * scale_factor),
                    height=int(18 * scale_factor),
                )
                name.pack()

                def enter(_event, current_card=card):
                    current_card.configure(
                        fg_color=self.colors['accent_soft'],
                        border_color=self.colors['accent_border'],
                    )

                def leave(_event, current_card=card):
                    current_card.configure(
                        fg_color=self.colors['panel'],
                        border_color=self.colors['border_soft'],
                    )

                for widget in (card, label, name):
                    widget.bind("<Button-1>", lambda _event, b=brawler: self.on_image_click(b))
                    widget.bind("<Enter>", enter)
                    widget.bind("<Leave>", leave)
            next_index = start_index + 16
            if next_index < len(matches):
                self._image_render_after_id = self.app.after(1, lambda: render_batch(next_index))
            else:
                self._image_render_after_id = None

        render_batch()

def dummy_data_setter(data):
    print("Data set:", data)
