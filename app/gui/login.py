import os
import sys

import customtkinter as ctk  # Import the customtkinter library
from gui.license_client import check_if_exists
from gui.theme import get_palette, load_ui_theme_mode, resolve_theme_mode
from i18n import configure_from_general_config, translate
from utils import api_base_url, load_toml_as_dict, save_dict_as_toml


def login(logged_in_setter):
    configure_from_general_config()

    if api_base_url == "localhost":
        logged_in_setter(True)
        return

    def validate_api_key(api_key):
        return check_if_exists(api_key)

    pal = get_palette(load_ui_theme_mode())

    def on_login_button_click():
        api_key = api_key_entry.get()
        if validate_api_key(api_key):
            result_label.configure(text=translate("login.success"), text_color=pal["success"])
            logged_in_setter(True)
            app.destroy()
            save_dict_as_toml({"key": api_key}, "./cfg/login.toml")
            return
        else:
            result_label.configure(text=translate("login.invalid"), text_color=pal["danger"])

    login_data = load_toml_as_dict('./cfg/login.toml')
    auth_key = login_data['key']
    if auth_key:
        if validate_api_key(auth_key):
            logged_in_setter(True)
            return

    ctk.set_appearance_mode(resolve_theme_mode(load_ui_theme_mode()))

    app = ctk.CTk()
    app.title(translate("login.title"))
    app.geometry('500x210')
    app.configure(fg_color=pal["bg"])

    label = ctk.CTkLabel(app, text=translate("login.prompt"), font=("Segoe UI", 18, "bold"), text_color=pal["text"])
    label.pack(pady=(20, 5))

    api_key_entry = ctk.CTkEntry(
        app,
        placeholder_text=translate("login.placeholder"),
        font=("Segoe UI", 16),
        width=400,
        height=38,
        corner_radius=10,
        fg_color=pal["surface"],
        border_color=pal["accent_border"],
        text_color=pal["text"],
        placeholder_text_color=pal["muted"],
    )
    api_key_entry.pack(pady=(18, 12))

    login_button = ctk.CTkButton(
        app,
        text=translate("login.button"),
        command=on_login_button_click,
        font=("Segoe UI", 16, "bold"),
        height=38,
        corner_radius=10,
        fg_color=pal["accent"],
        hover_color=pal["accent_hover"],
        text_color="#ffffff",
    )
    login_button.pack()

    result_label = ctk.CTkLabel(app, text="", font=("Segoe UI", 12), text_color=pal["muted"])
    result_label.pack(pady=(10, 0))

    app.mainloop()
