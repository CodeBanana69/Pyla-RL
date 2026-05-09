"""Shared dashboard-style theme tokens for CustomTkinter GUIs."""

FONT_FAMILY = "Segoe UI"

# Backgrounds & surfaces
BG = "#141417"
CARD = "#1c1c21"
CARD_BORDER = "#2d2d35"

# Text
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#A0A0A8"
TEXT_MUTED = "#888888"

# Accents (reference palette)
ACCENT = "#B197FC"
ACCENT_HOVER = "#9B7FE8"
YELLOW = "#FFD43B"
TEAL = "#63E6BE"
SKY = "#74C0FC"

# Controls
INACTIVE = "#2A2A32"
INACTIVE_HOVER = "#353540"
SEGMENT_SELECTED = "#FFFFFF"
SEGMENT_SELECTED_TEXT = "#141417"

# Semantic (stats / status)
SUCCESS = "#63E6BE"
ERROR = "#E57373"
WARN = "#FFD43B"


def ui_font(size: int, weight: str = "normal"):
    """Tuple for CustomTkinter ``font=`` arguments."""
    return (FONT_FAMILY, size, weight)


def entry_kwargs():
    """Common styling for CTkEntry widgets."""
    return {
        "fg_color": CARD,
        "border_color": CARD_BORDER,
        "text_color": TEXT_PRIMARY,
        "placeholder_text_color": TEXT_SECONDARY,
    }


def primary_button_kwargs(corner_radius: int):
    return {
        "fg_color": ACCENT,
        "hover_color": ACCENT_HOVER,
        "text_color": TEXT_PRIMARY,
        "corner_radius": corner_radius,
    }


def secondary_button_kwargs(corner_radius: int):
    return {
        "fg_color": INACTIVE,
        "hover_color": INACTIVE_HOVER,
        "text_color": TEXT_PRIMARY,
        "corner_radius": corner_radius,
    }


def option_menu_kwargs(width: int, height: int):
    return {
        "fg_color": ACCENT,
        "button_color": ACCENT,
        "button_hover_color": ACCENT_HOVER,
        "text_color": TEXT_PRIMARY,
        "width": width,
        "height": height,
    }


def checkbox_kwargs():
    return {"fg_color": ACCENT, "hover_color": ACCENT_HOVER}
