import json
import os
import subprocess
import sys
import time
import ctypes
from collections import deque
from pathlib import Path


RUNNING = "running"
PAUSED = "paused"

IPS_STALE_AFTER = 5.0
IPS_HISTORY_SECONDS = 60.0
IPS_GRAPH_AXIS_FLOOR = 10.0


def write_state(path, state):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(state, encoding="utf-8")


def read_state(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip().lower()
    except OSError:
        return RUNNING


def _ips_path_for(state_path):
    return Path(state_path).with_suffix(".ips")


def publish_ips(ips_path, value):
    """Atomically publish the latest IPS value, or clear when value is None."""
    target = Path(ips_path)
    try:
        if value is None:
            try:
                target.unlink()
            except FileNotFoundError:
                pass
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"ips": float(value), "ts": time.time()})
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, target)
    except OSError:
        # Disk hiccup must never break the main bot loop.
        pass


def read_ips(ips_path, max_age=IPS_STALE_AFTER):
    """Return (value, age_seconds) or (None, None) when missing or stale."""
    try:
        raw = Path(ips_path).read_text(encoding="utf-8")
    except OSError:
        return None, None
    try:
        data = json.loads(raw)
        value = float(data["ips"])
        ts = float(data["ts"])
    except (ValueError, KeyError, TypeError):
        return None, None
    age = max(0.0, time.time() - ts)
    if age > max_age:
        return None, None
    return value, age


def _load_ips_tracker_enabled():
    try:
        from utils import load_toml_as_dict, _config_bool
        general = load_toml_as_dict("cfg/general_config.toml")
        return _config_bool(general.get("pause_menu_ips_tracker", "yes"), True)
    except Exception:
        return True


def _load_low_ips_threshold():
    try:
        from utils import load_toml_as_dict
        time_thresholds = load_toml_as_dict("cfg/time_tresholds.toml")
        return float(time_thresholds.get("low_ips_recovery_threshold", 4.0))
    except Exception:
        return 4.0


class RuntimeControlWindow:
    def __init__(self):
        state_dir = Path("logs")
        self.state_path = state_dir / f"runtime_control_{os.getpid()}.state"
        self.ips_path = _ips_path_for(self.state_path)
        self.ips_tracker_enabled = _load_ips_tracker_enabled()
        self.process = None
        write_state(self.state_path, RUNNING)
        # Clear any leftover .ips file from a previous run with this PID.
        try:
            self.ips_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def start(self):
        if self.process and self.process.poll() is None:
            return
        script_path = Path(__file__).resolve()
        args = [sys.executable, str(script_path), "--window", str(self.state_path)]
        if self.ips_tracker_enabled:
            args.extend([
                "--ips", str(self.ips_path),
                "--threshold", str(_load_low_ips_threshold()),
            ])
        self.process = subprocess.Popen(
            args,
            cwd=str(script_path.parent),
            close_fds=True,
        )
        time.sleep(0.2)
        if self.process.poll() is not None:
            print("Runtime pause control window failed to start.")

    def is_paused(self):
        return read_state(self.state_path) == PAUSED

    def publish_ips(self, value):
        if not self.ips_tracker_enabled:
            return
        publish_ips(self.ips_path, value)

    def close(self):
        write_state(self.state_path, RUNNING)
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        try:
            self.ips_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


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


def run_window(state_path, ips_path=None, threshold=None):
    import tkinter as tk
    import customtkinter as ctk
    from gui import theme

    ips_tracker_enabled = ips_path is not None
    threshold = float(threshold) if threshold is not None else 4.0

    ctk.set_appearance_mode("dark")

    root = ctk.CTk()
    root.title("PylaAi-XXZ Control")
    root.geometry("280x260" if ips_tracker_enabled else "280x170")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.configure(fg_color=theme.BG)
    owner_pid = None
    try:
        owner_pid = int(Path(state_path).stem.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        owner_pid = None

    status_var = tk.StringVar(value="Running")
    button_var = tk.StringVar(value="Pause Bot")

    card = ctk.CTkFrame(
        root,
        fg_color=theme.CARD,
        corner_radius=14,
        border_width=1,
        border_color=theme.CARD_BORDER,
    )
    card.pack(fill="both", expand=True, padx=12, pady=12)

    title = ctk.CTkLabel(
        card,
        text="PylaAi-XXZ Bot Control",
        text_color=theme.TEXT_PRIMARY,
        font=theme.ui_font(17, "bold"),
    )
    title.pack(pady=(14, 2))

    history = deque(maxlen=int(IPS_HISTORY_SECONDS / 0.75) + 4)
    last_seen_ts = [0.0]

    ips_value_label = None
    graph_canvas = None
    if ips_tracker_enabled:
        ips_value_label = ctk.CTkLabel(
            card,
            text="\u2014 IPS",
            text_color=theme.SUCCESS,
            font=theme.ui_font(22, "bold"),
        )
        ips_value_label.pack(pady=(8, 4))

        graph_frame = ctk.CTkFrame(
            card,
            fg_color=theme.BG,
            corner_radius=8,
            border_width=1,
            border_color=theme.CARD_BORDER,
        )
        graph_frame.pack(padx=12, pady=(0, 8))

        graph_canvas = tk.Canvas(
            graph_frame,
            width=242,
            height=52,
            bg=theme.BG,
            highlightthickness=0,
            bd=0,
        )
        graph_canvas.pack(padx=2, pady=2)

    status_label = ctk.CTkLabel(
        card,
        textvariable=status_var,
        text_color=theme.SUCCESS,
        font=theme.ui_font(14, "bold"),
    )
    status_label.pack(pady=(0, 12))

    def redraw_graph():
        if graph_canvas is None:
            return
        graph_canvas.delete("all")
        width = int(graph_canvas.winfo_width()) or 242
        height = int(graph_canvas.winfo_height()) or 52
        pad = 3

        max_value = max((v for _, v in history), default=0.0)
        axis_max = max(IPS_GRAPH_AXIS_FLOOR, max_value * 1.15, threshold * 1.25)

        def y_for(value):
            value = max(0.0, min(value, axis_max))
            return height - pad - (value / axis_max) * (height - 2 * pad)

        mid_y = y_for(axis_max / 2)
        graph_canvas.create_line(
            pad, mid_y, width - pad, mid_y,
            fill=theme.CARD_BORDER, width=1,
        )

        threshold_y = y_for(threshold)
        graph_canvas.create_line(
            pad, threshold_y, width - pad, threshold_y,
            fill=theme.ERROR, width=1, dash=(3, 3),
        )

        if len(history) < 2:
            graph_canvas.create_text(
                width / 2, height / 2,
                text="waiting...",
                fill=theme.TEXT_MUTED,
                font=(theme.FONT_FAMILY, 9),
            )
            return

        usable_w = width - 2 * pad
        n = len(history)
        points = []
        for i, (_, value) in enumerate(history):
            x = pad + (i / (n - 1)) * usable_w
            y = y_for(value)
            points.extend((x, y))
        graph_canvas.create_line(
            *points,
            fill=theme.SUCCESS,
            width=2,
            smooth=False,
        )

    def update_ips_ui():
        if not ips_tracker_enabled:
            return
        value, _age = read_ips(ips_path) if ips_path else (None, None)
        if value is None:
            if ips_value_label is not None:
                ips_value_label.configure(text="\u2014 IPS")
        else:
            if ips_value_label is not None:
                ips_value_label.configure(text=f"{value:.1f} IPS")
            try:
                raw = Path(ips_path).read_text(encoding="utf-8")
                ts = float(json.loads(raw).get("ts", 0.0))
            except (OSError, ValueError, KeyError, TypeError):
                ts = 0.0
            if ts and ts > last_seen_ts[0]:
                last_seen_ts[0] = ts
                history.append((ts, value))
        # Drop samples older than the visible window.
        cutoff = time.time() - IPS_HISTORY_SECONDS
        while history and history[0][0] < cutoff:
            history.popleft()
        redraw_graph()

    def refresh():
        if owner_pid and not process_is_alive(owner_pid):
            root.destroy()
            return
        paused = read_state(state_path) == PAUSED
        status_var.set("Paused" if paused else "Running")
        button_var.set("Resume Bot" if paused else "Pause Bot")
        status_label.configure(text_color=theme.WARN if paused else theme.SUCCESS)
        pause_button.configure(
            fg_color=theme.TEAL if paused else theme.ACCENT,
            hover_color=theme.SKY if paused else theme.ACCENT_HOVER,
        )
        update_ips_ui()

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

    def on_close():
        write_state(state_path, RUNNING)
        root.destroy()

    pause_button = ctk.CTkButton(
        card,
        textvariable=button_var,
        command=toggle_pause,
        width=170,
        height=40,
        corner_radius=10,
        fg_color=theme.ACCENT,
        hover_color=theme.ACCENT_HOVER,
        text_color=theme.TEXT_PRIMARY,
        font=theme.ui_font(15, "bold"),
    )
    pause_button.pack(pady=(0, 8))

    hint = ctk.CTkLabel(
        card,
        text="Movement stops instantly while paused.",
        text_color=theme.TEXT_SECONDARY,
        font=theme.ui_font(11),
    )
    hint.pack()

    root.protocol("WM_DELETE_WINDOW", on_close)
    refresh_loop()
    root.mainloop()


def _parse_window_args(argv):
    """Parse the subprocess --window args into (state_path, ips_path, threshold)."""
    if len(argv) < 3 or argv[1] != "--window":
        return None
    state_path = argv[2]
    ips_path = None
    threshold = None
    i = 3
    while i < len(argv):
        if argv[i] == "--ips" and i + 1 < len(argv):
            ips_path = argv[i + 1]
            i += 2
        elif argv[i] == "--threshold" and i + 1 < len(argv):
            try:
                threshold = float(argv[i + 1])
            except ValueError:
                threshold = None
            i += 2
        else:
            i += 1
    return state_path, ips_path, threshold


if __name__ == "__main__":
    parsed = _parse_window_args(sys.argv)
    if parsed is not None:
        run_window(*parsed)
