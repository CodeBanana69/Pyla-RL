import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import toml

from gui.hub_state import HubStateStore
from utils import clear_toml_cache


class QmlHubStateTests(unittest.TestCase):
    def make_store(
            self,
            bot_config=None,
            general_config=None,
            time_tresholds=None,
            match_history=None,
            discord_config=None,
            telegram_base=None,
            telegram_local=None,
            api_base=None,
            api_local=None,
    ):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        bot_path = root / "bot_config.toml"
        general_path = root / "general_config.toml"
        timer_path = root / "time_tresholds.toml"
        history_path = root / "match_history.toml"
        discord_path = root / "discord_config.toml"
        telegram_base_path = root / "telegram_config.toml"
        telegram_local_path = root / "telegram_config.local.toml"
        api_base_path = root / "brawl_stars_api.toml"
        api_local_path = root / "brawl_stars_api.local.toml"
        bot_path.write_text(toml.dumps(bot_config or {}), encoding="utf-8")
        general_path.write_text(toml.dumps(general_config or {}), encoding="utf-8")
        timer_path.write_text(toml.dumps(time_tresholds or {}), encoding="utf-8")
        history_path.write_text(toml.dumps(match_history or {}), encoding="utf-8")
        discord_path.write_text(toml.dumps(discord_config or {}), encoding="utf-8")
        telegram_base_path.write_text(toml.dumps(telegram_base or {}), encoding="utf-8")
        telegram_local_path.write_text(toml.dumps(telegram_local or {}), encoding="utf-8")
        api_base_path.write_text(toml.dumps(api_base or {}), encoding="utf-8")
        api_local_path.write_text(toml.dumps(api_local or {}), encoding="utf-8")
        return (
            HubStateStore(
                str(bot_path),
                str(general_path),
                str(timer_path),
                str(history_path),
                str(discord_path),
                str(telegram_base_path),
                str(telegram_local_path),
                str(api_base_path),
                str(api_local_path),
            ),
            {
                "bot": bot_path,
                "general": general_path,
                "timers": timer_path,
                "history": history_path,
                "discord": discord_path,
                "telegram": telegram_local_path,
                "api": api_local_path,
            },
        )

    def test_hub_state_creates_missing_default_configs(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        bundle = Path(temp.name) / "app"
        (bundle / "cfg").mkdir(parents=True)

        with patch("utils.project_root", return_value=str(bundle)):
            clear_toml_cache()
            store = HubStateStore()
            bot_path = bundle / "cfg" / "bot_config.toml"
            general_path = bundle / "cfg" / "general_config.toml"

        self.assertTrue(bot_path.exists())
        self.assertTrue(general_path.exists())
        bot = toml.load(bot_path)
        self.assertEqual(bot["gamemode"], store.bot_config["gamemode"])

    def test_qml_initial_state_uses_desktop_values(self):
        store, _ = self.make_store(
            {"gamemode_type": 3, "gamemode": "showdown"},
            {"current_emulator": "MuMu"},
        )

        self.assertEqual(
            store.initial_state(),
            {
                "mode": "showdown-trio",
                "emulator": "mumu",
            },
        )

    def test_qml_overview_selection_persists_to_toml(self):
        store, paths = self.make_store()

        store.apply_state({
            "mode": "showdown-trio",
            "emulator": "ldplayer",
        })

        self.assertEqual(toml.load(paths["bot"])["gamemode_type"], 3)
        self.assertEqual(toml.load(paths["bot"])["gamemode"], "showdown")
        self.assertEqual(toml.load(paths["general"])["current_emulator"], "LDPlayer")
        self.assertEqual(toml.load(paths["general"])["emulator_port"], 5555)

    def test_qml_brawl_ball_mode_sets_playstyle(self):
        store, paths = self.make_store()

        store.apply_state({"mode": "brawl-ball"})

        bot = toml.load(paths["bot"])
        self.assertEqual(bot["gamemode_type"], 4)
        self.assertEqual(bot["gamemode"], "brawlball")
        self.assertEqual(bot["current_playstyle"], "default.pyla")
        self.assertEqual(store.initial_state()["mode"], "brawl-ball")

    def test_qml_state_exposes_old_menu_configs(self):
        store, _ = self.make_store(
            bot_config={"wall_detection_confidence": 0.7},
            general_config={"cpu_or_gpu": "directml"},
            discord_config={"username": "Pyla"},
            telegram_base={"enabled": False},
            telegram_local={"notification_chat_ids": ["123", "456"]},
            api_base={"player_tag": "#TAG"},
            time_tresholds={"super": 0.25},
            match_history={"shelly": {"victory": 3, "defeat": 1}},
        )

        state = store.ui_state()

        self.assertEqual(state["settings"]["wall_detection_confidence"], 0.7)
        self.assertEqual(state["settings"]["cpu_or_gpu"], "directml")
        self.assertEqual(state["discord"]["username"], "Pyla")
        self.assertEqual(state["telegram"]["notification_chat_ids"], "123, 456")
        self.assertEqual(state["api"]["player_tag"], "#TAG")
        self.assertEqual(state["timers"]["super"], 0.25)
        self.assertEqual(state["history"]["items"][0]["brawler"], "shelly")
        self.assertEqual(state["history"]["items"][0]["winRate"], 75.0)

    def test_qml_update_config_persists_to_correct_old_files(self):
        store, paths = self.make_store()

        store.update_config("settings", "wall_detection_confidence", "0.55")
        store.update_config("settings", "terminal_logging", "true")
        store.update_config("discord", "ping_every_x_match", "5")
        store.update_config("telegram", "notification_chat_ids", "123; 456")
        store.update_config("api", "auto_refresh_token", "false")
        store.update_config("api", "sync_trophies_after_match", "false")
        store.update_config("timers", "low_ips_app_restart_after", "3")

        self.assertEqual(toml.load(paths["bot"])["wall_detection_confidence"], 0.55)
        self.assertEqual(toml.load(paths["general"])["terminal_logging"], "yes")
        self.assertEqual(toml.load(paths["discord"])["ping_every_x_match"], 5)
        self.assertEqual(toml.load(paths["telegram"])["notification_chat_ids"], ["123", "456"])
        self.assertFalse(toml.load(paths["api"])["auto_refresh_token"])
        self.assertFalse(toml.load(paths["api"])["sync_trophies_after_match"])
        self.assertEqual(toml.load(paths["timers"])["low_ips_app_restart_after"], 3)

    @patch("utils.resolve_project_path")
    @patch("gui.instance_config.resolve_project_path")
    def test_editing_instance_uses_per_instance_queue(self, mock_resolve, mock_utils_resolve):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "cfg").mkdir(parents=True, exist_ok=True)
        (root / "instances" / "default").mkdir(parents=True, exist_ok=True)
        (root / "instances" / "acc-1").mkdir(parents=True, exist_ok=True)
        (root / "cfg" / "instances.toml").write_text(
            toml.dumps({
                "multi_instance": {"enabled": True, "default_instance": "default"},
                "instances": {
                    "default": {
                        "name": "Default",
                        "enabled": True,
                        "emulator": "ldplayer",
                        "emulator_port": 5555,
                        "emulator_profile_index": "0",
                        "queue_path": "instances/default/latest_brawler_data.json",
                    },
                    "acc-1": {
                        "name": "Account 1",
                        "enabled": True,
                        "emulator": "ldplayer",
                        "emulator_port": 5557,
                        "emulator_profile_index": "1",
                        "queue_path": "instances/acc-1/latest_brawler_data.json",
                    },
                },
            }),
            encoding="utf-8",
        )
        (root / "instances" / "default" / "latest_brawler_data.json").write_text("[]", encoding="utf-8")
        (root / "instances" / "acc-1" / "latest_brawler_data.json").write_text(
            json.dumps([{"brawler": "colt", "push_until": 1000}]),
            encoding="utf-8",
        )
        mock_resolve.side_effect = lambda path: str(root / path)
        mock_utils_resolve.side_effect = lambda path: str(root / path)
        clear_toml_cache()
        for name in (
            "bot_config.toml",
            "general_config.toml",
            "time_tresholds.toml",
            "match_history.toml",
            "discord_config.toml",
            "telegram_config.toml",
            "telegram_config.local.toml",
            "brawl_stars_api.toml",
            "brawl_stars_api.local.toml",
        ):
            (root / name).write_text("", encoding="utf-8")

        store = HubStateStore(
            str(root / "bot_config.toml"),
            str(root / "general_config.toml"),
            str(root / "time_tresholds.toml"),
            str(root / "match_history.toml"),
            str(root / "discord_config.toml"),
            str(root / "telegram_config.toml"),
            str(root / "telegram_config.local.toml"),
            str(root / "brawl_stars_api.toml"),
            str(root / "brawl_stars_api.local.toml"),
        )
        store.set_editing_instance_id("acc-1")
        queue = store.load_queue()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["brawler"], "colt")

    def test_multi_instance_bridge_and_qml_wired(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")
        bridge = Path("gui/qml_hub.py").read_text(encoding="utf-8")
        self.assertIn("def startAllReadyInstances(self):", bridge)
        self.assertIn("def quickAddInstances(self", bridge)
        self.assertIn("def setEditingInstance(self", bridge)
        self.assertIn("EDITING FARM PLAN FOR", qml)
        self.assertIn("Quick Add All Unassigned", qml)
        self.assertIn("hubBridge.alignWindows()", qml)

    def test_reorder_queue_action_is_wired(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")
        bridge = Path("gui/qml_hub.py").read_text(encoding="utf-8")
        self.assertIn('if action == "reorder-queue":', bridge)
        self.assertIn('runActionWithPayload("reorder-queue"', qml)
        self.assertIn("component QueueRow", qml)
        self.assertIn("DragHandler {", qml)
        self.assertIn("DropArea {", qml)
        self.assertIn('"text/plain": String(queueRow.rowIndex)', qml)
        self.assertIn("filteredPickerOptions", qml)
        self.assertIn('runActionWithPayload("update-queue-item"', qml)
        self.assertIn('action == "update-queue-item"', bridge)

    def test_farm_plan_page_uses_fill_height_queue(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")
        self.assertIn("component FarmPlanPage", qml)
        self.assertIn("id: farmQueueList", qml)
        self.assertIn("Layout.fillHeight: true", qml)
        self.assertIn("No brawlers in the farm plan yet", qml)

    def test_hub_window_is_resizable(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")
        self.assertIn("minimumWidth: 720", qml)
        self.assertIn("minimumHeight: 480", qml)
        self.assertIn("component WindowResizeGrip", qml)
        self.assertIn("startSystemResize", qml)
        self.assertIn("function navLabel(tab)", qml)
        self.assertIn("statusToastTimer", qml)

    def test_settings_only_entrypoint_exists(self):
        bridge = Path("gui/qml_hub.py").read_text(encoding="utf-8")
        self.assertIn("--settings-only", bridge)
        self.assertIn('context.setContextProperty("settingsOnly", settings_only)', bridge)
        self.assertIn("def closeHub(self):", bridge)

    def test_qml_uses_styled_sliders_for_timer_values(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertIn("component NumericSlider", qml)
        self.assertIn("Slider {", qml)
        self.assertIn('label: "Super Delay"', qml)
        self.assertIn('onSaved: function(value) { root.saveValue("timers", "super", value) }', qml)

    def test_qml_settings_tab_has_complete_old_settings_blocks(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertIn('label: "Performance Profile"', qml)
        self.assertIn('label: "Apply Performance Mode"', qml)
        self.assertIn('root.runAction("profile-', qml)
        self.assertNotIn('color: "transparent"\n\n        Text {\n            id: labelText', qml)

    def test_qml_settings_controls_fit_inside_rows(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertIn("implicitWidth: Math.max(66", qml)
        self.assertIn("anchors.leftMargin: 190", qml)
        self.assertIn("Layout.fillWidth: true", qml)
        self.assertIn('model: ["auto", "directml", "amd", "cuda", "openvino", "cpu"]', qml)

    def test_qml_config_inputs_have_visible_row_height(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertIn("implicitHeight: 34", qml)
        self.assertIn("height: implicitHeight", qml)

    def test_qml_secret_inputs_actions_and_history_are_polished(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertIn("property bool revealed: false", qml)
        self.assertIn('text: inputBox.revealed ? "hide" : "show"', qml)
        self.assertIn("component ActionRow", qml)
        self.assertIn("component CenterRow", qml)
        self.assertIn('ActionRow {', qml)
        self.assertIn("Image {", qml)
        self.assertIn("source: modelData.icon", qml)

    def test_qml_action_rows_have_consistent_bottom_spacing(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertIn("component ActionRow", qml)
        self.assertIn("Layout.topMargin: 18", qml)
        self.assertIn("Layout.bottomMargin: 8", qml)
        self.assertIn("Layout.alignment: Qt.AlignHCenter", qml)
        self.assertIn("width: parent ? parent.width : actionRowInner.implicitWidth", qml)
        self.assertIn("implicitHeight: actionRowInner.implicitHeight + 20", qml)
        self.assertIn("contentHeight: pageBody.implicitHeight + pageBody.y + 32", qml)

    def test_qml_switch_rows_align_to_control_column_start(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertIn("component CenterRow", qml)
        self.assertIn("anchors.left: parent.left", qml)
        self.assertNotIn("anchors.horizontalCenter: parent.horizontalCenter\n            anchors.verticalCenter: parent.verticalCenter\n            spacing: 10\n        }\n    }\n\n    component ActionRow", qml)

    def test_qml_overview_visuals_match_current_design_contract(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertNotIn('label: "LDPlayer"\n                                    iconKind:', qml)
        self.assertNotIn('label: "MuMu"\n                                    iconKind:', qml)
        self.assertIn('text: settingsOnly ? "Pyla-RL Settings (bot running)" : "Pyla-RL Hub"', qml)
        self.assertIn("id: startButton", qml)
        self.assertIn("id: closeSettingsButton", qml)
        self.assertIn("id: startBar", qml)
        self.assertIn('text: "START"', qml)
        self.assertIn("hubState.preflight", qml)
        self.assertIn("statusChecked", qml)
        self.assertIn("emulatorPreflightStatus", qml)
        self.assertIn("function startBot()", qml)
        self.assertNotIn("gradient: Gradient", qml)

    def test_preflight_actions_preserve_cache_and_stay_async(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")
        bridge = Path("gui/qml_hub.py").read_text(encoding="utf-8")

        self.assertIn("return json.dumps(self._ui_state())", bridge)
        self.assertIn('return self._start_background_action("preflight-fix", payload)', bridge)
        self.assertIn('if action == "preflight-fix":', bridge)
        self.assertIn('return json.dumps({"ok": True, "state": self._ui_state()})', bridge)
        self.assertIn("statusText = \"Please wait for the current hub action to finish.\"\n            statusOk = false", qml)
        self.assertIn("enabled: !root.hubBusy\n                                        onClicked: applyBridgeResult(hubBridge.runPreflightFix", qml)

    def test_normalize_dialog_path_handles_file_urls(self):
        from gui.qml_hub import _normalize_dialog_path

        self.assertEqual(
            _normalize_dialog_path("file:///C:/Users/test/farm_plan.json").replace("\\", "/"),
            "C:/Users/test/farm_plan.json",
        )
        self.assertEqual(_normalize_dialog_path("C:\\Users\\test\\farm_plan.json"), "C:\\Users\\test\\farm_plan.json")

    def test_qml_farm_plan_has_tutorial_and_picker_grid(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertIn("activeTutorialId", qml)
        self.assertIn("component TutorialOverlay", qml)
        self.assertIn('openTutorial("farm-plan")', qml)
        self.assertIn('label: "Tutorial"', qml)
        self.assertIn("component BrawlerPickTile", qml)
        self.assertIn("filteredPickerOptions", qml)
        self.assertIn('label: "Refresh"', qml)
        self.assertIn("compact: true", qml)

        self.assertIn("import QtQuick.Dialogs", qml)
        self.assertIn("id: importQueueDialog", qml)
        self.assertIn("id: exportQueueDialog", qml)

    def test_qml_help_tab_and_tutorial_contract(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")
        bridge = Path("gui/qml_hub.py").read_text(encoding="utf-8")

        self.assertIn('"Help"', qml)
        self.assertIn('visible: root.activeTab === "Help"', qml)
        self.assertIn("function openTutorial(id)", qml)
        self.assertIn("function filteredHelpTopics()", qml)
        self.assertIn("component TutorialHelpButton", qml)
        self.assertIn("TutorialOverlay {}", qml)
        self.assertIn("reset-setup-wizard", qml)
        self.assertIn("result.showWizard", qml)
        self.assertIn("def tutorialTopicsJson(self):", bridge)
        self.assertIn("def openTutorialDoc(self, doc_path):", bridge)
        self.assertIn('"tutorials": tutorial_topics()', Path("gui/hub_state.py").read_text(encoding="utf-8"))

    def test_qml_instances_tab_is_always_available(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertIn(
            'readonly property var navItems: ["Overview", "Instances", "Farm Plan", "Settings", "Discord", "Telegram", "API", "Timers", "Match History", "Help"]',
            qml,
        )
        self.assertIn("setMultiInstanceEnabled", qml)
        self.assertIn('visible: root.activeTab === "Instances"', qml)

    def test_qml_instances_tab_supports_add_and_save(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertIn('title: "ADD INSTANCE"', qml)
        self.assertIn("saveNewInstance", qml)
        self.assertIn("saveInstanceProfile", qml)
        self.assertIn("deleteInstanceProfile", qml)

    def test_qml_anti_reseller_ui_contract(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertIn("UNOFFICIAL COPY", qml)
        self.assertIn("accept-license", qml)
        self.assertIn("report-reseller", qml)
        self.assertIn("check-updates", qml)
        self.assertIn("licenseTermsAccepted", qml)
        self.assertIn("title: \"ABOUT\"", qml)

    def test_qml_config_controls_use_known_store_keys(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")
        fields = {
            "settings": HubStateStore.SETTINGS_FIELDS,
            "discord": HubStateStore.DISCORD_FIELDS,
            "telegram": HubStateStore.TELEGRAM_FIELDS,
            "api": HubStateStore.API_FIELDS,
            "timers": HubStateStore.TIMER_FIELDS,
        }

        for section, key in re.findall(r'root\.saveValue\("([^"]+)", "([^"]+)"', qml):
            self.assertIn(section, fields)
            self.assertIn(key, fields[section])

    def test_qml_actions_are_wired_to_bridge_handlers(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")
        bridge = Path("gui/qml_hub.py").read_text(encoding="utf-8")
        direct_handlers = set(re.findall(r'if action == "([^"]+)"', bridge))

        for action in re.findall(r'root\.runAction\("([^"]+)"', qml):
            if action == "profile-":
                self.assertIn('if action.startswith("profile-"):', bridge)
            else:
                self.assertIn(action, direct_handlers)

        self.assertIn('hubBridge.updateSetting("mode", "showdown-trio")', qml)
        self.assertIn('hubBridge.updateSetting("emulator", "ldplayer")', qml)
        self.assertIn('hubBridge.updateSetting("emulator", "mumu")', qml)
        self.assertIn("def startPyla(self):", bridge)
        self.assertIn("runActionWithPayload", bridge)
        self.assertIn("function startBot()", qml)
        self.assertIn("onClicked: hubBridge.openDiscord()", qml)
        self.assertIn("onClicked: hubBridge.openPatreon()", qml)

    def test_qml_hub_is_primary_without_legacy_fallback(self):
        main_source = Path("app/main.py").read_text(encoding="utf-8")

        self.assertIn("from gui.qml_hub import QmlHub", main_source)
        self.assertIn("return QmlHub(*args, **kwargs)", main_source)
        self.assertNotIn("falling back to legacy hub", main_source)

    def test_qml_hub_can_repair_missing_pyside6(self):
        bridge = Path("gui/qml_hub.py").read_text(encoding="utf-8")

        self.assertIn("ensure_pyside6_available", bridge)
        self.assertIn('"PySide6>=6.7.0"', bridge)

    def test_ui_theme_setting_persists(self):
        store, paths = self.make_store()

        self.assertEqual(store.general_config.get("ui_theme"), "system")
        self.assertEqual(store.general_config.get("ui_animations"), "yes")

        store.update_config("settings", "ui_theme", "light")
        store.update_config("settings", "ui_animations", "false")

        general = toml.load(paths["general"])
        self.assertEqual(general["ui_theme"], "light")
        self.assertEqual(general["ui_animations"], "no")

        state = store.ui_state()
        self.assertEqual(state["settings"]["ui_theme"], "light")
        self.assertFalse(state["settings"]["ui_animations"])

    def test_ui_theme_setting_rejects_invalid_modes(self):
        store, _ = self.make_store()

        with self.assertRaises(ValueError):
            store.update_config("settings", "ui_theme", "neon")

    def test_qml_liquid_glass_theme_contract(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")
        bridge = Path("gui/qml_hub.py").read_text(encoding="utf-8")

        # Live theme bridge
        self.assertIn("def themeJson(self):", bridge)
        self.assertIn("apply_windows_glass_effects", bridge)
        self.assertIn("function applyTheme()", qml)
        self.assertIn("hubBridge.themeJson()", qml)
        self.assertIn("function setThemeMode(mode)", qml)
        self.assertIn("function cycleThemeMode()", qml)
        self.assertIn('root.saveValue("settings", "ui_theme", mode)', qml)
        self.assertIn('root.saveValue("settings", "ui_animations", value)', qml)

        # Theme toggle + appearance settings
        self.assertIn("id: themeToggleButton", qml)
        self.assertIn('title: "APPEARANCE"', qml)
        self.assertIn('model: ["light", "dark", "system"]', qml)

        # Glass backdrop + animated tokens
        self.assertIn("id: backdropCanvas", qml)
        self.assertIn("createRadialGradient", qml)
        self.assertIn("property color glassHighlight", qml)
        self.assertIn("property color scrim", qml)
        self.assertIn("Behavior on bg { ColorAnimation { duration: root.durSlow } }", qml)

        # Motion language with reduced-motion support
        self.assertIn("readonly property int durFast: animationsEnabled ? 130 : 0", qml)
        self.assertIn("id: pageEnterAnim", qml)
        self.assertIn("id: navIndicator", qml)
        self.assertIn("add: Transition {", qml)


if __name__ == "__main__":
    unittest.main()
