import sys
import json
import subprocess
from pathlib import Path

from gui.hub_state import HubStateStore


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
    ):
        ensure_pyside6_available()
        from PySide6.QtCore import QObject, QUrl, Signal, Slot
        from PySide6.QtGui import QGuiApplication, QIcon
        from PySide6.QtQml import QQmlApplicationEngine

        class HubBridge(QObject):
            stateChanged = Signal(str, str)
            closeRequested = Signal()

            def __init__(self, store, correct_zoom=True):
                super().__init__()
                self._store = store
                self._correct_zoom = correct_zoom
                self._preflight_cache = {"ready": False, "checks": []}
                state = store.initial_state()
                self._mode = state["mode"]
                self._emulator = state["emulator"]

            def _ui_state(self, preflight=None):
                if preflight is None:
                    preflight = self._preflight_cache
                return self._store.ui_state(preflight=preflight, correct_zoom=self._correct_zoom)

            @Slot(result=str)
            def mode(self):
                return self._mode

            @Slot(result=str)
            def emulator(self):
                return self._emulator

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
                    from gui.preflight import run_preflight_checks

                    self._preflight_cache = run_preflight_checks(correct_zoom=self._correct_zoom)
                    result = self._preflight_cache
                    lines = []
                    for check in result["checks"]:
                        prefix = "OK" if check["ok"] else "WARN"
                        lines.append(f"{prefix}: {check['label']} - {check['detail']}")
                    summary = "Ready to start." if result["ready"] else "Fix required checks before START."
                    return summary + "\n" + "\n".join(lines)
                if action == "test-emulator":
                    from gui.preflight import test_emulator_connection

                    ok, message = test_emulator_connection()
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
                    from PySide6.QtWidgets import QFileDialog

                    path, _ = QFileDialog.getOpenFileName(None, "Import Farm Plan", "", "JSON (*.json)")
                    if not path:
                        return "Import cancelled."
                    from gui.brawler_queue import load_queue, save_queue

                    queue = load_queue(path)
                    if not queue:
                        raise ValueError("Selected file did not contain a brawler queue.")
                    save_queue(queue)
                    return f"Imported {len(queue)} brawler(s)."
                if action == "export-queue":
                    from PySide6.QtWidgets import QFileDialog

                    queue = self._store.load_queue()
                    if not queue:
                        raise ValueError("Farm plan is empty.")
                    path, _ = QFileDialog.getSaveFileName(None, "Export Farm Plan", "farm_plan.json", "JSON (*.json)")
                    if not path:
                        return "Export cancelled."
                    from gui.brawler_queue import save_queue

                    save_queue(queue, path)
                    return f"Exported {len(queue)} brawler(s) to {path}"
                if action == "clear-queue":
                    self._store.save_queue([])
                    return "Farm plan cleared."
                if action == "build-push-all":
                    target = int(payload.get("target", 1000) or 1000)
                    queue = self._store.build_push_all(target)
                    return f"Built Push All queue with {len(queue)} brawler(s) to {target} trophies."
                if action == "add-to-queue":
                    from gui.brawler_queue import load_queue, persist_queue

                    queue = load_queue()
                    queue.append(payload)
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
                raise ValueError(f"Unknown action: {action}")

            @Slot(result=str)
            def startPyla(self):
                from gui.preflight import run_preflight_checks

                self._preflight_cache = run_preflight_checks(correct_zoom=self._correct_zoom)
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
                return json.dumps({"ok": True, "message": "Starting PylaAi-XXZ...", "state": self._ui_state()})

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
        self.started = False

        app = QGuiApplication.instance()
        owns_app = app is None
        if app is None:
            app = QGuiApplication(sys.argv[:1])

        app.setApplicationName("PylaAi-XXZ Hub")
        icon_path = Path(__file__).resolve().parent.parent / "images" / "icon.ico"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))

        self._store = HubStateStore()
        self._bridge = HubBridge(self._store, correct_zoom=correct_zoom)
        self._bridge.closeRequested.connect(self._mark_started_and_close)

        engine = QQmlApplicationEngine()
        context = engine.rootContext()
        context.setContextProperty("hubBridge", self._bridge)
        context.setContextProperty("hubVersion", self.version_str)
        context.setContextProperty("latestVersion", self.latest_version_str or "")
        context.setContextProperty("correctZoom", self.correct_zoom)

        qml_path = Path(__file__).resolve().parent / "qml" / "PylaHub.qml"
        engine.load(QUrl.fromLocalFile(str(qml_path)))
        if not engine.rootObjects():
            raise RuntimeError(f"Could not load QML hub: {qml_path}")

        self._app = app
        self._engine = engine
        app.exec()

        if self.started and callable(self.on_close_callback):
            self.on_close_callback()

        if owns_app:
            self._engine = None
            self._bridge = None

    def _mark_started_and_close(self):
        self.started = True
        self._app.quit()
