import json
from pathlib import Path

import toml


def load_toml_as_dict(path):
    if not Path(path).exists():
        return {}
    return toml.load(path)


def save_dict_as_toml(data, path):
    with open(path, "w", encoding="utf-8") as handle:
        toml.dump(data, handle)


def _to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "yes", "true", "on"}


def _yes_no(value):
    return "yes" if _to_bool(value) else "no"


def _chat_ids_to_text(value):
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value if str(item).strip())
    return str(value or "")


def _text_to_chat_ids(value):
    return [part.strip() for part in str(value or "").replace(";", ",").split(",") if part.strip()]


def _coerce(value, kind):
    if kind == "bool":
        return _to_bool(value)
    if kind == "yesno":
        return _yes_no(value)
    if kind == "int":
        return int(float(str(value).strip() or "0"))
    if kind == "float":
        return float(str(value).strip() or "0")
    if kind == "chat_ids":
        return _text_to_chat_ids(value)
    return str(value)


class HubStateStore:
    SETTINGS_FIELDS = {
        "minimum_movement_delay": ("bot", "float"),
        "wall_detection_confidence": ("bot", "float"),
        "entity_detection_confidence": ("bot", "float"),
        "unstuck_movement_delay": ("bot", "float"),
        "unstuck_movement_hold_time": ("bot", "float"),
        "super_pixels_minimum": ("bot", "float"),
        "gadget_pixels_minimum": ("bot", "float"),
        "hypercharge_pixels_minimum": ("bot", "float"),
        "current_playstyle": ("bot", "str"),
        "post_match_action": ("bot", "str"),
        "showdown_playstyle_mode": ("bot", "str"),
        "cpu_or_gpu": ("general", "str"),
        "directml_device_id": ("general", "str"),
        "long_press_star_drop": ("general", "yesno"),
        "terminal_logging": ("general", "yesno"),
        "visual_debug": ("general", "yesno"),
        "advanced_visuals": ("general", "yesno"),
        "pause_menu_ips_graph": ("general", "yesno"),
        "pause_menu_session_strip": ("general", "yesno"),
        "pause_menu_graph_samples": ("general", "int"),
        "capture_bad_vision_frames": ("general", "yesno"),
        "trophies_multiplier": ("general", "int"),
        "ocr_scale_down_factor": ("general", "float"),
        "max_ips": ("general", "int"),
        "scrcpy_max_fps": ("general", "int"),
        "used_threads": ("general", "str"),
    }
    DISCORD_FIELDS = {
        "webhook_url": "str",
        "discord_id": "str",
        "username": "str",
        "send_match_summary": "bool",
        "include_screenshot": "bool",
        "ping_when_stuck": "bool",
        "ping_when_target_is_reached": "bool",
        "ping_every_x_match": "int",
        "ping_every_x_minutes": "int",
        "discord_control_enabled": "bool",
        "discord_bot_token": "str",
        "discord_control_user_id": "str",
        "discord_control_channel_id": "str",
        "discord_control_guild_id": "str",
    }
    TELEGRAM_FIELDS = {
        "enabled": "bool",
        "bot_token": "str",
        "notification_chat_ids": "chat_ids",
        "send_match_summary": "bool",
        "include_screenshot": "bool",
        "allow_multiple_notification_chat_ids": "bool",
        "remote_control_enabled": "bool",
        "poll_timeout_seconds": "int",
    }
    API_FIELDS = {
        "player_tag": "str",
        "auto_refresh_token": "bool",
        "developer_email": "str",
        "developer_password": "str",
        "api_token": "str",
        "timeout_seconds": "int",
        "public_ip_service": "str",
        "key_name_prefix": "str",
        "delete_old_auto_tokens": "bool",
    }
    TIMER_FIELDS = {
        "super": "float",
        "hypercharge": "float",
        "gadget": "float",
        "wall_detection": "float",
        "no_detection_proceed": "float",
        "low_ips_recovery_seconds": "int",
        "low_ips_recovery_cooldown": "int",
        "low_ips_app_restart_after": "int",
        "low_ips_emulator_restart_after": "int",
    }

    def __init__(
            self,
            bot_config_path="cfg/bot_config.toml",
            general_config_path="cfg/general_config.toml",
            time_tresholds_path="cfg/time_tresholds.toml",
            match_history_path="cfg/match_history.toml",
            discord_config_path="cfg/discord_config.toml",
            telegram_base_config_path="cfg/telegram_config.toml",
            telegram_config_path="cfg/telegram_config.local.toml",
            brawl_stars_api_base_config_path="cfg/brawl_stars_api.toml",
            brawl_stars_api_config_path="cfg/brawl_stars_api.local.toml",
    ):
        self.bot_config_path = bot_config_path
        self.general_config_path = general_config_path
        self.time_tresholds_path = time_tresholds_path
        self.match_history_path = match_history_path
        self.discord_config_path = discord_config_path
        self.telegram_base_config_path = telegram_base_config_path
        self.telegram_config_path = telegram_config_path
        self.brawl_stars_api_base_config_path = brawl_stars_api_base_config_path
        self.brawl_stars_api_config_path = brawl_stars_api_config_path
        self.bot_config = load_toml_as_dict(bot_config_path)
        self.general_config = load_toml_as_dict(general_config_path)
        self.time_tresholds = load_toml_as_dict(time_tresholds_path)
        self.match_history = load_toml_as_dict(match_history_path)
        self.discord_config = load_toml_as_dict(discord_config_path)
        self.telegram_config = dict(load_toml_as_dict(telegram_base_config_path))
        self.telegram_config.update(load_toml_as_dict(telegram_config_path))
        self.brawl_stars_api_config = dict(load_toml_as_dict(brawl_stars_api_base_config_path))
        self.brawl_stars_api_config.update(load_toml_as_dict(brawl_stars_api_config_path))
        self._apply_defaults()

    def _apply_defaults(self):
        self.bot_config.setdefault("gamemode_type", 3)
        self.bot_config.setdefault("gamemode", "showdown")
        self.bot_config.setdefault("minimum_movement_delay", 0.4)
        self.bot_config.setdefault("wall_detection_confidence", 0.9)
        self.bot_config.setdefault("entity_detection_confidence", 0.6)
        self.bot_config.setdefault("unstuck_movement_delay", 3.0)
        self.bot_config.setdefault("unstuck_movement_hold_time", 1.5)
        self.bot_config.setdefault("super_pixels_minimum", 1800.0)
        self.bot_config.setdefault("gadget_pixels_minimum", 1100.0)
        self.bot_config.setdefault("hypercharge_pixels_minimum", 1800.0)
        self.bot_config.setdefault("post_match_action", "lobby")
        self.bot_config.setdefault("current_playstyle", "default.pyla")
        self.bot_config.setdefault("showdown_playstyle_mode", "follow")

        self.general_config.setdefault("cpu_or_gpu", "auto")
        self.general_config.setdefault("directml_device_id", "auto")
        self.general_config.setdefault("long_press_star_drop", "no")
        self.general_config.setdefault("terminal_logging", "no")
        self.general_config.setdefault("visual_debug", "no")
        self.general_config.setdefault("advanced_visuals", "no")
        self.general_config.setdefault("pause_menu_ips_graph", "no")
        self.general_config.setdefault("pause_menu_session_strip", "yes")
        self.general_config.setdefault("pause_menu_graph_samples", 45)
        self.general_config.setdefault("capture_bad_vision_frames", "no")
        self.general_config.setdefault("trophies_multiplier", 1)
        self.general_config.setdefault("ocr_scale_down_factor", 0.5)
        self.general_config.setdefault("max_ips", 30)
        self.general_config.setdefault("scrcpy_max_fps", 30)
        self.general_config.setdefault("used_threads", self.general_config.get("onnx_cpu_threads", "auto"))
        self.general_config.setdefault("current_emulator", "LDPlayer")
        self.general_config.setdefault("emulator_port", 5555)

        self.discord_config.setdefault("webhook_url", self.general_config.get("personal_webhook", ""))
        self.discord_config.setdefault("discord_id", self.general_config.get("discord_id", ""))
        self.discord_config.setdefault("username", "PylaAi-XXZ")
        self.discord_config.setdefault("send_match_summary", False)
        self.discord_config.setdefault("include_screenshot", True)
        self.discord_config.setdefault("ping_when_stuck", False)
        self.discord_config.setdefault("ping_when_target_is_reached", False)
        self.discord_config.setdefault("ping_every_x_match", 0)
        self.discord_config.setdefault("ping_every_x_minutes", 0)
        self.discord_config.setdefault("discord_control_enabled", False)
        self.discord_config.setdefault("discord_bot_token", "")
        self.discord_config.setdefault("discord_control_user_id", "")
        self.discord_config.setdefault("discord_control_channel_id", "")
        self.discord_config.setdefault("discord_control_guild_id", "")

        self.telegram_config.setdefault("enabled", False)
        self.telegram_config.setdefault("bot_token", "")
        self.telegram_config.setdefault("notification_chat_ids", [])
        self.telegram_config.setdefault("send_match_summary", True)
        self.telegram_config.setdefault("include_screenshot", True)
        self.telegram_config.setdefault("allow_multiple_notification_chat_ids", False)
        self.telegram_config.setdefault("remote_control_enabled", True)
        self.telegram_config.setdefault("poll_timeout_seconds", 25)

        self.brawl_stars_api_config.setdefault("player_tag", "#YOURTAG")
        self.brawl_stars_api_config.setdefault("timeout_seconds", 15)
        self.brawl_stars_api_config.setdefault("auto_refresh_token", True)
        self.brawl_stars_api_config.setdefault("developer_email", "")
        self.brawl_stars_api_config.setdefault("developer_password", "")
        self.brawl_stars_api_config.setdefault("public_ip_service", "https://api.ipify.org")
        self.brawl_stars_api_config.setdefault("key_name_prefix", "PylaAi-XXZ Auto")
        self.brawl_stars_api_config.setdefault("delete_old_auto_tokens", True)
        self.brawl_stars_api_config.setdefault("api_token", "")

        self.time_tresholds.setdefault("super", 0.1)
        self.time_tresholds.setdefault("hypercharge", 2.0)
        self.time_tresholds.setdefault("gadget", 0.5)
        self.time_tresholds.setdefault("wall_detection", 1.0)
        self.time_tresholds.setdefault("no_detection_proceed", 8.5)
        self.time_tresholds.setdefault("low_ips_recovery_seconds", 45)
        self.time_tresholds.setdefault("low_ips_recovery_cooldown", 35)
        self.time_tresholds.setdefault("low_ips_app_restart_after", 1)
        self.time_tresholds.setdefault("low_ips_emulator_restart_after", 6)

    def initial_state(self):
        gamemode = str(self.bot_config.get("gamemode", "showdown")).strip().lower()
        emulator = str(self.general_config.get("current_emulator", "LDPlayer")).strip().lower()
        return {
            "mode": "showdown-trio" if gamemode == "showdown" else gamemode,
            "emulator": "mumu" if emulator == "mumu" else "ldplayer",
        }

    def ui_state(self):
        state = self.initial_state()
        state.update({
            "settings": self._settings_state(),
            "discord": dict(self.discord_config),
            "telegram": self._telegram_state(),
            "api": dict(self.brawl_stars_api_config),
            "timers": {key: self.time_tresholds.get(key) for key in self.TIMER_FIELDS},
            "history": self._history_state(),
        })
        return state

    def state_json(self):
        return json.dumps(self.ui_state())

    def _settings_state(self):
        data = {}
        for key, (section, _) in self.SETTINGS_FIELDS.items():
            source = self.general_config if section == "general" else self.bot_config
            value = source.get(key, "")
            if key in {
                "long_press_star_drop",
                "terminal_logging",
                "visual_debug",
                "advanced_visuals",
                "pause_menu_ips_graph",
                "pause_menu_session_strip",
                "capture_bad_vision_frames",
            }:
                value = _to_bool(value)
            data[key] = value
        return data

    def _telegram_state(self):
        data = dict(self.telegram_config)
        data["notification_chat_ids"] = _chat_ids_to_text(data.get("notification_chat_ids", []))
        return data

    def _history_state(self):
        items = []
        for brawler, stats in self.match_history.items():
            if brawler == "total" or not isinstance(stats, dict):
                continue
            wins = int(stats.get("victory", 0) or 0)
            losses = int(stats.get("defeat", 0) or 0)
            games = wins + losses
            win_rate = round((wins / games) * 100, 1) if games else 0
            icon_path = Path("api") / "assets" / "brawler_icons" / f"{brawler}.png"
            items.append({
                "brawler": str(brawler),
                "victory": wins,
                "defeat": losses,
                "games": games,
                "winRate": win_rate,
                "icon": icon_path.resolve().as_uri() if icon_path.exists() else "",
            })
        items.sort(key=lambda item: (-item["games"], item["brawler"]))
        return items

    def update_config(self, section, key, value):
        if section == "settings":
            config_name, kind = self.SETTINGS_FIELDS[key]
            target = self.general_config if config_name == "general" else self.bot_config
            target[key] = _coerce(value, kind)
            save_dict_as_toml(target, self.general_config_path if config_name == "general" else self.bot_config_path)
        elif section == "discord":
            self.discord_config[key] = _coerce(value, self.DISCORD_FIELDS[key])
            save_dict_as_toml(self.discord_config, self.discord_config_path)
        elif section == "telegram":
            self.telegram_config[key] = _coerce(value, self.TELEGRAM_FIELDS[key])
            save_dict_as_toml(self.telegram_config, self.telegram_config_path)
        elif section == "api":
            self.brawl_stars_api_config[key] = _coerce(value, self.API_FIELDS[key])
            save_dict_as_toml(self.brawl_stars_api_config, self.brawl_stars_api_config_path)
        elif section == "timers":
            self.time_tresholds[key] = _coerce(value, self.TIMER_FIELDS[key])
            save_dict_as_toml(self.time_tresholds, self.time_tresholds_path)
        else:
            raise KeyError(section)
        return self.ui_state()

    def apply_state(self, patch):
        changed_bot = False
        changed_general = False

        mode = patch.get("mode")
        if mode == "showdown-trio":
            self.bot_config["gamemode_type"] = 3
            self.bot_config["gamemode"] = "showdown"
            changed_bot = True

        emulator = patch.get("emulator")
        if emulator in ("ldplayer", "mumu"):
            if emulator == "mumu":
                self.general_config["current_emulator"] = "MuMu"
                self.general_config["emulator_port"] = 16384
            else:
                self.general_config["current_emulator"] = "LDPlayer"
                self.general_config["emulator_port"] = 5555
            changed_general = True

        if changed_bot:
            save_dict_as_toml(self.bot_config, self.bot_config_path)
        if changed_general:
            save_dict_as_toml(self.general_config, self.general_config_path)
