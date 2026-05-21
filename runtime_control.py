import os
import subprocess
import sys
import time
import ctypes
from pathlib import Path

from runtime_metrics import delete_metrics, format_session_summary, format_uptime, read_metrics
from utils import load_toml_as_dict


RUNNING = "running"
PAUSED = "paused"
STOP_REQUESTED = "stop_requested"

SPARKLINE_WIDTH = 200
SPARKLINE_HEIGHT = 32


def write_state(path, state):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(state, encoding="utf-8")


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
        state_dir = Path("logs")
        self.state_path = state_dir / f"runtime_control_{os.getpid()}.state"
        self.metrics_path = metrics_path
        self.process = None
        write_state(self.state_path, RUNNING)

    def start(self):
        if self.process and self.process.poll() is None:
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

    ctk.set_appearance_mode("dark")

    graph_enabled = pause_menu_graph_enabled() and metrics_path is not None
    strip_enabled = pause_menu_session_strip_enabled() and metrics_path is not None
    window_height = 206
    if graph_enabled:
        window_height += 42
    if strip_enabled:
        window_height += 56

    root = ctk.CTk()
    root.title("PylaAi-XXZ Control")
    root.geometry(f"310x{window_height}")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.overrideredirect(True)
    root.configure(fg_color="#121212")
    owner_pid = None
    try:
        owner_pid = int(Path(state_path).stem.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        owner_pid = None

    status_var = tk.StringVar(value="Running")
    button_var = tk.StringVar(value="Pause Bot")
    ips_var = tk.StringVar(value="IPS --")

    def start_move(event):
        root._pyla_drag_offset = (event.x_root - root.winfo_x(), event.y_root - root.winfo_y())

    def drag_move(event):
        drag_x, drag_y = getattr(root, "_pyla_drag_offset", (0, 0))
        root.geometry(f"+{event.x_root - drag_x}+{event.y_root - drag_y}")

    chrome = ctk.CTkFrame(
        root,
        fg_color="#121212",
        border_color="#262626",
        border_width=1,
        corner_radius=0,
        height=42,
    )
    chrome.pack(fill="x")
    chrome.pack_propagate(False)
    chrome.bind("<ButtonPress-1>", start_move)
    chrome.bind("<B1-Motion>", drag_move)

    ctk.CTkLabel(
        chrome,
        text="Pyla  ·  Running",
        text_color="#f4f4f4",
        font=("Segoe UI", 13, "bold"),
    ).place(relx=0.5, rely=0.5, anchor="center")

    def on_close():
        write_state(state_path, RUNNING)
        root.destroy()

    ctk.CTkButton(
        chrome,
        text="×",
        command=on_close,
        fg_color="transparent",
        hover_color="#1f1f1f",
        text_color="#b8b8b8",
        font=("Segoe UI", 13, "bold"),
        width=34,
        height=28,
        corner_radius=6,
    ).place(relx=0.985, rely=0.5, anchor="e")

    card = ctk.CTkFrame(root, fg_color="#0c0c0c", corner_radius=0)
    card.pack(fill="both", expand=True)

    panel = ctk.CTkFrame(
        card,
        fg_color="#181818",
        border_color="#262626",
        border_width=1,
        corner_radius=10,
    )
    panel.pack(fill="both", expand=True, padx=14, pady=14)

    title = ctk.CTkLabel(
        panel,
        text="STATUS",
        text_color="#b8b8b8",
        font=("Segoe UI", 11, "bold"),
    )
    title.pack(pady=(12, 0))

    status_label = ctk.CTkLabel(
        panel,
        textvariable=status_var,
        text_color="#30d158",
        font=("Segoe UI", 18, "bold"),
    )
    status_label.pack(pady=(0, 4 if strip_enabled else (6 if graph_enabled else 10)))

    session_line1_var = tk.StringVar(value="-- · --")
    session_line2_var = tk.StringVar(value="W0 L0 · IPS -- · --")
    session_notice_var = tk.StringVar(value="Running")
    session_strip = None
    session_labels = []
    if strip_enabled:
        session_strip = ctk.CTkFrame(panel, fg_color="#141414", corner_radius=8)
        session_strip.pack(fill="x", padx=10, pady=(0, 8))

        for index, (var, color, size) in enumerate(
            (
                (session_line1_var, "#f4f4f4", 12),
                (session_line2_var, "#b8b8b8", 11),
                (session_notice_var, "#6d6d6d", 10),
            )
        ):
            label = ctk.CTkLabel(
                session_strip,
                textvariable=var,
                text_color=color,
                font=("Segoe UI", size),
                anchor="w",
            )
            label.pack(fill="x", padx=10, pady=(6 if index == 0 else 0, 6 if index == 2 else 2))
            session_labels.append(label)

    sparkline_canvas = None
    if graph_enabled:
        graph_row = ctk.CTkFrame(panel, fg_color="transparent")
        graph_row.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkLabel(
            graph_row,
            textvariable=ips_var,
            text_color="#b8b8b8",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(side="left")

        sparkline_canvas = tk.Canvas(
            graph_row,
            width=SPARKLINE_WIDTH,
            height=SPARKLINE_HEIGHT,
            bg="#181818",
            highlightthickness=0,
            bd=0,
        )
        sparkline_canvas.pack(side="right")
        draw_ips_sparkline(sparkline_canvas, [], "#30d158")

    def graph_color(paused):
        return "#ff9f0a" if paused else "#30d158"

    def read_current_metrics():
        if not metrics_path:
            return None
        return read_metrics(Path(metrics_path).resolve())

    def update_graph(paused, metrics):
        if not graph_enabled or sparkline_canvas is None:
            return
        color = graph_color(paused)
        if metrics is None:
            ips_var.set("IPS --")
            draw_ips_sparkline(sparkline_canvas, [], color)
            return
        ips_var.set(f"IPS {metrics['ips']:.1f}")
        history = metrics.get("history") or []
        draw_ips_sparkline(sparkline_canvas, history, color)

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
        if metrics is not None and isinstance(metrics.get("ips"), (int, float)):
            ips_text = f"{metrics['ips']:.1f}"
        session_line2_var.set(
            f"W{session.get('session_wins', 0)} L{session.get('session_losses', 0)} · "
            f"IPS {ips_text} · {session.get('state') or '--'}"
        )
        session_notice_var.set(session.get("notice") or "Running")

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
        session_notice_var.set("Copied!")
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

    def refresh():
        if owner_pid and not process_is_alive(owner_pid):
            root.destroy()
            return
        paused = read_state(state_path) == PAUSED
        metrics = read_current_metrics()
        status_var.set("Paused" if paused else "Running")
        button_var.set("Resume Bot" if paused else "Pause Bot")
        status_label.configure(text_color="#ff9f0a" if paused else "#30d158")
        pause_button.configure(
            fg_color="#ff9f0a" if paused else "#1f1f1f",
            hover_color="#ffb23a" if paused else "#2a2a2a",
            border_color="#8f610e" if paused else "#333333",
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

    pause_button = ctk.CTkButton(
        panel,
        textvariable=button_var,
        command=toggle_pause,
        width=170,
        height=38,
        corner_radius=8,
        fg_color="#1f1f1f",
        hover_color="#2a2a2a",
        border_color="#333333",
        border_width=1,
        text_color="#FFFFFF",
        font=("Segoe UI", 15, "bold"),
    )
    pause_button.pack(pady=(0, 12))

    root.protocol("WM_DELETE_WINDOW", on_close)
    refresh_loop()
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--window":
        metrics_arg = sys.argv[3] if len(sys.argv) >= 4 else None
        run_window(sys.argv[2], metrics_arg)
