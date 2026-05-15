import os
import sys

import customtkinter as ctk  # Import the customtkinter library
from gui.api import check_if_exists
from gui.theme import THEME
from utils import api_base_url, save_dict_as_toml

sys.path.append(os.path.abspath('../'))
from utils import  load_toml_as_dict


def login(logged_in_setter):

    if api_base_url == "localhost":
        logged_in_setter(True)
        return

    def validate_api_key(api_key):
        return check_if_exists(api_key)

    def on_login_button_click():
        api_key = api_key_entry.get()
        if validate_api_key(api_key):
            result_label.configure(text="Login Successful!", text_color=THEME["success"])
            logged_in_setter(True)
            app.destroy()
            save_dict_as_toml({"key": api_key}, "./cfg/login.toml")
            return
        else:
            result_label.configure(text="Invalid API Key", text_color=THEME["danger"])

    login_data = load_toml_as_dict('./cfg/login.toml')
    auth_key = login_data['key']
    if auth_key:
        if validate_api_key(auth_key):
            logged_in_setter(True)
            return

    app = ctk.CTk()
    app.title('API Key Login')
    app.geometry('500x200')
    app.configure(fg_color=THEME["bg"])
    ctk.set_appearance_mode("dark")

    label = ctk.CTkLabel(app, text="Enter API Key:", font=("Comic sans MS", 20), text_color=THEME["text"])
    label.pack(pady=(20, 5))

    api_key_entry = ctk.CTkEntry(
        app,
        placeholder_text="API Key",
        font=("Comic sans MS", 20),
        width=400,
        fg_color=THEME["surface"],
        border_color=THEME["accent"],
        text_color=THEME["text"],
    )
    api_key_entry.pack(pady=(20, 10))

    login_button = ctk.CTkButton(
        app,
        text="Login",
        command=on_login_button_click,
        font=("Comic sans MS", 25),
        fg_color=THEME["accent"],
        hover_color=THEME["accent_hover"],
        text_color=THEME["text"],
    )
    login_button.pack()

    result_label = ctk.CTkLabel(app, text="", text_color=THEME["muted"])
    result_label.pack(pady=(10, 0))

    app.mainloop()
