import threading
import tkinter as tk


class SetupProgressWindow:
    def __init__(self, title="PylaAi-XXZ Setup"):
        self._root = tk.Tk()
        self._root.title(title)
        self._root.geometry("420x120")
        self._root.resizable(False, False)
        self._label = tk.Label(self._root, text="Starting setup...", anchor="w", justify="left")
        self._label.pack(fill="both", expand=True, padx=12, pady=12)
        self._root.update_idletasks()

    def update(self, message):
        self._label.configure(text=str(message))
        self._root.update_idletasks()

    def close(self):
        try:
            self._root.destroy()
        except tk.TclError:
            pass


def run_with_progress(steps):
    window = SetupProgressWindow()
    try:
        for message, action in steps:
            window.update(message)
            if action:
                action()
    finally:
        window.close()
