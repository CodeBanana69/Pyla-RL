import re
import tempfile
import unittest
from pathlib import Path

import toml

from gui.hub_state import HubStateStore


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
        store.update_config("timers", "low_ips_app_restart_after", "3")

        self.assertEqual(toml.load(paths["bot"])["wall_detection_confidence"], 0.55)
        self.assertEqual(toml.load(paths["general"])["terminal_logging"], "yes")
        self.assertEqual(toml.load(paths["discord"])["ping_every_x_match"], 5)
        self.assertEqual(toml.load(paths["telegram"])["notification_chat_ids"], ["123", "456"])
        self.assertFalse(toml.load(paths["api"])["auto_refresh_token"])
        self.assertEqual(toml.load(paths["timers"])["low_ips_app_restart_after"], 3)

    def test_qml_uses_styled_sliders_for_timer_values(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertIn("component NumericSlider", qml)
        self.assertIn("Slider {", qml)
        self.assertIn('label: "Super Delay"', qml)
        self.assertIn('onSaved: root.saveValue("timers", "super", value)', qml)

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
        self.assertIn("contentHeight: pageBody.y + pageBody.implicitHeight + 72", qml)

    def test_qml_switch_rows_align_to_control_column_start(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertIn("component CenterRow", qml)
        self.assertIn("anchors.left: parent.left", qml)
        self.assertNotIn("anchors.horizontalCenter: parent.horizontalCenter\n            anchors.verticalCenter: parent.verticalCenter\n            spacing: 10\n        }\n    }\n\n    component ActionRow", qml)

    def test_qml_overview_visuals_match_current_design_contract(self):
        qml = Path("gui/qml/PylaHub.qml").read_text(encoding="utf-8")

        self.assertNotIn('label: "LDPlayer"\n                                    iconKind:', qml)
        self.assertNotIn('label: "MuMu"\n                                    iconKind:', qml)
        self.assertIn('font.weight: Font.Bold\n                    }\n                    Text {\n                        text: "XXZ Hub', qml)
        self.assertIn("id: startButton", qml)
        self.assertIn('text: "START"', qml)
        self.assertIn("hubState.preflight", qml)
        self.assertIn("function startBot()", qml)
        self.assertNotIn("gradient: Gradient", qml)
        self.assertNotIn("scale: startMouse.pressed", qml)

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
        main_source = Path("main.py").read_text(encoding="utf-8")

        self.assertIn("from gui.qml_hub import QmlHub", main_source)
        self.assertIn("return QmlHub(*args, **kwargs)", main_source)
        self.assertNotIn("falling back to legacy hub", main_source)

    def test_qml_hub_can_repair_missing_pyside6(self):
        bridge = Path("gui/qml_hub.py").read_text(encoding="utf-8")

        self.assertIn("ensure_pyside6_available", bridge)
        self.assertIn('"PySide6>=6.7.0"', bridge)


if __name__ == "__main__":
    unittest.main()
