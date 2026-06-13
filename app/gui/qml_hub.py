import json
import os
import subprocess
import sys
from pathlib import Path

from gui.hub_state import HubStateStore, _to_bool as _to_bool_setting


def _normalize_dialog_path(raw_path):
    path = str(raw_path or "").strip()
    if not path:
        return ""
    if path.startswith("file:"):
        from PySide6.QtCore import QUrl

        return QUrl(path).toLocalFile()
    return path


def apply_windows_glass_effects(window, dark=True):
    """Best-effort Win11 DWM polish for the frameless hub window.

    Rounds the window corners and matches the titlebar/backdrop hint to the
    active theme. Safe no-op on older Windows or non-Windows platforms.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(window.winId())
        if not hwnd:
            return
        dwm = ctypes.windll.dwmapi
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        dark_flag = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_flag), ctypes.sizeof(dark_flag))
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2
        corner = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
    except Exception:
        pass


def ensure_pyside6_available():
    try:
        import PySide6  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    if str(Path(sys.executable).name).lower() in {"python.exe", "pythonw.exe"}:
        print("PySide6 is missing; installing it so the new QML hub can start...")
        subprocess.check_call([
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "PySide6>=6.7.0",
        ])
        return
    raise ModuleNotFoundError(
        "No module named 'PySide6'. Run setup.exe or `py -3.11-64 -m pip install PySide6>=6.7.0`."
    )


class QmlHub:
    def __init__(
            self,
            version_str,
            latest_version_str,
            correct_zoom=True,
            on_close_callback=None,
            settings_only=False,
    ):
        os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.window=false")
        ensure_pyside6_available()
        from PySide6.QtCore import QObject, QUrl, Signal, Slot, QFileSystemWatcher, QTimer, QThread
        from PySide6.QtGui import QGuiApplication, QIcon
        from PySide6.QtQml import QQmlApplicationEngine
        from gui.hub_action_runner import HubActionWorker, is_blocking_hub_action, pending_action_message

        class HubBridge(QObject):
            stateChanged = Signal(str, str)
            iconsUpdated = Signal(str)
            queueChanged = Signal()
            closeRequested = Signal()
            instancesUpdated = Signal()
            actionFinished = Signal(str)
            actionBusyChanged = Signal(bool)

            def __init__(
                self,
                store,
                correct_zoom=True,
                settings_only=False,
                on_multi_instance_enabled=None,
                on_multi_instance_disabled=None,
            ):
                super().__init__()
                self._store = store
                self._correct_zoom = correct_zoom
                self._settings_only = settings_only
                self._on_multi_instance_enabled = on_multi_instance_enabled
                self._on_multi_instance_disabled = on_multi_instance_disabled
                self._preflight_cache = {"ready": False, "checks": []}
                self._icon_download_started = False
                self._multi_instance_service = None
                self._action_thread = None
                self._action_busy = False
                state = store.initial_state()
                self._mode = state["mode"]
                self._emulator = state["emulator"]
                self._queue_reload_timer = QTimer()
                self._queue_reload_timer.setSingleShot(True)
                self._queue_reload_timer.setInterval(300)
                self._queue_reload_timer.timeout.connect(self.queueChanged.emit)
                self._queue_watcher = QFileSystemWatcher()
                self._sync_queue_watcher()
                self._queue_watcher.fileChanged.connect(self._on_queue_file_changed)
                self._instances_timer = QTimer()
                self._instances_timer.setInterval(2000)
                self._instances_timer.timeout.connect(self.instancesUpdated.emit)

            def set_multi_instance_service(self, service):
                self._multi_instance_service = service
                if service is not None:
                    self._instances_timer.start()
                else:
                    self._instances_timer.stop()

            @Slot(result=bool)
            def actionBusy(self):
                return self._action_busy

            def _set_action_busy(self, busy):
                busy = bool(busy)
                if self._action_busy == busy:
                    return
                self._action_busy = busy
                self.actionBusyChanged.emit(busy)

            def _start_background_action(self, action, payload_json="", *, start_pyla=False):
                if self._action_thread is not None and self._action_thread.isRunning():
                    return json.dumps({
                        "ok": False,
                        "message": "Another hub action is still running.",
                        "state": self._ui_state(),
                    })
                self._set_action_busy(True)
                thread = QThread()
                worker = HubActionWorker(
                    self,
                    action=action,
                    payload_json=payload_json,
                    start_pyla=start_pyla,
                )
                worker.moveToThread(thread)
                thread.started.connect(worker.run)
                worker.finished.connect(self._on_background_action_finished)
                worker.finished.connect(thread.quit)
                worker.finished.connect(worker.deleteLater)
                thread.finished.connect(thread.deleteLater)
                self._action_thread = thread
                thread.start()
                message = pending_action_message("start-pyla" if start_pyla else action)
                return json.dumps({"ok": True, "pending": True, "message": message})

            def _on_background_action_finished(self, payload_json):
                self._action_thread = None
                self._set_action_busy(False)
                self.actionFinished.emit(payload_json)
                try:
                    payload = json.loads(payload_json)
                except json.JSONDecodeError:
                    return
                if payload.get("closeHub"):
                    self.closeRequested.emit()

            @Slot(result=bool)
            def multiInstanceEnabled(self):
                from gui.instance_config import is_multi_instance_enabled

                return is_multi_instance_enabled()

            @Slot(bool, result=str)
            def setMultiInstanceEnabled(self, enabled):
                try:
                    from gui.instance_config import is_multi_instance_enabled

                    was_enabled = is_multi_instance_enabled()
                    self._store.set_multi_instance_enabled(bool(enabled))
                    if enabled and not was_enabled:
                        if self._on_multi_instance_enabled:
                            self._on_multi_instance_enabled()
                        message = (
                            "Multi-instance enabled. Start bots from this tab. "
                            "Restart the Hub if Discord/Telegram remote control does not pick up instances."
                        )
                    elif not enabled and was_enabled:
                        if self._on_multi_instance_disabled:
                            self._on_multi_instance_disabled()
                        message = "Multi-instance disabled. Use START on Overview for single-instance mode."
                    else:
                        message = "Multi-instance setting saved."
                    self.instancesUpdated.emit()
                    return json.dumps({"ok": True, "message": message, "state": self._ui_state()})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(str, result=str)
            def runPreflightFix(self, action):
                try:
                    from gui.preflight_fixes import run_preflight_fix

                    emulator, port = self._preflight_emulator_args()
                    ok, message = run_preflight_fix(action, emulator=emulator, port=port)
                    self._preflight_cache = self._run_preflight()
                    return json.dumps({
                        "ok": ok,
                        "message": message,
                        "state": self._ui_state(),
                    })
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(result=str)
            def calibratePerformance(self):
                try:
                    from performance_autotuner import calibrate_performance_profile

                    result = calibrate_performance_profile(seconds=2.0)
                    self._store.general_config.clear()
                    self._store.general_config.update(
                        __import__("gui.hub_state", fromlist=["load_toml_as_dict"]).load_toml_as_dict(
                            self._store.general_config_path
                        )
                    )
                    profile = result.get("recommended_profile", "balanced")
                    return json.dumps({
                        "ok": True,
                        "message": (
                            f"Calibration complete. Recommended profile: {profile} "
                            f"(best capture: {result.get('best_capture', '?')}). Restart bots to apply."
                        ),
                        "state": self._ui_state(),
                    })
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(bool, result=str)
            def setAutoRestartCrashed(self, enabled):
                try:
                    self._store.set_auto_restart_crashed(bool(enabled))
                    self.instancesUpdated.emit()
                    label = "enabled" if enabled else "disabled"
                    return json.dumps({
                        "ok": True,
                        "message": f"Auto-restart on crash {label}.",
                        "state": self._ui_state(),
                    })
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            def _instance_response(self, ok, message, meta=None):
                payload = {"ok": ok, "message": message, "state": self._ui_state()}
                if meta:
                    for key in ("action", "actionLabel", "instanceId"):
                        if key in meta:
                            payload[key] = meta[key]
                if ok:
                    self.instancesUpdated.emit()
                return json.dumps(payload)

            @Slot(str, result=str)
            def startInstance(self, instance_id):
                if self._multi_instance_service is None:
                    return self._instance_response(False, "Multi-instance service is not running.")
                ok, message, meta = self._multi_instance_service.start_instance(instance_id)
                return self._instance_response(ok, message, meta)

            @Slot(str, result=str)
            def stopInstance(self, instance_id):
                if self._multi_instance_service is None:
                    return self._instance_response(False, "Multi-instance service is not running.")
                ok, message, meta = self._multi_instance_service.stop_instance(instance_id)
                return self._instance_response(ok, message, meta)

            @Slot(str, result=str)
            def restartInstance(self, instance_id):
                if self._multi_instance_service is None:
                    return self._instance_response(False, "Multi-instance service is not running.")
                ok, message, meta = self._multi_instance_service.restart_instance(instance_id)
                return self._instance_response(ok, message, meta)

            @Slot(result=str)
            def alignWindows(self):
                if self._multi_instance_service is None:
                    return json.dumps({"ok": False, "message": "Multi-instance service is not running."})
                ok, message = self._multi_instance_service.align_windows()
                return json.dumps({"ok": ok, "message": message, "state": self._ui_state()})

            @Slot(result=str)
            def startAllReadyInstances(self):
                if self._multi_instance_service is None:
                    return json.dumps({"ok": False, "message": "Multi-instance service is not running."})
                results, message = self._multi_instance_service.start_all_ready()
                self.instancesUpdated.emit()
                return json.dumps({"ok": True, "message": message, "results": results, "state": self._ui_state()})

            @Slot(result=str)
            def stopAllInstances(self):
                if self._multi_instance_service is None:
                    return json.dumps({"ok": False, "message": "Multi-instance service is not running."})
                results, message = self._multi_instance_service.stop_all()
                self.instancesUpdated.emit()
                return json.dumps({"ok": True, "message": message, "results": results, "state": self._ui_state()})

            @Slot(result=str)
            def listAvailableEmulators(self):
                if self._multi_instance_service is None:
                    from gui.instance_config import list_available_emulator_instances, list_unassigned_emulator_instances

                    payload = {
                        "all": list_available_emulator_instances(),
                        "unassigned": list_unassigned_emulator_instances(),
                    }
                else:
                    payload = self._multi_instance_service.list_available_emulators()
                return json.dumps({"ok": True, "emulators": payload, "state": self._ui_state()})

            @Slot(str, result=str)
            def quickAddInstances(self, payload_json):
                try:
                    payload = json.loads(payload_json or "{}")
                    if self._multi_instance_service is None:
                        from gui.instance_config import quick_add_emulator_instances

                        created = quick_add_emulator_instances(
                            payload.get("items"),
                            copy_farm_plan_from=payload.get("copy_farm_plan_from", "default"),
                        )
                    else:
                        created = self._multi_instance_service.quick_add_instances(payload)
                    return json.dumps({
                        "ok": True,
                        "message": f"Added {len(created)} instance(s).",
                        "created": created,
                        "state": self._ui_state(),
                    })
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(str, result=str)
            def setEditingInstance(self, instance_id):
                try:
                    self._store.set_editing_instance_id(instance_id)
                    self._sync_queue_watcher()
                    self.queueChanged.emit()
                    return json.dumps({"ok": True, "state": self._ui_state()})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(str, result=str)
            def saveInstanceLocalSettings(self, payload_json):
                try:
                    payload = json.loads(payload_json or "{}")
                    instance_id = payload.get("id", "")
                    self._store.save_instance_local_settings(instance_id, payload)
                    return json.dumps({"ok": True, "message": "Instance settings saved.", "state": self._ui_state()})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(str, result=str)
            def copyInstanceFarmPlan(self, payload_json):
                try:
                    payload = json.loads(payload_json or "{}")
                    self._store.copy_instance_farm_plan(
                        payload.get("id", ""),
                        payload.get("from_id", "default"),
                    )
                    self.queueChanged.emit()
                    return json.dumps({"ok": True, "message": "Farm plan copied.", "state": self._ui_state()})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(result=str)
            def dismissMultiInstanceSetup(self):
                from gui.instance_config import set_multi_instance_setup_dismissed

                set_multi_instance_setup_dismissed(True)
                return json.dumps({"ok": True, "state": self._ui_state()})

            @Slot(str, result=str)
            def testInstanceWebhook(self, instance_id):
                try:
                    import asyncio

                    from discord_notifier import async_send_test_notification, load_instance_discord_settings

                    import os

                    previous = os.environ.get("PYLA_INSTANCE_ID")
                    os.environ["PYLA_INSTANCE_ID"] = str(instance_id).strip()
                    try:
                        settings = load_instance_discord_settings(instance_id)
                        if not settings.get("webhook_url"):
                            raise ValueError("No webhook URL configured for this instance.")
                        sent = asyncio.run(async_send_test_notification())
                    finally:
                        if previous is None:
                            os.environ.pop("PYLA_INSTANCE_ID", None)
                        else:
                            os.environ["PYLA_INSTANCE_ID"] = previous
                    if not sent:
                        from discord_notifier import last_discord_error

                        raise ValueError(last_discord_error() or "Webhook test failed.")
                    return json.dumps({"ok": True, "message": "Webhook test sent.", "state": self._ui_state()})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(str, result=str)
            def saveInstanceProfile(self, payload_json):
                try:
                    payload = json.loads(payload_json or "{}")
                    profile = self._store.save_instance_profile(payload.get("id", ""), payload)
                    return json.dumps({"ok": True, "message": f"Saved instance '{profile['id']}'.", "state": self._ui_state()})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(str, result=str)
            def deleteInstanceProfile(self, instance_id):
                try:
                    deleted = self._store.delete_instance_profile(instance_id)
                    if not deleted:
                        return json.dumps({"ok": False, "message": f"Unknown instance '{instance_id}'.", "state": self._ui_state()})
                    return json.dumps({"ok": True, "message": f"Deleted instance '{instance_id}'.", "state": self._ui_state()})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(result=str)
            def refreshInstances(self):
                from gui.instance_config import ensure_multi_instance_profiles

                ensure_multi_instance_profiles()
                return json.dumps({"ok": True, "state": self._ui_state()})

            def _ui_state(self, preflight=None):
                if preflight is None:
                    preflight = self._preflight_cache
                return self._store.ui_state(preflight=preflight, correct_zoom=self._correct_zoom)

            def _active_queue_path(self):
                return self._store._active_queue_path()

            def _sync_queue_watcher(self):
                queue_path = self._active_queue_path().resolve()
                for watched in list(self._queue_watcher.files()):
                    self._queue_watcher.removePath(watched)
                if queue_path.exists():
                    self._queue_watcher.addPath(str(queue_path))
                elif queue_path.parent.exists():
                    self._queue_watcher.addPath(str(queue_path.parent))

            def _on_queue_file_changed(self, _path):
                self._sync_queue_watcher()
                self._queue_reload_timer.start()

            @Slot(result=bool)
            def settingsOnly(self):
                return self._settings_only

            @Slot(result=str)
            def themeJson(self):
                from gui.theme import normalize_theme_mode, qml_theme_payload

                mode = normalize_theme_mode(self._store.general_config.get("ui_theme", "system"))
                animations = _to_bool_setting(self._store.general_config.get("ui_animations", "yes"))
                return json.dumps(qml_theme_payload(mode, animations))

            @Slot(bool)
            def applyWindowTheme(self, dark):
                window = getattr(self, "_window", None)
                if window is not None:
                    apply_windows_glass_effects(window, dark=bool(dark))

            @Slot()
            def closeHub(self):
                self._app.quit()

            @Slot(result=str)
            def mode(self):
                return self._mode

            @Slot(result=str)
            def emulator(self):
                return self._emulator

            def _preflight_emulator_args(self):
                self._store.apply_state({
                    "mode": self._mode,
                    "emulator": self._emulator,
                })
                general = self._store.general_config
                emulator = "mumu" if str(self._emulator).lower() == "mumu" else "ldplayer"
                port = int(general.get("emulator_port", 5555 if emulator == "ldplayer" else 16384) or (5555 if emulator == "ldplayer" else 16384))
                return emulator, port

            def _run_preflight(self):
                from gui.preflight import run_preflight_checks

                emulator, port = self._preflight_emulator_args()
                try:
                    self._preflight_cache = run_preflight_checks(
                        correct_zoom=self._correct_zoom,
                        emulator=emulator,
                        port=port,
                    )
                except Exception as exc:
                    self._preflight_cache = {
                        "ready": False,
                        "checks": [{
                            "id": "preflight",
                            "label": "Pre-flight checks",
                            "ok": False,
                            "severity": "required",
                            "detail": str(exc),
                        }],
                        "emulator_status": {},
                    }
                return self._preflight_cache

            @Slot(str, str)
            def updateSetting(self, key, value):
                if key == "mode":
                    self._mode = value
                elif key == "emulator":
                    self._emulator = value
                else:
                    return
                self._store.apply_state({
                    "mode": self._mode,
                    "emulator": self._emulator,
                })
                self.stateChanged.emit(self._mode, self._emulator)

            @Slot(result=str)
            def stateJson(self):
                return self._store.state_json(correct_zoom=self._correct_zoom)

            @Slot(str, str, str, result=str)
            def updateConfig(self, section, key, value):
                try:
                    return json.dumps({"ok": True, "state": self._store.update_config(section, key, value)})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(str, result=str)
            def runAction(self, action):
                if is_blocking_hub_action(action):
                    return self._start_background_action(action, "")
                return self._run_action_json(action, "")

            @Slot(str, str, result=str)
            def runActionWithPayload(self, action, payload_json):
                if is_blocking_hub_action(action):
                    return self._start_background_action(action, payload_json)
                return self._run_action_json(action, payload_json)

            def _run_action_json(self, action, payload_json):
                try:
                    result = self._run_action(action, payload_json)
                    if isinstance(result, dict):
                        payload = {"ok": True, "state": self._ui_state(), **result}
                        payload.setdefault("message", "")
                        return json.dumps(payload)
                    return json.dumps({"ok": True, "message": result, "state": self._ui_state()})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            def _run_action(self, action, payload_json=""):
                import asyncio
                import webbrowser

                payload = {}
                if payload_json:
                    payload = json.loads(payload_json)

                if action == "discord-webhook-guide":
                    webbrowser.open("https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks")
                    return "Opened Discord webhook guide."
                if action == "discord-developer-portal":
                    webbrowser.open("https://discord.com/developers/applications")
                    return "Opened Discord Developer Portal."
                if action == "telegram-botfather":
                    webbrowser.open("https://t.me/BotFather")
                    return "Opened @BotFather."
                if action == "brawl-stars-developer":
                    webbrowser.open("https://developer.brawlstars.com/")
                    return "Opened Brawl Stars Developer Portal."
                if action == "discord-test":
                    from discord_notifier import (
                        async_send_test_notification,
                        last_discord_error,
                        validate_discord_webhook_url,
                    )

                    valid, message = validate_discord_webhook_url(self._store.discord_config.get("webhook_url", ""))
                    if not valid:
                        raise ValueError(message)
                    ok = asyncio.run(async_send_test_notification())
                    if ok:
                        return "Discord test sent."
                    reason = last_discord_error() or "Discord rejected the request."
                    raise ValueError(f"Discord test failed. URL format is valid, but Discord rejected or blocked it: {reason}")
                if action == "telegram-test":
                    from telegram_notifier import async_send_test_notification

                    ok = asyncio.run(async_send_test_notification())
                    return "Telegram test sent." if ok else "Telegram test failed. Send /start once and check the token."
                if action == "telegram-find-chats":
                    from telegram_notifier import async_fetch_recent_chat_ids

                    token = self._store.telegram_config.get("bot_token", "")
                    chat_ids = asyncio.run(async_fetch_recent_chat_ids(token))
                    if len(chat_ids) == 1:
                        current = self._store.telegram_config.get("notification_chat_ids", [])
                        if not isinstance(current, list):
                            current = []
                        if chat_ids[0] not in current:
                            current.append(chat_ids[0])
                        self._store.telegram_config["notification_chat_ids"] = current
                        from gui.hub_state import save_dict_as_toml

                        save_dict_as_toml(self._store.telegram_config, self._store.telegram_config_path)
                        return f"Saved Telegram chat ID: {chat_ids[0]}"
                    if chat_ids:
                        return "Found multiple chat IDs: " + ", ".join(chat_ids)
                    return "No chats found. Send /start to the bot, then try again."
                if action == "api-test":
                    from utils import (
                        brawl_stars_api_config_status,
                        fetch_brawl_stars_player,
                        load_brawl_stars_api_config,
                    )

                    config = load_brawl_stars_api_config(force_refresh=True)
                    player = fetch_brawl_stars_player(
                        config.get("api_token", ""),
                        config.get("player_tag", ""),
                        timeout=int(config.get("timeout_seconds", 15) or 15),
                    )
                    name = player.get("name") or config.get("player_tag") or "player"
                    status = brawl_stars_api_config_status(
                        self._store.brawl_stars_api_config,
                        self._store.brawl_stars_api_config_path,
                    )
                    return f"API test passed for {name}. {status}"
                if action.startswith("profile-"):
                    from performance_profile import apply_performance_profile

                    profile = action.removeprefix("profile-")
                    result = apply_performance_profile(
                        profile,
                        general_config_path=self._store.general_config_path,
                        bot_config_path=self._store.bot_config_path,
                    )
                    self._store.general_config.clear()
                    self._store.general_config.update(result["general_config"])
                    self._store.bot_config.clear()
                    self._store.bot_config.update(result["bot_config"])
                    return f"Applied {result['profile']} profile. Restart the bot to use it."
                if action == "calibrate-performance":
                    from performance_autotuner import calibrate_performance_profile

                    result = calibrate_performance_profile(seconds=2.0)
                    self._store.general_config.clear()
                    from gui.hub_state import load_toml_as_dict

                    self._store.general_config.update(load_toml_as_dict(self._store.general_config_path))
                    profile = result.get("recommended_profile", "balanced")
                    return (
                        f"Calibration complete. Recommended profile: {profile} "
                        f"(best capture: {result.get('best_capture', '?')}). Restart bots to apply."
                    )
                if action == "preflight-check":
                    result = self._run_preflight()
                    lines = []
                    for check in result["checks"]:
                        prefix = "OK" if check["ok"] else "WARN"
                        lines.append(f"{prefix}: {check['label']} - {check['detail']}")
                    summary = "Ready to start." if result["ready"] else "Fix required checks before START."
                    return summary + "\n" + "\n".join(lines)
                if action == "test-emulator":
                    from gui.preflight import test_emulator_connection

                    emulator, port = self._preflight_emulator_args()
                    ok, message = test_emulator_connection(emulator=emulator, port=port)
                    if ok:
                        return f"Emulator connection OK: {message}"
                    return f"Emulator connection failed: {message}"
                if action == "export-history":
                    path = self._store.export_match_history_csv()
                    return f"Match history exported to {path}"
                if action == "reset-history":
                    self._store.reset_match_history()
                    return "Match history reset."
                if action == "refresh-history":
                    self._store.refresh_match_history()
                    return "Match history refreshed."
                if action == "read-recovery-log":
                    from recovery_events import read_recent_events

                    events = read_recent_events(limit=10)
                    if not events:
                        return "No recovery events logged yet."
                    lines = []
                    for event in events:
                        lines.append(
                            f"{event.get('ts', '')} {event.get('event_type', '')}: {event.get('detail', '')}"
                        )
                    return "Recent recovery events:\n" + "\n".join(lines)
                if action == "import-queue":
                    path = _normalize_dialog_path(payload.get("path", ""))
                    if not path:
                        return "Import cancelled."
                    from gui.brawler_queue import load_queue, save_queue

                    queue = load_queue(path)
                    if not queue:
                        raise ValueError("Selected file did not contain a brawler queue.")
                    save_queue(queue)
                    return f"Imported {len(queue)} brawler(s) from {Path(path).name}."
                if action == "export-queue":
                    path = _normalize_dialog_path(payload.get("path", ""))
                    queue = self._store.load_queue()
                    if not queue:
                        raise ValueError("Farm plan is empty.")
                    if not path:
                        return "Export cancelled."
                    if not path.lower().endswith(".json"):
                        path = f"{path}.json"
                    from gui.brawler_queue import save_queue

                    save_queue(queue, path)
                    return f"Exported {len(queue)} brawler(s) to {Path(path).name}."
                if action == "clear-queue":
                    self._store.save_queue([])
                    return "Farm plan cleared."
                if action == "build-push-all":
                    target = int(payload.get("target", 1000) or 1000)
                    queue = self._store.build_push_all(target)
                    return f"Built Push All queue with {len(queue)} brawler(s) to {target} trophies."
                if action == "sort-queue-by-trophies":
                    descending = str(payload.get("order", "desc")).strip().lower() != "asc"
                    queue = self._store.sort_queue_by_trophies(descending=descending)
                    direction = "highest to lowest" if descending else "lowest to highest"
                    return f"Sorted {len(queue)} brawler(s) by cups ({direction})."
                if action == "sort-queue":
                    from gui.brawler_queue import QUEUE_SORT_MODES

                    mode = str(payload.get("mode", "cups_desc") or "cups_desc").strip().lower()
                    queue, mode = self._store.sort_queue(mode=mode)
                    label = QUEUE_SORT_MODES.get(mode, "sorted")
                    return f"Sorted {len(queue)} brawler(s): {label}."
                if action == "add-to-queue":
                    from gui.brawler_queue import load_queue, normalize_queue_row, persist_queue

                    queue_path = self._store._active_queue_path()
                    queue = load_queue(queue_path)
                    queue.append(normalize_queue_row(payload))
                    persist_queue(queue, queue_path)
                    return f"Added {payload.get('brawler', 'brawler')} to farm plan."
                if action == "remove-from-queue":
                    from gui.brawler_queue import load_queue, persist_queue

                    queue_path = self._store._active_queue_path()
                    index = int(payload.get("index", -1))
                    queue = load_queue(queue_path)
                    if index < 0 or index >= len(queue):
                        raise ValueError("Invalid queue index.")
                    removed = queue.pop(index)
                    persist_queue(queue, queue_path)
                    return f"Removed {removed.get('brawler', 'brawler')} from farm plan."
                if action == "move-queue-item":
                    from gui.brawler_queue import load_queue, persist_queue

                    queue_path = self._store._active_queue_path()
                    index = int(payload.get("index", -1))
                    direction = int(payload.get("direction", 0))
                    queue = load_queue(queue_path)
                    target = index + direction
                    if index < 0 or index >= len(queue) or target < 0 or target >= len(queue):
                        raise ValueError("Cannot move queue item.")
                    item = queue.pop(index)
                    queue.insert(target, item)
                    persist_queue(queue, queue_path)
                    return "Queue order updated."
                if action == "reorder-queue":
                    from gui.brawler_queue import load_queue, persist_queue

                    queue_path = self._store._active_queue_path()
                    from_index = int(payload.get("fromIndex", -1))
                    to_index = int(payload.get("toIndex", -1))
                    queue = load_queue(queue_path)
                    if from_index < 0 or from_index >= len(queue):
                        raise ValueError("Invalid source queue index.")
                    if to_index < 0 or to_index >= len(queue):
                        raise ValueError("Invalid target queue index.")
                    if from_index == to_index:
                        return "Queue order unchanged."
                    item = queue.pop(from_index)
                    queue.insert(to_index, item)
                    persist_queue(queue, queue_path)
                    return "Queue order updated."
                if action == "update-queue-item":
                    from gui.brawler_queue import load_queue, normalize_queue_row, persist_queue

                    queue_path = self._store._active_queue_path()
                    index = int(payload.get("index", -1))
                    queue = load_queue(queue_path)
                    if index < 0 or index >= len(queue):
                        raise ValueError("Invalid queue index.")
                    row = dict(queue[index])
                    if "push_until" in payload:
                        row["push_until"] = int(payload.get("push_until", row.get("push_until", 1000)) or 1000)
                    if "automatically_pick" in payload:
                        row["automatically_pick"] = bool(payload.get("automatically_pick"))
                    queue[index] = normalize_queue_row(row)
                    persist_queue(queue, queue_path)
                    brawler = queue[index].get("brawler", "brawler")
                    return f"Updated {brawler} target to {queue[index]['push_until']} trophies."
                if action == "open-brawler-picker":
                    return "Use Add Brawler in the farm plan tab."
                if action == "open-config-folder":
                    import os

                    from utils import resolve_project_path

                    config_dir = Path(resolve_project_path("cfg")).resolve()
                    os.startfile(str(config_dir))
                    return f"Opened {config_dir}"
                if action == "complete-wizard":
                    self._store.update_config("settings", "first_run_wizard", "no")
                    return "First-run wizard dismissed."
                if action == "show-wizard":
                    return {
                        "message": "Setup wizard reopened.",
                        "showWizard": True,
                    }
                if action == "reset-setup-wizard":
                    self._store.update_config("settings", "first_run_wizard", "yes")
                    return {
                        "message": "Setup wizard will show again on next launch. Opening it now.",
                        "showWizard": True,
                    }
                if action == "accept-license":
                    self._store.update_config("settings", "license_accepted", "yes")
                    from tools.hub_first_run import mark_hub_license_acknowledged
                    from utils import project_root

                    mark_hub_license_acknowledged(project_root())
                    return "License accepted. Pyla-RL is free and must not be sold."
                if action == "check-updates":
                    import webbrowser

                    from gui.brand import OFFICIAL_GITHUB

                    webbrowser.open(f"{OFFICIAL_GITHUB}/releases")
                    updater_exe = Path("updater.exe")
                    if updater_exe.exists():
                        return "Opened official GitHub releases. Run updater.exe in this folder to install updates."
                    return "Opened official GitHub releases."
                if action == "report-reseller":
                    import webbrowser

                    from gui.brand import RESELLER_REPORT_URL

                    webbrowser.open(RESELLER_REPORT_URL)
                    return "Opened the official reseller report form."
                if action == "ensure-brawler-icons":
                    if self._icon_download_started:
                        return "Downloading brawler icons..."
                    self._icon_download_started = True

                    def download_icons():
                        message = "Brawler icons ready."
                        try:
                            from utils import resolve_project_path

                            icon_dir = Path(resolve_project_path("api/assets/brawler_icons"))
                            icon_dir.mkdir(parents=True, exist_ok=True)
                            from utils import get_brawler_list, update_missing_brawlers_info

                            brawlers = get_brawler_list()
                            if brawlers:
                                update_missing_brawlers_info(brawlers)
                            else:
                                message = "Could not fetch brawler list for icon download."
                        except Exception as exc:
                            message = f"Brawler icon download failed: {exc}"
                        finally:
                            self._icon_download_started = False
                            self._store.invalidate_static_ui_cache()
                            self.iconsUpdated.emit(message)

                    import threading

                    threading.Thread(target=download_icons, daemon=True).start()
                    return "Downloading brawler icons..."
                raise ValueError(f"Unknown action: {action}")

            def _start_pyla_sync(self):
                self._preflight_cache = self._run_preflight()
                if not self._preflight_cache.get("ready"):
                    return json.dumps({
                        "ok": False,
                        "message": "Pre-flight checks failed. Run checks on Overview and fix required items.",
                        "state": self._ui_state(),
                    })
                self._store.apply_state({
                    "mode": self._mode,
                    "emulator": self._emulator,
                })
                queue = self._store.load_queue()
                if queue:
                    from gui.brawler_queue import persist_queue

                    persist_queue(queue)
                return json.dumps({
                    "ok": True,
                    "message": "Starting Pyla-RL...",
                    "state": self._ui_state(),
                    "closeHub": True,
                })

            @Slot(result=str)
            def startPyla(self):
                if self._settings_only:
                    return json.dumps({
                        "ok": False,
                        "message": "START is disabled while the bot is running. Close this window when finished editing settings.",
                        "state": self._ui_state(),
                    })
                from gui.instance_config import is_multi_instance_enabled

                if is_multi_instance_enabled():
                    return json.dumps({
                        "ok": True,
                        "message": "Multi-instance mode is enabled. Start bots from the Instances tab.",
                        "state": self._ui_state(),
                        "multiInstance": True,
                    })
                from gui.hub_state import _to_bool

                if not _to_bool(self._store.general_config.get("license_accepted", "no")):
                    return json.dumps({
                        "ok": False,
                        "message": "Accept the free-use license in the hub wizard or Settings → About before START.",
                        "state": self._ui_state(),
                    })
                return self._start_background_action("start-pyla", start_pyla=True)

            @Slot(result=str)
            def tutorialTopicsJson(self):
                from gui.hub_tutorials import tutorial_topics

                return json.dumps(tutorial_topics())

            @Slot(str, result=str)
            def openTutorialDoc(self, doc_path):
                try:
                    from gui.hub_tutorials import open_tutorial_doc

                    path = open_tutorial_doc(doc_path)
                    return json.dumps({"ok": True, "message": f"Opened {Path(path).name}"})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc)})

            @Slot()
            def openOfficialRepo(self):
                import webbrowser

                from gui.brand import OFFICIAL_GITHUB

                webbrowser.open(OFFICIAL_GITHUB)

            @Slot()
            def openDiscord(self):
                import webbrowser

                from utils import get_discord_link

                webbrowser.open(get_discord_link() or "https://discord.gg/xUusk3fw4A")

            @Slot()
            def openPatreon(self):
                import webbrowser

                webbrowser.open("https://www.patreon.com/pyla/membership")

        self.version_str = version_str
        self.latest_version_str = latest_version_str
        self.correct_zoom = correct_zoom
        self.on_close_callback = on_close_callback
        self.settings_only = settings_only
        self.started = False

        app = QGuiApplication.instance()
        owns_app = app is None
        if app is None:
            app = QGuiApplication(sys.argv[:1])

        app.setApplicationName("Pyla-RL Settings" if settings_only else "Pyla-RL Hub")
        icon_path = Path(__file__).resolve().parent.parent / "images" / "icon.ico"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))

        from gui import brand

        self._store = HubStateStore()
        self._multi_instance_service = None

        def _start_multi_instance_service():
            if self._multi_instance_service is not None or settings_only:
                return
            from gui.multi_instance_service import MultiInstanceService

            self._multi_instance_service = MultiInstanceService()
            self._multi_instance_service.start()
            self._bridge.set_multi_instance_service(self._multi_instance_service)

        def _stop_multi_instance_service():
            if self._multi_instance_service is None:
                return
            for item in self._multi_instance_service.list_instances():
                if item.get("running"):
                    self._multi_instance_service.stop_instance(item["id"])
            self._multi_instance_service.close()
            self._multi_instance_service = None
            self._bridge.set_multi_instance_service(None)

        self._start_multi_instance_service = _start_multi_instance_service
        self._stop_multi_instance_service = _stop_multi_instance_service
        self._bridge = HubBridge(
            self._store,
            correct_zoom=correct_zoom,
            settings_only=settings_only,
            on_multi_instance_enabled=_start_multi_instance_service,
            on_multi_instance_disabled=_stop_multi_instance_service,
        )
        self._bridge._app = app
        if not settings_only:
            from gui.instance_config import ensure_multi_instance_profiles, is_multi_instance_enabled

            if is_multi_instance_enabled():
                try:
                    ensure_multi_instance_profiles()
                except Exception as exc:
                    print(f"Warning: could not auto-repair instance profiles: {exc}")
                _start_multi_instance_service()
        if not settings_only:
            self._bridge.closeRequested.connect(self._mark_started_and_close)

        engine = QQmlApplicationEngine()
        context = engine.rootContext()
        context.setContextProperty("hubBridge", self._bridge)
        context.setContextProperty("settingsOnly", settings_only)
        context.setContextProperty("hubVersion", self.version_str)
        context.setContextProperty("latestVersion", self.latest_version_str or "")
        context.setContextProperty("correctZoom", self.correct_zoom)
        context.setContextProperty("hubBrand", {
            "productName": brand.PRODUCT_NAME,
            "freeNotice": brand.FREE_NOTICE,
            "footerNotice": brand.FOOTER_NOTICE,
            "officialGithub": brand.OFFICIAL_GITHUB,
            "licenseName": brand.LICENSE_NAME,
        })

        qml_path = Path(__file__).resolve().parent / "qml" / "PylaHub.qml"
        engine.load(QUrl.fromLocalFile(str(qml_path)))
        if not engine.rootObjects():
            raise RuntimeError(f"Could not load QML hub: {qml_path}")

        root_window = engine.rootObjects()[0]
        self._bridge._window = root_window
        try:
            from gui.theme import resolve_theme_mode

            resolved = resolve_theme_mode(self._store.general_config.get("ui_theme", "system"))
            apply_windows_glass_effects(root_window, dark=resolved != "light")
        except Exception:
            pass

        self._app = app
        self._engine = engine
        app.exec()

        if self._multi_instance_service is not None:
            self._multi_instance_service.close()

        if self.started and callable(self.on_close_callback):
            self.on_close_callback()

        if owns_app:
            self._engine = None
            self._bridge = None

    def _mark_started_and_close(self):
        self.started = True
        self._app.quit()


def main():
    import argparse

    from utils import load_toml_as_dict

    parser = argparse.ArgumentParser(description="Launch the Pyla-RL QML hub.")
    parser.add_argument(
        "--settings-only",
        action="store_true",
        help="Open settings without starting the bot (for use during an active session).",
    )
    args = parser.parse_args()
    version = str(load_toml_as_dict("cfg/general_config.toml").get("pyla_version", "0.8.1"))
    QmlHub(version, version, settings_only=args.settings_only)


if __name__ == "__main__":
    main()
