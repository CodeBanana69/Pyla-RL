import os
import subprocess
import sys
import time
import ctypes
from pathlib import Path


RUNNING = "running"
PAUSED = "paused"


def write_state(path, state):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(state, encoding="utf-8")


def read_state(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip().lower()
    except OSError:
        return RUNNING


class RuntimeControlWindow:
    def __init__(self):
        state_dir = Path("logs")
        self.state_path = state_dir / f"runtime_control_{os.getpid()}.state"
        self.process = None
        write_state(self.state_path, RUNNING)

    def start(self):
        if self.process and self.process.poll() is None:
            return
        script_path = Path(__file__).resolve()
        self.process = subprocess.Popen(
            [sys.executable, str(script_path), "--window", str(self.state_path)],
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


def run_window(state_path):
    import tkinter as tk
    import customtkinter as ctk

    ctk.set_appearance_mode("dark")

    root = ctk.CTk()
    root.title("PylaAi-XXZ Control")
    root.geometry("310x206")
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
    status_label.pack(pady=(0, 10))

    def refresh():
        if owner_pid and not process_is_alive(owner_pid):
            root.destroy()
            return
        paused = read_state(state_path) == PAUSED
        status_var.set("Paused" if paused else "Running")
        button_var.set("Resume Bot" if paused else "Pause Bot")
        status_label.configure(text_color="#ff9f0a" if paused else "#30d158")
        pause_button.configure(
            fg_color="#ff9f0a" if paused else "#1f1f1f",
            hover_color="#ffb23a" if paused else "#2a2a2a",
            border_color="#8f610e" if paused else "#333333",
        )

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
        run_window(sys.argv[2])
