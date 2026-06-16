import json
import os
import subprocess
import sys
import time
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
            initial_tab="",
    ):
        os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.window=false")
        ensure_pyside6_available()
        from PySide6.QtCore import QObject, QUrl, Signal, Slot, QFileSystemWatcher, QTimer, QThread, Qt
        from PySide6.QtGui import QGuiApplication, QIcon
        from PySide6.QtQml import QQmlApplicationEngine
        from gui.hub_action_runner import HubActionWorker, is_blocking_hub_action, pending_action_message

        class HubBridge(QObject):
            stateChanged = Signal(str, str)
            iconsUpdated = Signal(str)
            updateStatusRefreshed = Signal()
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
                self._preflight_cache_checked_at = 0.0
                self._icon_download_started = False
                self._multi_instance_service = None
                self._action_thread = None
                self._action_worker = None
                self._action_busy = False
                self._action_generation = 0
                self._action_timeout_timer = QTimer()
                self._action_timeout_timer.setSingleShot(True)
                self._action_timeout_timer.timeout.connect(self._on_action_timeout)
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
                self._schedule_update_status_refresh()

            def _schedule_update_status_refresh(self):
                import threading

                def work():
                    try:
                        from gui.hub_update_status import check_update_status
                        from utils import project_root

                        status = check_update_status(project_root())
                    except Exception:
                        return

                    def apply():
                        self._store.set_update_status(status)
                        self.updateStatusRefreshed.emit()

                    QTimer.singleShot(0, apply)

                threading.Thread(target=work, daemon=True).start()

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

            def _clear_action_state(self):
                self._action_timeout_timer.stop()
                self._action_thread = None
                self._action_worker = None
                self._set_action_busy(False)

            def _on_action_timeout(self):
                if not self._action_busy:
                    return
                thread = self._action_thread
                self._action_generation += 1
                self._action_timeout_timer.stop()
                self._action_thread = None
                self._action_worker = None
                self._set_action_busy(False)
                if thread is not None and thread.isRunning():
                    thread.requestInterruption()
                    thread.terminate()
                    thread.wait(3000)
                self.actionFinished.emit(json.dumps({
                    "ok": False,
                    "message": __import__("gui.i18n", fromlist=["t"]).t("msg.action_timeout"),
                    "state": self._ui_state(),
                }))

            def _on_action_thread_finished(self, thread, generation):
                if generation != self._action_generation:
                    return
                if self._action_thread is thread:
                    self._action_thread = None
                if self._action_busy:
                    self._action_timeout_timer.stop()
                    self._set_action_busy(False)

            def _start_background_action(self, action, payload_json="", *, start_pyla=False):
                if self._action_thread is not None:
                    if self._action_thread.isRunning():
                        return json.dumps({
                            "ok": False,
                            "message": __import__("gui.i18n", fromlist=["t"]).t("msg.another_action_running"),
                            "state": self._ui_state(),
                        })
                    self._clear_action_state()

                self._action_generation += 1
                generation = self._action_generation
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
                worker.finished.connect(
                    self._on_background_action_finished,
                    Qt.ConnectionType.QueuedConnection,
                )
                worker.finished.connect(thread.quit)
                worker.finished.connect(worker.deleteLater)
                thread.finished.connect(thread.deleteLater)
                thread.finished.connect(
                    lambda: self._on_action_thread_finished(thread, generation),
                    Qt.ConnectionType.QueuedConnection,
                )
                self._action_thread = thread
                self._action_worker = worker
                thread.start()
                self._action_timeout_timer.start(120_000)
                message = pending_action_message("start-pyla" if start_pyla else action)
                return json.dumps({"ok": True, "pending": True, "message": message})

            def _on_background_action_finished(self, payload_json):
                worker = self.sender()
                if self._action_worker is None:
                    return
                if worker is not None and worker is not self._action_worker:
                    return
                self._action_timeout_timer.stop()
                self._action_thread = None
                self._action_worker = None
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
                        message = __import__("gui.i18n", fromlist=["t"]).t("msg.multi_instance_enabled")
                    elif not enabled and was_enabled:
                        if self._on_multi_instance_disabled:
                            self._on_multi_instance_disabled()
                        message = __import__("gui.i18n", fromlist=["t"]).t("msg.multi_instance_disabled")
                    else:
                        message = __import__("gui.i18n", fromlist=["t"]).t("msg.multi_instance_saved")
                    self.instancesUpdated.emit()
                    return json.dumps({"ok": True, "message": message, "state": self._ui_state()})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(str, result=str)
            def runPreflightFix(self, action):
                payload = json.dumps({"action": action})
                return self._start_background_action("preflight-fix", payload)

            @Slot(result=str)
            def calibratePerformance(self):
                try:
                    from gui.i18n import t
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
                        "message": t(
                            "msg.calibration_complete",
                            profile=profile,
                            capture=result.get("best_capture", "?"),
                        ),
                        "state": self._ui_state(),
                    })
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(bool, result=str)
            def setAutoRestartCrashed(self, enabled):
                try:
                    from gui.i18n import t

                    self._store.set_auto_restart_crashed(bool(enabled))
                    self.instancesUpdated.emit()
                    message = t("msg.auto_restart_enabled") if enabled else t("msg.auto_restart_disabled")
                    return json.dumps({
                        "ok": True,
                        "message": message,
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
                    return self._instance_response(False, __import__("gui.i18n", fromlist=["t"]).t("msg.multi_instance_service_down"))
                ok, message, meta = self._multi_instance_service.start_instance(instance_id)
                return self._instance_response(ok, message, meta)

            @Slot(str, result=str)
            def stopInstance(self, instance_id):
                if self._multi_instance_service is None:
                    return self._instance_response(False, __import__("gui.i18n", fromlist=["t"]).t("msg.multi_instance_service_down"))
                ok, message, meta = self._multi_instance_service.stop_instance(instance_id)
                return self._instance_response(ok, message, meta)

            @Slot(str, result=str)
            def restartInstance(self, instance_id):
                if self._multi_instance_service is None:
                    return self._instance_response(False, __import__("gui.i18n", fromlist=["t"]).t("msg.multi_instance_service_down"))
                ok, message, meta = self._multi_instance_service.restart_instance(instance_id)
                return self._instance_response(ok, message, meta)

            @Slot(result=str)
            def alignWindows(self):
                if self._multi_instance_service is None:
                    return json.dumps({"ok": False, "message": __import__("gui.i18n", fromlist=["t"]).t("msg.multi_instance_service_down")})
                ok, message = self._multi_instance_service.align_windows()
                return json.dumps({"ok": ok, "message": message, "state": self._ui_state()})

            @Slot(result=str)
            def startAllReadyInstances(self):
                if self._multi_instance_service is None:
                    return json.dumps({"ok": False, "message": __import__("gui.i18n", fromlist=["t"]).t("msg.multi_instance_service_down")})
                results, message = self._multi_instance_service.start_all_ready()
                self.instancesUpdated.emit()
                return json.dumps({"ok": True, "message": message, "results": results, "state": self._ui_state()})

            @Slot(result=str)
            def stopAllInstances(self):
                if self._multi_instance_service is None:
                    return json.dumps({"ok": False, "message": __import__("gui.i18n", fromlist=["t"]).t("msg.multi_instance_service_down")})
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
                    from gui.i18n import t

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
                        "message": t("msg.instances_added", count=len(created)),
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
                    from gui.i18n import t

                    payload = json.loads(payload_json or "{}")
                    instance_id = payload.get("id", "")
                    self._store.save_instance_local_settings(instance_id, payload)
                    return json.dumps({"ok": True, "message": t("msg.instance_settings_saved"), "state": self._ui_state()})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(str, result=str)
            def copyInstanceFarmPlan(self, payload_json):
                try:
                    from gui.i18n import t

                    payload = json.loads(payload_json or "{}")
                    self._store.copy_instance_farm_plan(
                        payload.get("id", ""),
                        payload.get("from_id", "default"),
                    )
                    self.queueChanged.emit()
                    return json.dumps({"ok": True, "message": t("msg.farm_plan_copied"), "state": self._ui_state()})
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
                    from gui.i18n import t
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
                    return json.dumps({"ok": True, "message": t("msg.webhook_test_sent"), "state": self._ui_state()})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(str, result=str)
            def saveInstanceProfile(self, payload_json):
                try:
                    from gui.i18n import t

                    payload = json.loads(payload_json or "{}")
                    profile = self._store.save_instance_profile(payload.get("id", ""), payload)
                    return json.dumps({"ok": True, "message": t("msg.instance_saved", id=profile["id"]), "state": self._ui_state()})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(str, result=str)
            def deleteInstanceProfile(self, instance_id):
                try:
                    from gui.i18n import t

                    deleted = self._store.delete_instance_profile(instance_id)
                    if not deleted:
                        return json.dumps({"ok": False, "message": t("msg.unknown_instance", id=instance_id), "state": self._ui_state()})
                    return json.dumps({"ok": True, "message": t("msg.instance_deleted", id=instance_id), "state": self._ui_state()})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(result=str)
            def refreshInstances(self):
                from gui.instance_config import ensure_multi_instance_profiles

                ensure_multi_instance_profiles()
                return json.dumps({"ok": True, "state": self._ui_state()})

            def _ui_state(self, preflight=None):
                from gui.i18n import translate_preflight_checks

                if preflight is None:
                    preflight = self._preflight_cache
                if isinstance(preflight, dict) and preflight.get("checks"):
                    preflight = {
                        **preflight,
                        "checks": translate_preflight_checks(preflight["checks"]),
                    }
                return self._store.ui_state(preflight=preflight, correct_zoom=self._correct_zoom)

            def _invalidate_preflight_cache(self):
                self._preflight_cache = {"ready": False, "checks": []}
                self._preflight_cache_checked_at = 0.0

            def _has_fresh_ready_preflight(self, max_age_seconds=300):
                if not self._preflight_cache.get("ready"):
                    return False
                if not self._preflight_cache.get("checks"):
                    return False
                checked_at = float(self._preflight_cache_checked_at or 0.0)
                return checked_at > 0 and (time.monotonic() - checked_at) <= max_age_seconds

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
                self._preflight_cache_checked_at = time.monotonic()
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
                self._invalidate_preflight_cache()
                self.stateChanged.emit(self._mode, self._emulator)

            @Slot(result=str)
            def stateJson(self):
                return json.dumps(self._ui_state())

            @Slot(str, str, str, result=str)
            def updateConfig(self, section, key, value):
                try:
                    self._store.update_config(section, key, value)
                    return json.dumps({"ok": True, "state": self._ui_state()})
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

                from gui.i18n import t, tutorial_doc_path

                payload = {}
                if payload_json:
                    payload = json.loads(payload_json)

                if action == "discord-webhook-guide":
                    webbrowser.open("https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks")
                    return t("msg.discord_webhook_guide")
                if action == "discord-developer-portal":
                    webbrowser.open("https://discord.com/developers/applications")
                    return t("msg.discord_portal_opened")
                if action == "telegram-botfather":
                    webbrowser.open("https://t.me/BotFather")
                    return t("msg.telegram_botfather_opened")
                if action == "brawl-stars-developer":
                    webbrowser.open("https://developer.brawlstars.com/")
                    return t("msg.brawl_api_portal_opened")
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
                        return t("msg.discord_test_sent")
                    reason = last_discord_error() or "Discord rejected the request."
                    raise ValueError(t("msg.discord_test_failed", reason=reason))
                if action == "telegram-test":
                    from telegram_notifier import async_send_test_notification

                    ok = asyncio.run(async_send_test_notification())
                    return t("msg.telegram_test_sent") if ok else t("msg.telegram_test_failed")
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
                        return t("msg.telegram_chat_saved", id=chat_ids[0])
                    if chat_ids:
                        return t("msg.telegram_chats_found", ids=", ".join(chat_ids))
                    return t("msg.telegram_no_chats")
                if action == "api-test":
                    from utils import (
                        brawl_stars_api_config_status,
                        fetch_brawl_stars_player,
                        get_config_player_tag,
                        refresh_brawl_stars_api_token_if_enabled,
                    )
                    from gui.hub_state import save_dict_as_toml

                    save_dict_as_toml(
                        self._store.brawl_stars_api_config,
                        self._store.brawl_stars_api_config_path,
                    )
                    config = dict(self._store.brawl_stars_api_config)
                    config["player_tag"] = get_config_player_tag(config)
                    config = refresh_brawl_stars_api_token_if_enabled(
                        config,
                        "cfg/brawl_stars_api.toml",
                        force=True,
                    )
                    self._store.brawl_stars_api_config.update(config)
                    save_dict_as_toml(
                        self._store.brawl_stars_api_config,
                        self._store.brawl_stars_api_config_path,
                    )
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
                    return t("msg.api_test_passed", name=name, status=status)
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
                    return t("msg.profile_applied", profile=result["profile"])
                if action == "calibrate-performance":
                    from performance_autotuner import calibrate_performance_profile

                    result = calibrate_performance_profile(seconds=2.0)
                    self._store.general_config.clear()
                    from gui.hub_state import load_toml_as_dict

                    self._store.general_config.update(load_toml_as_dict(self._store.general_config_path))
                    profile = result.get("recommended_profile", "balanced")
                    return t(
                        "msg.calibration_complete",
                        profile=profile,
                        capture=result.get("best_capture", "?"),
                    )
                if action == "preflight-check":
                    result = self._run_preflight()
                    lines = []
                    for check in result["checks"]:
                        prefix = "OK" if check["ok"] else "WARN"
                        lines.append(f"{prefix}: {check['label']} - {check['detail']}")
                    summary = t("msg.preflight_ready") if result["ready"] else t("msg.preflight_fix_required")
                    return summary + "\n" + "\n".join(lines)
                if action == "preflight-fix":
                    from gui.preflight_fixes import run_preflight_fix

                    fix_action = str(payload.get("action", "") or "").strip()
                    if not fix_action:
                        raise ValueError(t("msg.missing_fix_action"))
                    emulator, port = self._preflight_emulator_args()
                    ok, message = run_preflight_fix(fix_action, emulator=emulator, port=port)
                    self._run_preflight()
                    return {
                        "ok": ok,
                        "message": message,
                    }
                if action == "test-emulator":
                    from gui.preflight import test_emulator_connection

                    emulator, port = self._preflight_emulator_args()
                    ok, message = test_emulator_connection(emulator=emulator, port=port)
                    if ok:
                        return t("msg.emulator_ok", detail=message)
                    return t("msg.emulator_failed", detail=message)
                if action == "export-history":
                    path = self._store.export_match_history_csv()
                    return t("msg.history_exported", path=path)
                if action == "reset-history":
                    self._store.reset_match_history()
                    return t("msg.history_reset")
                if action == "refresh-history":
                    self._store.refresh_match_history()
                    return t("msg.history_refreshed")
                if action == "read-recovery-log":
                    from recovery_events import read_recent_events

                    events = read_recent_events(limit=10)
                    if not events:
                        return t("msg.no_recovery_events")
                    lines = []
                    for event in events:
                        lines.append(
                            f"{event.get('ts', '')} {event.get('event_type', '')}: {event.get('detail', '')}"
                        )
                    return t("msg.recovery_events_header") + "\n" + "\n".join(lines)
                if action == "import-queue":
                    path = _normalize_dialog_path(payload.get("path", ""))
                    if not path:
                        return t("msg.import_cancelled")
                    from gui.brawler_queue import load_queue, save_queue

                    queue = load_queue(path)
                    if not queue:
                        raise ValueError(t("msg.import_invalid"))
                    save_queue(queue)
                    return t("msg.imported_queue", count=len(queue), name=Path(path).name)
                if action == "export-queue":
                    path = _normalize_dialog_path(payload.get("path", ""))
                    queue = self._store.load_queue()
                    if not queue:
                        raise ValueError(t("common.farm_plan_empty"))
                    if not path:
                        return t("msg.export_cancelled")
                    if not path.lower().endswith(".json"):
                        path = f"{path}.json"
                    from gui.brawler_queue import save_queue

                    save_queue(queue, path)
                    return t("msg.exported_queue", count=len(queue), name=Path(path).name)
                if action == "clear-queue":
                    self._store.save_queue([])
                    return t("msg.farm_plan_cleared")
                if action == "build-push-all":
                    target = int(payload.get("target", 1000) or 1000)
                    queue = self._store.build_push_all(target)
                    return t("msg.push_all_built", count=len(queue), target=target)
                if action == "sort-queue-by-trophies":
                    descending = str(payload.get("order", "desc")).strip().lower() != "asc"
                    queue = self._store.sort_queue_by_trophies(descending=descending)
                    direction = t("msg.cups_high_to_low") if descending else t("msg.cups_low_to_high")
                    return t("msg.sorted_by_cups", count=len(queue), direction=direction)
                if action == "sort-queue":
                    from gui.brawler_queue import QUEUE_SORT_MODES

                    mode = str(payload.get("mode", "cups_desc") or "cups_desc").strip().lower()
                    queue, mode = self._store.sort_queue(mode=mode)
                    label = t(f"sort.{mode}") if mode in QUEUE_SORT_MODES else t("common.sort")
                    return t("msg.sorted_queue", count=len(queue), label=label)
                if action == "add-to-queue":
                    from gui.brawler_queue import load_queue, normalize_queue_row, persist_queue

                    queue_path = self._store._active_queue_path()
                    queue = load_queue(queue_path)
                    queue.append(normalize_queue_row(payload))
                    persist_queue(queue, queue_path)
                    return t("msg.added_to_queue", brawler=payload.get("brawler", t("common.brawler")))
                if action == "remove-from-queue":
                    from gui.brawler_queue import load_queue, persist_queue

                    queue_path = self._store._active_queue_path()
                    index = int(payload.get("index", -1))
                    queue = load_queue(queue_path)
                    if index < 0 or index >= len(queue):
                        raise ValueError(t("msg.invalid_queue_index"))
                    removed = queue.pop(index)
                    persist_queue(queue, queue_path)
                    return t("msg.removed_from_queue", brawler=removed.get("brawler", t("common.brawler")))
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
                    return t("msg.queue_order_updated")
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
                        return t("msg.queue_order_unchanged")
                    item = queue.pop(from_index)
                    queue.insert(to_index, item)
                    persist_queue(queue, queue_path)
                    return t("msg.queue_order_updated")
                if action == "update-queue-item":
                    from gui.brawler_queue import load_queue, normalize_queue_row, persist_queue

                    queue_path = self._store._active_queue_path()
                    index = int(payload.get("index", -1))
                    queue = load_queue(queue_path)
                    if index < 0 or index >= len(queue):
                        raise ValueError(t("msg.invalid_queue_index"))
                    row = dict(queue[index])
                    if "push_until" in payload:
                        row["push_until"] = int(payload.get("push_until", row.get("push_until", 1000)) or 1000)
                    if "automatically_pick" in payload:
                        row["automatically_pick"] = bool(payload.get("automatically_pick"))
                    queue[index] = normalize_queue_row(row)
                    persist_queue(queue, queue_path)
                    brawler = queue[index].get("brawler", t("common.brawler"))
                    return t("msg.updated_target", brawler=brawler, target=queue[index]["push_until"])
                if action == "open-brawler-picker":
                    return t("msg.use_add_brawler")
                if action == "open-config-folder":
                    import os

                    from utils import resolve_project_path

                    config_dir = Path(resolve_project_path("cfg")).resolve()
                    os.startfile(str(config_dir))
                    return t("msg.opened_folder", path=config_dir)
                if action == "complete-wizard":
                    self._store.update_config("settings", "first_run_wizard", "no")
                    return t("msg.wizard_dismissed")
                if action == "show-wizard":
                    return {
                        "message": t("msg.wizard_reopened"),
                        "showWizard": True,
                    }
                if action == "reset-setup-wizard":
                    self._store.update_config("settings", "first_run_wizard", "yes")
                    return {
                        "message": t("msg.wizard_reset"),
                        "showWizard": True,
                    }
                if action == "accept-license":
                    self._store.update_config("settings", "license_accepted", "yes")
                    from tools.hub_first_run import mark_hub_license_acknowledged
                    from utils import project_root

                    mark_hub_license_acknowledged(project_root())
                    return t("msg.license_accepted")
                if action == "check-updates":
                    import webbrowser

                    from gui.brand import OFFICIAL_GITHUB

                    webbrowser.open(f"{OFFICIAL_GITHUB}/releases")
                    updater_exe = Path("updater.exe")
                    if updater_exe.exists():
                        return t("msg.updates_with_updater")
                    return t("msg.updates_opened")
                if action == "refresh-update-status":
                    from gui.hub_update_status import check_update_status
                    from utils import project_root

                    self._store.set_update_status(check_update_status(project_root()))
                    return t("msg.update_status_refreshed")
                if action == "launch-updater":
                    from utils import project_root

                    updater_exe = Path(project_root()) / "updater.exe"
                    if updater_exe.is_file():
                        subprocess.Popen(
                            [str(updater_exe)],
                            cwd=str(project_root()),
                            close_fds=True,
                        )
                        return t("msg.updater_launched")
                    return t("update.no_updater")
                if action == "report-reseller":
                    import webbrowser

                    from gui.brand import RESELLER_REPORT_URL

                    webbrowser.open(RESELLER_REPORT_URL)
                    return t("msg.reseller_report_opened")
                if action == "ensure-brawler-icons":
                    if self._icon_download_started:
                        return t("msg.icons_downloading")
                    self._icon_download_started = True

                    def download_icons():
                        message = t("msg.icons_ready")
                        try:
                            from utils import resolve_project_path

                            icon_dir = Path(resolve_project_path("api/assets/brawler_icons"))
                            icon_dir.mkdir(parents=True, exist_ok=True)
                            from utils import get_brawler_list, update_missing_brawlers_info

                            brawlers = get_brawler_list()
                            if brawlers:
                                update_missing_brawlers_info(brawlers)
                            else:
                                message = t("msg.icons_list_failed")
                        except Exception as exc:
                            message = t("msg.icons_download_failed", error=exc)
                        finally:
                            self._icon_download_started = False
                            self._store.invalidate_static_ui_cache()
                            self.iconsUpdated.emit(message)

                    import threading

                    threading.Thread(target=download_icons, daemon=True).start()
                    return t("msg.icons_downloading")
                raise ValueError(t("msg.unknown_action", action=action))

            def _start_pyla_sync(self):
                from gui.i18n import t

                if not self._has_fresh_ready_preflight():
                    self._preflight_cache = self._run_preflight()
                if not self._preflight_cache.get("ready"):
                    return json.dumps({
                        "ok": False,
                        "message": t("msg.preflight_failed"),
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
                    "message": t("msg.starting_pyla"),
                    "state": self._ui_state(),
                    "closeHub": True,
                })

            @Slot(result=str)
            def startPyla(self):
                from gui.i18n import t

                if self._settings_only:
                    return json.dumps({
                        "ok": False,
                        "message": t("msg.start_disabled_running"),
                        "state": self._ui_state(),
                    })
                from gui.instance_config import is_multi_instance_enabled

                if is_multi_instance_enabled():
                    return json.dumps({
                        "ok": True,
                        "message": t("msg.start_multi_instance"),
                        "state": self._ui_state(),
                        "multiInstance": True,
                    })
                from gui.hub_state import _to_bool

                if not _to_bool(self._store.general_config.get("license_accepted", "no")):
                    return json.dumps({
                        "ok": False,
                        "message": t("msg.license_required"),
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
                    from gui.i18n import t, tutorial_doc_path

                    path = open_tutorial_doc(tutorial_doc_path(doc_path))
                    return json.dumps({"ok": True, "message": t("msg.opened_doc", name=Path(path).name)})
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
        self.initial_tab = str(initial_tab or "").strip()
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
        context.setContextProperty("initialTab", self.initial_tab)
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
    parser.add_argument(
        "--initial-tab",
        default="",
        help="Open directly on a Hub tab (e.g. 'Farm Plan'). Used by screenshot capture.",
    )
    args = parser.parse_args()
    version = str(load_toml_as_dict("cfg/general_config.toml").get("pyla_version", "0.8.1"))
    QmlHub(version, version, settings_only=args.settings_only, initial_tab=args.initial_tab)


if __name__ == "__main__":
    main()
