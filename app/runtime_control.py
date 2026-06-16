import os
import subprocess
import sys
import time
import ctypes
from pathlib import Path

from runtime_metrics import (
    delete_metrics,
    feed_fps_warning,
    format_session_summary,
    format_uptime,
    read_metrics,
)
from utils import load_toml_as_dict, resolve_project_path


RUNNING = "running"
PAUSED = "paused"
STOP_REQUESTED = "stop_requested"

SPARKLINE_WIDTH = 200
SPARKLINE_HEIGHT = 32
_settings_hub_process = None
_SW_MINIMIZE = 6


def minimize_frameless_window(window):
    """Minimize a frameless CustomTkinter/Tk window on Windows."""
    if sys.platform == "win32":
        try:
            window.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            if not hwnd:
                hwnd = window.winfo_id()
            ctypes.windll.user32.ShowWindow(hwnd, _SW_MINIMIZE)
            return True
        except Exception as exc:
            print(f"[Control] Win32 minimize failed: {exc}")

    try:
        override = bool(window.overrideredirect())
        if override:
            window.overrideredirect(False)
            window.update_idletasks()
        window.iconify()
        if override:
            window.after(50, lambda: window.overrideredirect(True))
        return True
    except Exception as exc:
        print(f"[Control] Minimize fallback failed: {exc}")
        window.withdraw()
        return False


def open_settings_hub():
    global _settings_hub_process
    if _settings_hub_process is not None and _settings_hub_process.poll() is None:
        return
    project_root = Path(__file__).resolve().parent
    _settings_hub_process = subprocess.Popen(
        [sys.executable, "-m", "gui.qml_hub", "--settings-only"],
        cwd=str(project_root),
    )


def write_state(path, state):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(state, encoding="utf-8")


def set_runtime_state(state_path, paused: bool) -> str:
    state = PAUSED if paused else RUNNING
    write_state(state_path, state)
    return state


def read_state(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip().lower()
    except OSError:
        return RUNNING


def is_stop_requested(path):
    return read_state(path) == STOP_REQUESTED


def request_stop(path):
    write_state(path, STOP_REQUESTED)
    return STOP_REQUESTED


def pause_menu_graph_enabled():
    general = load_toml_as_dict("cfg/general_config.toml")
    return str(general.get("pause_menu_ips_graph", "no")).strip().lower() in (
        "yes",
        "true",
        "1",
        "on",
    )


def pause_menu_session_strip_enabled():
    general = load_toml_as_dict("cfg/general_config.toml")
    return str(general.get("pause_menu_session_strip", "yes")).strip().lower() in (
        "yes",
        "true",
        "1",
        "on",
    )


def pause_menu_auto_reopen_enabled():
    general = load_toml_as_dict("cfg/general_config.toml")
    return str(general.get("pause_menu_auto_reopen", "yes")).strip().lower() in (
        "yes",
        "true",
        "1",
        "on",
    )


def control_command_path(state_path):
    state = Path(state_path)
    return state.with_name(f"{state.stem}.cmd")


def write_control_command(state_path, command):
    path = control_command_path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(command or "").strip().lower(), encoding="utf-8")


def read_and_clear_control_command(state_path):
    path = control_command_path(state_path)
    try:
        command = path.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return ""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return command


def remote_command_path(state_path):
    state = Path(state_path)
    return state.with_name(f"{state.stem}.remote.jsonl")


def enqueue_remote_command(state_path, command: dict) -> str:
    import json
    import uuid

    command = dict(command or {})
    command.setdefault("id", str(uuid.uuid4()))
    path = remote_command_path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(command) + "\n")
    return str(command["id"])


def read_remote_commands(state_path):
    import json

    path = remote_command_path(state_path)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    commands = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            commands.append(payload)
    return commands


def clear_remote_commands(state_path):
    try:
        remote_command_path(state_path).unlink(missing_ok=True)
    except OSError:
        pass


def write_remote_reply(reply_path, payload: dict) -> None:
    import json

    path = Path(reply_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    import os
    os.replace(temp_path, path)


def read_remote_reply(reply_path, *, clear: bool = False):
    import json

    path = Path(reply_path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if clear:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return payload if isinstance(payload, dict) else None


def drain_remote_commands(state_path, handler):
    commands = read_remote_commands(state_path)
    if not commands:
        return
    for command in commands:
        try:
            handler(command)
        except Exception as exc:
            reply_path = command.get("reply_path")
            if reply_path:
                write_remote_reply(reply_path, {"ok": False, "error": str(exc)})
    clear_remote_commands(state_path)


def blend_samples(current, target, factor=0.45):
    """Ease displayed sparkline samples toward the latest values for smooth motion."""
    if not target:
        return list(target)
    if not current or len(current) != len(target):
        return list(target)
    return [old + (new - old) * factor for old, new in zip(current, target)]


def draw_ips_sparkline(canvas, samples, color, width=SPARKLINE_WIDTH, height=SPARKLINE_HEIGHT):
    canvas.delete("all")
    mid_y = height / 2
    if not samples:
        canvas.create_line(0, mid_y, width, mid_y, fill=color, width=1)
        return
    if len(samples) == 1:
        y = mid_y
        canvas.create_line(0, y, width, y, fill=color, width=1.5)
        return

    min_val = min(samples)
    max_val = max(samples)
    span = max_val - min_val
    if span < 0.5:
        span = 0.5
        mid = (min_val + max_val) / 2
        min_val = mid - span / 2
        max_val = mid + span / 2
    padding = span * 0.08
    min_val -= padding
    max_val += padding
    span = max_val - min_val

    points = []
    last_index = len(samples) - 1
    for index, value in enumerate(samples):
        x = (index / last_index) * width
        ratio = (value - min_val) / span
        y = height - (ratio * (height - 4)) - 2
        points.extend((x, y))

    if len(points) >= 4:
        canvas.create_line(*points, fill=color, width=1.5, smooth=True)


class RuntimeControlWindow:
    def __init__(self, metrics_path=None):
        state_dir = Path(resolve_project_path("logs"))
        state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = state_dir / f"runtime_control_{os.getpid()}.state"
        self.metrics_path = metrics_path
        self.process = None
        write_state(self.state_path, RUNNING)

    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def start(self):
        if self.is_running():
            return
        script_path = Path(__file__).resolve()
        cmd = [sys.executable, str(script_path), "--window", str(self.state_path)]
        if self.metrics_path is not None:
            cmd.append(str(Path(self.metrics_path).resolve()))
        self.process = subprocess.Popen(
            cmd,
            cwd=str(script_path.parent),
            close_fds=True,
        )
        time.sleep(0.2)
        if self.process.poll() is not None:
            print("Runtime pause control window failed to start.")

    def reopen(self, mode="show"):
        if not self.is_running():
            self.start()
            return
        write_control_command(self.state_path, mode)

    def show(self):
        self.reopen("show")

    def show_compact(self):
        self.reopen("compact")

    def is_paused(self):
        return read_state(self.state_path) == PAUSED

    def close(self):
        write_state(self.state_path, RUNNING)
        if self.metrics_path is not None:
            delete_metrics(self.metrics_path)
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()


def process_is_alive(pid):
    if not pid or pid == os.getpid():
        return True
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    process_query_limited_information = 0x1000
    still_active = 259
    handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def run_window(state_path, metrics_path=None):
    import tkinter as tk
    import customtkinter as ctk

    from gui.i18n import t
    from gui.theme import get_palette, load_ui_theme_mode, resolve_theme_mode

    pal = get_palette(load_ui_theme_mode())
    ctk.set_appearance_mode(resolve_theme_mode(load_ui_theme_mode()))

    graph_enabled = pause_menu_graph_enabled() and metrics_path is not None
    strip_enabled = pause_menu_session_strip_enabled() and metrics_path is not None
    auto_reopen = pause_menu_auto_reopen_enabled()
    window_width = 360
    window_height = 300
    if graph_enabled:
        window_height += 52
    if strip_enabled:
        window_height += 62

    root = ctk.CTk()
    root.title(t("control.window_title"))
    root.geometry(f"{window_width}x{window_height}")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.overrideredirect(True)
    root.configure(fg_color=pal["chrome"])

    compact_root = ctk.CTkToplevel(root)
    compact_root.title(t("control.window_title"))
    compact_root.geometry("300x58")
    compact_root.resizable(False, False)
    compact_root.attributes("-topmost", True)
    compact_root.overrideredirect(True)
    compact_root.configure(fg_color=pal["chrome"])
    compact_root.withdraw()

    owner_pid = None
    try:
        owner_pid = int(Path(state_path).stem.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        owner_pid = None

    status_var = tk.StringVar(value=t("control.running"))
    button_var = tk.StringVar(value=t("control.pause_bot"))
    ips_var = tk.StringVar(value="IPS --")
    compact_status_var = tk.StringVar(value=t("control.running"))
    compact_button_var = tk.StringVar(value=t("control.pause_short"))

    def start_move(window, event):
        window._pyla_drag_offset = (event.x_root - window.winfo_x(), event.y_root - window.winfo_y())

    def drag_move(window, event):
        drag_x, drag_y = getattr(window, "_pyla_drag_offset", (0, 0))
        window.geometry(f"+{event.x_root - drag_x}+{event.y_root - drag_y}")

    def bind_drag(widget, window):
        widget.bind("<ButtonPress-1>", lambda event: start_move(window, event))
        widget.bind("<B1-Motion>", lambda event: drag_move(window, event))

    def show_full():
        compact_root.withdraw()
        root.deiconify()
        root.lift()
        root.attributes("-topmost", True)
        root.focus_force()

    def show_compact():
        root.withdraw()
        compact_root.deiconify()
        compact_root.lift()
        compact_root.attributes("-topmost", True)

    def minimize_full():
        minimize_frameless_window(root)

    def minimize_compact():
        minimize_frameless_window(compact_root)

    def handle_control_command():
        command = read_and_clear_control_command(state_path)
        if command == "show":
            show_full()
        elif command == "compact":
            show_compact()
        elif command == "hide":
            root.withdraw()
            compact_root.withdraw()

    def hide_menu():
        root.withdraw()
        compact_root.withdraw()

    def chrome_button(parent, text, command, *, width=32):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color="transparent",
            hover_color=pal["surface_2"],
            text_color=pal["muted"],
            font=("Segoe UI", 12, "bold"),
            width=width,
            height=28,
            corner_radius=6,
        )

    accent_bar = ctk.CTkFrame(root, fg_color=pal["accent"], corner_radius=0, height=2)
    accent_bar.pack(fill="x")
    accent_bar.pack_propagate(False)

    chrome = ctk.CTkFrame(
        root,
        fg_color=pal["chrome"],
        border_color=pal["hairline"],
        border_width=0,
        corner_radius=0,
        height=40,
    )
    chrome.pack(fill="x")
    chrome.pack_propagate(False)
    bind_drag(chrome, root)

    chrome_left = ctk.CTkFrame(chrome, fg_color="transparent")
    chrome_left.pack(side="left", fill="y", padx=(12, 0))
    bind_drag(chrome_left, root)

    brand_dot = ctk.CTkFrame(chrome_left, width=8, height=8, corner_radius=4, fg_color=pal["accent"])
    brand_dot.pack(side="left", pady=16)
    brand_dot.pack_propagate(False)

    ctk.CTkLabel(
        chrome_left,
        text=t("control.chrome_title"),
        text_color=pal["text"],
        font=("Segoe UI", 13, "bold"),
    ).pack(side="left", padx=(8, 0))

    chrome_right = ctk.CTkFrame(chrome, fg_color="transparent")
    chrome_right.pack(side="right", fill="y", padx=(0, 6))
    chrome_button(chrome_right, "−", minimize_full).pack(side="left", padx=2)
    chrome_button(chrome_right, "×", show_compact).pack(side="left", padx=2)

    compact_chrome = ctk.CTkFrame(
        compact_root,
        fg_color=pal["surface"],
        border_color=pal["hairline"],
        border_width=1,
        corner_radius=12,
    )
    compact_chrome.pack(fill="both", expand=True, padx=4, pady=4)
    bind_drag(compact_chrome, compact_root)

    compact_status_dot = ctk.CTkFrame(compact_chrome, width=8, height=8, corner_radius=4, fg_color=pal["success"])
    compact_status_dot.place(x=12, y=25)

    compact_status = ctk.CTkLabel(
        compact_chrome,
        textvariable=compact_status_var,
        text_color=pal["success"],
        font=("Segoe UI", 12, "bold"),
        anchor="w",
    )
    compact_status.place(x=26, y=18)

    card = ctk.CTkFrame(root, fg_color=pal["bg"], corner_radius=0)
    card.pack(fill="both", expand=True)

    panel = ctk.CTkFrame(
        card,
        fg_color=pal["surface"],
        border_color=pal["hairline"],
        border_width=1,
        corner_radius=12,
    )
    panel.pack(fill="both", expand=True, padx=14, pady=(10, 14))

    status_pill = ctk.CTkFrame(panel, fg_color=pal["surface_2"], corner_radius=18, height=34)
    status_pill.pack(pady=(14, 10))
    status_pill.pack_propagate(False)

    status_dot = ctk.CTkFrame(status_pill, width=10, height=10, corner_radius=5, fg_color=pal["success"])
    status_dot.pack(side="left", padx=(14, 8), pady=12)
    status_dot.pack_propagate(False)

    status_label = ctk.CTkLabel(
        status_pill,
        textvariable=status_var,
        text_color=pal["success"],
        font=("Segoe UI", 15, "bold"),
    )
    status_label.pack(side="left", padx=(0, 14), pady=6)

    session_line1_var = tk.StringVar(value="-- · --")
    session_line2_var = tk.StringVar(value="W0 L0 · IPS -- · --")
    session_notice_var = tk.StringVar(value=t("control.running"))
    session_strip = None
    session_labels = []
    if strip_enabled:
        session_strip = ctk.CTkFrame(panel, fg_color=pal["surface_2"], corner_radius=10)
        session_strip.pack(fill="x", padx=12, pady=(0, 10))

        for index, (var, color, size, weight) in enumerate(
            (
                (session_line1_var, pal["text"], 12, "bold"),
                (session_line2_var, pal["muted"], 11, "normal"),
                (session_notice_var, pal["muted_2"], 10, "normal"),
            )
        ):
            label = ctk.CTkLabel(
                session_strip,
                textvariable=var,
                text_color=color,
                font=("Segoe UI", size, weight),
                anchor="w",
            )
            label.pack(fill="x", padx=12, pady=(8 if index == 0 else 0, 8 if index == 2 else 2))
            session_labels.append(label)

    sparkline_canvas = None
    ips_label = None
    if graph_enabled:
        graph_panel = ctk.CTkFrame(panel, fg_color=pal["surface_2"], corner_radius=10)
        graph_panel.pack(fill="x", padx=12, pady=(0, 10))

        graph_row = ctk.CTkFrame(graph_panel, fg_color="transparent")
        graph_row.pack(fill="x", padx=10, pady=8)

        ips_label = ctk.CTkLabel(
            graph_row,
            textvariable=ips_var,
            text_color=pal["muted"],
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        )
        ips_label.pack(side="left")

        sparkline_canvas = tk.Canvas(
            graph_row,
            width=SPARKLINE_WIDTH,
            height=SPARKLINE_HEIGHT,
            bg=pal["surface_2"],
            highlightthickness=0,
            bd=0,
        )
        sparkline_canvas.pack(side="right")
        draw_ips_sparkline(sparkline_canvas, [], pal["success"])

    def graph_color(paused):
        return pal["accent"] if paused else pal["success"]

    def read_current_metrics():
        if not metrics_path:
            return None
        return read_metrics(Path(metrics_path).resolve())

    sparkline_state = {"displayed": []}

    def update_graph(paused, metrics):
        if not graph_enabled or sparkline_canvas is None:
            return
        color = graph_color(paused)
        if metrics is None:
            ips_var.set("IPS -- · Feed --")
            sparkline_state["displayed"] = []
            draw_ips_sparkline(sparkline_canvas, [], color)
            return
        feed_text = f"{metrics['feed_fps']:.1f}"
        ips_var.set(f"IPS {metrics['ips']:.1f} · Feed {feed_text}")
        if ips_label is not None:
            if feed_fps_warning(metrics):
                ips_label.configure(text_color=pal["accent_hover"])
            else:
                ips_label.configure(text_color=pal["muted"])
        history = metrics.get("history") or []
        sparkline_state["displayed"] = blend_samples(sparkline_state["displayed"], history)
        draw_ips_sparkline(sparkline_canvas, sparkline_state["displayed"], color)

    def update_session_strip(metrics):
        if not strip_enabled:
            return
        session = (metrics or {}).get("session") or {}
        brawler = session.get("brawler") or "--"
        target = session.get("target")
        trophies = session.get("trophies")
        if target not in (None, ""):
            progress = f"{brawler} → {target}"
            if trophies is not None:
                progress = f"{progress} ({trophies})"
        else:
            progress = brawler
        session_line1_var.set(f"{format_uptime(session.get('uptime_s'))} · {progress}")
        ips_text = "--"
        feed_text = "--"
        if metrics is not None and isinstance(metrics.get("ips"), (int, float)):
            ips_text = f"{metrics['ips']:.1f}"
        if metrics is not None and isinstance(metrics.get("feed_fps"), (int, float)):
            feed_text = f"{metrics['feed_fps']:.1f}"
        session_line2_var.set(
            f"W{session.get('session_wins', 0)} L{session.get('session_losses', 0)} · "
            f"IPS {ips_text} · Feed {feed_text} · {session.get('state') or '--'}"
        )
        session_notice_var.set(session.get("notice") or t("control.running"))

    copy_reset_job = {"id": None}

    def copy_session_summary(_event=None):
        if not strip_enabled:
            return
        summary = format_session_summary(read_current_metrics())
        root.clipboard_clear()
        root.clipboard_append(summary)
        original = (
            session_line1_var.get(),
            session_line2_var.get(),
            session_notice_var.get(),
        )
        session_notice_var.set(t("control.copied"))
        if copy_reset_job["id"] is not None:
            root.after_cancel(copy_reset_job["id"])

        def restore():
            session_line1_var.set(original[0])
            session_line2_var.set(original[1])
            session_notice_var.set(original[2])
            copy_reset_job["id"] = None

        copy_reset_job["id"] = root.after(900, restore)

    if session_strip is not None:
        session_strip.bind("<Button-1>", copy_session_summary)
        for label in session_labels:
            label.bind("<Button-1>", copy_session_summary)

    pause_button = ctk.CTkButton(
        panel,
        textvariable=button_var,
        height=40,
        corner_radius=10,
        fg_color=pal["surface_2"],
        hover_color=pal["surface_3"],
        border_color=pal["hairline_strong"],
        border_width=1,
        text_color=pal["text"],
        font=("Segoe UI", 15, "bold"),
    )
    pause_button.pack(fill="x", padx=12, pady=(0, 8))

    button_row = ctk.CTkFrame(panel, fg_color="transparent")
    button_row.pack(fill="x", padx=12, pady=(0, 8))
    button_row.grid_columnconfigure(0, weight=1)
    button_row.grid_columnconfigure(1, weight=1)

    def request_stop_bot():
        request_stop(state_path)
        refresh()

    stop_button = ctk.CTkButton(
        button_row,
        text=t("control.stop_bot"),
        command=request_stop_bot,
        height=34,
        corner_radius=10,
        fg_color=pal["danger_soft"],
        hover_color=pal["danger_border"],
        border_color=pal["danger"],
        border_width=1,
        text_color=pal["danger"],
        font=("Segoe UI", 12, "bold"),
    )
    stop_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))

    hub_button = ctk.CTkButton(
        button_row,
        text=t("control.open_hub"),
        command=open_settings_hub,
        height=34,
        corner_radius=10,
        fg_color=pal["surface_2"],
        hover_color=pal["surface_3"],
        border_color=pal["hairline_strong"],
        border_width=1,
        text_color=pal["text"],
        font=("Segoe UI", 12, "bold"),
    )
    hub_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

    footer = ctk.CTkFrame(panel, fg_color="transparent")
    footer.pack(fill="x", padx=12, pady=(0, 12))
    ctk.CTkLabel(
        footer,
        text=t("control.footer_hotkey"),
        text_color=pal["muted_2"],
        font=("Segoe UI", 10),
        anchor="w",
    ).pack(fill="x")
    if strip_enabled:
        ctk.CTkLabel(
            footer,
            text=t("control.footer_copy_session"),
            text_color=pal["faint"],
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

    def refresh():
        if owner_pid and not process_is_alive(owner_pid):
            compact_root.destroy()
            root.destroy()
            return
        handle_control_command()
        paused = read_state(state_path) == PAUSED
        metrics = read_current_metrics()
        status_text = t("control.paused") if paused else t("control.running")
        button_text = t("control.resume_bot") if paused else t("control.pause_bot")
        compact_button_text = t("control.resume_short") if paused else t("control.pause_short")
        status_color = pal["accent"] if paused else pal["success"]
        status_var.set(status_text)
        button_var.set(button_text)
        compact_status_var.set(status_text)
        compact_button_var.set(compact_button_text)
        status_label.configure(text_color=status_color)
        compact_status.configure(text_color=status_color)
        status_dot.configure(fg_color=status_color)
        compact_status_dot.configure(fg_color=status_color)
        pause_fg = pal["accent"] if paused else pal["surface_2"]
        pause_hover = pal["accent_hover"] if paused else pal["surface_3"]
        pause_border = pal["accent_border"] if paused else pal["hairline_strong"]
        pause_text = pal["text"] if paused else pal["text"]
        pause_button.configure(
            fg_color=pause_fg,
            hover_color=pause_hover,
            border_color=pause_border,
            text_color=pause_text,
        )
        compact_pause_button.configure(
            fg_color=pause_fg,
            hover_color=pause_hover,
            border_color=pause_border,
        )
        update_graph(paused, metrics)
        update_session_strip(metrics)

    def root_exists():
        try:
            return bool(root.winfo_exists())
        except tk.TclError:
            return False

    def refresh_loop():
        if not root_exists():
            return
        refresh()
        if root_exists():
            root.after(750, refresh_loop)

    def toggle_pause():
        write_state(state_path, RUNNING if read_state(state_path) == PAUSED else PAUSED)
        refresh()

    def on_pause_hotkey(_event=None):
        toggle_pause()

    root.bind("<F8>", on_pause_hotkey)
    compact_root.bind("<F8>", on_pause_hotkey)

    pause_button.configure(command=toggle_pause)

    compact_pause_button = ctk.CTkButton(
        compact_chrome,
        textvariable=compact_button_var,
        command=toggle_pause,
        width=96,
        height=30,
        corner_radius=8,
        fg_color=pal["surface_2"],
        hover_color=pal["surface_3"],
        border_color=pal["hairline_strong"],
        border_width=1,
        text_color=pal["text"],
        font=("Segoe UI", 12, "bold"),
    )
    compact_pause_button.place(x=108, y=14)

    ctk.CTkButton(
        compact_chrome,
        text=t("control.hub_short"),
        command=open_settings_hub,
        width=48,
        height=30,
        corner_radius=8,
        fg_color=pal["surface_2"],
        hover_color=pal["surface_3"],
        border_color=pal["hairline_strong"],
        border_width=1,
        text_color=pal["text"],
        font=("Segoe UI", 11, "bold"),
    ).place(x=210, y=14)

    chrome_button(compact_chrome, "□", show_full, width=28).place(x=248, y=15)
    chrome_button(compact_chrome, "−", minimize_compact, width=28).place(x=268, y=15)
    chrome_button(
        compact_chrome,
        "×",
        minimize_compact if auto_reopen else hide_menu,
        width=28,
    ).place(x=288, y=15)

    root.protocol("WM_DELETE_WINDOW", show_compact)
    compact_root.protocol("WM_DELETE_WINDOW", show_compact)
    refresh_loop()
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--window":
        metrics_arg = sys.argv[3] if len(sys.argv) >= 4 else None
        run_window(sys.argv[2], metrics_arg)
