import os
import sys

import customtkinter as ctk
from gui.api import check_if_exists
from utils import api_base_url, save_dict_as_toml
from gui import theme

sys.path.append(os.path.abspath('../'))
from utils import load_toml_as_dict


def login(logged_in_setter):

    if api_base_url == "localhost":
        logged_in_setter(True)
        return

    def validate_api_key(api_key):
        return check_if_exists(api_key)

    def on_login_button_click():
        api_key = api_key_entry.get()
        if validate_api_key(api_key):
            result_label.configure(text="Login Successful!", text_color=theme.SUCCESS)
            logged_in_setter(True)
            app.destroy()
            save_dict_as_toml({"key": api_key}, "./cfg/login.toml")
            return
        else:
            result_label.configure(text="Invalid API Key", text_color=theme.ERROR)

    login_data = load_toml_as_dict('./cfg/login.toml')
    auth_key = login_data['key']
    if auth_key:
        if validate_api_key(auth_key):
            logged_in_setter(True)
            return

    app = ctk.CTk()
    app.title('API Key Login')
    app.geometry('520x340')
    app.configure(fg_color=theme.BG)
    ctk.set_appearance_mode("dark")

    card = ctk.CTkFrame(
        app,
        fg_color=theme.CARD,
        corner_radius=20,
        border_width=1,
        border_color=theme.CARD_BORDER,
    )
    card.pack(expand=True, fill="both", padx=28, pady=28)

    label = ctk.CTkLabel(card, text="Enter API Key:", font=theme.ui_font(22, "bold"))
    label.pack(pady=(28, 8))

    api_key_entry = ctk.CTkEntry(
        card,
        placeholder_text="API Key",
        font=theme.ui_font(18),
        width=420,
        **theme.entry_kwargs(),
    )
    api_key_entry.pack(pady=(12, 16))

    login_button = ctk.CTkButton(
        card,
        text="Login",
        command=on_login_button_click,
        font=theme.ui_font(20, "bold"),
        width=220,
        height=46,
        **theme.primary_button_kwargs(14),
    )
    login_button.pack(pady=(8, 8))

    result_label = ctk.CTkLabel(card, text="", font=theme.ui_font(14))
    result_label.pack(pady=(10, 24))

    app.mainloop()
