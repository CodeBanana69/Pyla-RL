"""Unified UI theme tokens for Pyla-RL.

Single source of truth for both the QML hub (via gui.qml_hub.HubBridge.themeJson)
and the CustomTkinter windows (login, brawler picker, pause menu).

Two full palettes (light + dark) share the same orange brand accent. The active
mode is stored as `ui_theme` in cfg/general_config.toml ("light" | "dark" |
"system"); "system" follows the Windows app theme.
"""

VALID_THEME_MODES = ("light", "dark", "system")

DARK = {
    "bg": "#0b0c12",
    "chrome": "#11131b",
    "surface": "#161925",
    "surface_2": "#1c2030",
    "surface_3": "#252a3d",
    "hairline": "#262b3d",
    "hairline_strong": "#333a52",
    "border": "#333a52",
    "accent": "#ff9f0a",
    "accent_hover": "#ffb23a",
    "accent_dark": "#b87405",
    "accent_soft": "#33250e",
    "accent_border": "#8f610e",
    "accent_ring": "#aa7414",
    "danger": "#ff5d52",
    "danger_hover": "#ff7d74",
    "danger_soft": "#3a1518",
    "danger_border": "#7a2020",
    "success": "#30d158",
    "success_soft": "#15301d",
    "warning": "#ffd60a",
    "warn_soft": "#2a220c",
    "text": "#f5f6fa",
    "muted": "#aab0c0",
    "muted_2": "#6b7185",
    "faint": "#707689",
    "link": "#7ccbff",
    "hover_tint": "#232636",
    "knob": "#ffffff",
    "disabled": "#585d6e",
    "glow_a": "#ff9f0a",
    "glow_b": "#7a5cff",
    "glow_c": "#2bd9c8",
}

LIGHT = {
    "bg": "#eef0f7",
    "chrome": "#f5f6fb",
    "surface": "#ffffff",
    "surface_2": "#f2f3f9",
    "surface_3": "#e7e9f2",
    "hairline": "#dcdfeb",
    "hairline_strong": "#c6cad9",
    "border": "#c6cad9",
    "accent": "#f08c00",
    "accent_hover": "#d97e06",
    "accent_dark": "#b86a04",
    "accent_soft": "#ffeed3",
    "accent_border": "#f3c277",
    "accent_ring": "#e8a93f",
    "danger": "#d93a2f",
    "danger_hover": "#b92c23",
    "danger_soft": "#fde2df",
    "danger_border": "#e7b4b0",
    "success": "#1e9e4a",
    "success_soft": "#ddf5e3",
    "warning": "#b8860b",
    "warn_soft": "#fff3d6",
    "text": "#1a1d28",
    "muted": "#4d5468",
    "muted_2": "#8b91a5",
    "faint": "#9298ab",
    "link": "#0a66c2",
    "hover_tint": "#e9ebf4",
    "knob": "#ffffff",
    "disabled": "#b9bdcb",
    "glow_a": "#ffb454",
    "glow_b": "#9d86ff",
    "glow_c": "#5fe3d2",
}

# Legacy alias: existing call sites import THEME directly (dark by default).
THEME = DARK


def _with_alpha(hex_color, alpha):
    """Return an #AARRGGBB color string for QML from #RRGGBB + 0..1 alpha."""
    value = str(hex_color).lstrip("#")
    channel = max(0, min(255, round(float(alpha) * 255)))
    return f"#{channel:02x}{value}"


def normalize_theme_mode(value):
    mode = str(value or "").strip().lower()
    return mode if mode in VALID_THEME_MODES else "system"


def detect_system_theme():
    """Best-effort Windows app theme detection. Defaults to dark."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if int(value) else "dark"
    except Exception:
        return "dark"


def resolve_theme_mode(mode=None):
    mode = normalize_theme_mode(mode)
    if mode == "system":
        return detect_system_theme()
    return mode


def get_palette(mode=None):
    return LIGHT if resolve_theme_mode(mode) == "light" else DARK


def load_ui_theme_mode(general_config_path="cfg/general_config.toml"):
    try:
        from utils import load_toml_as_dict

        config = load_toml_as_dict(general_config_path)
        if config:
            return normalize_theme_mode(config.get("ui_theme", "system"))
    except Exception:
        pass
    return "system"


def load_ui_animations_enabled(general_config_path="cfg/general_config.toml"):
    try:
        from utils import load_toml_as_dict

        config = load_toml_as_dict(general_config_path)
        if config:
            value = str(config.get("ui_animations", "yes")).strip().lower()
            return value in {"1", "yes", "true", "on"}
    except Exception:
        pass
    return True


def qml_colors(mode=None):
    """Build the QML-facing color map with translucent glass variants."""
    resolved = resolve_theme_mode(mode)
    pal = LIGHT if resolved == "light" else DARK
    dark = resolved == "dark"
    edge = "#ffffff" if dark else "#1a2036"
    return {
        "bg": pal["bg"],
        "chrome": _with_alpha(pal["chrome"], 0.66 if dark else 0.72),
        "panel": _with_alpha(pal["surface"], 0.62 if dark else 0.66),
        "panel2": _with_alpha(pal["surface_2"], 0.72 if dark else 0.74),
        "panel3": _with_alpha(pal["surface_3"], 0.92),
        "border": _with_alpha(edge, 0.16 if dark else 0.18),
        "borderSoft": _with_alpha(edge, 0.08 if dark else 0.10),
        "hover": _with_alpha(edge, 0.07),
        "glassHighlight": _with_alpha("#ffffff", 0.07 if dark else 0.80),
        "scrim": _with_alpha("#000000", 0.55) if dark else _with_alpha("#1a2036", 0.45),
        "text": pal["text"],
        "muted": pal["muted"],
        "faint": pal["faint"],
        "accent": pal["accent"],
        "accentHover": pal["accent_hover"],
        "accentSoft": _with_alpha(pal["accent"], 0.16),
        "accentBorder": _with_alpha(pal["accent"], 0.55),
        "ok": pal["success"],
        "okSoft": _with_alpha(pal["success"], 0.18),
        "danger": pal["danger"],
        "dangerSoft": _with_alpha(pal["danger"], 0.16),
        "warnSoft": _with_alpha(pal["warning"], 0.16),
        "knob": pal["knob"],
        "disabled": pal["disabled"],
        "link": pal["link"],
        "glowA": pal["glow_a"],
        "glowB": pal["glow_b"],
        "glowC": pal["glow_c"],
    }


def qml_theme_payload(mode=None, animations=True):
    mode = normalize_theme_mode(mode)
    resolved = resolve_theme_mode(mode)
    return {
        "mode": mode,
        "resolved": resolved,
        "animations": bool(animations),
        "colors": qml_colors(resolved),
    }
