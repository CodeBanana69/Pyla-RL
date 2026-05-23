import sys
import json
import subprocess
from pathlib import Path

from gui.hub_state import HubStateStore


def _normalize_dialog_path(raw_path):
    path = str(raw_path or "").strip()
    if not path:
        return ""
    if path.startswith("file:"):
        from PySide6.QtCore import QUrl

        return QUrl(path).toLocalFile()
    return path


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
        ensure_pyside6_available()
        from PySide6.QtCore import QObject, QUrl, Signal, Slot, QFileSystemWatcher, QTimer
        from PySide6.QtGui import QGuiApplication, QIcon
        from PySide6.QtQml import QQmlApplicationEngine

        class HubBridge(QObject):
            stateChanged = Signal(str, str)
            iconsUpdated = Signal(str)
            queueChanged = Signal()
            closeRequested = Signal()
            instancesUpdated = Signal()

            def __init__(self, store, correct_zoom=True, settings_only=False):
                super().__init__()
                self._store = store
                self._correct_zoom = correct_zoom
                self._settings_only = settings_only
                self._preflight_cache = {"ready": False, "checks": []}
                self._icon_download_started = False
                self._multi_instance_service = None
                state = store.initial_state()
                self._mode = state["mode"]
                self._emulator = state["emulator"]
                self._queue_reload_timer = QTimer()
                self._queue_reload_timer.setSingleShot(True)
                self._queue_reload_timer.setInterval(300)
                self._queue_reload_timer.timeout.connect(self.queueChanged.emit)
                self._queue_watcher = QFileSystemWatcher()
                from gui.brawler_queue import QUEUE_PATH

                queue_path = Path(QUEUE_PATH).resolve()
                if queue_path.exists():
                    self._queue_watcher.addPath(str(queue_path))
                else:
                    self._queue_watcher.addPath(str(queue_path.parent.resolve()))
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
            def multiInstanceEnabled(self):
                from gui.instance_config import is_multi_instance_enabled

                return is_multi_instance_enabled()

            @Slot(bool, result=str)
            def setMultiInstanceEnabled(self, enabled):
                try:
                    self._store.set_multi_instance_enabled(bool(enabled))
                    return json.dumps({"ok": True, "state": self._ui_state()})
                except Exception as exc:
                    return json.dumps({"ok": False, "message": str(exc), "state": self._ui_state()})

            @Slot(str, result=str)
            def startInstance(self, instance_id):
                if self._multi_instance_service is None:
                    return json.dumps({"ok": False, "message": "Multi-instance service is not running."})
                ok, message = self._multi_instance_service.start_instance(instance_id)
                return json.dumps({"ok": ok, "message": message, "state": self._ui_state()})

            @Slot(str, result=str)
            def stopInstance(self, instance_id):
                if self._multi_instance_service is None:
                    return json.dumps({"ok": False, "message": "Multi-instance service is not running."})
                ok, message = self._multi_instance_service.stop_instance(instance_id)
                return json.dumps({"ok": ok, "message": message, "state": self._ui_state()})

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
                return self.stateJson()

            def _ui_state(self, preflight=None):
                if preflight is None:
                    preflight = self._preflight_cache
                return self._store.ui_state(preflight=preflight, correct_zoom=self._correct_zoom)

            def _on_queue_file_changed(self, _path):
                from gui.brawler_queue import QUEUE_PATH

                queue_path = str(Path(QUEUE_PATH).resolve())
                if Path(queue_path).exists() and queue_path not in self._queue_watcher.files():
                    self._queue_watcher.addPath(queue_path)
                self._queue_reload_timer.start()

            @Slot(result=bool)
            def settingsOnly(self):
                return self._settings_only

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
                self._preflight_cache = run_preflight_checks(
                    correct_zoom=self._correct_zoom,
                    emulator=emulator,
                    port=port,
                )
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
                return self._run_action_json(action, "")

            @Slot(str, str, result=str)
            def runActionWithPayload(self, action, payload_json):
                return self._run_action_json(action, payload_json)

            def _run_action_json(self, action, payload_json):
                try:
                    message = self._run_action(action, payload_json)
                    return json.dumps({"ok": True, "message": message, "state": self._ui_state()})
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
                    raise ValueError(f"Emulator connection failed: {message}")
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
                if action == "add-to-queue":
                    from gui.brawler_queue import load_queue, normalize_queue_row, persist_queue

                    queue = load_queue()
                    queue.append(normalize_queue_row(payload))
                    persist_queue(queue)
                    return f"Added {payload.get('brawler', 'brawler')} to farm plan."
                if action == "remove-from-queue":
                    from gui.brawler_queue import load_queue, persist_queue

                    index = int(payload.get("index", -1))
                    queue = load_queue()
                    if index < 0 or index >= len(queue):
                        raise ValueError("Invalid queue index.")
                    removed = queue.pop(index)
                    persist_queue(queue)
                    return f"Removed {removed.get('brawler', 'brawler')} from farm plan."
                if action == "move-queue-item":
                    from gui.brawler_queue import load_queue, persist_queue

                    index = int(payload.get("index", -1))
                    direction = int(payload.get("direction", 0))
                    queue = load_queue()
                    target = index + direction
                    if index < 0 or index >= len(queue) or target < 0 or target >= len(queue):
                        raise ValueError("Cannot move queue item.")
                    item = queue.pop(index)
                    queue.insert(target, item)
                    persist_queue(queue)
                    return "Queue order updated."
                if action == "reorder-queue":
                    from gui.brawler_queue import load_queue, persist_queue

                    from_index = int(payload.get("fromIndex", -1))
                    to_index = int(payload.get("toIndex", -1))
                    queue = load_queue()
                    if from_index < 0 or from_index >= len(queue):
                        raise ValueError("Invalid source queue index.")
                    if to_index < 0 or to_index >= len(queue):
                        raise ValueError("Invalid target queue index.")
                    if from_index == to_index:
                        return "Queue order unchanged."
                    item = queue.pop(from_index)
                    queue.insert(to_index, item)
                    persist_queue(queue)
                    return "Queue order updated."
                if action == "update-queue-item":
                    from gui.brawler_queue import load_queue, normalize_queue_row, persist_queue

                    index = int(payload.get("index", -1))
                    queue = load_queue()
                    if index < 0 or index >= len(queue):
                        raise ValueError("Invalid queue index.")
                    row = dict(queue[index])
                    if "push_until" in payload:
                        row["push_until"] = int(payload.get("push_until", row.get("push_until", 1000)) or 1000)
                    if "automatically_pick" in payload:
                        row["automatically_pick"] = bool(payload.get("automatically_pick"))
                    queue[index] = normalize_queue_row(row)
                    persist_queue(queue)
                    brawler = queue[index].get("brawler", "brawler")
                    return f"Updated {brawler} target to {queue[index]['push_until']} trophies."
                if action == "open-brawler-picker":
                    return "Use Add Brawler in the farm plan tab."
                if action == "open-config-folder":
                    import os

                    config_dir = Path("cfg").resolve()
                    os.startfile(str(config_dir))
                    return f"Opened {config_dir}"
                if action == "complete-wizard":
                    self._store.update_config("settings", "first_run_wizard", "no")
                    return "First-run wizard dismissed."
                if action == "accept-license":
                    self._store.update_config("settings", "license_accepted", "yes")
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
                            icon_dir = Path("api") / "assets" / "brawler_icons"
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
                            self.iconsUpdated.emit(message)

                    import threading

                    threading.Thread(target=download_icons, daemon=True).start()
                    return "Downloading brawler icons..."
                raise ValueError(f"Unknown action: {action}")

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
                self.closeRequested.emit()
                return json.dumps({"ok": True, "message": "Starting Pyla-RL...", "state": self._ui_state()})

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
        self._bridge = HubBridge(self._store, correct_zoom=correct_zoom, settings_only=settings_only)
        self._bridge._app = app
        self._multi_instance_service = None
        if not settings_only:
            from gui.instance_config import is_multi_instance_enabled

            if is_multi_instance_enabled():
                from gui.multi_instance_service import MultiInstanceService

                self._multi_instance_service = MultiInstanceService()
                self._multi_instance_service.start()
                self._bridge.set_multi_instance_service(self._multi_instance_service)
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
