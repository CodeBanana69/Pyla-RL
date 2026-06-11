import json
from pathlib import Path

import toml

from gui.hub_validators import validate_config_value


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
        "close_tile_detector_enabled": ("bot", "yesno"),
        "centered_wall_detection": ("bot", "yesno"),
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
        "ui_theme": ("general", "str"),
        "ui_animations": ("general", "yesno"),
        "long_press_star_drop": ("general", "yesno"),
        "terminal_logging": ("general", "yesno"),
        "terminal_verbosity": ("general", "str"),
        "movement_debug": ("general", "yesno"),
        "terminal_summary_seconds": ("general", "float"),
        "visual_debug": ("general", "yesno"),
        "advanced_visuals": ("general", "yesno"),
        "pause_menu_ips_graph": ("general", "yesno"),
        "pause_menu_session_strip": ("general", "yesno"),
        "pause_menu_auto_reopen": ("general", "yesno"),
        "pause_menu_graph_samples": ("general", "int"),
        "console_ips": ("general", "yesno"),
        "first_run_wizard": ("general", "yesno"),
        "license_accepted": ("general", "yesno"),
        "capture_bad_vision_frames": ("general", "yesno"),
        "trophies_multiplier": ("general", "int"),
        "ocr_scale_down_factor": ("general", "float"),
        "max_ips": ("general", "int"),
        "scrcpy_max_fps": ("general", "int"),
        "used_threads": ("general", "str"),
        "play_again_on_win": ("bot", "yesno"),
        "bot_uses_gadgets": ("bot", "yesno"),
        "enemy_spacing_enabled": ("bot", "yesno"),
        "enemy_spacing_blend": ("bot", "float"),
        "enemy_spacing_tolerance": ("bot", "float"),
        "enemy_spacing_hold_strafe": ("bot", "yesno"),
        "combat_los_dodge_enabled": ("bot", "yesno"),
        "combat_dodge_blend": ("bot", "float"),
        "combat_dodge_jitter_degrees": ("bot", "float"),
        "run_for_minutes": ("general", "int"),
        "emulator_autorestart": ("general", "yesno"),
        "scrcpy_max_width": ("general", "int"),
        "scrcpy_bitrate": ("general", "int"),
        "visual_debug_scale": ("general", "float"),
        "visual_debug_max_fps": ("general", "int"),
        "visual_debug_max_boxes": ("general", "int"),
        "super_debug": ("general", "yesno"),
        "wall_stuck_debug": ("general", "yesno"),
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
        "notify_on_recovery": "bool",
        "recovery_alert_threshold": "int",
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
        "notify_on_recovery": "bool",
        "recovery_alert_threshold": "int",
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
        "sync_trophies_after_match": "bool",
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
        "lobby_stuck_restart": "float",
        "visual_freeze_restart": "float",
        "global_freeze_restart": "float",
        "emulator_restart_cooldown": "float",
        "state_check": "float",
        "idle": "float",
        "low_ips_recovery_threshold": "float",
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
        self._migrate_legacy_webhook_config(discord_config_path)
        self._apply_defaults()

    def _migrate_legacy_webhook_config(self, discord_config_path):
        legacy_path = Path(discord_config_path).parent / "webhook_config.toml"
        discord_path = Path(discord_config_path)
        if not discord_path.exists() and legacy_path.exists():
            legacy_config = load_toml_as_dict(str(legacy_path))
            save_dict_as_toml(legacy_config, str(discord_path))
            self.discord_config = dict(legacy_config)

    def _apply_defaults(self):
        self.bot_config.setdefault("gamemode_type", 3)
        self.bot_config.setdefault("gamemode", "showdown")
        self.bot_config.setdefault("minimum_movement_delay", 0.4)
        self.bot_config.setdefault("wall_detection_confidence", 0.9)
        self.bot_config.setdefault("close_tile_detector_enabled", "no")
        self.bot_config.setdefault("entity_detection_confidence", 0.6)
        self.bot_config.setdefault("unstuck_movement_delay", 3.0)
        self.bot_config.setdefault("unstuck_movement_hold_time", 1.5)
        self.bot_config.setdefault("super_pixels_minimum", 1800.0)
        self.bot_config.setdefault("gadget_pixels_minimum", 1100.0)
        self.bot_config.setdefault("hypercharge_pixels_minimum", 1800.0)
        self.bot_config.setdefault("post_match_action", "lobby")
        self.bot_config.setdefault("current_playstyle", "team_showdown.pyla")
        self.bot_config.setdefault("centered_wall_detection", "no")
        self.bot_config.setdefault("perceived_tile_size", 54)
        if _to_bool(self.bot_config.get("close_tile_detector_enabled")):
            self.bot_config["centered_wall_detection"] = "yes"
        self.bot_config.setdefault("showdown_playstyle_mode", "follow")
        self.bot_config.setdefault("play_again_on_win", "no")
        self.bot_config.setdefault("bot_uses_gadgets", "yes")
        self.bot_config.setdefault("enemy_spacing_enabled", "yes")
        self.bot_config.setdefault("enemy_spacing_blend", 0.35)
        self.bot_config.setdefault("enemy_spacing_tolerance", 40)
        self.bot_config.setdefault(
            "enemy_spacing_hold_strafe",
            self.bot_config.get("strafe_while_attacking", "yes"),
        )
        self.bot_config.setdefault("combat_los_dodge_enabled", "yes")
        self.bot_config.setdefault("combat_dodge_blend", 0.45)
        self.bot_config.setdefault("combat_dodge_jitter_degrees", 18.0)

        self.general_config.setdefault("cpu_or_gpu", "auto")
        self.general_config.setdefault("directml_device_id", "auto")
        self.general_config.setdefault("ui_theme", "system")
        self.general_config.setdefault("ui_animations", "yes")
        self.general_config.setdefault("long_press_star_drop", "no")
        self.general_config.setdefault("terminal_logging", "no")
        self.general_config.setdefault("terminal_verbosity", "normal")
        self.general_config.setdefault("movement_debug", "no")
        self.general_config.setdefault("terminal_summary_seconds", 5)
        self.general_config.setdefault("visual_debug", "no")
        self.general_config.setdefault("advanced_visuals", "no")
        self.general_config.setdefault("pause_menu_ips_graph", "no")
        self.general_config.setdefault("pause_menu_session_strip", "yes")
        self.general_config.setdefault("pause_menu_auto_reopen", "yes")
        self.general_config.setdefault("pause_menu_graph_samples", 45)
        self.general_config.setdefault("console_ips", "yes")
        self.general_config.setdefault("first_run_wizard", "yes")
        self.general_config.setdefault("license_accepted", "no")
        self.general_config.setdefault("capture_bad_vision_frames", "no")
        self.general_config.setdefault("trophies_multiplier", 1)
        self.general_config.setdefault("ocr_scale_down_factor", 0.5)
        self.general_config.setdefault("max_ips", 30)
        self.general_config.setdefault("scrcpy_max_fps", 30)
        self.general_config.setdefault("used_threads", self.general_config.get("onnx_cpu_threads", "auto"))
        self.general_config.setdefault("current_emulator", "LDPlayer")
        self.general_config.setdefault("emulator_port", 5555)
        self.general_config.setdefault("run_for_minutes", 0)
        self.general_config.setdefault("emulator_autorestart", "no")
        self.general_config.setdefault("scrcpy_max_width", 960)
        self.general_config.setdefault("scrcpy_bitrate", 3000000)
        self.general_config.setdefault("visual_debug_scale", 1.0)
        self.general_config.setdefault("visual_debug_max_fps", 15)
        self.general_config.setdefault("visual_debug_max_boxes", 40)
        self.general_config.setdefault("super_debug", "no")
        self.general_config.setdefault("wall_stuck_debug", "no")

        self.discord_config.setdefault("webhook_url", self.general_config.get("personal_webhook", ""))
        self.discord_config.setdefault("discord_id", self.general_config.get("discord_id", ""))
        self.discord_config.setdefault("username", "Pyla-RL")
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
        self.discord_config.setdefault("notify_on_recovery", False)
        self.discord_config.setdefault("recovery_alert_threshold", 3)

        self.telegram_config.setdefault("enabled", False)
        self.telegram_config.setdefault("bot_token", "")
        self.telegram_config.setdefault("notification_chat_ids", [])
        self.telegram_config.setdefault("send_match_summary", True)
        self.telegram_config.setdefault("include_screenshot", True)
        self.telegram_config.setdefault("allow_multiple_notification_chat_ids", False)
        self.telegram_config.setdefault("remote_control_enabled", True)
        self.telegram_config.setdefault("poll_timeout_seconds", 25)
        self.telegram_config.setdefault("notify_on_recovery", False)
        self.telegram_config.setdefault("recovery_alert_threshold", 3)

        self.brawl_stars_api_config.setdefault("player_tag", "#YOURTAG")
        self.brawl_stars_api_config.setdefault("timeout_seconds", 15)
        self.brawl_stars_api_config.setdefault("auto_refresh_token", True)
        self.brawl_stars_api_config.setdefault("developer_email", "")
        self.brawl_stars_api_config.setdefault("developer_password", "")
        self.brawl_stars_api_config.setdefault("public_ip_service", "https://api.ipify.org")
        self.brawl_stars_api_config.setdefault("key_name_prefix", "Pyla-RL Auto")
        self.brawl_stars_api_config.setdefault("delete_old_auto_tokens", True)
        self.brawl_stars_api_config.setdefault("sync_trophies_after_match", True)
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
        self.time_tresholds.setdefault("lobby_stuck_restart", 120.0)
        self.time_tresholds.setdefault("visual_freeze_restart", 45.0)
        self.time_tresholds.setdefault("global_freeze_restart", 60.0)
        self.time_tresholds.setdefault("emulator_restart_cooldown", 180.0)
        self.time_tresholds.setdefault("state_check", 0.5)
        self.time_tresholds.setdefault("idle", 30.0)
        self.time_tresholds.setdefault("low_ips_recovery_threshold", 3.0)

    def initial_state(self):
        gamemode = str(self.bot_config.get("gamemode", "showdown")).strip().lower()
        emulator = str(self.general_config.get("current_emulator", "LDPlayer")).strip().lower()
        if gamemode == "showdown":
            mode = "showdown-trio"
        elif gamemode == "brawlball":
            mode = "brawl-ball"
        else:
            mode = gamemode
        return {
            "mode": mode,
            "emulator": "mumu" if emulator == "mumu" else "ldplayer",
        }

    def ui_state(self, preflight=None, correct_zoom=True):
        from performance_profile import PERFORMANCE_PROFILES
        from gui.brawler_queue import brawler_icon_uri, load_push_order, load_queue, queue_state_items
        from gui.official_source import read_build_info, verify_official_source
        from utils import get_brawler_list, get_playstyles_list

        from gui.hub_tutorials import tutorial_topics

        brawler_names = get_brawler_list()
        source_status = verify_official_source()
        build_info = read_build_info()
        state = self.initial_state()
        if preflight is None:
            preflight = {"ready": False, "checks": []}
        state.update({
            "settings": self._settings_state(),
            "discord": dict(self.discord_config),
            "telegram": self._telegram_state(),
            "api": dict(self.brawl_stars_api_config),
            "timers": {key: self.time_tresholds.get(key) for key in self.TIMER_FIELDS},
            "history": self._history_state(),
            "preflight": preflight,
            "queue": queue_state_items(load_queue()),
            "multiInstance": self._multi_instance_state(),
            "meta": {
                "profileDescriptions": {
                    key: profile.get("description", "")
                    for key, profile in PERFORMANCE_PROFILES.items()
                },
                "firstRunWizard": _to_bool(self.general_config.get("first_run_wizard", "yes")),
                "licenseAccepted": _to_bool(self.general_config.get("license_accepted", "no")),
                "sourceStatus": source_status,
                "buildInfo": build_info,
                "configDir": str(Path("cfg").resolve()),
                "pushOrder": load_push_order(),
                "brawlers": brawler_names,
                "brawlerOptions": [
                    {"name": name, "icon": brawler_icon_uri(name)}
                    for name in brawler_names
                ],
                "tutorials": tutorial_topics(),
                "playstyles": [
                    {
                        "filename": item.get("filename", ""),
                        "name": (item.get("metadata") or {}).get("name", item.get("filename", "")),
                        "description": (item.get("metadata") or {}).get("description", ""),
                    }
                    for item in get_playstyles_list()
                ],
            },
        })
        return state

    def _multi_instance_state(self):
        from gui.instance_config import is_multi_instance_enabled, load_instances_config
        from gui.instance_registry import list_instances

        config = load_instances_config()
        return {
            "enabled": is_multi_instance_enabled(),
            "defaultInstance": str(config.get("multi_instance", {}).get("default_instance", "") or ""),
            "instances": list_instances(),
        }

    def set_multi_instance_enabled(self, enabled: bool):
        from gui.instance_config import ensure_multi_instance_profiles, set_multi_instance_enabled

        if enabled:
            ensure_multi_instance_profiles()
        return set_multi_instance_enabled(enabled)

    def save_instance_profile(self, instance_id: str, profile: dict):
        from gui.instance_config import upsert_instance_profile

        return upsert_instance_profile(instance_id, profile)

    def delete_instance_profile(self, instance_id: str):
        from gui.instance_config import delete_instance_profile

        return delete_instance_profile(instance_id)

    def state_json(self, preflight=None, correct_zoom=True):
        return json.dumps(self.ui_state(preflight=preflight, correct_zoom=correct_zoom))

    def _settings_state(self):
        data = {}
        for key, (section, _) in self.SETTINGS_FIELDS.items():
            source = self.general_config if section == "general" else self.bot_config
            value = source.get(key, "")
            if key in {
                "long_press_star_drop",
                "ui_animations",
                "terminal_logging",
                "movement_debug",
                "visual_debug",
                "advanced_visuals",
                "pause_menu_ips_graph",
                "pause_menu_session_strip",
                "pause_menu_auto_reopen",
                "console_ips",
                "first_run_wizard",
                "license_accepted",
                "capture_bad_vision_frames",
                "play_again_on_win",
                "bot_uses_gadgets",
                "enemy_spacing_enabled",
                "enemy_spacing_hold_strafe",
                "combat_los_dodge_enabled",
                "emulator_autorestart",
                "super_debug",
                "wall_stuck_debug",
            }:
                value = _to_bool(value)
            data[key] = value
        return data

    def _telegram_state(self):
        data = dict(self.telegram_config)
        data["notification_chat_ids"] = _chat_ids_to_text(data.get("notification_chat_ids", []))
        return data

    def _history_state(self):
        from gui.brawler_queue import brawler_icon_uri
        from match_journal import read_recent_matches

        items = []
        total_wins = 0
        total_losses = 0
        total_draws = 0
        for brawler, stats in self.match_history.items():
            if brawler == "total" or not isinstance(stats, dict):
                continue
            wins = int(stats.get("victory", 0) or 0)
            losses = int(stats.get("defeat", 0) or 0)
            draws = int(stats.get("draw", 0) or 0)
            games = wins + losses + draws
            win_rate = round((wins / games) * 100, 1) if games else 0
            total_wins += wins
            total_losses += losses
            total_draws += draws
            items.append({
                "brawler": str(brawler),
                "victory": wins,
                "defeat": losses,
                "draw": draws,
                "games": games,
                "winRate": win_rate,
                "icon": brawler_icon_uri(brawler),
            })
        items.sort(key=lambda item: (-item["games"], item["brawler"]))
        total_games = total_wins + total_losses + total_draws
        summary = {
            "victory": total_wins,
            "defeat": total_losses,
            "draw": total_draws,
            "games": total_games,
            "winRate": round((total_wins / total_games) * 100, 1) if total_games else 0,
        }
        recent = []
        for record in read_recent_matches(limit=50):
            brawler = str(record.get("brawler", "") or "")
            recent.append({
                "ts": record.get("ts", ""),
                "brawler": brawler,
                "result": record.get("result", ""),
                "delta": record.get("delta"),
                "mode": record.get("mode", ""),
                "icon": brawler_icon_uri(brawler),
            })
        return {
            "items": items,
            "summary": summary,
            "recent": recent,
        }

    def update_config(self, section, key, value):
        validate_config_value(section, key, value)
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

    def export_match_history_csv(self):
        from match_journal import read_all_matches

        export_dir = Path("logs")
        export_dir.mkdir(parents=True, exist_ok=True)
        export_path = export_dir / "match_history_export.csv"
        lines = ["brawler,victory,defeat,draw,games,win_rate"]
        history = self._history_state()
        for item in history["items"]:
            lines.append(
                f"{item['brawler']},{item['victory']},{item['defeat']},{item['draw']},"
                f"{item['games']},{item['winRate']}"
            )
        lines.append("")
        lines.append("timestamp,brawler,mode,result,delta")
        for record in read_all_matches():
            lines.append(
                f"{record.get('ts', '')},{record.get('brawler', '')},{record.get('mode', '')},"
                f"{record.get('result', '')},{record.get('delta', '')}"
            )
        export_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(export_path.resolve())

    def refresh_match_history(self):
        self.match_history = load_toml_as_dict(self.match_history_path)
        return self.ui_state()

    def load_queue(self):
        from gui.brawler_queue import load_queue
        return load_queue()

    def save_queue(self, queue):
        from gui.brawler_queue import save_queue
        return save_queue(queue)

    def sort_queue(self, *, mode="cups_desc"):
        from gui.brawler_queue import QUEUE_SORT_MODES, load_queue, persist_queue, sort_queue

        queue = sort_queue(load_queue(), mode=mode)
        if not queue:
            raise ValueError("Farm plan is empty.")
        persist_queue(queue)
        return queue, mode if mode in QUEUE_SORT_MODES else "cups_desc"

    def sort_queue_by_trophies(self, *, descending=True):
        from gui.brawler_queue import load_queue, persist_queue, sort_queue_by_trophies

        queue = sort_queue_by_trophies(load_queue(), descending=descending)
        if not queue:
            raise ValueError("Farm plan is empty.")
        persist_queue(queue)
        return queue

    def build_push_all(self, target_trophies):
        from gui.brawler_queue import build_push_all_queue, load_push_order, persist_queue
        from utils import get_brawler_list

        queue = build_push_all_queue(
            target_trophies=target_trophies,
            brawlers=get_brawler_list(),
            priority_order=load_push_order(),
        )
        if not queue:
            raise ValueError("No brawlers below the target trophy count.")
        persist_queue(queue)
        return queue

    def reset_match_history(self):
        from match_journal import clear_journal

        self.match_history = {"total": {"victory": 0, "defeat": 0, "draw": 0}}
        save_dict_as_toml(self.match_history, self.match_history_path)
        clear_journal()
        return self.ui_state()

    def apply_state(self, patch):
        changed_bot = False
        changed_general = False

        mode = patch.get("mode")
        mode_map = {
            "showdown-trio": (3, "showdown"),
            "brawl-ball": (4, "brawlball"),
            "other-3": (3, "other"),
            "basketbrawl": (5, "basketbrawl"),
        }
        if mode in mode_map:
            gamemode_type, gamemode = mode_map[mode]
            self.bot_config["gamemode_type"] = gamemode_type
            self.bot_config["gamemode"] = gamemode
            if mode == "brawl-ball":
                self.bot_config["current_playstyle"] = "default.pyla"
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
