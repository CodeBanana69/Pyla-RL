import customtkinter as ctk
import asyncio
import subprocess
import sys
import threading
import webbrowser
import os
import pyautogui
from pathlib import Path
from PIL import Image
import tkinter as tk
from utils import load_toml_as_dict, save_dict_as_toml, get_discord_link, get_dpi_scale
from packaging import version
from performance_profile import apply_performance_profile
from discord_notifier import async_send_test_notification
from gui import theme

orig_screen_width, orig_screen_height = 1920, 1080
width, height = pyautogui.size()
width_ratio = width / orig_screen_width
height_ratio = height / orig_screen_height
scale_factor = min(width_ratio, height_ratio)
scale_factor *= 96/get_dpi_scale()

def S(value):
    """Helper to scale integer sizes based on the user's screen."""
    return int(value * scale_factor)


class Hub:
    """
    Updated, more user-friendly interface for the PylaAi-XXZ bot.
    """

    def __init__(self,
                 version_str,
                 latest_version_str,
                 correct_zoom=True,
                 on_close_callback=None):

        self.version_str = version_str
        self.latest_version_str = latest_version_str
        self.correct_zoom = correct_zoom
        self.on_close_callback = on_close_callback

        # -----------------------------------------------------------------------------------------
        # Load configs
        # -----------------------------------------------------------------------------------------
        self.bot_config_path = "cfg/bot_config.toml"
        self.time_tresholds_path = "cfg/time_tresholds.toml"
        self.match_history_path = "cfg/match_history.toml"
        self.general_config_path = "cfg/general_config.toml"
        self.webhook_config_path = "cfg/discord_config.toml"
        legacy_webhook_config_path = "cfg/webhook_config.toml"

        self.bot_config = load_toml_as_dict(self.bot_config_path)
        self.time_tresholds = load_toml_as_dict(self.time_tresholds_path)
        self.match_history = load_toml_as_dict(self.match_history_path)
        self.general_config = load_toml_as_dict(self.general_config_path)
        if not Path(self.webhook_config_path).exists() and Path(legacy_webhook_config_path).exists():
            self.webhook_config = load_toml_as_dict(legacy_webhook_config_path)
            save_dict_as_toml(self.webhook_config, self.webhook_config_path)
        else:
            self.webhook_config = load_toml_as_dict(self.webhook_config_path)

        # -----------------------------------------------------------------------------------------
        # Defaults
        # -----------------------------------------------------------------------------------------
        # Bot config defaults
        self.bot_config.setdefault("gamemode_type", 3)
        self.bot_config.setdefault("gamemode", "brawlball")
        self.bot_config.setdefault("bot_uses_gadgets", "yes")
        self.bot_config.setdefault("minimum_movement_delay", 0.4)
        self.bot_config.setdefault("wall_detection_confidence", 0.9)
        self.bot_config.setdefault("entity_detection_confidence", 0.6)
        self.bot_config.setdefault("projectile_detection_confidence", 0.55)
        self.bot_config.setdefault("projectile_yolo_confidence", 0.35)
        self.bot_config.setdefault("projectile_tracker_backend", "bytetrack")
        self.bot_config.setdefault("intercept_confirm_enabled", "yes")
        self.bot_config.setdefault("unstuck_movement_delay", 3.0)
        self.bot_config.setdefault("unstuck_movement_hold_time", 1.5)
        self.bot_config.setdefault("play_again_on_win", "no")
        self.bot_config.setdefault("current_playstyle", "default.pyla")
        self.bot_config.setdefault("use_rl_movement", "no")
        self.bot_config.setdefault("enable_rl_movement_training", "no")
        self.bot_config.setdefault("rl_algorithm", "sac")
        self.bot_config.setdefault("rl_record_transitions", self.bot_config.get("enable_rl_movement_training", "no"))
        self.bot_config.setdefault("rl_replay_dir", "data/rl_replay")
        self.bot_config.setdefault("rl_replay_disk_budget_mb", 2048)
        self.bot_config.setdefault("rl_replay_batch_size", 1000)
        self.bot_config.setdefault("rl_replay_flush_seconds", 30.0)
        self.bot_config.setdefault("rl_frame_stack", 1)
        self.bot_config.setdefault("rl_obs_use_hp", "yes")
        self.bot_config.setdefault("rl_obs_use_fog", "yes")
        self.bot_config.setdefault("rl_obs_use_walls", "yes")
        self.bot_config.setdefault("rl_obs_use_super", "yes")
        self.bot_config.setdefault("rl_fog_ray_max_px", 200.0)
        self.bot_config.setdefault("rl_fog_ray_step_px", 4.0)
        self.bot_config.setdefault("rl_damage_lookback_norm_seconds", 5.0)
        self.bot_config.setdefault("rl_hp_potential_coef", 1.0)
        self.bot_config.setdefault("rl_stationary_penalty", 0.05)
        self.bot_config.setdefault("rl_stationary_need_seconds", 2.0)
        self.bot_config.setdefault("rl_stationary_small_action_mag", 0.1)
        self.bot_config.setdefault("rl_wall_hug_penalty", 0.05)
        self.bot_config.setdefault("rl_wall_hug_min_walls", 3)
        self.bot_config.setdefault("rl_fog_proximity_penalty", 0.10)
        self.bot_config.setdefault("rl_fog_proximity_threshold", 0.15)
        self.bot_config.setdefault("rl_sac_gamma", 0.97)
        self.bot_config.setdefault("rl_movement_model_path", "models/rl_movement_policy.zip")
        self.bot_config.setdefault("rl_use_projectile_features", "yes")
        self.bot_config.setdefault("rl_show_projectile_debug", "yes")
        self.bot_config.setdefault("rl_use_hp_drop_penalty", "no")
        self.bot_config.setdefault("showdown_playstyle_mode", "hide")
        self.bot_config.setdefault("teammate_lock_max_jump", 320)
        self.bot_config.setdefault("teammate_follow_step_distance", 8)
        self.bot_config.setdefault("teammate_combat_bias", 0.75)
        self.bot_config.setdefault("teammate_follow_force_direct", "yes")
        self.bot_config.setdefault("teammate_marker_follow_enabled", "yes")
        self.bot_config.setdefault("teammate_marker_edge_margin", 0.28)
        self.bot_config.setdefault("jump_pad_detection_enabled", "yes")
        self.bot_config.setdefault("jump_pad_escape_distance", 620)
        self.bot_config.setdefault("jump_pad_escape_min_distance", 55)
        self.bot_config.setdefault("jump_pad_escape_requires_edge", "yes")
        self.bot_config.setdefault("jump_pad_escape_edge_margin", 0.22)
        self.bot_config.setdefault("jump_pad_escape_teammate_safe_distance", 360)
        self.bot_config.setdefault("jump_pad_smoke_early_distance", 230)
        self.bot_config.setdefault("health_ocr_primary", "yes")
        self.bot_config.setdefault("health_ocr_poll_hz", 5.0)
        self.bot_config.setdefault("health_ocr_run_in_thread", "auto")
        self.bot_config.setdefault("health_ocr_full_hp_lock_repeats", 2)
        self.bot_config.setdefault("health_ocr_min_confidence", 0.35)
        self.bot_config.setdefault("health_ocr_log_terminal", "yes")
        self.bot_config.setdefault("health_ocr_damage_drop_min", 1)
        self.bot_config.setdefault("health_hsv_fallback_enabled", "yes")

        # Time thresholds defaults
        self.time_tresholds.setdefault("state_check", 3)
        self.time_tresholds.setdefault("no_detections", 10)
        self.time_tresholds.setdefault("idle", 10)
        self.time_tresholds.setdefault("super", 0.1)
        self.time_tresholds.setdefault("gadget", 0.5)
        self.time_tresholds.setdefault("hypercharge", 2)

        # General config defaults
        self.general_config.setdefault("max_ips", "auto")
        self.general_config.setdefault("scrcpy_max_fps", 15)
        self.general_config.setdefault("onnx_cpu_threads", "auto")
        self.general_config.setdefault("used_threads", self.general_config.get("onnx_cpu_threads", "auto"))
        self.general_config.setdefault("super_debug", "no")
        self.general_config.setdefault("cpu_or_gpu", "auto")
        self.general_config.setdefault("directml_device_id", "auto")
        self.general_config.setdefault("long_press_star_drop", "no")
        self.general_config.setdefault("easyocr_torch_gpu", "auto")
        self.general_config.setdefault(
            "starr_nova_long_press_seconds", [1.9, 2.85, 3.95, 9.5]
        )
        self.general_config.setdefault("trophies_multiplier", 1.0)
        self.general_config.setdefault("ocr_scale_down_factor", 0.5)
        self.general_config.setdefault("current_emulator", "LDPlayer")
        self.general_config.setdefault("emulator_port", 5555)
        self.general_config.setdefault("terminal_logging", "no")
        self.general_config.setdefault("visual_debug", "no")
        self.general_config.setdefault("visual_debug_scale", 0.6)
        self.general_config.setdefault("visual_debug_max_fps", 30)
        self.general_config.setdefault("visual_debug_max_boxes", 120)
        self.general_config.setdefault("visual_debug_motion_boxes", "no")
        self.general_config.setdefault("capture_bad_vision_frames", "no")
        self.general_config.setdefault("pause_menu_ips_tracker", "yes")

        self.webhook_config.setdefault("webhook_url", self.general_config.get("personal_webhook", ""))
        self.webhook_config.setdefault("discord_id", self.general_config.get("discord_id", ""))
        self.webhook_config.setdefault("username", "PylaAi-XXZ")
        self.webhook_config.setdefault("send_match_summary", False)
        self.webhook_config.setdefault("include_screenshot", True)
        self.webhook_config.setdefault("ping_when_stuck", False)
        self.webhook_config.setdefault("ping_when_target_is_reached", False)
        self.webhook_config.setdefault("ping_every_x_match", 0)
        self.webhook_config.setdefault("ping_every_x_minutes", 0)
        self.webhook_config.setdefault("discord_control_enabled", False)
        self.webhook_config.setdefault("discord_bot_token", "")
        self.webhook_config.setdefault("discord_control_user_id", "")
        self.webhook_config.setdefault("discord_control_channel_id", "")
        self.webhook_config.setdefault("discord_control_guild_id", "")

        # -----------------------------------------------------------------------------------------
        # Appearance
        # -----------------------------------------------------------------------------------------
        ctk.set_appearance_mode("dark")

        # For showing tooltips in Toplevel windows
        # For showing tooltips
        self.tooltip_window = None
        self._tooltip_after_id = None
        self._tooltip_owner = None
        self._tooltip_text = ""

        # -----------------------------------------------------------------------------------------
        # Main window
        # -----------------------------------------------------------------------------------------
        self.app = ctk.CTk()
        self.app.title(f"PylaAi-XXZ Hub – {self.version_str}")
        self.app.geometry(f"{S(1180)}x{S(780)}")
        self.app.resizable(False, False)
        self.app.configure(fg_color=theme.BG)

        # Hide tooltip on "global" interactions (tab switch, clicks, scroll, key press, focus loss, etc.)
        for seq in ("<ButtonPress>", "<MouseWheel>", "<KeyPress>", "<FocusOut>"):
            self.app.bind_all(seq, self._hide_tooltip, add="+")
        self.app.bind("<Configure>", self._hide_tooltip, add="+")  # window move/resize

        # -----------------------------------------------------------------------------------------
        # Header + main TabView
        # -----------------------------------------------------------------------------------------
        main_area = ctk.CTkFrame(self.app, fg_color="transparent")
        main_area.pack(fill="both", expand=True, padx=S(12), pady=S(12))

        header = ctk.CTkFrame(main_area, fg_color="transparent")
        header.pack(fill="x", pady=(0, S(8)))

        ctk.CTkLabel(
            header,
            text="pyla",
            font=theme.ui_font(S(26), "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).pack(side="left", padx=(S(4), S(10)))

        ctk.CTkLabel(
            header,
            text="PylaAi-XXZ Hub",
            font=theme.ui_font(S(13)),
            text_color=theme.TEXT_SECONDARY,
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text=f"v{self.version_str}",
            font=theme.ui_font(S(13)),
            text_color=theme.TEXT_MUTED,
        ).pack(side="right", padx=S(8))

        self.tabview = ctk.CTkTabview(
            main_area,
            width=S(1140),
            height=S(690),
            corner_radius=S(20),
            fg_color=theme.CARD,
            border_width=1,
            border_color=theme.CARD_BORDER,
        )
        self.tabview.pack(fill="both", expand=True)

        # Pill-style segmented tabs (purple selected segment; shared text color for readability)
        self.tabview._segmented_button.configure(
            corner_radius=S(14),
            border_width=0,
            fg_color=theme.CARD,
            selected_color=theme.ACCENT,
            selected_hover_color=theme.ACCENT_HOVER,
            unselected_color=theme.INACTIVE,
            unselected_hover_color=theme.INACTIVE_HOVER,
            text_color=theme.TEXT_PRIMARY,
            font=theme.ui_font(S(15), "bold"),
            height=S(42),
        )

        # Add tabs
        self.tab_overview = self.tabview.add("Overview")
        self.tab_additional = self.tabview.add("Additional Settings")
        self.tab_webhook = self.tabview.add("Discord")
        self.tab_timers = self.tabview.add("Timers")
        self.tab_history = self.tabview.add("Match History")

        # Init each tab
        self._init_overview_tab()
        self._init_additional_tab()
        self._init_webhook_tab()
        self._init_timers_tab()
        self._init_history_tab()

        # Main loop
        self.app.mainloop()

    # ---------------------------------------------------------------------------------------------
    #  Tooltip Handler
    # ---------------------------------------------------------------------------------------------
    def _pointer_over_widget(self, widget) -> bool:
        if widget is None or not widget.winfo_exists():
            return False
        try:
            px, py = widget.winfo_pointerx(), widget.winfo_pointery()
            x, y = widget.winfo_rootx(), widget.winfo_rooty()
            w, h = widget.winfo_width(), widget.winfo_height()
            return x <= px <= x + w and y <= py <= y + h
        except tk.TclError:
            return False

    def _hide_tooltip(self, _event=None):
        # cancel delayed show if pending
        if self._tooltip_after_id is not None:
            try:
                self.app.after_cancel(self._tooltip_after_id)
            except Exception:
                pass
            self._tooltip_after_id = None

        # destroy current tooltip window
        if self.tooltip_window is not None:
            try:
                self.tooltip_window.destroy()
            except Exception:
                pass
            self.tooltip_window = None

        self._tooltip_owner = None
        self._tooltip_text = ""

    def attach_tooltip(self, widget, text, delay_ms: int = 250):
        """
        Robust tooltip:
        - shows after delay
        - hides on Leave, Unmap (tab switch), Destroy, clicks/scroll/keys (via global binds)
        - prevents stuck tooltips when switching tabs
        """

        def schedule_show(event=None):
            # reset any existing tooltip
            self._hide_tooltip()

            self._tooltip_owner = widget
            self._tooltip_text = text

            def do_show():
                # widget may have disappeared / tab switched
                if (self._tooltip_owner is None
                        or not self._tooltip_owner.winfo_exists()
                        or not self._tooltip_owner.winfo_viewable()
                        or not self._pointer_over_widget(self._tooltip_owner)):
                    self._hide_tooltip()
                    return

                # create tooltip
                self.tooltip_window = ctk.CTkToplevel(self.app)
                self.tooltip_window.overrideredirect(True)
                self.tooltip_window.attributes("-topmost", True)

                # position near cursor
                px = self.app.winfo_pointerx()
                py = self.app.winfo_pointery()
                self.tooltip_window.geometry(f"+{px + 12}+{py + 12}")

                label = ctk.CTkLabel(
                    self.tooltip_window,
                    text=self._tooltip_text,
                    fg_color=theme.INACTIVE,
                    text_color=theme.TEXT_PRIMARY,
                    corner_radius=S(8),
                    font=theme.ui_font(S(12)),
                )
                label.pack(padx=S(6), pady=S(4))

                # if mouse enters tooltip itself, hide (avoids "stuck" hovering on tooltip)
                self.tooltip_window.bind("<Enter>", self._hide_tooltip)
                self.tooltip_window.bind("<Leave>", self._hide_tooltip)

            self._tooltip_after_id = self.app.after(delay_ms, do_show)

        def on_leave(_event=None):
            self._hide_tooltip()

        # Bindings
        widget.bind("<Enter>", schedule_show, add="+")
        widget.bind("<Leave>", on_leave, add="+")
        widget.bind("<Unmap>", on_leave, add="+")  # IMPORTANT: tab switching / frame hidden
        widget.bind("<Destroy>", on_leave, add="+")  # safety
        widget.bind("<ButtonPress>", on_leave, add="+")  # click on the widget -> hide

    def _launch_train_rl_offline(self) -> None:
        """Spawn offline SAC trainer (replay .npz → gradient steps)."""
        hub_dir = Path(__file__).resolve().parent
        root = hub_dir.parent
        script = root / "tools" / "train_rl_offline.py"
        if not script.is_file():
            print(f"[Hub] Missing {script}")
            return
        rep = str(self.bot_config.get("rl_replay_dir", "data/rl_replay"))
        mod = str(self.bot_config.get("rl_movement_model_path", "models/rl_movement_policy.zip"))
        gam = str(self.bot_config.get("rl_sac_gamma", 0.97))
        cmd = [
            sys.executable,
            str(script),
            "--replay-dir",
            os.path.expandvars(os.path.expanduser(rep)),
            "--model-path",
            os.path.expandvars(os.path.expanduser(mod)),
            "--total-steps",
            "200000",
            "--gamma",
            gam,
            "--tensorboard",
            str(root / "runs" / "rl_sac"),
            "--device",
            "auto",
        ]
        cwd = str(root)
        cf = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if sys.platform == "win32" else 0
        try:
            subprocess.Popen(cmd, cwd=cwd, creationflags=cf)
        except Exception as exc:
            print(f"[Hub] Could not launch offline trainer: {exc}")

    # ---------------------------------------------------------------------------------------------
    #  Overview Tab
    # ---------------------------------------------------------------------------------------------
    def _init_overview_tab(self):
        frame = self.tab_overview

        outer = ctk.CTkFrame(frame, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=S(10), pady=S(10))
        outer.grid_columnconfigure(0, weight=2)
        outer.grid_columnconfigure(1, weight=1)

        left_card = ctk.CTkFrame(
            outer,
            fg_color=theme.CARD,
            corner_radius=S(20),
            border_width=1,
            border_color=theme.CARD_BORDER,
        )
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, S(8)), pady=0)

        right_card = ctk.CTkFrame(
            outer,
            fg_color=theme.CARD,
            corner_radius=S(20),
            border_width=1,
            border_color=theme.CARD_BORDER,
        )
        right_card.grid(row=0, column=1, sticky="new", padx=(S(8), 0), pady=0)

        container = ctk.CTkFrame(left_card, fg_color="transparent")
        container.pack(expand=True, fill="both", padx=S(18), pady=S(18))

        row_ = 0

        # -----------------------------------------------------------------
        # 1) Warnings at the top (bigger, red), if any
        # -----------------------------------------------------------------
        w_list = []
        if not self.correct_zoom:
            w_list.append("Warning: Your Windows zoom isn't 100% (DPI != 96).")
        if self.latest_version_str and version.parse(self.version_str) < version.parse(self.latest_version_str):
            w_list.append(f"Warning: You are not on the latest version ({self.latest_version_str}).")

        if w_list:
            warn_text = "\n".join(w_list)
            warn_label = ctk.CTkLabel(
                container,
                text=warn_text,
                text_color=theme.ERROR,
                font=theme.ui_font(S(16), "bold"),
            )
            warn_label.grid(row=row_, column=0, columnspan=2, pady=S(10))
            row_ += 1

        # -----------------------------------------------------------------
        # 2) Map Orientation selection
        # -----------------------------------------------------------------
        self.gamemode_type_var = tk.IntVar(value=self.bot_config["gamemode_type"])

        orientation_frame = ctk.CTkFrame(container, fg_color="transparent")
        orientation_frame.grid(row=row_, column=0, columnspan=2, pady=S(10))

        label_type = ctk.CTkLabel(
            orientation_frame,
            text="Map Orientation:",
            font=theme.ui_font(S(20), "bold"),
        )
        label_type.pack(side="left", padx=S(15))

        def set_gamemode_type(t):
            """Only change the local var & refresh everything so frames swap."""
            self.gamemode_type_var.set(t)
            self._refresh_gamemode_buttons()

        self.btn_type_vertical = ctk.CTkButton(
            orientation_frame,
            text="Vertical",
            command=lambda: set_gamemode_type(3),
            font=theme.ui_font(S(16), "bold"),
            corner_radius=S(12),
            width=S(120),
            height=S(40),
        )
        self.btn_type_vertical.pack(side="left", padx=S(10))

        self.btn_type_horizontal = ctk.CTkButton(
            orientation_frame,
            text="Horizontal",
            command=lambda: set_gamemode_type(5),
            font=theme.ui_font(S(16), "bold"),
            corner_radius=S(12),
            width=S(120),
            height=S(40),
        )
        self.btn_type_horizontal.pack(side="left", padx=S(10))

        row_ += 1

        # -----------------------------------------------------------------
        # 3) Gamemode Selection as rectangular buttons
        # -----------------------------------------------------------------
        gm_label = ctk.CTkLabel(container, text="Select Gamemode:", font=theme.ui_font(S(20), "bold"))
        gm_label.grid(row=row_, column=0, columnspan=2, pady=S(10))
        row_ += 1

        gm_buttons_frame = ctk.CTkFrame(container, fg_color="transparent")
        gm_buttons_frame.grid(row=row_, column=0, columnspan=2, pady=S(10))

        self.gm3_frame = ctk.CTkFrame(gm_buttons_frame, fg_color="transparent")
        self.gm5_frame = ctk.CTkFrame(gm_buttons_frame, fg_color="transparent")

        self.gamemode_var = tk.StringVar(value=self.bot_config["gamemode"])

        def create_gamemode_button(parent, gm_value, text_display, disabled=False, orientation=3):
            """Creates a rectangular toggle button for a gamemode."""

            def on_click():
                if disabled:
                    return
                # Set orientation + gamemode in config
                self.bot_config["gamemode_type"] = orientation
                self.bot_config["gamemode"] = gm_value
                save_dict_as_toml(self.bot_config, self.bot_config_path)

                self.gamemode_type_var.set(orientation)
                self.gamemode_var.set(gm_value)
                self._refresh_gamemode_buttons()

            btn = ctk.CTkButton(
                parent,
                text=text_display,
                command=on_click,
                corner_radius=S(12),
                width=S(150),
                height=S(40),
                font=theme.ui_font(S(16), "bold"),
                state=("disabled" if disabled else "normal"),
            )
            return btn

        # For type=3 (vertical)
        self.rb_brawlball_3 = create_gamemode_button(
            self.gm3_frame, "brawlball", "Brawlball", orientation=3
        )
        self.rb_showdown_3 = create_gamemode_button(
            self.gm3_frame, "showdown", "Showdown Trio", orientation=3
        )
        self.rb_other_3 = create_gamemode_button(
            self.gm3_frame, "other", "Other", orientation=3
        )

        self.rb_brawlball_3.grid(row=0, column=0, padx=S(10), pady=S(5))
        self.rb_showdown_3.grid(row=0, column=1, padx=S(10), pady=S(5))
        self.rb_other_3.grid(row=0, column=2, padx=S(10), pady=S(5))

        # For type=5 (horizontal)
        self.rb_basketbrawl_5 = create_gamemode_button(
            self.gm5_frame, "basketbrawl", "Basket Brawl", orientation=5
        )
        self.rb_bb5v5_5 = create_gamemode_button(
            self.gm5_frame, "brawlball_5v5", "Brawlball 5v5", orientation=5
        )

        self.rb_basketbrawl_5.grid(row=0, column=0, padx=S(10), pady=S(5))
        self.rb_bb5v5_5.grid(row=0, column=1, padx=S(10), pady=S(5))

        def refresh_gm_buttons():
            """Refresh button colors to highlight the currently selected gamemode."""
            gm_now = self.gamemode_var.get()

            def set_button_color(btn, val):
                if val == gm_now:
                    btn.configure(fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER)
                else:
                    btn.configure(fg_color=theme.INACTIVE, hover_color=theme.INACTIVE_HOVER)

            # For vertical set
            set_button_color(self.rb_brawlball_3, "brawlball")
            set_button_color(self.rb_showdown_3, "showdown")
            set_button_color(self.rb_other_3, "other")

            # For horizontal set
            set_button_color(self.rb_basketbrawl_5, "basketbrawl")
            set_button_color(self.rb_bb5v5_5, "brawlball_5v5")

        def refresh_orientation_buttons():
            """Refresh the orientation buttons' color based on self.gamemode_type_var."""
            t = self.gamemode_type_var.get()
            if t == 3:
                self.btn_type_vertical.configure(fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER)
                self.btn_type_horizontal.configure(fg_color=theme.INACTIVE, hover_color=theme.INACTIVE_HOVER)
            else:
                self.btn_type_vertical.configure(fg_color=theme.INACTIVE, hover_color=theme.INACTIVE_HOVER)
                self.btn_type_horizontal.configure(fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER)

        self._refresh_orientation_buttons = refresh_orientation_buttons

        def _refresh_gm_frames():
            """Show/hide frames depending on orientation."""
            self.gm3_frame.pack_forget()
            self.gm5_frame.pack_forget()

            if self.gamemode_type_var.get() == 3:
                self.gm3_frame.pack(side="top")
            else:
                self.gm5_frame.pack(side="top")

        def full_refresh():
            self._refresh_orientation_buttons()
            _refresh_gm_frames()
            refresh_gm_buttons()

        self._refresh_gamemode_buttons = full_refresh
        full_refresh()

        row_ += 1

        # -----------------------------------------------------------------
        # 4) Emulator Selection
        # -----------------------------------------------------------------
        emulator_label = ctk.CTkLabel(container, text="Select Emulator:", font=theme.ui_font(S(20), "bold"))
        emulator_label.grid(row=row_, column=0, columnspan=2, pady=S(10))
        row_ += 1

        self.emulator_frame = ctk.CTkFrame(container, fg_color="transparent")
        self.emulator_frame.grid(row=row_, column=0, columnspan=2, pady=S(10))
        row_ += 1

        supported_emulators = {
            "LDPlayer": 5555,
            "MuMu": 16384,
        }

        def infer_supported_emulator(configured_port):
            try:
                configured_port = int(configured_port)
            except (TypeError, ValueError):
                return "LDPlayer"
            if configured_port in (16384, 16416, 16448, 7555):
                return "MuMu"
            return "LDPlayer"

        current_emulator = self.general_config.get("current_emulator", "LDPlayer")
        try:
            current_port = int(self.general_config.get("emulator_port", 0))
        except (TypeError, ValueError):
            current_port = 0
        if current_emulator not in supported_emulators:
            current_emulator = infer_supported_emulator(self.general_config.get("emulator_port"))
            self.general_config["current_emulator"] = current_emulator
            self.general_config["emulator_port"] = supported_emulators[current_emulator]
            save_dict_as_toml(self.general_config, self.general_config_path)
        elif current_port == 5037:
            self.general_config["emulator_port"] = supported_emulators[current_emulator]
            save_dict_as_toml(self.general_config, self.general_config_path)

        self.emu_var = tk.StringVar(value=current_emulator)

        def handle_emulator_choice(choice):
            if choice not in supported_emulators:
                choice = "LDPlayer"
            self.emu_var.set(choice)
            self.general_config["current_emulator"] = choice
            self.general_config["emulator_port"] = supported_emulators[choice]
            save_dict_as_toml(self.general_config, self.general_config_path)
            refresh_emu_buttons()

        def create_emu_button(parent, text_display):
            def on_click():
                handle_emulator_choice(text_display)

            btn = ctk.CTkButton(
                parent,
                text=text_display,
                command=on_click,
                corner_radius=S(12),
                width=S(150),
                height=S(40),
                font=theme.ui_font(S(16), "bold"),
            )
            return btn

        self.btn_ldplayer = create_emu_button(self.emulator_frame, "LDPlayer")
        self.btn_mumu = create_emu_button(self.emulator_frame, "MuMu")

        self.btn_ldplayer.grid(row=0, column=0, padx=S(10), pady=S(5))
        self.btn_mumu.grid(row=0, column=1, padx=S(10), pady=S(5))

        def refresh_emu_buttons():
            curr_emu = self.emu_var.get()

            def color(btn, val):
                if val == curr_emu:
                    btn.configure(fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER)
                else:
                    btn.configure(fg_color=theme.INACTIVE, hover_color=theme.INACTIVE_HOVER)

            color(self.btn_ldplayer, "LDPlayer")
            color(self.btn_mumu, "MuMu")

        refresh_emu_buttons()

        # -----------------------------------------------------------------
        # Some spacing
        # -----------------------------------------------------------------
        row_ += 1

        # -----------------------------------------------------------------
        # 5) Start Button
        # -----------------------------------------------------------------
        start_button = ctk.CTkButton(
            container,
            text="Next",
            command=self._on_start,
            width=S(220),
            height=S(60),
            font=theme.ui_font(S(24), "bold"),
            **theme.primary_button_kwargs(S(14)),
        )
        start_button.grid(row=row_, column=0, columnspan=2, padx=S(20), pady=S(30))
        row_ += 1

        # -----------------------------------------------------------------
        # 6) "Pyla is free..." label at bottom, link in blue only
        # -----------------------------------------------------------------
        disclaim_frame = ctk.CTkFrame(container, fg_color="transparent")
        disclaim_frame.grid(row=row_, column=0, columnspan=2, pady=S(10))

        disclaim_label = ctk.CTkLabel(
            disclaim_frame,
            text="Pyla is free, public and open-source. Join the Discord -> ",
            font=theme.ui_font(S(18), "bold"),
            text_color=theme.TEXT_PRIMARY,
        )
        disclaim_label.pack(side="left")

        discord_link = get_discord_link()

        def open_discord_link():
            webbrowser.open(discord_link)

        link_label = ctk.CTkLabel(
            disclaim_frame,
            text=discord_link,
            font=theme.ui_font(S(18), "bold"),
            text_color=theme.SKY,
            cursor="hand2",
        )
        link_label.pack(side="left")
        link_label.bind("<Button-1>", lambda e: open_discord_link())

        row_ += 1

        ad_frame = ctk.CTkFrame(container, fg_color="transparent")
        ad_frame.grid(row=row_, column=0, columnspan=2, pady=S(10))

        ad_label = ctk.CTkLabel(
            ad_frame,
            text="Support Pyla and get Early Access to updates by becoming a Patreon supporter -> ",
            font=theme.ui_font(S(18), "bold"),
            text_color=theme.TEXT_PRIMARY,
        )
        ad_label.pack(side="left")

        shown_patreon_link = "www.patreon.com/c/pyla"
        patreon_link = "https://www.patreon.com/pyla/membership"
        def open_patreon_link():
            webbrowser.open(patreon_link)
        patreon_label = ctk.CTkLabel(
            ad_frame,
            text=shown_patreon_link,
            font=theme.ui_font(S(18), "bold"),
            text_color=theme.SKY,
            cursor="hand2",
        )
        patreon_label.pack(side="left")
        patreon_label.bind("<Button-1>", lambda e: open_patreon_link())

        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=1)

        # --- Match stats (real data from match_history.toml) ---
        ctk.CTkLabel(
            right_card,
            text="Match stats",
            font=theme.ui_font(S(18), "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).pack(anchor="w", padx=S(18), pady=(S(18), S(8)))

        total_stats = self.match_history.get("total", {})
        wins = int(total_stats.get("victory", 0))
        losses = int(total_stats.get("defeat", 0))
        draws = int(total_stats.get("draw", 0))
        games = wins + losses + draws
        win_pct = round(100 * wins / games, 1) if games else 0.0
        loss_pct = round(100 * losses / games, 1) if games else 0.0

        def add_stat_row(parent, label, value, value_color=theme.TEXT_PRIMARY):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=S(18), pady=S(6))
            ctk.CTkLabel(row, text=label, font=theme.ui_font(S(14)), text_color=theme.TEXT_SECONDARY).pack(
                side="left"
            )
            ctk.CTkLabel(
                row, text=value, font=theme.ui_font(S(14), "bold"), text_color=value_color
            ).pack(side="right")

        add_stat_row(right_card, "Games played", str(games))
        add_stat_row(right_card, "Wins", str(wins), theme.TEAL)
        add_stat_row(right_card, "Losses", str(losses), theme.ERROR)
        add_stat_row(right_card, "Draws", str(draws), theme.TEXT_SECONDARY)
        add_stat_row(right_card, "Win rate", f"{win_pct}%", theme.TEAL)
        add_stat_row(right_card, "Loss rate", f"{loss_pct}%", theme.ERROR)

        ctk.CTkLabel(
            right_card,
            text="Totals from saved match history.",
            font=theme.ui_font(S(11)),
            text_color=theme.TEXT_MUTED,
            wraplength=S(220),
        ).pack(anchor="w", padx=S(18), pady=(S(14), S(18)))

    # ---------------------------------------------------------------------------------------------
    #  Additional Settings Tab
    # ---------------------------------------------------------------------------------------------
    def _init_additional_tab(self):
        frame = self.tab_additional
        wrap = ctk.CTkFrame(frame, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=S(10), pady=S(10))
        card = ctk.CTkFrame(
            wrap,
            fg_color=theme.CARD,
            corner_radius=S(20),
            border_width=1,
            border_color=theme.CARD_BORDER,
        )
        card.pack(fill="both", expand=True)
        container = ctk.CTkScrollableFrame(card, width=S(880), height=S(600), fg_color="transparent")
        container.pack(fill="both", expand=True, padx=S(12), pady=S(12))

        # Extra space to avoid tooltip clipping
        container.grid_rowconfigure(0, minsize=S(10))

        row_idx = 0
        entry_vars = {}

        # -----------------------------------------------------------------------------------------
        # Helper to create labeled entries in either bot_config or general_config
        # -----------------------------------------------------------------------------------------
        def create_labeled_entry(label_text,
                                 config_key,
                                 convert_func,
                                 use_general_config=False,
                                 tooltip_text=None):
            nonlocal row_idx
            lbl = ctk.CTkLabel(container, text=label_text, font=theme.ui_font(S(18)))
            lbl.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))

            # Decide which dictionary to read/write
            if use_general_config:
                current_config = self.general_config
                current_path = self.general_config_path
            else:
                current_config = self.bot_config
                current_path = self.bot_config_path
            var_str = tk.StringVar(value=str(current_config[config_key]))
            entry_vars[(use_general_config, config_key)] = var_str

            def on_save(*_):
                val_str = var_str.get().strip()
                if val_str == "":
                    var_str.set(str(current_config[config_key]))
                    return
                try:
                    val = convert_func(val_str)
                    current_config[config_key] = val
                    save_dict_as_toml(current_config, current_path)
                except ValueError:
                    var_str.set(str(current_config[config_key]))

            entry = ctk.CTkEntry(
                container,
                textvariable=var_str,
                width=S(120),
                font=theme.ui_font(S(16)),
                **theme.entry_kwargs(),
            )
            entry.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
            entry.bind("<FocusOut>", on_save)
            entry.bind("<Return>", on_save)

            if tooltip_text:
                self.attach_tooltip(entry, tooltip_text)

            row_idx += 1


        # 6) Minimum Movement Delay (bot_config)
        create_labeled_entry(
            label_text="Minimum Movement Delay:",
            config_key="minimum_movement_delay",
            convert_func=float,
            use_general_config=False,
            tooltip_text="How long (in seconds) the bot must maintain a movement before changing it."
        )

        # 9) Wall Detection Confidence (bot_config)
        create_labeled_entry(
            label_text="Wall Detection Confidence:",
            config_key="wall_detection_confidence",
            convert_func=float,
            use_general_config=False,
            tooltip_text="On a scale between 0 and 1, how sure must the bot be to detect a wall  (lower means it can detect more things but increases false detections and mistakes)."
        )

        # 9) Wall Detection Confidence (bot_config)
        create_labeled_entry(
            label_text="Player/Enemy Detection Confidence:",
            config_key="entity_detection_confidence",
            convert_func=float,
            use_general_config=False,
            tooltip_text="On a scale between 0 and 1, how sure must the bot be to detect the player/enemies/allies. (lower means it can detect more things but increases false detections and mistakes)."
        )

        # Projectile Detection Confidence (bot_config) — RL fork
        create_labeled_entry(
            label_text="Projectile Detection Confidence:",
            config_key="projectile_detection_confidence",
            convert_func=float,
            use_general_config=False,
            tooltip_text="On a scale between 0 and 1, how strict the RL projectile filter is. Higher values only count projectiles clearly moving toward you. Lower lets in more candidates (more reactions but more false dodges)."
        )

        # Dedicated projectile YOLO ONNX (models/projectileDetector.onnx)
        create_labeled_entry(
            label_text="Projectile YOLO Confidence:",
            config_key="projectile_yolo_confidence",
            convert_func=float,
            use_general_config=False,
            tooltip_text="On a scale between 0 and 1, minimum score to keep a box from the dedicated projectile ONNX model. Training exports rarely exceed ~0.8; use ~0.25–0.45 for recall. This is separate from Projectile Detection Confidence (RL / incoming-angle strictness)."
        )

        lbl_bt = ctk.CTkLabel(
            container, text="Projectile tracker backend:", font=theme.ui_font(S(18))
        )
        lbl_bt.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        bt_var = tk.StringVar(
            value=str(self.bot_config.get("projectile_tracker_backend", "bytetrack")).lower()
        )

        def on_bt_change(choice):
            self.bot_config["projectile_tracker_backend"] = str(choice).lower()
            save_dict_as_toml(self.bot_config, self.bot_config_path)

        bt_menu = ctk.CTkOptionMenu(
            container,
            values=["bytetrack", "greedy"],
            command=on_bt_change,
            variable=bt_var,
            font=theme.ui_font(S(16)),
            **theme.option_menu_kwargs(S(160), S(35)),
        )
        bt_menu.grid(row=row_idx, column=1, padx=S(20), pady=S(10), sticky="w")
        row_idx += 1

        lbl_ic = ctk.CTkLabel(
            container, text="Intercept HP confirmation:", font=theme.ui_font(S(18))
        )
        lbl_ic.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        ic_var = tk.BooleanVar(
            value=str(self.bot_config.get("intercept_confirm_enabled", "yes")).lower()
            in ("yes", "true", "1")
        )

        def toggle_intercept_confirm():
            self.bot_config["intercept_confirm_enabled"] = "yes" if ic_var.get() else "no"
            save_dict_as_toml(self.bot_config, self.bot_config_path)

        ic_cb = ctk.CTkCheckBox(
            container,
            text="",
            variable=ic_var,
            command=toggle_intercept_confirm,
            width=S(30),
            height=S(30),
            **theme.checkbox_kwargs(),
        )
        ic_cb.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
        self.attach_tooltip(
            ic_cb,
            "When on (and Cross-reference projectile hits is on), RL damage uses predicted "
            "projectile impact time matched to HP drops. Reduces false positive hits.",
        )
        row_idx += 1

        # 7) Unstuck Movement Delay (bot_config)
        create_labeled_entry(
            label_text="Unstuck Movement Delay:",
            config_key="unstuck_movement_delay",
            convert_func=float,
            use_general_config=False,
            tooltip_text="How long (in seconds) can the bot maintain a movement before trying to unstuck itself."
        )

        # 8) Unstucking Duration (bot_config)
        create_labeled_entry(
            label_text="Unstucking Duration:",
            config_key="unstuck_movement_hold_time",
            convert_func=float,
            use_general_config=False,
            tooltip_text="For how long (in seconds) will the bot try to go in a different position to unstuck itself before going back to normal."
        )

        # 4) CPU/GPU (store in general_config)
        lbl_gpu = ctk.CTkLabel(container, text="Inference device:", font=theme.ui_font(S(18)))
        lbl_gpu.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))

        gpu_values = ["auto", "directml", "cuda", "openvino", "cpu"]
        gpu_var = tk.StringVar(value=self.general_config["cpu_or_gpu"])

        def on_gpu_change(choice):
            self.general_config["cpu_or_gpu"] = choice
            save_dict_as_toml(self.general_config, self.general_config_path)

        gpu_menu = ctk.CTkOptionMenu(
            container,
            values=gpu_values,
            command=on_gpu_change,
            variable=gpu_var,
            font=theme.ui_font(S(16)),
            **theme.option_menu_kwargs(S(100), S(35)),
        )
        gpu_menu.grid(row=row_idx, column=1, padx=S(20), pady=S(10), sticky="w")
        row_idx += 1

        create_labeled_entry(
            label_text="DirectML GPU ID:",
            config_key="directml_device_id",
            convert_func=str,
            use_general_config=True,
            tooltip_text="DirectML adapter index. Keep auto unless DirectML uses the wrong GPU; try 0 or 1 on laptops with two GPUs."
        )

        lbl_long_press = ctk.CTkLabel(container, text="Longpress star_drop:", font=theme.ui_font(S(18)))
        lbl_long_press.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        long_press_var = tk.BooleanVar(
            value=(str(self.general_config["long_press_star_drop"]).lower() in ["yes", "true"])
        )

        def toggle_long_press_detection():
            self.general_config["long_press_star_drop"] = "yes" if long_press_var.get() else "no"
            save_dict_as_toml(self.general_config, self.general_config_path)

        long_press_cb = ctk.CTkCheckBox(
            container,
            text="",
            variable=long_press_var,
            command=toggle_long_press_detection,
            width=S(30),
            height=S(30),
            **theme.checkbox_kwargs(),
        )
        long_press_cb.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
        row_idx += 1

        lbl_play_again = ctk.CTkLabel(container, text="Play Again On Win:", font=theme.ui_font(S(18)))
        lbl_play_again.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        play_again_var = tk.BooleanVar(
            value=(str(self.bot_config["play_again_on_win"]).lower() in ["yes", "true"])
        )

        def toggle_play_again():
            self.bot_config["play_again_on_win"] = "yes" if play_again_var.get() else "no"
            save_dict_as_toml(self.bot_config, self.bot_config_path)

        play_again_cb = ctk.CTkCheckBox(
            container,
            text="",
            variable=play_again_var,
            command=toggle_play_again,
            width=S(30),
            height=S(30),
            **theme.checkbox_kwargs(),
        )
        play_again_cb.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
        self.attach_tooltip(
            play_again_cb,
            "If enabled, the bot presses 'Play Again' after a win instead of returning to the lobby."
        )
        row_idx += 1

        lbl_rl_movement = ctk.CTkLabel(container, text="Use RL Movement:", font=theme.ui_font(S(18)))
        lbl_rl_movement.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        rl_movement_var = tk.BooleanVar(
            value=(str(self.bot_config["use_rl_movement"]).lower() in ["yes", "true"])
        )

        def toggle_rl_movement():
            self.bot_config["use_rl_movement"] = "yes" if rl_movement_var.get() else "no"
            save_dict_as_toml(self.bot_config, self.bot_config_path)

        rl_movement_cb = ctk.CTkCheckBox(
            container,
            text="",
            variable=rl_movement_var,
            command=toggle_rl_movement,
            width=S(30),
            height=S(30),
            **theme.checkbox_kwargs(),
        )
        rl_movement_cb.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
        self.attach_tooltip(
            rl_movement_cb,
            "If enabled, movement is driven by the RL policy. Heuristic attacks/supers/gadgets stay on. Takes effect on next bot start."
        )
        row_idx += 1

        lbl_rl_train = ctk.CTkLabel(container, text="Record RL transitions (offline training):", font=theme.ui_font(S(18)))
        lbl_rl_train.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        rl_train_var = tk.BooleanVar(
            value=(str(self.bot_config["enable_rl_movement_training"]).lower() in ["yes", "true"])
        )

        def toggle_rl_training():
            yn = "yes" if rl_train_var.get() else "no"
            self.bot_config["enable_rl_movement_training"] = yn
            self.bot_config["rl_record_transitions"] = yn
            save_dict_as_toml(self.bot_config, self.bot_config_path)

        rl_train_cb = ctk.CTkCheckBox(
            container,
            text="",
            variable=rl_train_var,
            command=toggle_rl_training,
            width=S(30),
            height=S(30),
            **theme.checkbox_kwargs(),
        )
        rl_train_cb.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
        self.attach_tooltip(
            rl_train_cb,
            "When ON while Use RL Movement is ON, saves executed (s,a,r,s') batches under rl_replay_dir for python tools/train_rl_offline.py. "
            "The live bot no longer runs gradient updates. Takes effect on next bot start.",
        )
        row_idx += 1

        lbl_train_offline = ctk.CTkLabel(
            container, text="Train RL offline:", font=theme.ui_font(S(18))
        )
        lbl_train_offline.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))

        train_offline_btn = ctk.CTkButton(
            container,
            text="Train RL Offline (200k steps)",
            font=theme.ui_font(S(16)),
            width=S(280),
            height=S(36),
            command=self._launch_train_rl_offline,
        )
        train_offline_btn.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
        self.attach_tooltip(
            train_offline_btn,
            "Runs tools/train_rl_offline.py in a new console using rl_replay_dir, rl_movement_model_path, and rl_sac_gamma from cfg/bot_config.toml.",
        )
        row_idx += 1

        lbl_rl_proj_obs = ctk.CTkLabel(
            container,
            text="RL Projectile Observations:",
            font=theme.ui_font(S(18)),
        )
        lbl_rl_proj_obs.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        rl_proj_obs_var = tk.BooleanVar(
            value=(
                str(self.bot_config.get("rl_use_projectile_features", "yes")).lower()
                in ("yes", "true", "1")
            )
        )

        def toggle_rl_projectile_obs():
            self.bot_config["rl_use_projectile_features"] = (
                "yes" if rl_proj_obs_var.get() else "no"
            )
            save_dict_as_toml(self.bot_config, self.bot_config_path)

        rl_proj_obs_cb = ctk.CTkCheckBox(
            container,
            text="",
            variable=rl_proj_obs_var,
            command=toggle_rl_projectile_obs,
            width=S(30),
            height=S(30),
            **theme.checkbox_kwargs(),
        )
        rl_proj_obs_cb.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
        self.attach_tooltip(
            rl_proj_obs_cb,
            "When OFF, the RL observation omits projectile track features (smaller observation; less CPU tracking when RL Projectile Debug Overlay is OFF). ON matches the legacy dodge-aware policy layout. Restart the bot.",
        )
        row_idx += 1

        lbl_rl_proj_dbg = ctk.CTkLabel(
            container,
            text="RL Projectile Debug Overlay:",
            font=theme.ui_font(S(18)),
        )
        lbl_rl_proj_dbg.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        rl_proj_dbg_var = tk.BooleanVar(
            value=(
                str(self.bot_config.get("rl_show_projectile_debug", "yes")).lower()
                in ("yes", "true", "1")
            )
        )

        def toggle_rl_projectile_debug():
            self.bot_config["rl_show_projectile_debug"] = (
                "yes" if rl_proj_dbg_var.get() else "no"
            )
            save_dict_as_toml(self.bot_config, self.bot_config_path)

        rl_proj_dbg_cb = ctk.CTkCheckBox(
            container,
            text="",
            variable=rl_proj_dbg_var,
            command=toggle_rl_projectile_debug,
            width=S(30),
            height=S(30),
            **theme.checkbox_kwargs(),
        )
        rl_proj_dbg_cb.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
        self.attach_tooltip(
            rl_proj_dbg_cb,
            "When ON and Debug Screen is on, projectile tracks are drawn. When OFF together with Projectile Observations, tracking work is skipped for RL to save CPU. Restart the bot.",
        )
        row_idx += 1

        lbl_rl_hp_pen = ctk.CTkLabel(
            container,
            text="RL HP Drop Penalty:",
            font=theme.ui_font(S(18)),
        )
        lbl_rl_hp_pen.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        rl_hp_pen_var = tk.BooleanVar(
            value=(
                str(self.bot_config.get("rl_use_hp_drop_penalty", "no")).lower()
                in ("yes", "true", "1")
            )
        )

        def toggle_rl_hp_drop_penalty():
            self.bot_config["rl_use_hp_drop_penalty"] = (
                "yes" if rl_hp_pen_var.get() else "no"
            )
            save_dict_as_toml(self.bot_config, self.bot_config_path)

        rl_hp_pen_cb = ctk.CTkCheckBox(
            container,
            text="",
            variable=rl_hp_pen_var,
            command=toggle_rl_hp_drop_penalty,
            width=S(30),
            height=S(30),
            **theme.checkbox_kwargs(),
        )
        rl_hp_pen_cb.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
        self.attach_tooltip(
            rl_hp_pen_cb,
            "When ON, RL penalizes HP loss from HealthMonitor (storm, melee, shots) instead of the projectile/intercept detector. Restart the bot.",
        )
        row_idx += 1

        lbl_ocr_hz = ctk.CTkLabel(
            container,
            text="HP OCR poll rate (Hz):",
            font=theme.ui_font(S(18)),
        )
        lbl_ocr_hz.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))

        ocr_hz_frame = ctk.CTkFrame(container, fg_color="transparent")
        ocr_hz_frame.grid(row=row_idx, column=1, padx=S(20), pady=S(10), sticky="w")

        try:
            _hz_init = float(self.bot_config.get("health_ocr_poll_hz", 5.0))
        except (TypeError, ValueError):
            _hz_init = 5.0
        _hz_init = max(1.0, min(15.0, _hz_init))
        ocr_hz_var = tk.StringVar(value=f"{_hz_init:.1f}")

        _ocr_primary_on = str(
            self.bot_config.get("health_ocr_primary", "yes")
        ).lower() in ("yes", "true", "1")
        _hz_state = "normal" if _ocr_primary_on else "disabled"

        ocr_hz_slider = ctk.CTkSlider(
            ocr_hz_frame,
            from_=1.0,
            to=15.0,
            number_of_steps=28,
            width=S(200),
            fg_color=theme.INACTIVE,
            progress_color=theme.ACCENT,
            button_color=theme.ACCENT,
            button_hover_color=theme.ACCENT_HOVER,
            state=_hz_state,
        )
        ocr_hz_slider.pack(side="left", padx=S(5))

        ocr_hz_entry = ctk.CTkEntry(
            ocr_hz_frame,
            textvariable=ocr_hz_var,
            width=S(70),
            font=theme.ui_font(S(16)),
            state=_hz_state,
            **theme.entry_kwargs(),
        )
        ocr_hz_entry.pack(side="left", padx=S(10))

        def _commit_ocr_hz(value: float):
            v = max(1.0, min(15.0, float(value)))
            v = round(v * 2.0) / 2.0
            self.bot_config["health_ocr_poll_hz"] = v
            save_dict_as_toml(self.bot_config, self.bot_config_path)

        def _on_ocr_hz_slider(value):
            if ocr_hz_slider.cget("state") == "disabled":
                return
            v = max(1.0, min(15.0, float(value)))
            v = round(v * 2.0) / 2.0
            ocr_hz_var.set(f"{v:.1f}")
            _commit_ocr_hz(v)

        def _on_ocr_hz_entry(_evt=None):
            if ocr_hz_entry.cget("state") == "disabled":
                return
            text = ocr_hz_var.get().strip()
            if not text:
                ocr_hz_var.set(f"{float(self.bot_config.get('health_ocr_poll_hz', 5.0)):.1f}")
                return
            try:
                v = float(text)
            except ValueError:
                ocr_hz_var.set(f"{float(self.bot_config.get('health_ocr_poll_hz', 5.0)):.1f}")
                return
            v = max(1.0, min(15.0, v))
            v = round(v * 2.0) / 2.0
            ocr_hz_var.set(f"{v:.1f}")
            ocr_hz_slider.set(v)
            _commit_ocr_hz(v)

        ocr_hz_slider.configure(command=_on_ocr_hz_slider)
        ocr_hz_slider.set(_hz_init)
        ocr_hz_entry.bind("<FocusOut>", _on_ocr_hz_entry)
        ocr_hz_entry.bind("<Return>", _on_ocr_hz_entry)

        if _ocr_primary_on:
            self.attach_tooltip(
                ocr_hz_slider,
                "How often EasyOCR re-reads the HP number. 5 Hz is a good default; "
                "higher = more CPU, lower = laggier damage signal. Takes effect on next match.",
            )
        else:
            self.attach_tooltip(
                ocr_hz_slider,
                "Disabled because 'health_ocr_primary' is off — HSV is the active HP source.",
            )
        row_idx += 1

        lbl_term_log = ctk.CTkLabel(container, text="Terminal Logging:", font=theme.ui_font(S(18)))
        lbl_term_log.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        term_log_var = tk.BooleanVar(
            value=(str(self.general_config["terminal_logging"]).lower() in ["yes", "true"])
        )

        def toggle_terminal_logging():
            self.general_config["terminal_logging"] = "yes" if term_log_var.get() else "no"
            save_dict_as_toml(self.general_config, self.general_config_path)

        term_log_cb = ctk.CTkCheckBox(
            container,
            text="",
            variable=term_log_var,
            command=toggle_terminal_logging,
            width=S(30),
            height=S(30),
            **theme.checkbox_kwargs(),
        )
        term_log_cb.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
        self.attach_tooltip(
            term_log_cb,
            "If enabled, terminal output is saved to logs/pyla_<date>.log files. Takes effect on next launch."
        )
        row_idx += 1

        lbl_debug_screen = ctk.CTkLabel(container, text="Debug Screen:", font=theme.ui_font(S(18)))
        lbl_debug_screen.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        debug_screen_var = tk.BooleanVar(
            value=(str(self.general_config["visual_debug"]).lower() in ["yes", "true"])
        )

        def toggle_debug_screen():
            self.general_config["visual_debug"] = "yes" if debug_screen_var.get() else "no"
            save_dict_as_toml(self.general_config, self.general_config_path)

        debug_screen_cb = ctk.CTkCheckBox(
            container,
            text="",
            variable=debug_screen_var,
            command=toggle_debug_screen,
            width=S(30),
            height=S(30),
            **theme.checkbox_kwargs(),
        )
        debug_screen_cb.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
        self.attach_tooltip(
            debug_screen_cb,
            "Shows a live OpenCV debug window with detected player, teammate, enemy, wall, fog, and range overlays. Takes effect on next bot start."
        )
        row_idx += 1

        lbl_showdown_style = ctk.CTkLabel(container, text="Trio Movement Style:", font=theme.ui_font(S(18)))
        lbl_showdown_style.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        style_labels = {
            "hide": "Hide / avoid enemies",
            "follow": "Follow teammates",
        }
        reverse_style_labels = {label: key for key, label in style_labels.items()}
        current_style = str(self.bot_config.get("showdown_playstyle_mode", "follow")).strip().lower()
        if current_style not in style_labels:
            current_style = "follow"
            self.bot_config["showdown_playstyle_mode"] = current_style
            save_dict_as_toml(self.bot_config, self.bot_config_path)
        style_var = tk.StringVar(value=style_labels.get(current_style, style_labels["follow"]))

        def on_showdown_style_change(choice):
            self.bot_config["showdown_playstyle_mode"] = reverse_style_labels.get(choice, "follow")
            save_dict_as_toml(self.bot_config, self.bot_config_path)

        style_menu = ctk.CTkOptionMenu(
            container,
            values=list(style_labels.values()),
            command=on_showdown_style_change,
            variable=style_var,
            font=theme.ui_font(S(16)),
            fg_color="#AA2A2A",
            button_color="#AA2A2A",
            button_hover_color="#BB3A3A",
            width=S(190),
            height=S(35),
        )
        style_menu.grid(row=row_idx, column=1, padx=S(20), pady=S(10), sticky="w")
        self.attach_tooltip(
            style_menu,
            "Hide/avoid enemies keeps the current safer roaming behavior. Follow teammates uses the official Pyla follower behavior when no reachable enemy is visible.",
        )
        row_idx += 1

        lbl_capture_vision = ctk.CTkLabel(container, text="Capture Vision Frames:", font=theme.ui_font(S(18)))
        lbl_capture_vision.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        capture_vision_var = tk.BooleanVar(
            value=(str(self.general_config["capture_bad_vision_frames"]).lower() in ["yes", "true"])
        )

        def toggle_capture_vision():
            self.general_config["capture_bad_vision_frames"] = "yes" if capture_vision_var.get() else "no"
            save_dict_as_toml(self.general_config, self.general_config_path)

        capture_vision_cb = ctk.CTkCheckBox(
            container,
            text="",
            variable=capture_vision_var,
            command=toggle_capture_vision,
            width=S(30),
            height=S(30),
            **theme.checkbox_kwargs(),
        )
        capture_vision_cb.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
        self.attach_tooltip(
            capture_vision_cb,
            "Saves bad vision frames for model training when the player is lost or wall-stuck. Takes effect on next bot start."
        )
        row_idx += 1

        lbl_ips_tracker = ctk.CTkLabel(container, text="Pause Window IPS Tracker:", font=theme.ui_font(S(18)))
        lbl_ips_tracker.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        ips_tracker_var = tk.BooleanVar(
            value=(str(self.general_config["pause_menu_ips_tracker"]).lower() in ["yes", "true"])
        )

        def toggle_ips_tracker():
            self.general_config["pause_menu_ips_tracker"] = "yes" if ips_tracker_var.get() else "no"
            save_dict_as_toml(self.general_config, self.general_config_path)

        ips_tracker_cb = ctk.CTkCheckBox(
            container,
            text="",
            variable=ips_tracker_var,
            command=toggle_ips_tracker,
            width=S(30),
            height=S(30),
            **theme.checkbox_kwargs(),
        )
        ips_tracker_cb.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
        self.attach_tooltip(
            ips_tracker_cb,
            "Adds a live IPS readout (bot iterations per second) and a small green graph to the floating pause window. Takes effect on next bot start."
        )
        row_idx += 1


        create_labeled_entry(
            label_text="Super Detection Pixel Treshold:",
            config_key="super_pixels_minimum",
            convert_func=float,
            use_general_config=False,
            tooltip_text='Amount of "yellow" pixels the bot must detect to consider the super is ready.'
        )

        create_labeled_entry(
            label_text="Trophies Multiplier:",
            config_key="trophies_multiplier",
            convert_func=int,
            use_general_config=True,
            tooltip_text="Enter the multiplier for trophies gained per match (for example : 2 for brawl arena)."
        )

        create_labeled_entry(
            label_text="OCR Scale:",
            config_key="ocr_scale_down_factor",
            convert_func=float,
            use_general_config=True,
            tooltip_text="Scale used for brawler-name OCR in the select menu. Lower is faster; adjust if it taps the wrong card."
        )

        create_labeled_entry(
            label_text="Current Playstyle:",
            config_key="current_playstyle",
            convert_func=str,
            use_general_config=False,
            tooltip_text="Filename from the playstyles folder used for editable match logic."
        )

        # 10) Gadget Detection Pixel Threshold (bot_config)
        create_labeled_entry(
            label_text="Gadget Detection Pixel Treshold:",
            config_key="gadget_pixels_minimum",
            convert_func=float,
            use_general_config=False,
            tooltip_text='Amount of "green" pixels the bot must detect to consider a gadget is ready.'
        )

        # 11) Hypercharge Detection Pixel Threshold (bot_config)
        create_labeled_entry(
            label_text="Hypercharge Detection Pixel Treshold:",
            config_key="hypercharge_pixels_minimum",
            convert_func=float,
            use_general_config=False,
            tooltip_text='Amount of "purple" pixels the bot must detect to consider a hypercharge is ready.'
        )

        # 1) Max IPS (store in general_config)
        create_labeled_entry(
            label_text="Max IPS (0 = unlimited):",
            config_key="max_ips",
            convert_func=int,
            use_general_config=True,
            tooltip_text="Maximum Images per second the bot processes. Set 0 for no bot-side IPS cap."
        )

        create_labeled_entry(
            label_text="Scrcpy Max FPS:",
            config_key="scrcpy_max_fps",
            convert_func=int,
            use_general_config=True,
            tooltip_text="Maximum emulator video frames per second captured by scrcpy."
        )

        create_labeled_entry(
            label_text="Used Threads:",
            config_key="used_threads",
            convert_func=lambda s: s if s.lower() == "auto" else int(s),
            use_general_config=True,
            tooltip_text="CPU threads used by the detection models. Lower values reduce CPU usage."
        )

        lbl_profile = ctk.CTkLabel(container, text="Performance Profile:", font=theme.ui_font(S(18)))
        lbl_profile.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
        profile_var = tk.StringVar(value="balanced")
        profile_menu = ctk.CTkOptionMenu(
            container,
            values=["balanced", "low-end", "quality"],
            variable=profile_var,
            font=theme.ui_font(S(16)),
            **theme.option_menu_kwargs(S(120), S(35)),
        )
        profile_menu.grid(row=row_idx, column=1, padx=S(20), pady=S(10), sticky="w")
        row_idx += 1

        profile_status = ctk.CTkLabel(container, text="", font=theme.ui_font(S(14)), text_color=theme.TEXT_SECONDARY)
        profile_status.grid(row=row_idx, column=0, columnspan=2, sticky="n", padx=S(20), pady=(0, S(4)))
        row_idx += 1

        def refresh_profile_fields(result):
            self.general_config.clear()
            self.general_config.update(result["general_config"])
            self.bot_config.clear()
            self.bot_config.update(result["bot_config"])
            for key in result["changed_general_keys"]:
                var = entry_vars.get((True, key))
                if var is not None:
                    var.set(str(self.general_config[key]))
            for key in result["changed_bot_keys"]:
                var = entry_vars.get((False, key))
                if var is not None:
                    var.set(str(self.bot_config[key]))
            gpu_var.set(str(self.general_config.get("cpu_or_gpu", "auto")))

        def on_apply_performance_profile():
            try:
                result = apply_performance_profile(
                    profile_var.get(),
                    general_config_path=self.general_config_path,
                    bot_config_path=self.bot_config_path,
                )
                refresh_profile_fields(result)
                profile_status.configure(
                    text=f"Applied {result['profile']} profile. Restart the bot to use it.",
                    text_color=theme.SUCCESS,
                )
            except Exception as exc:
                profile_status.configure(text=f"Could not apply profile: {exc}", text_color=theme.ERROR)

        apply_profile_btn = ctk.CTkButton(
            container,
            text="Apply Performance Mode",
            command=on_apply_performance_profile,
            font=theme.ui_font(S(16), "bold"),
            width=S(220),
            height=S(40),
            **theme.primary_button_kwargs(S(12)),
        )
        apply_profile_btn.grid(row=row_idx, column=0, columnspan=2, padx=S(20), pady=S(10))
        self.attach_tooltip(
            apply_profile_btn,
            "Applies safe bot-side capture, FPS, GPU, and detection settings. It does not edit emulator files."
        )
        row_idx += 1

        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=1)

    def _init_webhook_tab(self):
        frame = self.tab_webhook
        wrap = ctk.CTkFrame(frame, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=S(10), pady=S(10))
        card = ctk.CTkFrame(
            wrap,
            fg_color=theme.CARD,
            corner_radius=S(20),
            border_width=1,
            border_color=theme.CARD_BORDER,
        )
        card.pack(fill="both", expand=True)
        container = ctk.CTkScrollableFrame(card, width=S(880), height=S(600), fg_color="transparent")
        container.pack(fill="both", expand=True, padx=S(12), pady=S(12))

        row_idx = 0

        def create_webhook_entry(label_text, config_key, convert_func=str, width=360, show=None):
            nonlocal row_idx
            lbl = ctk.CTkLabel(container, text=label_text, font=theme.ui_font(S(18)))
            lbl.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
            var_str = tk.StringVar(value=str(self.webhook_config.get(config_key, "")))

            def on_save(*_):
                val_str = var_str.get().strip()
                try:
                    self.webhook_config[config_key] = convert_func(val_str)
                    save_dict_as_toml(self.webhook_config, self.webhook_config_path)
                except ValueError:
                    var_str.set(str(self.webhook_config.get(config_key, "")))

            entry = ctk.CTkEntry(
                container,
                textvariable=var_str,
                width=S(width),
                font=theme.ui_font(S(16)),
                show=show,
                **theme.entry_kwargs(),
            )
            entry.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
            entry.bind("<FocusOut>", on_save)
            entry.bind("<Return>", on_save)
            row_idx += 1

        def create_webhook_toggle(label_text, config_key):
            nonlocal row_idx
            lbl = ctk.CTkLabel(container, text=label_text, font=theme.ui_font(S(18)))
            lbl.grid(row=row_idx, column=0, sticky="e", padx=S(20), pady=S(10))
            var_bool = tk.BooleanVar(value=bool(self.webhook_config.get(config_key, False)))

            def on_toggle():
                self.webhook_config[config_key] = bool(var_bool.get())
                save_dict_as_toml(self.webhook_config, self.webhook_config_path)

            checkbox = ctk.CTkCheckBox(
                container,
                text="",
                variable=var_bool,
                command=on_toggle,
                width=S(30),
                height=S(30),
                **theme.checkbox_kwargs(),
            )
            checkbox.grid(row=row_idx, column=1, sticky="w", padx=S(20), pady=S(10))
            row_idx += 1

        create_webhook_entry("Webhook URL:", "webhook_url", str, width=440)
        create_webhook_entry("Discord ID:", "discord_id", str, width=220)
        create_webhook_entry("Webhook Name:", "username", str, width=220)
        create_webhook_toggle("Send Match Summary:", "send_match_summary")
        create_webhook_toggle("Include Screenshots:", "include_screenshot")
        create_webhook_toggle("Ping When Stuck:", "ping_when_stuck")
        create_webhook_toggle("Ping On Target:", "ping_when_target_is_reached")
        create_webhook_entry("Ping Every X Matches:", "ping_every_x_match", lambda s: 0 if s == "" else int(s), width=120)
        create_webhook_entry("Ping Every X Minutes:", "ping_every_x_minutes", lambda s: 0 if s == "" else int(s), width=120)
        create_webhook_toggle("Discord Remote Control:", "discord_control_enabled")
        create_webhook_entry("Bot Token:", "discord_bot_token", str, width=440, show="*")
        create_webhook_entry("Allowed User ID:", "discord_control_user_id", str, width=220)
        create_webhook_entry("Allowed Channel ID:", "discord_control_channel_id", str, width=220)
        create_webhook_entry("Guild ID:", "discord_control_guild_id", str, width=220)

        webhook_status = ctk.CTkLabel(container, text="", font=theme.ui_font(S(14)), text_color=theme.TEXT_SECONDARY)
        webhook_status.grid(row=row_idx, column=0, columnspan=2, sticky="n", padx=S(20), pady=(S(6), 0))
        row_idx += 1

        def send_test_webhook():
            webhook_status.configure(text="Sending Discord test...", text_color=theme.TEXT_SECONDARY)

            def worker():
                try:
                    ok = asyncio.run(async_send_test_notification())
                    message = "Discord test sent." if ok else "Discord test failed. Check URL and Discord permissions."
                    color = theme.SUCCESS if ok else theme.ERROR
                except Exception as exc:
                    message = f"Discord test failed: {exc}"
                    color = theme.ERROR
                try:
                    self.app.after(0, lambda: webhook_status.configure(text=message, text_color=color))
                except Exception:
                    pass

            threading.Thread(target=worker, daemon=True).start()

        test_btn = ctk.CTkButton(
            container,
            text="Send Discord Test",
            command=send_test_webhook,
            font=theme.ui_font(S(16), "bold"),
            width=S(220),
            height=S(40),
            **theme.primary_button_kwargs(S(12)),
        )
        test_btn.grid(row=row_idx, column=0, columnspan=2, padx=S(20), pady=S(12))
        self.attach_tooltip(test_btn, "Sends a Discord test message using the current Discord settings.")
        row_idx += 1

        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=1)

    # ---------------------------------------------------------------------------------------------
    #  Timers Tab
    # ---------------------------------------------------------------------------------------------
    def _init_timers_tab(self):
        frame = self.tab_timers
        wrap = ctk.CTkFrame(frame, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=S(10), pady=S(10))
        card = ctk.CTkFrame(
            wrap,
            fg_color=theme.CARD,
            corner_radius=S(20),
            border_width=1,
            border_color=theme.CARD_BORDER,
        )
        card.pack(fill="both", expand=True)
        container = ctk.CTkFrame(card, fg_color="transparent")
        container.pack(expand=True, fill="both", padx=S(12), pady=S(12))

        container.grid_rowconfigure(0, minsize=S(70))  # extra top space for tooltips

        row_idx = 1

        def create_timer_setting(param_name, label_text, tooltip_text=None, disabled=False):
            nonlocal row_idx

            lbl = ctk.CTkLabel(container, text=label_text, font=theme.ui_font(S(18)))
            lbl.grid(row=row_idx, column=0, padx=S(20), pady=S(10), sticky="e")

            # Frame to hold slider & entry side by side
            slider_entry_frame = ctk.CTkFrame(container, fg_color="transparent")
            slider_entry_frame.grid(row=row_idx, column=1, padx=S(20), pady=S(10), sticky="w")

            val_var = tk.StringVar(value=str(self.time_tresholds[param_name]))

            # The slider
            sld = ctk.CTkSlider(
                slider_entry_frame,
                from_=0.1,
                to=10,
                number_of_steps=99,
                width=S(200),
                command=lambda v: on_slider_change(v, val_var, param_name),
                state=("disabled" if disabled else "normal"),
                fg_color=theme.INACTIVE,
                progress_color=theme.ACCENT,
                button_color=theme.ACCENT,
                button_hover_color=theme.ACCENT_HOVER,
            )
            sld.pack(side="left", padx=S(5))

            # The text entry
            entry = ctk.CTkEntry(
                slider_entry_frame,
                textvariable=val_var,
                width=S(80),
                font=theme.ui_font(S(16)),
                state=("disabled" if disabled else "normal"),
                **theme.entry_kwargs(),
            )
            entry.pack(side="left", padx=S(10))

            def on_save(_):
                if disabled:
                    return
                new_val_str = val_var.get().strip()
                if new_val_str == "":
                    val_var.set(str(self.time_tresholds[param_name]))
                    return
                try:
                    val = float(new_val_str)
                    self.time_tresholds[param_name] = val
                    save_dict_as_toml(self.time_tresholds, self.time_tresholds_path)
                    # Update slider visually
                    if val < 0.1:
                        sld.set(0.1)
                    elif val > 10:
                        sld.set(10)
                    else:
                        sld.set(val)
                except ValueError:
                    val_var.set(str(self.time_tresholds[param_name]))

            entry.bind("<FocusOut>", on_save)
            entry.bind("<Return>", on_save)

            def on_slider_change(value, v_var, p_name):
                if disabled:
                    return
                v = float(value)
                # update entry text
                v_var.set(f"{v:.2f}")
                self.time_tresholds[p_name] = v
                save_dict_as_toml(self.time_tresholds, self.time_tresholds_path)

            # Initialize slider
            try:
                init_val = float(self.time_tresholds[param_name])
                if init_val < 0.1:
                    init_val = 0.1
                elif init_val > 10:
                    init_val = 10
                sld.set(init_val)
            except:
                sld.set(1.0)

            # NOTE: We removed "self.attach_tooltip(lbl, tooltip_text)" so the label has no tooltip.
            if tooltip_text and not disabled:
                self.attach_tooltip(sld, tooltip_text)
                self.attach_tooltip(entry, tooltip_text)

            row_idx += 1

        create_timer_setting(
            param_name="super",
            label_text="Super Delay:",
            tooltip_text="How often (in seconds) the bot checks if super is ready."
        )
        create_timer_setting(
            param_name="hypercharge",
            label_text="Hypercharge Delay:",
            tooltip_text="How often (in seconds) the bot checks if hypercharge is ready."
        )
        create_timer_setting(
            param_name="gadget",
            label_text="Gadget Check Delay:",
            tooltip_text="How often (in seconds) the bot checks if gadget is ready."
        )
        create_timer_setting(
            param_name="wall_detection",
            label_text="Wall Detection:",
            tooltip_text="How often (in seconds) the bot detects the walls around it."
        )
        create_timer_setting(
            param_name="no_detection_proceed",
            label_text="No detections proceed Delay:",
            tooltip_text="How often (in seconds) does the bot press Q to proceed when it doesn't find the player but doesn't know in what state it is."
        )

        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=1)

    # ---------------------------------------------------------------------------------------------
    #  Match History Tab
    # ---------------------------------------------------------------------------------------------
    def _init_history_tab(self):
        frame = self.tab_history

        wrap = ctk.CTkFrame(frame, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=S(10), pady=S(10))
        card = ctk.CTkFrame(
            wrap,
            fg_color=theme.CARD,
            corner_radius=S(20),
            border_width=1,
            border_color=theme.CARD_BORDER,
        )
        card.pack(fill="both", expand=True)
        scroll_frame = ctk.CTkScrollableFrame(
            card, width=S(880), height=S(580), fg_color="transparent", corner_radius=S(16)
        )
        scroll_frame.pack(fill="both", expand=True, padx=S(8), pady=S(8))

        max_cols = 4
        row_idx = 0
        col_idx = 0

        icon_size = S(100)  # bigger icons
        for brawler, stats in self.match_history.items():
            if brawler == "total":
                continue
            icon_path = f"./api/assets/brawler_icons/{brawler}.png"
            if not os.path.exists(icon_path):
                icon_img = None
            else:
                pil_img = Image.open(icon_path).resize((icon_size, icon_size))
                icon_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(icon_size, icon_size))

            total_games = stats["victory"] + stats["defeat"]
            if total_games == 0:
                wr = lr = dr = 0
            else:
                wr = round(100 * stats["victory"] / total_games, 1)
                lr = round(100 * stats["defeat"] / total_games, 1)

            cell_frame = ctk.CTkFrame(
                scroll_frame,
                width=S(200),
                height=S(220),
                corner_radius=S(16),
                fg_color=theme.BG,
                border_width=1,
                border_color=theme.CARD_BORDER,
            )
            cell_frame.grid(row=row_idx, column=col_idx, padx=S(15), pady=S(15))

            # Icon
            if icon_img:
                icon_label = ctk.CTkLabel(cell_frame, image=icon_img, text="")
                icon_label.pack(pady=S(5))

            # Brawler name & total games
            text_label = ctk.CTkLabel(
                cell_frame,
                text=f"{brawler}\n{total_games} games",
                font=theme.ui_font(S(16), "bold")
            )
            text_label.pack()

            stats_frame = ctk.CTkFrame(cell_frame, fg_color="transparent")
            stats_frame.pack(pady=S(5))

            color_win = theme.TEAL
            color_loss = theme.ERROR

            lbl_win = ctk.CTkLabel(
                stats_frame,
                text=f"{wr}%",
                font=theme.ui_font(S(14), "bold"),
                text_color=color_win
            )
            lbl_win.pack(side="left", padx=S(5))

            lbl_loss = ctk.CTkLabel(
                stats_frame,
                text=f"{lr}%",
                font=theme.ui_font(S(14), "bold"),
                text_color=color_loss
            )
            lbl_loss.pack(side="left", padx=S(5))

            col_idx += 1
            if col_idx >= max_cols:
                col_idx = 0
                row_idx += 1

    # ---------------------------------------------------------------------------------------------
    #  On Start => close window + callback
    # ---------------------------------------------------------------------------------------------
    def _on_start(self):
        try:
            for after_id in self.app.tk.call("after", "info"):
                try:
                    self.app.after_cancel(after_id)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.app.withdraw()
            self.app.update_idletasks()
        except Exception:
            pass
        try:
            self.app.quit()
        except Exception:
            pass
        try:
            self.app.destroy()
        except Exception:
            pass

        if callable(self.on_close_callback):
            self.on_close_callback()
