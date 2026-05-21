import re


def validate_config_value(section, key, value):
    text = str(value or "").strip()

    if section == "settings" and key == "pause_menu_graph_samples":
        sample_count = int(float(text or "0"))
        if sample_count < 30 or sample_count > 120:
            raise ValueError("Pause graph samples must be between 30 and 120.")

    if section == "settings" and key in {
        "wall_detection_confidence",
        "entity_detection_confidence",
        "minimum_movement_delay",
        "unstuck_movement_delay",
        "unstuck_movement_hold_time",
        "ocr_scale_down_factor",
    }:
        number = float(text or "0")
        if number < 0:
            raise ValueError(f"{key.replace('_', ' ')} cannot be negative.")

    if section == "discord" and key == "webhook_url" and text:
        if not re.match(r"^https://discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$", text):
            raise ValueError("Discord webhook URL format looks invalid.")

    if section == "discord" and key == "discord_bot_token" and text:
        if len(text) < 20 or "." not in text:
            raise ValueError("Discord bot token format looks invalid.")

    if section == "telegram" and key == "bot_token" and text:
        if ":" not in text or len(text) < 20:
            raise ValueError("Telegram bot token format looks invalid.")

    if section == "api" and key == "player_tag" and text:
        if not text.startswith("#"):
            raise ValueError("Player tag should start with #.")
