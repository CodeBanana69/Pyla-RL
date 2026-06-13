import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    width: settingsOnly ? 640 : 820
    height: settingsOnly ? 600 : 560
    minimumWidth: 720
    minimumHeight: 480
    visible: true
    title: settingsOnly ? "Pyla-RL Settings" : "Pyla-RL Hub"
    color: theme.bg
    flags: Qt.FramelessWindowHint | Qt.Window

    property string mode: hubBridge ? hubBridge.mode() : "showdown-trio"
    property string emulator: hubBridge ? hubBridge.emulator() : "ldplayer"
    property string activeTab: "Overview"
    property var hubState: ({ settings: {}, discord: {}, telegram: {}, api: {}, timers: {}, history: { items: [], summary: {}, recent: [] }, queue: [], preflight: { ready: false, checks: [] } })
    property var preflightChecks: []
    property string statusText: ""
    property bool statusOk: true
    property string performanceProfile: "balanced"
    property string settingsFilter: ""
    property bool hubBusy: false
    property bool showWizard: true
    property int wizardStep: 0
    property bool licenseTermsAccepted: false
    readonly property bool unofficialCopy: !!(hubState.meta && hubState.meta.sourceStatus && hubState.meta.sourceStatus.official === false)
    readonly property bool licenseAccepted: !!(hubState.meta && hubState.meta.licenseAccepted)
    property string pushAllTarget: "1000"
    property bool showBrawlerPicker: false
    property string activeTutorialId: ""
    property string helpFilter: ""
    property string pickerFilter: ""
    property string pickerBrawler: ""
    property string pickerTarget: "1000"
    property string pickerType: "trophies"
    property string historySort: "games"
    property string themeMode: "system"
    property string resolvedTheme: "dark"
    property bool animationsEnabled: true
    readonly property int durFast: animationsEnabled ? 130 : 0
    readonly property int durMed: animationsEnabled ? 210 : 0
    readonly property int durSlow: animationsEnabled ? 320 : 0
    readonly property var trophyTargetPresets: ["250", "500", "750", "1000", "1250", "1500", "1750", "2000"]
    readonly property var queueSortOptions: [
        { id: "cups_desc", label: "Cups high \u2192 low" },
        { id: "cups_asc", label: "Cups low \u2192 high" },
        { id: "gap_asc", label: "Closest to target" },
        { id: "gap_desc", label: "Furthest from target" },
        { id: "target_desc", label: "Target high \u2192 low" },
        { id: "target_asc", label: "Target low \u2192 high" },
        { id: "name_asc", label: "Name A \u2192 Z" },
        { id: "name_desc", label: "Name Z \u2192 A" },
        { id: "efficiency", label: "Best trophies/hour" }
    ]

    function healthColor(status) {
        if (status === "good") return theme.ok
        if (status === "degraded") return theme.accent
        return theme.danger
    }

    function parseTrophyTarget(value) {
        var parsed = parseInt(String(value || "").trim())
        return isNaN(parsed) ? 0 : parsed
    }

    function trophyTargetFromUi(fieldText, fallbackValue) {
        var text = String(fieldText || "").trim()
        if (text !== "") {
            return parseTrophyTarget(text)
        }
        return parseTrophyTarget(fallbackValue)
    }

    function emulatorPreflightStatus(emulatorId) {
        if (!(hubState.preflight && hubState.preflight.emulator_status)) {
            return null
        }
        return hubState.preflight.emulator_status[emulatorId] || null
    }
    readonly property var navItems: ["Overview", "Instances", "Farm Plan", "Settings", "Discord", "Telegram", "API", "Timers", "Match History", "Help"]
    readonly property var filteredPickerOptions: {
        const options = (hubState.meta && hubState.meta.brawlerOptions) ? hubState.meta.brawlerOptions.slice() : []
        const needle = pickerFilter.trim().toLowerCase()
        if (!needle) {
            return options
        }
        return options.filter(function(item) {
            return String(item.name || "").toLowerCase().indexOf(needle) >= 0
        })
    }
    property int queueDragSource: -1
    property int queueDropTarget: -1
    property bool showAddInstanceForm: false
    property bool showMultiInstanceSetup: false
    property bool showAdvancedInstanceForm: false
    property string instanceFormId: ""
    property string instanceFormName: ""
    property string instanceFormEmulator: "ldplayer"
    property string instanceFormPort: "5555"
    property string instanceFormPlayerTag: ""
    property string instanceFormEmulatorName: ""
    property string pendingInstanceAction: ""
    property string pendingInstanceActionLabel: ""
    property string pendingInstanceActionId: ""

    function reloadHubState() {
        if (!hubBridge) {
            return
        }
        hubState = JSON.parse(hubBridge.stateJson())
        preflightChecks = (hubState.preflight && hubState.preflight.checks) ? hubState.preflight.checks : []
    }

    function applyTheme() {
        if (!hubBridge || !hubBridge.themeJson) {
            return
        }
        const data = JSON.parse(hubBridge.themeJson())
        root.themeMode = data.mode
        root.resolvedTheme = data.resolved
        root.animationsEnabled = !!data.animations
        const c = data.colors
        theme.bg = c.bg
        theme.chrome = c.chrome
        theme.panel = c.panel
        theme.panel2 = c.panel2
        theme.panel3 = c.panel3
        theme.border = c.border
        theme.borderSoft = c.borderSoft
        theme.hover = c.hover
        theme.glassHighlight = c.glassHighlight
        theme.scrim = c.scrim
        theme.text = c.text
        theme.muted = c.muted
        theme.faint = c.faint
        theme.accent = c.accent
        theme.accentHover = c.accentHover
        theme.accentSoft = c.accentSoft
        theme.accentBorder = c.accentBorder
        theme.ok = c.ok
        theme.okSoft = c.okSoft
        theme.danger = c.danger
        theme.dangerSoft = c.dangerSoft
        theme.warnSoft = c.warnSoft
        theme.knob = c.knob
        theme.disabled = c.disabled
        theme.link = c.link
        theme.glowA = c.glowA
        theme.glowB = c.glowB
        theme.glowC = c.glowC
        if (hubBridge.applyWindowTheme) {
            hubBridge.applyWindowTheme(root.resolvedTheme !== "light")
        }
        if (typeof backdropCanvas !== "undefined" && backdropCanvas) {
            backdropCanvas.requestPaint()
            backdropFade.restart()
        }
    }

    function setThemeMode(mode) {
        root.saveValue("settings", "ui_theme", mode)
        root.applyTheme()
    }

    function cycleThemeMode() {
        const next = root.themeMode === "system" ? "light" : (root.themeMode === "light" ? "dark" : "system")
        root.setThemeMode(next)
    }

    function setAnimationsEnabled(value) {
        root.saveValue("settings", "ui_animations", value)
        root.applyTheme()
    }

    Connections {
        target: hubBridge
        function onInstancesUpdated() {
            root.reloadHubState()
        }
    }

    function navLabel(tab) {
        if (tab === "Farm Plan") {
            var count = (hubState.queue || []).length
            return count > 0 ? ("Farm Plan (" + count + ")") : "Farm Plan"
        }
        return tab
    }

    function closeHubWindow() {
        if (settingsOnly && hubBridge) {
            hubBridge.closeHub()
        } else {
            root.close()
        }
    }

    Timer {
        id: statusToastTimer
        interval: 2500
        onTriggered: {
            if (root.statusOk) {
                root.statusText = ""
            }
        }
    }

    function reloadState() {
        if (hubBridge) {
            hubState = JSON.parse(hubBridge.stateJson())
            mode = hubState.mode || mode
            emulator = hubState.emulator || emulator
            preflightChecks = (hubState.preflight && hubState.preflight.checks) ? hubState.preflight.checks : []
        }
    }

    function applyBridgeResult(resultText) {
        const result = JSON.parse(resultText)
        if (result.pending) {
            root.hubBusy = true
            if (result.message) {
                statusText = result.message
                statusOk = true
            }
            return result
        }
        if (result.state) {
            hubState = result.state
            preflightChecks = (result.state.preflight && result.state.preflight.checks) ? result.state.preflight.checks : []
        }
        if (result.message) {
            statusText = result.message
            statusOk = !!result.ok
            if (result.ok) {
                statusToastTimer.restart()
            }
        }
        if (result.showWizard) {
            root.showWizard = true
            root.wizardStep = root.licenseAccepted ? 1 : 0
        }
        if (result.action) {
            root.pendingInstanceAction = result.action
            root.pendingInstanceActionLabel = result.actionLabel || ""
            root.pendingInstanceActionId = result.instanceId || ""
        } else if (result.ok) {
            root.pendingInstanceAction = ""
            root.pendingInstanceActionLabel = ""
            root.pendingInstanceActionId = ""
        }
        return result
    }

    function readinessColor(status) {
        if (status === "ready") return theme.ok
        if (status === "port_conflict") return theme.danger
        return theme.accent
    }

    function readinessLabel(item) {
        if (!item || !item.readiness) return "Unknown"
        const status = item.readiness.status || ""
        if (status === "ready") return "Ready"
        if (status === "needs_farm_plan") return "Needs farm plan"
        if (status === "port_conflict") return "Port conflict"
        if (status === "no_emulator") return "No emulator"
        return item.readiness.message || status
    }

    function editInstanceFarmPlan(instanceId) {
        applyBridgeResult(hubBridge.setEditingInstance(instanceId))
        activeTab = "Farm Plan"
    }

    function runPendingInstanceAction() {
        const action = pendingInstanceAction
        const instanceId = pendingInstanceActionId
        pendingInstanceAction = ""
        pendingInstanceActionLabel = ""
        pendingInstanceActionId = ""
        if (action === "edit_farm_plan" && instanceId) {
            editInstanceFarmPlan(instanceId)
        } else if (action === "enable_multi_instance") {
            applyBridgeResult(hubBridge.setMultiInstanceEnabled(true))
        } else if (action === "rescan_emulators") {
            applyBridgeResult(hubBridge.listAvailableEmulators())
        }
    }

    function quickAddUnassignedInstances() {
        applyBridgeResult(hubBridge.quickAddInstances(JSON.stringify({ copy_farm_plan_from: "default" })))
    }

    function dismissMultiInstanceSetup() {
        showMultiInstanceSetup = false
        applyBridgeResult(hubBridge.dismissMultiInstanceSetup())
    }

    function copyInstanceFarmPlan(instanceId) {
        applyBridgeResult(hubBridge.copyInstanceFarmPlan(JSON.stringify({ id: instanceId, from_id: "default" })))
    }

    function saveInstanceNotifications(instanceId, localSettings) {
        const payload = {
            id: instanceId,
            player_tag: (localSettings && localSettings.player_tag) ? localSettings.player_tag : "",
            discord_webhook_url: (localSettings && localSettings.discord_webhook_url) ? localSettings.discord_webhook_url : "",
            discord_id: (localSettings && localSettings.discord_id) ? localSettings.discord_id : "",
            telegram_notification_chat_id: (localSettings && localSettings.telegram_notification_chat_id) ? localSettings.telegram_notification_chat_id : ""
        }
        applyBridgeResult(hubBridge.saveInstanceLocalSettings(JSON.stringify(payload)))
    }

    function tutorialTopic(id) {
        const topics = (hubState.meta && hubState.meta.tutorials) ? hubState.meta.tutorials : []
        for (var i = 0; i < topics.length; i++) {
            if (topics[i].id === id) {
                return topics[i]
            }
        }
        return null
    }

    function openTutorial(id) {
        root.activeTutorialId = String(id || "")
    }

    function closeTutorial() {
        root.activeTutorialId = ""
    }

    function openTutorialDoc(docPath) {
        if (!docPath) {
            return
        }
        const result = JSON.parse(hubBridge.openTutorialDoc(docPath))
        if (result.message) {
            statusText = result.message
            statusOk = !!result.ok
        }
    }

    function filteredHelpTopics() {
        const topics = (hubState.meta && hubState.meta.tutorials) ? hubState.meta.tutorials : []
        const query = helpFilter.trim().toLowerCase()
        if (!query) {
            return topics
        }
        return topics.filter(function(topic) {
            return topic.title.toLowerCase().indexOf(query) >= 0
                || String(topic.tab || "").toLowerCase().indexOf(query) >= 0
                || String(topic.id || "").toLowerCase().indexOf(query) >= 0
        })
    }

    function saveNewInstance() {
        const payload = {
            id: instanceFormId.trim(),
            name: instanceFormName.trim() || instanceFormId.trim(),
            emulator: instanceFormEmulator,
            emulator_port: parseInt(instanceFormPort, 10) || 5555,
            emulator_instance_name: instanceFormEmulatorName.trim(),
            player_tag: instanceFormPlayerTag.trim(),
            enabled: true,
            copy_farm_plan: true,
            copy_farm_plan_from: "default"
        }
        const result = applyBridgeResult(hubBridge.saveInstanceProfile(JSON.stringify(payload)))
        if (result.ok) {
            showAddInstanceForm = false
            showAdvancedInstanceForm = false
            instanceFormId = ""
            instanceFormName = ""
            instanceFormEmulator = "ldplayer"
            instanceFormPort = "5555"
            instanceFormPlayerTag = ""
            instanceFormEmulatorName = ""
        }
        return result
    }

    function pickDetectedEmulator(item) {
        if (!item) return
        instanceFormEmulator = item.emulator || "ldplayer"
        instanceFormPort = String(item.adb_port || "5555")
        instanceFormEmulatorName = item.name || ""
        instanceFormName = item.name || instanceFormName
        if (!instanceFormId.trim()) {
            instanceFormId = String(item.emulator || "emu") + "-" + String(item.index || 0)
        }
    }

    function setInstanceFormEmulator(value) {
        instanceFormEmulator = value
        if (value === "mumu" && (instanceFormPort === "5555" || instanceFormPort === "5557" || instanceFormPort === "5559")) {
            instanceFormPort = "16384"
        } else if (value === "ldplayer" && (instanceFormPort === "16384" || instanceFormPort === "16416" || instanceFormPort === "16448")) {
            instanceFormPort = "5555"
        }
    }

    function saveValue(section, key, value) {
        const result = applyBridgeResult(hubBridge.updateConfig(section, key, String(value)))
        if (!result.ok && result.message) {
            statusText = result.message
            statusOk = false
        } else if (result.ok) {
            statusText = "Saved"
            statusOk = true
            statusToastTimer.restart()
        }
        return result
    }

    function value(section, key) {
        if (!hubState[section] || hubState[section][key] === undefined || hubState[section][key] === null) {
            return ""
        }
        return hubState[section][key]
    }

    function boolValue(section, key) {
        const item = value(section, key)
        return item === true || String(item).toLowerCase() === "true" || String(item).toLowerCase() === "yes"
    }

    function runAction(action) {
        statusText = "Working..."
        statusOk = true
        const result = applyBridgeResult(hubBridge.runAction(action))
        if (result.ok) {
            statusToastTimer.restart()
        }
    }

    function runActionWithPayload(action, payload) {
        statusText = "Working..."
        statusOk = true
        const result = applyBridgeResult(hubBridge.runActionWithPayload(action, JSON.stringify(payload || {})))
        if (result.ok) {
            statusToastTimer.restart()
        }
    }

    function startBot() {
        if (root.hubBusy) {
            return
        }
        statusText = "Checking pre-flight..."
        statusOk = true
        applyBridgeResult(hubBridge.startPyla())
    }

    function sortedHistoryItems() {
        const items = (hubState.history && hubState.history.items) ? hubState.history.items.slice() : []
        if (historySort === "name") {
            items.sort(function(a, b) { return String(a.brawler).localeCompare(String(b.brawler)) })
        } else if (historySort === "winRate") {
            items.sort(function(a, b) { return (b.winRate || 0) - (a.winRate || 0) })
        } else {
            items.sort(function(a, b) { return (b.games || 0) - (a.games || 0) })
        }
        return items
    }

    Component.onCompleted: {
        applyTheme()
        reloadState()
        runAction("ensure-brawler-icons")
        if (settingsOnly) {
            showWizard = false
            activeTab = "Farm Plan"
            return
        }
        const needsLicense = !(hubState.meta && hubState.meta.licenseAccepted)
        const needsWizard = !!(hubState.meta && hubState.meta.firstRunWizard)
        showWizard = needsLicense || needsWizard
        wizardStep = needsLicense ? 0 : 1
        if (showWizard && wizardStep >= 1) {
            runAction("preflight-check")
        }
    }

    Connections {
        target: hubBridge
        function onIconsUpdated(message) {
            reloadState()
            statusText = message
            statusOk = true
        }
        function onStateChanged(nextMode, nextEmulator) {
            root.mode = nextMode
            root.emulator = nextEmulator
        }
        function onQueueChanged() {
            reloadState()
        }
        function onActionFinished(resultText) {
            root.hubBusy = false
            applyBridgeResult(resultText)
        }
        function onActionBusyChanged(busy) {
            root.hubBusy = busy
        }
    }

    Item {
        id: theme
        visible: false
        property color bg: "#0b0c12"
        property color chrome: "#a811131b"
        property color panel: "#9e161925"
        property color panel2: "#b81c2030"
        property color panel3: "#eb252a3d"
        property color border: "#29ffffff"
        property color borderSoft: "#14ffffff"
        property color hover: "#12ffffff"
        property color glassHighlight: "#12ffffff"
        property color scrim: "#8c000000"
        property color text: "#f5f6fa"
        property color muted: "#aab0c0"
        property color faint: "#707689"
        property color accent: "#ff9f0a"
        property color accentHover: "#ffb23a"
        property color accentSoft: "#29ff9f0a"
        property color accentBorder: "#8cff9f0a"
        property color ok: "#30d158"
        property color okSoft: "#2e30d158"
        property color danger: "#ff5d52"
        property color dangerSoft: "#29ff5d52"
        property color warnSoft: "#29ffd60a"
        property color knob: "#ffffff"
        property color disabled: "#585d6e"
        property color link: "#7ccbff"
        property color glowA: "#ff9f0a"
        property color glowB: "#7a5cff"
        property color glowC: "#2bd9c8"

        Behavior on bg { ColorAnimation { duration: root.durSlow } }
        Behavior on chrome { ColorAnimation { duration: root.durSlow } }
        Behavior on panel { ColorAnimation { duration: root.durSlow } }
        Behavior on panel2 { ColorAnimation { duration: root.durSlow } }
        Behavior on panel3 { ColorAnimation { duration: root.durSlow } }
        Behavior on border { ColorAnimation { duration: root.durSlow } }
        Behavior on borderSoft { ColorAnimation { duration: root.durSlow } }
        Behavior on hover { ColorAnimation { duration: root.durSlow } }
        Behavior on glassHighlight { ColorAnimation { duration: root.durSlow } }
        Behavior on scrim { ColorAnimation { duration: root.durSlow } }
        Behavior on text { ColorAnimation { duration: root.durSlow } }
        Behavior on muted { ColorAnimation { duration: root.durSlow } }
        Behavior on faint { ColorAnimation { duration: root.durSlow } }
        Behavior on accent { ColorAnimation { duration: root.durSlow } }
        Behavior on accentHover { ColorAnimation { duration: root.durSlow } }
        Behavior on accentSoft { ColorAnimation { duration: root.durSlow } }
        Behavior on accentBorder { ColorAnimation { duration: root.durSlow } }
        Behavior on ok { ColorAnimation { duration: root.durSlow } }
        Behavior on okSoft { ColorAnimation { duration: root.durSlow } }
        Behavior on danger { ColorAnimation { duration: root.durSlow } }
        Behavior on dangerSoft { ColorAnimation { duration: root.durSlow } }
        Behavior on warnSoft { ColorAnimation { duration: root.durSlow } }
        Behavior on disabled { ColorAnimation { duration: root.durSlow } }
        Behavior on link { ColorAnimation { duration: root.durSlow } }
    }

    component Glyph: Item {
        id: icon
        property string kind: "play"
        property color stroke: theme.muted
        width: 16
        height: 16

        Canvas {
            id: glyphCanvas
            anchors.fill: parent
            antialiasing: true
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            Connections {
                target: icon
                function onKindChanged() { glyphCanvas.requestPaint() }
                function onStrokeChanged() { glyphCanvas.requestPaint() }
            }
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                ctx.strokeStyle = icon.stroke
                ctx.fillStyle = icon.stroke
                ctx.lineWidth = 1.35
                ctx.lineCap = "round"
                ctx.lineJoin = "round"

                if (icon.kind === "monitor") {
                    ctx.roundedRect(2, 3, 12, 8, 1.4, 1.4)
                    ctx.stroke()
                    ctx.beginPath()
                    ctx.moveTo(8, 11.5)
                    ctx.lineTo(8, 14)
                    ctx.moveTo(6, 14)
                    ctx.lineTo(10, 14)
                    ctx.stroke()
                } else if (icon.kind === "phone") {
                    ctx.roundedRect(5, 2, 6, 12, 1.5, 1.5)
                    ctx.stroke()
                    ctx.beginPath()
                    ctx.arc(8, 12, 0.55, 0, Math.PI * 2)
                    ctx.fill()
                } else if (icon.kind === "play") {
                    ctx.beginPath()
                    ctx.moveTo(5, 3.5)
                    ctx.lineTo(12, 8)
                    ctx.lineTo(5, 12.5)
                    ctx.closePath()
                    ctx.fill()
                } else if (icon.kind === "lock") {
                    ctx.beginPath()
                    ctx.moveTo(5, 7)
                    ctx.lineTo(5, 5)
                    ctx.bezierCurveTo(5, 2, 11, 2, 11, 5)
                    ctx.lineTo(11, 7)
                    ctx.stroke()
                    ctx.roundedRect(4, 7, 8, 6, 1.4, 1.4)
                    ctx.stroke()
                    ctx.beginPath()
                    ctx.arc(8, 10, 0.65, 0, Math.PI * 2)
                    ctx.fill()
                }
            }
        }
    }

    component NavButton: Rectangle {
        id: nav
        property string label: ""
        property string tabId: ""
        property bool selected: root.activeTab === tabId
        property bool hovered: false
        signal clicked()

        width: Math.max(96, navText.implicitWidth + 18)
        height: 30
        radius: 9
        color: !selected && hovered ? theme.hover : "transparent"

        Behavior on color { ColorAnimation { duration: root.durFast } }

        Text {
            id: navText
            anchors.centerIn: parent
            text: nav.label
            color: nav.selected ? theme.text : (nav.hovered ? theme.text : theme.muted)
            font.pixelSize: 11
            font.weight: nav.selected ? Font.DemiBold : Font.Medium
            horizontalAlignment: Text.AlignHCenter

            Behavior on color { ColorAnimation { duration: root.durFast } }
        }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                nav.hovered = false
                nav.clicked()
            }
            onEntered: nav.hovered = true
            onExited: nav.hovered = false
            onCanceled: nav.hovered = false
        }
    }

    component OptionCard: Rectangle {
        id: card
        property string label: ""
        property string detail: ""
        property string iconKind: ""
        property bool selected: false
        property bool locked: false
        property bool statusChecked: false
        property bool statusOk: false
        property bool hovered: false
        signal clicked()

        height: 58
        radius: 12
        color: selected && !locked ? theme.accentSoft : (hovered ? theme.hover : theme.panel)
        border.width: 1
        border.color: selected && !locked ? theme.accentBorder : (hovered ? theme.border : theme.borderSoft)
        opacity: locked ? 0.62 : 1
        scale: cardPressMouse.pressed && !locked ? 0.985 : 1.0

        Behavior on color { ColorAnimation { duration: root.durFast } }
        Behavior on border.color { ColorAnimation { duration: root.durFast } }
        Behavior on scale { NumberAnimation { duration: root.durFast; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: root.durFast } }

        Rectangle {
            anchors.top: parent.top
            anchors.topMargin: 1
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width - parent.radius * 2
            height: 1
            color: theme.glassHighlight
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            spacing: 12

            Rectangle {
                visible: card.iconKind !== "" || card.locked
                Layout.preferredWidth: visible ? 30 : 0
                Layout.preferredHeight: 30
                radius: 8
                color: theme.panel3

                Glyph {
                    anchors.centerIn: parent
                    kind: card.locked ? "lock" : card.iconKind
                    stroke: card.selected && !card.locked ? theme.accent : theme.muted
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    Layout.fillWidth: true
                    text: card.label
                    color: card.locked ? theme.muted : theme.text
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                Text {
                    visible: card.detail !== ""
                    Layout.fillWidth: true
                    text: card.detail
                    color: theme.faint
                    font.pixelSize: 11
                    elide: Text.ElideRight
                }
            }

            Rectangle {
                Layout.preferredWidth: 16
                Layout.preferredHeight: 16
                radius: 8
                color: card.statusChecked
                    ? (card.statusOk ? theme.okSoft : theme.dangerSoft)
                    : (card.selected && !card.locked ? theme.accent : "transparent")
                border.width: card.statusChecked || (card.selected && !card.locked) ? 0 : 1
                border.color: theme.border

                Behavior on color { ColorAnimation { duration: root.durFast } }

                Text {
                    anchors.centerIn: parent
                    visible: card.statusChecked
                    text: card.statusOk ? "\u2713" : "\u2717"
                    color: card.statusOk ? theme.ok : theme.danger
                    font.pixelSize: 10
                    font.weight: Font.Bold
                }

                Rectangle {
                    visible: !card.statusChecked && card.selected && !card.locked
                    anchors.centerIn: parent
                    width: 6
                    height: 6
                    radius: 3
                    color: theme.knob
                }
            }
        }

        MouseArea {
            id: cardPressMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: card.locked ? Qt.ForbiddenCursor : Qt.PointingHandCursor
            onClicked: if (!card.locked) card.clicked()
            onEntered: card.hovered = true
            onExited: card.hovered = false
        }
    }

    component SectionTitle: Column {
        property string title: ""
        property string subtitle: ""
        spacing: 4
        Text {
            text: parent.title
            color: theme.faint
            font.pixelSize: 11
            font.weight: Font.DemiBold
            font.letterSpacing: 1.2
        }
        Text {
            visible: parent.subtitle !== ""
            text: parent.subtitle
            color: theme.faint
            font.pixelSize: 11
        }
    }

    component FooterLink: Item {
        id: link
        property string label: ""
        signal clicked()

        implicitWidth: linkText.implicitWidth
        implicitHeight: linkText.implicitHeight

        Text {
            id: linkText
            text: link.label
            color: linkMouse.containsMouse ? theme.text : theme.muted
            font.pixelSize: 11
            font.underline: linkMouse.containsMouse
        }

        MouseArea {
            id: linkMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: link.clicked()
        }
    }

    component HubButton: Rectangle {
        id: button
        property string label: ""
        property bool secondary: false
        property bool compact: false
        property bool clickable: true
        signal clicked()

        opacity: button.clickable ? 1.0 : 0.55

        implicitWidth: compact
            ? Math.max(52, buttonText.implicitWidth + 16)
            : Math.max(118, buttonText.implicitWidth + 30)
        implicitHeight: compact ? 26 : 34
        radius: compact ? 8 : 9
        color: buttonMouse.containsMouse
            ? (secondary ? theme.panel3 : theme.accentHover)
            : (secondary ? theme.panel2 : theme.accent)
        border.width: 1
        border.color: secondary ? theme.border : theme.accentBorder
        scale: buttonMouse.pressed && button.clickable ? 0.96 : 1.0

        Behavior on color { ColorAnimation { duration: root.durFast } }
        Behavior on border.color { ColorAnimation { duration: root.durFast } }
        Behavior on scale { NumberAnimation { duration: root.durFast; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: root.durFast } }

        Text {
            id: buttonText
            anchors.centerIn: parent
            text: button.label
            color: button.secondary ? theme.text : "#ffffff"
            font.pixelSize: button.compact ? 10 : 12
            font.weight: Font.DemiBold
        }

        MouseArea {
            id: buttonMouse
            anchors.fill: parent
            hoverEnabled: button.clickable
            enabled: button.clickable
            cursorShape: Qt.PointingHandCursor
            onClicked: button.clicked()
        }
    }

    component ConfigInput: Rectangle {
        id: inputBox
        property string value: ""
        property alias editText: field.text
        property bool secret: false
        property bool revealed: false
        property bool live: false
        signal saved(string value)

        implicitHeight: 34
        height: 34
        radius: 9
        color: field.activeFocus ? theme.panel2 : theme.panel
        border.width: 1
        border.color: field.activeFocus ? theme.accentBorder : theme.borderSoft

        Behavior on color { ColorAnimation { duration: root.durFast } }
        Behavior on border.color { ColorAnimation { duration: root.durFast } }

        TextInput {
            id: field
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: inputBox.secret ? 54 : 12
            verticalAlignment: TextInput.AlignVCenter
            color: theme.text
            selectionColor: theme.accent
            selectedTextColor: "#ffffff"
            font.pixelSize: 12
            echoMode: inputBox.secret && !inputBox.revealed ? TextInput.Password : TextInput.Normal
            selectByMouse: true
            clip: true
            onTextChanged: if (inputBox.live) inputBox.saved(text)
            onEditingFinished: if (!inputBox.live) inputBox.saved(text)
        }

        Component.onCompleted: field.text = inputBox.value

        onValueChanged: {
            if (field.text !== inputBox.value) {
                field.text = inputBox.value
            }
        }

        Rectangle {
            visible: inputBox.secret
            width: 42
            height: 24
            radius: 6
            anchors.right: parent.right
            anchors.rightMargin: 5
            anchors.verticalCenter: parent.verticalCenter
            color: revealMouse.containsMouse ? theme.panel3 : theme.panel2
            border.width: 1
            border.color: theme.borderSoft

            Behavior on color { ColorAnimation { duration: root.durFast } }

            Text {
                anchors.centerIn: parent
                text: inputBox.revealed ? "hide" : "show"
                color: theme.muted
                font.pixelSize: 10
                font.weight: Font.DemiBold
            }

            MouseArea {
                id: revealMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: inputBox.revealed = !inputBox.revealed
            }
        }
    }

    component NumericSlider: Item {
        id: sliderBox
        property string value: "0"
        property real from: 0
        property real to: 10
        property bool integer: false
        signal saved(string value)

        implicitWidth: 360
        implicitHeight: 34

        function numericValue() {
            const parsed = Number(sliderBox.value)
            if (isNaN(parsed)) {
                return sliderBox.from
            }
            return Math.max(sliderBox.from, Math.min(sliderBox.to, parsed))
        }

        function format(value) {
            return sliderBox.integer ? String(Math.round(value)) : Number(value).toFixed(2)
        }

        RowLayout {
            anchors.fill: parent
            spacing: 12

            Slider {
                id: control
                Layout.fillWidth: true
                from: sliderBox.from
                to: sliderBox.to
                value: sliderBox.numericValue()
                stepSize: sliderBox.integer ? 1 : 0.01
                snapMode: Slider.SnapOnRelease
                onMoved: sliderBox.saved(sliderBox.format(value))

                background: Rectangle {
                    x: control.leftPadding
                    y: control.topPadding + control.availableHeight / 2 - height / 2
                    width: control.availableWidth
                    height: 6
                    radius: 3
                    color: theme.panel3
                    border.width: 1
                    border.color: theme.borderSoft

                    Rectangle {
                        width: control.visualPosition * parent.width
                        height: parent.height
                        radius: 3
                        color: theme.accent
                    }
                }

                handle: Rectangle {
                    x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
                    y: control.topPadding + control.availableHeight / 2 - height / 2
                    width: 16
                    height: 16
                    radius: 8
                    color: theme.knob
                    border.width: 2
                    border.color: control.pressed ? theme.accentHover : theme.accent
                    scale: control.pressed ? 1.18 : 1.0

                    Behavior on scale { NumberAnimation { duration: root.durFast; easing.type: Easing.OutCubic } }
                    Behavior on border.color { ColorAnimation { duration: root.durFast } }
                }
            }

            ConfigInput {
                Layout.preferredWidth: 74
                Layout.preferredHeight: 34
                value: sliderBox.format(control.value)
                onSaved: function(value) { sliderBox.saved(value) }
            }
        }
    }

    component ToggleSwitch: Item {
        id: toggle
        property bool checked: false
        signal toggled(bool value)

        width: 40
        height: 22

        Rectangle {
            anchors.fill: parent
            radius: 11
            color: toggle.checked ? theme.accent : theme.panel3
            border.width: toggle.checked ? 0 : 1
            border.color: theme.border

            Behavior on color { ColorAnimation { duration: root.durFast } }
        }

        Rectangle {
            width: 18
            height: 18
            radius: 9
            y: 2
            x: toggle.checked ? 20 : 2
            color: theme.knob
            Behavior on x { NumberAnimation { duration: root.durFast; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: toggle.toggled(!toggle.checked)
        }
    }

    component ChoicePill: Rectangle {
        id: pill
        property string label: ""
        property bool selected: false
        signal clicked()

        implicitWidth: Math.max(66, pillText.implicitWidth + 22)
        height: 32
        radius: 16
        color: selected ? theme.accentSoft : (pillMouse.containsMouse ? theme.hover : theme.panel)
        border.width: 1
        border.color: selected ? theme.accentBorder : (pillMouse.containsMouse ? theme.border : theme.borderSoft)
        scale: pillMouse.pressed ? 0.95 : 1.0

        Behavior on color { ColorAnimation { duration: root.durFast } }
        Behavior on border.color { ColorAnimation { duration: root.durFast } }
        Behavior on scale { NumberAnimation { duration: root.durFast; easing.type: Easing.OutCubic } }

        Text {
            id: pillText
            anchors.centerIn: parent
            text: pill.label
            color: pill.selected ? theme.text : theme.muted
            font.pixelSize: 12
            font.weight: pill.selected ? Font.DemiBold : Font.Medium
            elide: Text.ElideRight

            Behavior on color { ColorAnimation { duration: root.durFast } }
        }

        MouseArea {
            id: pillMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: pill.clicked()
        }
    }

    component BrawlerPickTile: Rectangle {
        id: pickTile
        property string name: ""
        property string iconSource: ""
        property bool selected: false
        signal clicked()

        width: 92
        height: 96
        radius: 12
        color: selected ? theme.accentSoft : (pickMouse.containsMouse ? theme.hover : theme.panel)
        border.width: 1
        border.color: selected ? theme.accentBorder : theme.borderSoft
        scale: pickMouse.pressed ? 0.96 : (pickMouse.containsMouse ? 1.03 : 1.0)

        Behavior on color { ColorAnimation { duration: root.durFast } }
        Behavior on border.color { ColorAnimation { duration: root.durFast } }
        Behavior on scale { NumberAnimation { duration: root.durFast; easing.type: Easing.OutCubic } }

        Column {
            anchors.centerIn: parent
            spacing: 6
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 44
                height: 44
                radius: 8
                color: theme.panel2
                border.width: 1
                border.color: theme.borderSoft
                clip: true
                Image {
                    anchors.fill: parent
                    anchors.margins: 4
                    source: pickTile.iconSource
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    visible: pickTile.iconSource !== ""
                }
                Text {
                    anchors.centerIn: parent
                    text: pickTile.name ? pickTile.name.charAt(0).toUpperCase() : "?"
                    color: theme.faint
                    font.pixelSize: 16
                    font.weight: Font.Bold
                    visible: pickTile.iconSource === ""
                }
            }
            Text {
                width: 84
                anchors.horizontalCenter: parent.horizontalCenter
                text: pickTile.name
                color: pickTile.selected ? theme.text : theme.muted
                font.pixelSize: 10
                font.weight: pickTile.selected ? Font.DemiBold : Font.Medium
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
            }
        }

        MouseArea {
            id: pickMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: pickTile.clicked()
        }
    }

    component FieldRow: Rectangle {
        id: row
        property string label: ""
        property string hint: ""
        property bool pinnedInSettingsSearch: false
        default property alias content: slot.data

        readonly property string panelTitle: {
            var item = row.parent
            if (item && item.parent && item.parent.title !== undefined) {
                return String(item.parent.title)
            }
            return ""
        }

        readonly property bool filterMatch: {
            if (root.activeTab !== "Settings" || row.pinnedInSettingsSearch) {
                return true
            }
            var query = root.settingsFilter.trim().toLowerCase()
            if (query === "") {
                return true
            }
            var panel = row.panelTitle.toLowerCase()
            return row.label.toLowerCase().indexOf(query) >= 0
                    || row.hint.toLowerCase().indexOf(query) >= 0
                    || (panel !== "" && panel.indexOf(query) >= 0)
        }
        visible: filterMatch

        readonly property bool hasHint: row.hint !== ""
        Layout.fillWidth: true
        implicitHeight: Math.max(hasHint ? 68 : 52, slot.implicitHeight + (hasHint ? 34 : 18))

        radius: 10
        color: theme.panel2
        border.width: 1
        border.color: theme.borderSoft

        Text {
            id: labelText
            width: 164
            anchors.left: parent.left
            anchors.leftMargin: 14
            anchors.top: row.hasHint ? parent.top : undefined
            anchors.topMargin: row.hasHint ? 12 : undefined
            anchors.verticalCenter: row.hasHint ? undefined : parent.verticalCenter
            text: row.label
            color: theme.text
            font.pixelSize: 12
            font.weight: Font.DemiBold
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }

        Text {
            visible: hasHint
            anchors.left: labelText.left
            anchors.right: labelText.right
            anchors.top: labelText.bottom
            anchors.topMargin: 2
            text: row.hint
            color: theme.faint
            font.pixelSize: 10
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }

        Item {
            id: slot
            anchors.left: parent.left
            anchors.leftMargin: 190
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            implicitHeight: children.length ? children[0].implicitHeight : 34
            height: implicitHeight
        }
    }

    component CenterRow: Item {
        id: centerRow
        default property alias content: row.data
        Layout.fillWidth: true
        width: parent ? parent.width : row.implicitWidth
        height: row.implicitHeight
        implicitHeight: row.implicitHeight

        Row {
            id: row
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
        }
    }

    component ActionRow: Item {
        id: actionRow
        default property alias content: actionRowInner.data
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignHCenter
        Layout.topMargin: 18
        Layout.bottomMargin: 8
        width: parent ? parent.width : actionRowInner.implicitWidth
        implicitHeight: actionRowInner.implicitHeight + 20

        Row {
            id: actionRowInner
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 10
            spacing: 10
        }
    }

    component FormPanel: Rectangle {
        id: panel
        property string title: ""
        property string tutorialId: ""
        default property alias content: body.data

        Layout.fillWidth: true
        implicitHeight: body.implicitHeight + 32
        radius: 14
        color: theme.panel
        border.width: 1
        border.color: theme.borderSoft

        Rectangle {
            anchors.top: parent.top
            anchors.topMargin: 1
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width - parent.radius * 2
            height: 1
            color: theme.glassHighlight
        }

        readonly property bool settingsPanelVisible: {
            if (root.activeTab !== "Settings" || !root.settingsFilter.trim()) {
                return true
            }
            var query = root.settingsFilter.trim().toLowerCase()
            if (panel.title.toLowerCase().indexOf(query) >= 0) {
                return true
            }
            return body.implicitHeight > 52
        }
        visible: settingsPanelVisible

        ColumnLayout {
            id: body
            x: 16
            y: 16
            width: parent.width - 32
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                SectionTitle {
                    Layout.fillWidth: true
                    title: panel.title
                }
                TutorialHelpButton {
                    visible: panel.tutorialId !== ""
                    tutorialId: panel.tutorialId
                }
            }
        }
    }

    component TabPage: ScrollView {
        id: page
        default property alias content: pageBody.data
        clip: true
        anchors.fill: parent
        contentWidth: availableWidth
        contentHeight: pageBody.implicitHeight + pageBody.y + 32
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        onVisibleChanged: {
            if (visible) {
                pageEnterAnim.restart()
            }
        }

        ColumnLayout {
            id: pageBody
            width: Math.max(320, page.availableWidth - 24)
            x: Math.max(12, (page.availableWidth - width) / 2)
            y: 20
            spacing: 12
            transform: Translate { id: pageShift; y: 0 }

            ParallelAnimation {
                id: pageEnterAnim
                NumberAnimation { target: pageBody; property: "opacity"; from: 0; to: 1; duration: root.durMed; easing.type: Easing.OutCubic }
                NumberAnimation { target: pageShift; property: "y"; from: 14; to: 0; duration: root.durMed; easing.type: Easing.OutCubic }
            }
        }
    }

    component TutorialHelpButton: Rectangle {
        property string tutorialId: ""

        width: 28
        height: 28
        radius: 14
        color: helpMouse.containsMouse ? theme.panel3 : theme.panel2
        border.width: 1
        border.color: helpMouse.containsMouse ? theme.border : theme.borderSoft

        Behavior on color { ColorAnimation { duration: root.durFast } }
        Behavior on border.color { ColorAnimation { duration: root.durFast } }

        Text {
            anchors.centerIn: parent
            text: "?"
            color: theme.muted
            font.pixelSize: 13
            font.weight: Font.Bold
        }

        MouseArea {
            id: helpMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.openTutorial(tutorialId)
        }
    }

    component TutorialOverlay: Rectangle {
        anchors.fill: parent
        opacity: root.activeTutorialId !== "" ? 1 : 0
        visible: opacity > 0.01
        color: theme.scrim
        z: 99

        Behavior on opacity { NumberAnimation { duration: root.durFast } }

        readonly property var topic: root.tutorialTopic(root.activeTutorialId)

        MouseArea {
            anchors.fill: parent
            onClicked: root.closeTutorial()
        }

        Rectangle {
            anchors.centerIn: parent
            width: Math.min(520, root.width - 48)
            radius: 14
            color: theme.panel3
            border.width: 1
            border.color: theme.border
            implicitHeight: tutorialOverlayColumn.implicitHeight + 32
            scale: root.activeTutorialId !== "" ? 1 : 0.94

            Behavior on scale { NumberAnimation { duration: root.durMed; easing.type: Easing.OutCubic } }

            MouseArea {
                anchors.fill: parent
            }

            ColumnLayout {
                id: tutorialOverlayColumn
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12

                Text {
                    text: topic ? topic.title : "Guide"
                    color: theme.text
                    font.pixelSize: 16
                    font.weight: Font.Bold
                }
                Text {
                    Layout.fillWidth: true
                    text: topic ? topic.summary : ""
                    color: theme.muted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    lineHeight: 1.25
                }
                RowLayout {
                    spacing: 8
                    Item { Layout.fillWidth: true }
                    HubButton {
                        label: "Open full guide"
                        secondary: true
                        visible: !!(topic && topic.doc)
                        onClicked: {
                            root.openTutorialDoc(topic.doc)
                            root.closeTutorial()
                        }
                    }
                    HubButton {
                        label: "Close"
                        secondary: true
                        onClicked: root.closeTutorial()
                    }
                }
            }
        }
    }

    component IconButton: Rectangle {
        id: iconButton
        property string glyph: "×"
        signal clicked()

        width: 28
        height: 28
        radius: 8
        color: iconMouse.containsMouse ? theme.hover : "transparent"
        scale: iconMouse.pressed ? 0.92 : 1.0

        Behavior on color { ColorAnimation { duration: root.durFast } }
        Behavior on scale { NumberAnimation { duration: root.durFast; easing.type: Easing.OutCubic } }

        Text {
            anchors.centerIn: parent
            text: iconButton.glyph
            color: theme.muted
            font.pixelSize: iconButton.glyph === "−" ? 16 : 14
            font.weight: Font.Bold
        }

        MouseArea {
            id: iconMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: iconButton.clicked()
        }
    }

    component WindowResizeGrip: Item {
        anchors.fill: parent
        z: 200

        MouseArea {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 6
            cursorShape: Qt.SizeHorCursor
            onPressed: root.startSystemResize(Qt.LeftEdge)
        }
        MouseArea {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 6
            cursorShape: Qt.SizeHorCursor
            onPressed: root.startSystemResize(Qt.RightEdge)
        }
        MouseArea {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 6
            cursorShape: Qt.SizeVerCursor
            onPressed: root.startSystemResize(Qt.TopEdge)
        }
        MouseArea {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 6
            cursorShape: Qt.SizeVerCursor
            onPressed: root.startSystemResize(Qt.BottomEdge)
        }
        MouseArea {
            anchors.left: parent.left
            anchors.top: parent.top
            width: 10
            height: 10
            cursorShape: Qt.SizeFDiagCursor
            onPressed: root.startSystemResize(Qt.LeftEdge | Qt.TopEdge)
        }
        MouseArea {
            anchors.right: parent.right
            anchors.top: parent.top
            width: 10
            height: 10
            cursorShape: Qt.SizeBDiagCursor
            onPressed: root.startSystemResize(Qt.RightEdge | Qt.TopEdge)
        }
        MouseArea {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            width: 10
            height: 10
            cursorShape: Qt.SizeBDiagCursor
            onPressed: root.startSystemResize(Qt.LeftEdge | Qt.BottomEdge)
        }
        MouseArea {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            width: 10
            height: 10
            cursorShape: Qt.SizeFDiagCursor
            onPressed: root.startSystemResize(Qt.RightEdge | Qt.BottomEdge)
        }
    }

    component QueueRow: Rectangle {
        id: queueRow
        property var rowData: ({})
        property int rowIndex: -1
        property bool isDropTarget: root.queueDropTarget === rowIndex
        property bool isDragSource: root.queueDragSource === rowIndex
        property bool hovered: false

        height: 52
        radius: 10
        color: hovered ? theme.panel2 : theme.panel
        opacity: isDragSource ? 0.72 : 1.0
        border.width: isDropTarget || rowIndex === 0 ? 2 : 1
        border.color: isDropTarget ? theme.accent : (rowIndex === 0 ? theme.accentBorder : theme.borderSoft)

        Behavior on color { ColorAnimation { duration: root.durFast } }
        Behavior on border.color { ColorAnimation { duration: root.durFast } }
        Behavior on opacity { NumberAnimation { duration: root.durFast } }

        Rectangle {
            visible: rowIndex === 0
            width: 3
            radius: 2
            color: theme.accent
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.leftMargin: 4
            anchors.topMargin: 8
            anchors.bottomMargin: 8
        }

        DropArea {
            anchors.fill: parent
            onEntered: function(drag) {
                if (drag.hasText || drag.hasColor) {
                    root.queueDropTarget = queueRow.rowIndex
                }
            }
            onExited: {
                if (root.queueDropTarget === queueRow.rowIndex) {
                    root.queueDropTarget = -1
                }
            }
            onDropped: function(drop) {
                var from = parseInt(drop.text)
                if (isNaN(from)) {
                    from = root.queueDragSource
                }
                if (from >= 0 && from !== queueRow.rowIndex) {
                    root.runActionWithPayload("reorder-queue", {
                        fromIndex: from,
                        toIndex: queueRow.rowIndex
                    })
                }
                root.queueDragSource = -1
                root.queueDropTarget = -1
            }
        }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.NoButton
            onContainsMouseChanged: queueRow.hovered = containsMouse
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 8
            spacing: 8

            Rectangle {
                id: dragGrip
                Layout.preferredWidth: 22
                Layout.preferredHeight: 32
                radius: 6
                color: gripDrag.active ? theme.panel3 : "transparent"

                Text {
                    anchors.centerIn: parent
                    text: "\u2261"
                    color: theme.faint
                    font.pixelSize: 14
                    font.weight: Font.Bold
                }

                DragHandler {
                    id: gripDrag
                    target: dragGrip
                    onActiveChanged: {
                        if (active) {
                            root.queueDragSource = queueRow.rowIndex
                        } else if (root.queueDragSource === queueRow.rowIndex) {
                            root.queueDragSource = -1
                        }
                    }
                }

                Drag.active: gripDrag.active
                Drag.dragType: Drag.Automatic
                Drag.supportedActions: Qt.MoveAction
                Drag.mimeData: {
                    "text/plain": String(queueRow.rowIndex)
                }
            }

            Rectangle {
                Layout.preferredWidth: 32
                Layout.preferredHeight: 32
                radius: 6
                color: theme.panel2
                border.width: 1
                border.color: theme.borderSoft
                clip: true

                Image {
                    anchors.fill: parent
                    anchors.margins: 3
                    source: queueRow.rowData.icon || ""
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    visible: (queueRow.rowData.icon || "") !== ""
                }
                Text {
                    anchors.centerIn: parent
                    text: queueRow.rowData.brawler ? queueRow.rowData.brawler.charAt(0).toUpperCase() : "?"
                    color: theme.faint
                    font.pixelSize: 13
                    font.weight: Font.Bold
                    visible: (queueRow.rowData.icon || "") === ""
                }
            }

            Text {
                Layout.preferredWidth: 28
                text: "#" + (queueRow.rowIndex + 1)
                color: theme.faint
                font.pixelSize: 10
                font.weight: Font.DemiBold
            }

            Text {
                Layout.fillWidth: true
                text: queueRow.rowData.brawler || "?"
                color: theme.text
                font.pixelSize: 12
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            Rectangle {
                visible: queueRow.rowIndex === 0
                Layout.preferredHeight: 18
                Layout.preferredWidth: activePill.implicitWidth + 10
                radius: 9
                color: theme.accentSoft
                border.width: 1
                border.color: theme.accentBorder
                Text {
                    id: activePill
                    anchors.centerIn: parent
                    text: "ACTIVE"
                    color: theme.accent
                    font.pixelSize: 8
                    font.weight: Font.Bold
                }
            }

            Text {
                text: String(queueRow.rowData.trophies || 0) + " \u2192"
                color: theme.muted
                font.pixelSize: 11
            }

            Rectangle {
                id: targetButton
                Layout.preferredHeight: 22
                Layout.preferredWidth: targetLabel.implicitWidth + 12
                radius: 6
                color: targetMouse.containsMouse ? theme.panel3 : theme.panel2
                border.width: 1
                border.color: targetMouse.containsMouse ? theme.accentBorder : theme.borderSoft

                Text {
                    id: targetLabel
                    anchors.centerIn: parent
                    text: String(queueRow.rowData.target || "")
                    color: theme.accent
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }

                MouseArea {
                    id: targetMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: queueTargetPopup.open()
                }

                Popup {
                    id: queueTargetPopup
                    parent: Overlay.overlay
                    width: Math.max(targetPopupColumn.implicitWidth + 16, 180)
                    height: Math.max(targetPopupColumn.implicitHeight + 16, 48)
                    padding: 8
                    modal: true
                    focus: true
                    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

                    function repositionWithinOverlay() {
                        var overlay = Overlay.overlay
                        if (!overlay) {
                            return
                        }
                        var margin = 8
                        var belowPos = targetButton.mapToItem(overlay, 0, targetButton.height)
                        var abovePos = targetButton.mapToItem(overlay, 0, 0)
                        var buttonRightPos = targetButton.mapToItem(overlay, targetButton.width, 0)
                        var popupW = queueTargetPopup.width
                        var popupH = queueTargetPopup.height
                        var maxX = Math.max(margin, overlay.width - popupW - margin)
                        var maxY = Math.max(margin, overlay.height - popupH - margin)

                        var nextX = belowPos.x
                        if (nextX + popupW > overlay.width - margin) {
                            nextX = buttonRightPos.x - popupW
                        }
                        queueTargetPopup.x = Math.max(margin, Math.min(nextX, maxX))

                        var nextY = belowPos.y + 4
                        if (nextY + popupH > overlay.height - margin) {
                            nextY = abovePos.y - popupH - 4
                        }
                        queueTargetPopup.y = Math.max(margin, Math.min(nextY, maxY))
                    }

                    onOpened: repositionWithinOverlay()

                    background: Rectangle {
                        radius: 10
                        color: theme.panel3
                        border.width: 1
                        border.color: theme.borderSoft
                    }

                    Column {
                        id: targetPopupColumn
                        spacing: 8

                        Flow {
                            spacing: 6
                            width: Math.min(480, (Overlay.overlay ? Overlay.overlay.width : root.width) - 32)
                            Repeater {
                                model: root.trophyTargetPresets
                                delegate: ChoicePill {
                                    label: modelData
                                    selected: String(queueRow.rowData.target || "") === modelData
                                    onClicked: {
                                        root.runActionWithPayload("update-queue-item", {
                                            index: queueRow.rowIndex,
                                            push_until: parseInt(modelData)
                                        })
                                        queueTargetPopup.close()
                                    }
                                }
                            }
                        }

                        RowLayout {
                            width: parent.width
                            spacing: 6
                            ConfigInput {
                                Layout.fillWidth: true
                                id: queueTargetCustomInput
                                value: String(queueRow.rowData.target || "")
                                onSaved: function(value) {
                                    var target = root.parseTrophyTarget(value)
                                    if (target <= 0) {
                                        return
                                    }
                                    root.runActionWithPayload("update-queue-item", {
                                        index: queueRow.rowIndex,
                                        push_until: target
                                    })
                                    queueTargetPopup.close()
                                }
                            }
                            Text {
                                text: "Custom"
                                color: theme.faint
                                font.pixelSize: 10
                            }
                        }
                    }
                }
            }

            IconButton {
                glyph: "×"
                onClicked: root.runActionWithPayload("remove-from-queue", { index: queueRow.rowIndex })
            }
        }
    }

    component FarmPlanPage: Item {
        id: farmPage
        anchors.fill: parent

        onVisibleChanged: {
            if (visible) {
                farmEnterAnim.restart()
            }
        }

        ColumnLayout {
            id: farmPageBody
            anchors.fill: parent
            anchors.margins: 12
            spacing: 10
            transform: Translate { id: farmPageShift; y: 0 }

            ParallelAnimation {
                id: farmEnterAnim
                NumberAnimation { target: farmPageBody; property: "opacity"; from: 0; to: 1; duration: root.durMed; easing.type: Easing.OutCubic }
                NumberAnimation { target: farmPageShift; property: "y"; from: 14; to: 0; duration: root.durMed; easing.type: Easing.OutCubic }
            }

            Rectangle {
                Layout.fillWidth: true
                visible: !!(hubState.multiInstance && hubState.multiInstance.enabled)
                implicitHeight: farmInstanceColumn.implicitHeight + 20
                radius: 10
                color: theme.panel
                border.width: 1
                border.color: theme.borderSoft
                ColumnLayout {
                    id: farmInstanceColumn
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 8
                    Text {
                        text: "EDITING FARM PLAN FOR"
                        color: theme.text
                        font.pixelSize: 12
                        font.bold: true
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: (hubState.multiInstance && hubState.multiInstance.instances) ? hubState.multiInstance.instances : []
                            delegate: ChoicePill {
                                label: modelData.name
                                selected: String(hubState.multiInstance.editingInstanceId || "") === String(modelData.id)
                                onClicked: applyBridgeResult(hubBridge.setEditingInstance(modelData.id))
                            }
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: String(hubState.multiInstance.editingInstanceId || "") === String(hubState.multiInstance.defaultInstance || "default")
                        text: "Other instances have their own farm plans — switch instance above."
                        color: theme.faint
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: pushAllColumn.implicitHeight + 24
                radius: 10
                color: theme.panel
                border.width: 1
                border.color: theme.borderSoft

                ColumnLayout {
                    id: pushAllColumn
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            text: "PUSH ALL"
                            color: theme.text
                            font.pixelSize: 12
                            font.weight: Font.Bold
                        }
                        Item { Layout.fillWidth: true }
                        TutorialHelpButton { tutorialId: "farm-plan" }
                        HubButton {
                            label: "Tutorial"
                            secondary: true
                            compact: true
                            onClicked: root.openTutorial("farm-plan")
                        }
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: root.trophyTargetPresets
                            delegate: ChoicePill {
                                label: modelData
                                selected: root.pushAllTarget === modelData
                                onClicked: root.pushAllTarget = modelData
                            }
                        }
                    }
                    FieldRow {
                        label: "Custom target"
                        Layout.fillWidth: true
                        ConfigInput {
                            id: pushAllTargetInput
                            anchors.fill: parent
                            value: root.pushAllTarget
                            onSaved: function(value) { root.pushAllTarget = value }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        HubButton {
                            label: "Build Queue"
                            compact: true
                            enabled: !root.hubBusy
                            onClicked: {
                                var target = root.trophyTargetFromUi(pushAllTargetInput.editText, root.pushAllTarget)
                                if (target <= 0) {
                                    root.statusText = "Enter a valid trophy target."
                                    root.statusOk = false
                                    return
                                }
                                root.runActionWithPayload("build-push-all", { target: target })
                            }
                        }
                        HubButton { label: "Import"; secondary: true; compact: true; onClicked: importQueueDialog.open() }
                        HubButton {
                            label: "Export"
                            secondary: true
                            compact: true
                            onClicked: {
                                if (!(root.hubState.queue && root.hubState.queue.length)) {
                                    root.statusText = "Farm plan is empty."
                                    root.statusOk = false
                                    return
                                }
                                exportQueueDialog.open()
                            }
                        }
                        HubButton {
                            id: queueSortButton
                            label: "Sort"
                            secondary: true
                            compact: true
                            onClicked: {
                                if (!(root.hubState.queue && root.hubState.queue.length)) {
                                    root.statusText = "Farm plan is empty."
                                    root.statusOk = false
                                    return
                                }
                                queueSortPopup.open()
                            }
                        }
                        Popup {
                            id: queueSortPopup
                            parent: Overlay.overlay
                            width: Math.max(queueSortPopupColumn.implicitWidth + 16, 220)
                            height: Math.max(queueSortPopupColumn.implicitHeight + 16, 48)
                            padding: 8
                            modal: true
                            focus: true
                            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

                            function repositionWithinOverlay() {
                                var overlay = Overlay.overlay
                                if (!overlay) {
                                    return
                                }
                                var margin = 8
                                var belowPos = queueSortButton.mapToItem(overlay, 0, queueSortButton.height)
                                var abovePos = queueSortButton.mapToItem(overlay, 0, 0)
                                var buttonRightPos = queueSortButton.mapToItem(overlay, queueSortButton.width, 0)
                                var popupW = queueSortPopup.width
                                var popupH = queueSortPopup.height
                                var maxX = Math.max(margin, overlay.width - popupW - margin)
                                var maxY = Math.max(margin, overlay.height - popupH - margin)

                                var nextX = belowPos.x
                                if (nextX + popupW > overlay.width - margin) {
                                    nextX = buttonRightPos.x - popupW
                                }
                                queueSortPopup.x = Math.max(margin, Math.min(nextX, maxX))

                                var nextY = belowPos.y + 4
                                if (nextY + popupH > overlay.height - margin) {
                                    nextY = abovePos.y - popupH - 4
                                }
                                queueSortPopup.y = Math.max(margin, Math.min(nextY, maxY))
                            }

                            onOpened: repositionWithinOverlay()

                            background: Rectangle {
                                radius: 10
                                color: theme.panel3
                                border.width: 1
                                border.color: theme.borderSoft
                            }

                            Column {
                                id: queueSortPopupColumn
                                spacing: 8

                                Text {
                                    text: "Sort farm plan"
                                    color: theme.text
                                    font.pixelSize: 11
                                    font.weight: Font.Bold
                                }

                                Flow {
                                    spacing: 6
                                    width: Math.min(420, (Overlay.overlay ? Overlay.overlay.width : root.width) - 32)
                                    Repeater {
                                        model: root.queueSortOptions
                                        delegate: ChoicePill {
                                            label: modelData.label
                                            onClicked: {
                                                root.runActionWithPayload("sort-queue", { mode: modelData.id })
                                                queueSortPopup.close()
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        HubButton { label: "Clear"; secondary: true; compact: true; onClicked: root.runAction("clear-queue") }
                        Item { Layout.fillWidth: true }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 10
                color: theme.panel
                border.width: 1
                border.color: theme.borderSoft

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            text: "QUEUE"
                            color: theme.text
                            font.pixelSize: 12
                            font.weight: Font.Bold
                        }
                        Text {
                            text: ((root.hubState.queue || []).length) + " brawler" + (((root.hubState.queue || []).length) === 1 ? "" : "s")
                            color: theme.faint
                            font.pixelSize: 11
                        }
                        Item { Layout.fillWidth: true }
                        HubButton {
                            label: "Refresh"
                            secondary: true
                            compact: true
                            onClicked: root.reloadState()
                        }
                        HubButton {
                            label: "Add"
                            compact: true
                            onClicked: {
                                const options = (hubState.meta && hubState.meta.brawlerOptions) ? hubState.meta.brawlerOptions : []
                                root.pickerBrawler = options.length ? options[0].name : ""
                                root.pickerFilter = ""
                                root.showBrawlerPicker = true
                            }
                        }
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        ListView {
                            id: farmQueueList
                            anchors.fill: parent
                            spacing: 6
                            clip: true
                            model: root.hubState.queue || []
                            ScrollBar.vertical: ScrollBar {
                                policy: ScrollBar.AsNeeded
                            }
                            delegate: QueueRow {
                                width: farmQueueList.width
                                rowData: modelData
                                rowIndex: modelData.index
                            }
                            displaced: Transition {
                                NumberAnimation { properties: "x,y"; duration: root.durFast; easing.type: Easing.OutCubic }
                            }
                            add: Transition {
                                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: root.durMed; easing.type: Easing.OutCubic }
                                NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: root.durMed; easing.type: Easing.OutCubic }
                            }
                            remove: Transition {
                                NumberAnimation { property: "opacity"; to: 0; duration: root.durFast }
                                NumberAnimation { property: "scale"; to: 0.96; duration: root.durFast }
                            }
                        }

                        ColumnLayout {
                            anchors.centerIn: parent
                            spacing: 8
                            visible: !(root.hubState.queue && root.hubState.queue.length)
                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: "No brawlers in the farm plan yet"
                                color: theme.muted
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: "Build a queue from API trophies or add brawlers manually"
                                color: theme.faint
                                font.pixelSize: 11
                            }
                            HubButton {
                                Layout.alignment: Qt.AlignHCenter
                                label: "Add Brawler"
                                compact: true
                                onClicked: {
                                    const options = (hubState.meta && hubState.meta.brawlerOptions) ? hubState.meta.brawlerOptions : []
                                    root.pickerBrawler = options.length ? options[0].name : ""
                                    root.pickerFilter = ""
                                    root.showBrawlerPicker = true
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: theme.bg

        Canvas {
            id: backdropCanvas
            anchors.fill: parent
            antialiasing: true
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()

            function paintGlow(ctx, x, y, radius, glowColor) {
                const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius)
                gradient.addColorStop(0, String(glowColor))
                gradient.addColorStop(1, String(Qt.rgba(glowColor.r, glowColor.g, glowColor.b, 0)))
                ctx.fillStyle = gradient
                ctx.beginPath()
                ctx.arc(x, y, radius, 0, Math.PI * 2)
                ctx.fill()
            }

            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                const span = Math.max(width, height)
                ctx.globalAlpha = root.resolvedTheme === "light" ? 0.22 : 0.15
                paintGlow(ctx, width * 0.14, height * 0.08, span * 0.55, theme.glowA)
                paintGlow(ctx, width * 0.94, height * 0.92, span * 0.6, theme.glowB)
                paintGlow(ctx, width * 0.78, height * 0.16, span * 0.38, theme.glowC)
                ctx.globalAlpha = 1
            }

            NumberAnimation {
                id: backdropFade
                target: backdropCanvas
                property: "opacity"
                from: 0
                to: 1
                duration: root.durSlow
                easing.type: Easing.OutCubic
            }
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                color: theme.chrome
                border.width: 1
                border.color: theme.borderSoft

                MouseArea {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.right: titleWindowControls.left
                    onPressed: root.startSystemMove()
                }

                Row {
                    anchors.centerIn: parent
                    spacing: 9
                    Text {
                        text: "Pyla"
                        color: theme.text
                        font.pixelSize: 13
                        font.weight: Font.Bold
                    }
                    Text {
                        text: "\u00b7"
                        color: theme.faint
                        font.pixelSize: 13
                        font.weight: Font.Bold
                    }
                    Text {
                        text: settingsOnly ? "Pyla-RL Settings (bot running)" : "Pyla-RL Hub"
                        color: theme.muted
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                    }
                }

                Row {
                    id: titleWindowControls
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4
                    Rectangle {
                        id: themeToggleButton
                        width: 28
                        height: 28
                        radius: 8
                        color: themeToggleMouse.containsMouse ? theme.hover : "transparent"
                        scale: themeToggleMouse.pressed ? 0.92 : 1.0

                        Behavior on color { ColorAnimation { duration: root.durFast } }
                        Behavior on scale { NumberAnimation { duration: root.durFast; easing.type: Easing.OutCubic } }

                        ToolTip.visible: themeToggleMouse.containsMouse
                        ToolTip.delay: 500
                        ToolTip.text: "Theme: " + root.themeMode + " (click to switch)"

                        Text {
                            anchors.centerIn: parent
                            text: root.themeMode === "system" ? "\u25d1" : (root.resolvedTheme === "light" ? "\u2600" : "\u263e")
                            color: theme.muted
                            font.pixelSize: 13

                            Behavior on color { ColorAnimation { duration: root.durFast } }
                        }

                        MouseArea {
                            id: themeToggleMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.cycleThemeMode()
                        }
                    }
                    IconButton {
                        glyph: "−"
                        onClicked: root.showMinimized()
                    }
                    IconButton {
                        onClicked: root.closeHubWindow()
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: warningBanner.visible ? 34 : 0
                visible: warningBanner.visible
                color: theme.warnSoft
                border.width: 1
                border.color: theme.accentBorder

                Text {
                    id: warningBanner
                    anchors.fill: parent
                    anchors.margins: 8
                    visible: (latestVersion && latestVersion !== "" && latestVersion !== hubVersion) || correctZoom === false
                    text: {
                        var parts = []
                        if (latestVersion && latestVersion !== "" && latestVersion !== hubVersion) {
                            parts.push("Update available: v" + latestVersion)
                        }
                        if (correctZoom === false) {
                            parts.push("Display scaling is not 100% — bot may misclick")
                        }
                        return parts.join(" · ")
                    }
                    color: theme.accent
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                    verticalAlignment: Text.AlignVCenter
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 58
                color: theme.chrome
                border.width: 1
                border.color: theme.borderSoft

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 4
                    radius: 12
                    color: theme.panel
                    border.width: 1
                    border.color: theme.border
                    clip: true

                    Rectangle {
                        anchors.top: parent.top
                        anchors.topMargin: 1
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: parent.width - parent.radius * 2
                        height: 1
                        color: theme.glassHighlight
                    }

                    ScrollView {
                        anchors.fill: parent
                        anchors.margins: 4
                        contentWidth: navHolder.width
                        contentHeight: navHolder.height
                        ScrollBar.vertical.policy: ScrollBar.AlwaysOff
                        ScrollBar.horizontal.policy: ScrollBar.AsNeeded

                        Item {
                            id: navHolder
                            width: navRow.implicitWidth
                            height: navRow.implicitHeight

                            function syncIndicator() {
                                for (var i = 0; i < navRow.children.length; i++) {
                                    var child = navRow.children[i]
                                    if (child && child.tabId !== undefined && child.tabId === root.activeTab) {
                                        navIndicator.x = child.x
                                        navIndicator.width = child.width
                                        return
                                    }
                                }
                            }

                            onWidthChanged: Qt.callLater(syncIndicator)
                            Component.onCompleted: Qt.callLater(syncIndicator)

                            Connections {
                                target: root
                                function onActiveTabChanged() { Qt.callLater(navHolder.syncIndicator) }
                            }

                            Rectangle {
                                id: navIndicator
                                y: 0
                                width: 0
                                height: navRow.implicitHeight
                                radius: 9
                                visible: width > 0
                                color: theme.panel3
                                border.width: 1
                                border.color: theme.border

                                Behavior on x { NumberAnimation { duration: root.durMed; easing.type: Easing.OutCubic } }
                                Behavior on width { NumberAnimation { duration: root.durMed; easing.type: Easing.OutCubic } }

                                Rectangle {
                                    anchors.bottom: parent.bottom
                                    anchors.bottomMargin: 3
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: 16
                                    height: 2
                                    radius: 1
                                    color: theme.accent
                                }
                            }

                            Row {
                                id: navRow
                                spacing: 2
                                Repeater {
                                    model: root.navItems
                                    delegate: NavButton {
                                        tabId: modelData
                                        label: root.navLabel(modelData)
                                        onClicked: root.activeTab = modelData
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                TabPage {
                    visible: root.activeTab === "Instances"

                    FormPanel {
                        title: "MULTI-INSTANCE MODE"
                        tutorialId: "multi-instance"
                        Text {
                            Layout.fillWidth: true
                            text: "Run multiple LDPlayer or MuMu bots in parallel. Discord/Telegram control uses one bot on those tabs; match alerts can be set per instance below."
                            color: theme.faint
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        FieldRow {
                            label: "Enable Multi-Instance"
                            CenterRow {
                                ToggleSwitch {
                                    checked: !!(hubState.multiInstance && hubState.multiInstance.enabled)
                                    onToggled: function(value) {
                                        const result = applyBridgeResult(hubBridge.setMultiInstanceEnabled(value))
                                        if (value && result.ok && hubState.multiInstance && !hubState.multiInstance.setupWizardDismissed) {
                                            root.showMultiInstanceSetup = true
                                            applyBridgeResult(hubBridge.listAvailableEmulators())
                                        }
                                    }
                                }
                            }
                        }
                        FieldRow {
                            label: "Auto-Restart Crashed"
                            visible: !!(hubState.multiInstance && hubState.multiInstance.enabled)
                            CenterRow {
                                ToggleSwitch {
                                    checked: !!(hubState.multiInstance && hubState.multiInstance.autoRestartCrashed)
                                    onToggled: function(value) {
                                        applyBridgeResult(hubBridge.setAutoRestartCrashed(value))
                                    }
                                }
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: !(hubState.multiInstance && hubState.multiInstance.enabled)
                            text: "Single-instance mode uses START on Overview. Enable this to run multiple bots from this tab."
                            color: theme.faint
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: !!(hubState.multiInstance && hubState.multiInstance.enabled)
                            text: "Multi-instance is active. Use Start all ready below instead of Overview START."
                            color: theme.ok
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        ActionRow {
                            HubButton { label: "Scan Emulators"; secondary: true; visible: !!(hubState.multiInstance && hubState.multiInstance.enabled); onClicked: applyBridgeResult(hubBridge.listAvailableEmulators()) }
                            HubButton { label: "Refresh"; secondary: true; onClicked: applyBridgeResult(hubBridge.refreshInstances()) }
                            HubButton { label: "Start All Ready"; visible: !!(hubState.multiInstance && hubState.multiInstance.enabled); onClicked: applyBridgeResult(hubBridge.startAllReadyInstances()) }
                            HubButton { label: "Stop All"; secondary: true; visible: !!(hubState.multiInstance && hubState.multiInstance.enabled); onClicked: applyBridgeResult(hubBridge.stopAllInstances()) }
                            HubButton { label: "Align Windows"; secondary: true; visible: !!(hubState.multiInstance && hubState.multiInstance.enabled); onClicked: applyBridgeResult(hubBridge.alignWindows()) }
                        }
                        ActionRow {
                            visible: root.pendingInstanceActionLabel !== ""
                            HubButton {
                                label: root.pendingInstanceActionLabel
                                onClicked: root.runPendingInstanceAction()
                            }
                        }
                    }

                    FormPanel {
                        title: "QUICK SETUP"
                        visible: !!(hubState.multiInstance && hubState.multiInstance.enabled) && root.showMultiInstanceSetup && !hubState.multiInstance.setupWizardDismissed
                        Text {
                            Layout.fillWidth: true
                            text: "Step 1: Default instance created from your current settings.\nStep 2: Scan detected emulators.\nStep 3: Quick add unassigned emulators (copies Default farm plan)."
                            color: theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            Layout.fillWidth: true
                            text: "Unassigned emulators: " + String((hubState.multiInstance.unassignedEmulators || []).length)
                            color: theme.faint
                            font.pixelSize: 11
                        }
                        ActionRow {
                            HubButton { label: "Quick Add All Unassigned"; onClicked: root.quickAddUnassignedInstances() }
                            HubButton { label: "Done"; secondary: true; onClicked: root.dismissMultiInstanceSetup() }
                        }
                    }

                    FormPanel {
                        title: "ADD INSTANCE"
                        visible: !!(hubState.multiInstance && hubState.multiInstance.enabled)
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            ActionRow {
                                HubButton { label: "Quick Add All Unassigned"; onClicked: root.quickAddUnassignedInstances() }
                                HubButton { label: showAddInstanceForm ? "Hide Manual Form" : "Manual Add"; secondary: true; onClicked: showAddInstanceForm = !showAddInstanceForm }
                            }
                            Repeater {
                                model: (hubState.multiInstance && hubState.multiInstance.unassignedEmulators) ? hubState.multiInstance.unassignedEmulators : []
                                delegate: RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.display_emulator + " · " + modelData.name + " · port " + modelData.adb_port
                                        color: theme.muted
                                        font.pixelSize: 11
                                        wrapMode: Text.WordWrap
                                    }
                                    HubButton {
                                        label: "Use"
                                        secondary: true
                                        compact: true
                                        onClicked: {
                                            root.pickDetectedEmulator(modelData)
                                            root.showAddInstanceForm = true
                                        }
                                    }
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                visible: showAddInstanceForm
                                FieldRow {
                                    label: "Detected Emulator"
                                    visible: root.instanceFormEmulatorName !== ""
                                    Text {
                                        text: root.instanceFormEmulatorName + " · port " + root.instanceFormPort
                                        color: theme.muted
                                        font.pixelSize: 11
                                    }
                                }
                                FieldRow {
                                    label: "Instance ID"
                                    ConfigInput { anchors.fill: parent; live: true; value: root.instanceFormId; onSaved: function(value) { root.instanceFormId = value } }
                                }
                                FieldRow {
                                    label: "Display Name"
                                    ConfigInput { anchors.fill: parent; live: true; value: root.instanceFormName; onSaved: function(value) { root.instanceFormName = value } }
                                }
                                FieldRow {
                                    label: "Player Tag"
                                    ConfigInput { anchors.fill: parent; live: true; value: root.instanceFormPlayerTag; onSaved: function(value) { root.instanceFormPlayerTag = value } }
                                }
                                HubButton {
                                    label: showAdvancedInstanceForm ? "Hide Advanced" : "Advanced"
                                    secondary: true
                                    onClicked: showAdvancedInstanceForm = !showAdvancedInstanceForm
                                }
                                ColumnLayout {
                                    visible: showAdvancedInstanceForm
                                    spacing: 8
                                    FieldRow {
                                        label: "Emulator"
                                        RowLayout {
                                            anchors.fill: parent
                                            spacing: 8
                                            HubButton { label: "LDPlayer"; secondary: root.instanceFormEmulator !== "ldplayer"; onClicked: root.setInstanceFormEmulator("ldplayer") }
                                            HubButton { label: "MuMu"; secondary: root.instanceFormEmulator !== "mumu"; onClicked: root.setInstanceFormEmulator("mumu") }
                                        }
                                    }
                                    FieldRow {
                                        label: "ADB Port"
                                        ConfigInput { anchors.fill: parent; live: true; value: root.instanceFormPort; onSaved: function(value) { root.instanceFormPort = value } }
                                    }
                                }
                                ActionRow {
                                    HubButton { label: "Save Instance"; onClicked: root.saveNewInstance() }
                                }
                            }
                        }
                    }

                    FormPanel {
                        title: "CONFIGURED INSTANCES"
                        visible: !!(hubState.multiInstance && hubState.multiInstance.enabled)
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            Repeater {
                                model: (hubState.multiInstance && hubState.multiInstance.instances) ? hubState.multiInstance.instances : []
                                delegate: Rectangle {
                                    Layout.fillWidth: true
                                    radius: 10
                                    color: theme.panel
                                    border.color: theme.border
                                    implicitHeight: instanceColumn.implicitHeight + 20
                                    ColumnLayout {
                                        id: instanceColumn
                                        anchors.fill: parent
                                        anchors.margins: 10
                                        spacing: 6
                                        RowLayout {
                                            spacing: 8
                                            Rectangle {
                                                width: 10
                                                height: 10
                                                radius: 5
                                                color: root.healthColor((modelData.health && modelData.health.status) ? modelData.health.status : "good")
                                                ToolTip.visible: healthTipHover.containsMouse
                                                ToolTip.text: (modelData.health && modelData.health.message) ? modelData.health.message : "Health unknown"
                                                MouseArea {
                                                    id: healthTipHover
                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                }
                                            }
                                            Text {
                                                Layout.fillWidth: true
                                                text: modelData.name + " (" + modelData.id + ")"
                                                color: theme.text
                                                font.pixelSize: 13
                                                font.bold: true
                                            }
                                        }
                                        Text {
                                            text: root.readinessLabel(modelData)
                                            color: root.readinessColor((modelData.readiness && modelData.readiness.status) ? modelData.readiness.status : "")
                                            font.pixelSize: 11
                                            font.bold: true
                                        }
                                        Text {
                                            text: String(modelData.emulator || "?").toUpperCase()
                                                + (modelData.emulator_instance_name ? (" · " + modelData.emulator_instance_name) : "")
                                                + " · port " + modelData.emulator_port
                                                + " · " + String(modelData.queue_count || 0) + " brawler(s)"
                                                + (modelData.running ? " · RUNNING" : " · stopped")
                                                + (modelData.brawler ? " · " + modelData.brawler : "")
                                                + (modelData.player_tag ? (" · " + modelData.player_tag) : "")
                                            color: theme.muted
                                            font.pixelSize: 11
                                            wrapMode: Text.WordWrap
                                            Layout.fillWidth: true
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 4
                                            visible: !!(modelData.health && modelData.health.recent_recoveries && modelData.health.recent_recoveries.length)
                                            Text {
                                                text: "Recent recoveries"
                                                color: theme.faint
                                                font.pixelSize: 10
                                            }
                                            Repeater {
                                                model: (modelData.health && modelData.health.recent_recoveries) ? modelData.health.recent_recoveries.slice(0, 5) : []
                                                delegate: Text {
                                                    Layout.fillWidth: true
                                                    text: String(modelData.event_type || "?") + ": " + String(modelData.detail || "")
                                                    color: theme.muted
                                                    font.pixelSize: 10
                                                    wrapMode: Text.WordWrap
                                                }
                                            }
                                        }
                                        RowLayout {
                                            spacing: 8
                                            HubButton { label: "Start"; visible: !modelData.running; onClicked: applyBridgeResult(hubBridge.startInstance(modelData.id)) }
                                            HubButton { label: "Stop"; secondary: true; visible: !!modelData.running; onClicked: applyBridgeResult(hubBridge.stopInstance(modelData.id)) }
                                            HubButton { label: "Restart"; secondary: true; visible: !!modelData.running; onClicked: applyBridgeResult(hubBridge.restartInstance(modelData.id)) }
                                            HubButton { label: "Edit Farm Plan"; secondary: true; onClicked: root.editInstanceFarmPlan(modelData.id) }
                                            HubButton {
                                                label: "Copy Default Plan"
                                                secondary: true
                                                visible: !!(modelData.readiness && modelData.readiness.status === "needs_farm_plan" && modelData.readiness.can_copy_default)
                                                onClicked: root.copyInstanceFarmPlan(modelData.id)
                                            }
                                            HubButton {
                                                label: "Delete"
                                                secondary: true
                                                visible: modelData.id !== String((hubState.multiInstance && hubState.multiInstance.defaultInstance) || "default")
                                                onClicked: applyBridgeResult(hubBridge.deleteInstanceProfile(modelData.id))
                                            }
                                        }
                                        Text {
                                            text: "Match notifications (optional)"
                                            color: theme.faint
                                            font.pixelSize: 10
                                            font.bold: true
                                        }
                                        FieldRow {
                                            label: "Webhook URL"
                                            ConfigInput {
                                                anchors.fill: parent
                                                live: true
                                                value: (modelData.local_settings && modelData.local_settings.discord_webhook_url) ? modelData.local_settings.discord_webhook_url : ""
                                                onSaved: function(value) {
                                                    const local = Object.assign({}, modelData.local_settings || {})
                                                    local.discord_webhook_url = value
                                                    root.saveInstanceNotifications(modelData.id, local)
                                                }
                                            }
                                        }
                                        FieldRow {
                                            label: "Ping Discord ID"
                                            ConfigInput {
                                                anchors.fill: parent
                                                live: true
                                                value: (modelData.local_settings && modelData.local_settings.discord_id) ? modelData.local_settings.discord_id : ""
                                                onSaved: function(value) {
                                                    const local = Object.assign({}, modelData.local_settings || {})
                                                    local.discord_id = value
                                                    root.saveInstanceNotifications(modelData.id, local)
                                                }
                                            }
                                        }
                                        ActionRow {
                                            HubButton {
                                                label: "Test Webhook"
                                                secondary: true
                                                onClicked: applyBridgeResult(hubBridge.testInstanceWebhook(modelData.id))
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                TabPage {
                    visible: root.activeTab === "Overview"

                    FormPanel {
                        visible: root.unofficialCopy
                        title: "UNOFFICIAL COPY"
                        Text {
                            Layout.fillWidth: true
                            text: (hubBrand ? hubBrand.freeNotice : "Pyla-RL is free.") + " Download only from GitHub or Pyla Discord."
                            color: theme.accent
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                        }
                        ActionRow {
                            HubButton { label: "Official GitHub"; secondary: true; onClicked: hubBridge.openOfficialRepo() }
                            HubButton { label: "Pyla Discord"; secondary: true; onClicked: hubBridge.openDiscord() }
                        }
                    }

                    FormPanel {
                        title: "PRE-FLIGHT CHECKS"
                        tutorialId: "overview"
                        Text {
                            Layout.fillWidth: true
                            text: "Verify emulator and ADB before START. Use 1920x1080 and 100% Windows scaling."
                            color: theme.faint
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        RowLayout {
                            spacing: 10
                            HubButton { label: "Run Checks"; secondary: true; onClicked: root.runAction("preflight-check") }
                            HubButton { label: "Test Connection"; secondary: true; onClicked: root.runAction("test-emulator") }
                            HubButton { label: "Recovery Log"; secondary: true; onClicked: root.runAction("read-recovery-log") }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            visible: root.preflightChecks && root.preflightChecks.length > 0
                            Repeater {
                                model: root.preflightChecks
                                delegate: RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Rectangle {
                                        width: 8
                                        height: 8
                                        radius: 4
                                        color: modelData.ok ? theme.ok : (modelData.severity === "required" ? theme.danger : theme.accent)
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.label + " — " + modelData.detail
                                        color: theme.muted
                                        font.pixelSize: 11
                                        wrapMode: Text.WordWrap
                                    }
                                    HubButton {
                                        visible: !!(modelData.fix && modelData.fix.action)
                                        label: modelData.fix ? modelData.fix.label : "Fix"
                                        secondary: true
                                        onClicked: applyBridgeResult(hubBridge.runPreflightFix(modelData.fix.action))
                                    }
                                }
                            }
                        }
                        ScrollView {
                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.min(120, Math.max(40, statusOverviewText.contentHeight + 12))
                            visible: root.statusText !== "" && root.activeTab === "Overview"
                            clip: true
                            contentWidth: availableWidth
                            contentHeight: statusOverviewText.contentHeight
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                            Text {
                                id: statusOverviewText
                                width: parent.width
                                text: root.statusText
                                color: root.statusOk ? theme.muted : theme.danger
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                        }
                    }

                    FormPanel {
                        title: "PERFORMANCE PROFILE"
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            Repeater {
                                model: ["balanced", "low_end", "quality", "high_ips"]
                                delegate: ChoicePill {
                                    label: modelData.replace("_", "-")
                                    selected: root.performanceProfile === modelData
                                    onClicked: {
                                        root.performanceProfile = modelData
                                        root.runAction("profile-" + modelData)
                                    }
                                }
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: {
                                var desc = hubState.meta && hubState.meta.profileDescriptions
                                    ? hubState.meta.profileDescriptions[root.performanceProfile] : ""
                                return desc ? desc + " Restart the bot after changing profiles." : ""
                            }
                            color: theme.faint
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                    }

                    FormPanel {
                        title: "GAME MODE"
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: 12
                            rowSpacing: 12
                            OptionCard {
                                Layout.fillWidth: true
                                label: "Brawl Ball"
                                selected: root.mode === "brawl-ball"
                                onClicked: hubBridge.updateSetting("mode", "brawl-ball")
                            }
                            OptionCard {
                                Layout.fillWidth: true
                                label: "Showdown Trio"
                                selected: root.mode === "showdown-trio"
                                onClicked: hubBridge.updateSetting("mode", "showdown-trio")
                            }
                        }
                    }

                    FormPanel {
                        title: "EMULATOR"
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            OptionCard {
                                Layout.fillWidth: true
                                label: "LDPlayer"
                                selected: root.emulator === "ldplayer"
                                statusChecked: {
                                    var status = root.emulatorPreflightStatus("ldplayer")
                                    return !!(status && status.checked)
                                }
                                statusOk: {
                                    var status = root.emulatorPreflightStatus("ldplayer")
                                    return !!(status && status.ok)
                                }
                                detail: {
                                    var status = root.emulatorPreflightStatus("ldplayer")
                                    return status && status.detail ? String(status.detail) : ""
                                }
                                onClicked: {
                                    hubBridge.updateSetting("emulator", "ldplayer")
                                    root.runAction("preflight-check")
                                }
                            }
                            OptionCard {
                                Layout.fillWidth: true
                                label: "MuMu"
                                selected: root.emulator === "mumu"
                                statusChecked: {
                                    var status = root.emulatorPreflightStatus("mumu")
                                    return !!(status && status.checked)
                                }
                                statusOk: {
                                    var status = root.emulatorPreflightStatus("mumu")
                                    return !!(status && status.ok)
                                }
                                detail: {
                                    var status = root.emulatorPreflightStatus("mumu")
                                    return status && status.detail ? String(status.detail) : ""
                                }
                                onClicked: {
                                    hubBridge.updateSetting("emulator", "mumu")
                                    root.runAction("preflight-check")
                                }
                            }
                        }
                    }

                }

                FarmPlanPage {
                    visible: root.activeTab === "Farm Plan"
                }

                TabPage {
                    visible: root.activeTab === "Settings"

                    FormPanel {
                        title: "HUB"
                        tutorialId: "settings"
                        FieldRow {
                            label: "Search Settings"
                            pinnedInSettingsSearch: true
                            ConfigInput {
                                anchors.fill: parent
                                live: true
                                value: root.settingsFilter
                                onSaved: function(value) { root.settingsFilter = value }
                            }
                        }
                        ActionRow {
                            HubButton { label: "Open cfg Folder"; secondary: true; onClicked: root.runAction("open-config-folder") }
                            HubButton {
                                label: "Show Setup Wizard Again"
                                secondary: true
                                onClicked: root.runAction("reset-setup-wizard")
                            }
                        }
                    }

                    FormPanel {
                        title: "APPEARANCE"
                        FieldRow {
                            label: "Theme"
                            hint: "Liquid glass in light or dark. System follows your Windows app theme."
                            Row {
                                spacing: 8
                                Repeater {
                                    model: ["light", "dark", "system"]
                                    delegate: ChoicePill {
                                        label: modelData
                                        selected: root.themeMode === modelData
                                        onClicked: root.setThemeMode(modelData)
                                    }
                                }
                            }
                        }
                        FieldRow {
                            label: "UI Animations"
                            hint: "Smooth transitions and hover effects. Turn off for minimum UI overhead."
                            CenterRow { ToggleSwitch { checked: root.animationsEnabled; onToggled: function(value) { root.setAnimationsEnabled(value) } } }
                        }
                    }

                    FormPanel {
                        title: "ABOUT"
                        Text {
                            Layout.fillWidth: true
                            text: (hubBrand ? hubBrand.productName : "Pyla-RL") + " v" + hubVersion
                                + " · " + ((hubState.meta && hubState.meta.buildInfo && hubState.meta.buildInfo.commit) ? hubState.meta.buildInfo.commit : "unknown")
                            color: theme.text
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                        }
                        Text {
                            Layout.fillWidth: true
                            text: (hubBrand ? hubBrand.freeNotice : "Pyla-RL is free.") + " Licensed under " + (hubBrand ? hubBrand.licenseName : "CC BY-NC 4.0") + "."
                            color: theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            visible: root.unofficialCopy
                            Layout.fillWidth: true
                            text: (hubState.meta && hubState.meta.sourceStatus) ? hubState.meta.sourceStatus.reason : "Unofficial copy detected."
                            color: theme.accent
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        ActionRow {
                            HubButton { label: "Official GitHub"; secondary: true; onClicked: hubBridge.openOfficialRepo() }
                            HubButton { label: "Pyla Discord"; secondary: true; onClicked: hubBridge.openDiscord() }
                            HubButton { label: "Check Updates"; secondary: true; onClicked: root.runAction("check-updates") }
                            HubButton { label: "Report Reseller"; secondary: true; onClicked: root.runAction("report-reseller") }
                        }
                        RowLayout {
                            visible: !root.licenseAccepted
                            spacing: 8
                            Layout.fillWidth: true
                            Rectangle {
                                width: 18
                                height: 18
                                radius: 4
                                color: root.licenseTermsAccepted ? theme.accentSoft : theme.panel2
                                border.width: 1
                                border.color: theme.borderSoft
                                Text {
                                    anchors.centerIn: parent
                                    visible: root.licenseTermsAccepted
                                    text: "\u2713"
                                    color: theme.text
                                    font.pixelSize: 11
                                    font.weight: Font.Bold
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.licenseTermsAccepted = !root.licenseTermsAccepted
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "I understand Pyla-RL is free and I will not sell it."
                                color: theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                            HubButton {
                                label: "Accept"
                                clickable: root.licenseTermsAccepted
                                onClicked: root.runAction("accept-license")
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: "Optional Patreon support helps development. It is not required and is not a purchase."
                            color: theme.faint
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }
                    }

                    FormPanel {
                        title: "DETECTION"
                        FieldRow {
                            label: "Close Tile Detector"
                            hint: "Player-centered 640x640 crop via models/closeTileDetector.onnx."
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "close_tile_detector_enabled"); onToggled: function(value) { root.saveValue("settings", "close_tile_detector_enabled", value) } } }
                        }
                        FieldRow {
                            label: "Wall Confidence"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "wall_detection_confidence")); from: 0.1; to: 1.0; onSaved: function(value) { root.saveValue("settings", "wall_detection_confidence", value) } }
                        }
                        FieldRow {
                            label: "Player Confidence"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "entity_detection_confidence")); from: 0.1; to: 1.0; onSaved: function(value) { root.saveValue("settings", "entity_detection_confidence", value) } }
                        }
                        FieldRow {
                            label: "Super Pixels"
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "super_pixels_minimum")); onSaved: function(value) { root.saveValue("settings", "super_pixels_minimum", value) } }
                        }
                        FieldRow {
                            label: "Gadget Pixels"
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "gadget_pixels_minimum")); onSaved: function(value) { root.saveValue("settings", "gadget_pixels_minimum", value) } }
                        }
                        FieldRow {
                            label: "Hypercharge Pixels"
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "hypercharge_pixels_minimum")); onSaved: function(value) { root.saveValue("settings", "hypercharge_pixels_minimum", value) } }
                        }
                    }

                    FormPanel {
                        title: "BEHAVIOR"
                        FieldRow {
                            label: "Minimum Movement Delay"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "minimum_movement_delay")); from: 0.05; to: 3.0; onSaved: function(value) { root.saveValue("settings", "minimum_movement_delay", value) } }
                        }
                        FieldRow {
                            label: "Unstuck Delay"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "unstuck_movement_delay")); from: 0.5; to: 10.0; onSaved: function(value) { root.saveValue("settings", "unstuck_movement_delay", value) } }
                        }
                        FieldRow {
                            label: "Unstuck Duration"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "unstuck_movement_hold_time")); from: 0.2; to: 5.0; onSaved: function(value) { root.saveValue("settings", "unstuck_movement_hold_time", value) } }
                        }
                        FieldRow {
                            label: "After Round"
                            Row { spacing: 8; ChoicePill { label: "Return to lobby"; selected: root.value("settings", "post_match_action") === "lobby"; onClicked: root.saveValue("settings", "post_match_action", "lobby") } ChoicePill { label: "Play again"; selected: root.value("settings", "post_match_action") === "play_again"; onClicked: root.saveValue("settings", "post_match_action", "play_again") } }
                        }
                        FieldRow {
                            label: "Play Again On Win"
                            hint: "Press Play Again after wins when available."
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "play_again_on_win"); onToggled: function(value) { root.saveValue("settings", "play_again_on_win", value) } } }
                        }
                        FieldRow {
                            label: "Use Gadgets"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "bot_uses_gadgets"); onToggled: function(value) { root.saveValue("settings", "bot_uses_gadgets", value) } } }
                        }
                        FieldRow {
                            label: "Enemy Spacing"
                            hint: "Maintain distance based on each brawler's safe and attack ranges."
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "enemy_spacing_enabled"); onToggled: function(value) { root.saveValue("settings", "enemy_spacing_enabled", value) } } }
                        }
                        FieldRow {
                            label: "Spacing Aggression"
                            hint: "0 = kite at safe range, 1 = hug max attack range. Purple debug circle shows this target distance."
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "enemy_spacing_blend")); from: 0.0; to: 1.0; onSaved: function(value) { root.saveValue("settings", "enemy_spacing_blend", value) } }
                        }
                        FieldRow {
                            label: "Spacing Tolerance (px)"
                            hint: "Dead zone around the target distance to reduce oscillation."
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "enemy_spacing_tolerance")); from: 10.0; to: 120.0; onSaved: function(value) { root.saveValue("settings", "enemy_spacing_tolerance", value) } }
                        }
                        FieldRow {
                            label: "Strafe In Range"
                            hint: "Sideways drift while holding the ideal spacing band."
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "enemy_spacing_hold_strafe"); onToggled: function(value) { root.saveValue("settings", "enemy_spacing_hold_strafe", value) } } }
                        }
                        FieldRow {
                            label: "Multi-Enemy Threat Weight"
                            hint: "Higher values flee harder from extra close enemies while kiting everyone at max range."
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "multi_enemy_flee_weight")); from: 0.0; to: 1.0; onSaved: function(value) { root.saveValue("settings", "multi_enemy_flee_weight", value) } }
                        }
                        FieldRow {
                            label: "Dodge Under Fire"
                            hint: "Random sideways jitter when an enemy has clear line of sight."
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "combat_los_dodge_enabled"); onToggled: function(value) { root.saveValue("settings", "combat_los_dodge_enabled", value) } } }
                        }
                        FieldRow {
                            label: "Dodge Blend"
                            hint: "How much random dodge mixes into movement (0 = off, 1 = full dodge)."
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "combat_dodge_blend")); from: 0.0; to: 1.0; onSaved: function(value) { root.saveValue("settings", "combat_dodge_blend", value) } }
                        }
                        FieldRow {
                            label: "Dodge Jitter (deg)"
                            hint: "Random angle wobble added to sideways dodge."
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "combat_dodge_jitter_degrees")); from: 5.0; to: 45.0; onSaved: function(value) { root.saveValue("settings", "combat_dodge_jitter_degrees", value) } }
                        }
                        FieldRow {
                            label: "Dodge Commit (sec)"
                            hint: "Hold each dodge direction before switching sides."
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "combat_dodge_commit_seconds")); from: 0.2; to: 2.0; onSaved: function(value) { root.saveValue("settings", "combat_dodge_commit_seconds", value) } }
                        }
                        FieldRow {
                            label: "Smart Aim"
                            hint: "Lead shots at moving enemies instead of auto-aim taps."
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "smart_aim_enabled"); onToggled: function(value) { root.saveValue("settings", "smart_aim_enabled", value) } } }
                        }
                        FieldRow {
                            label: "Attack Interval (sec)"
                            hint: "Minimum time between full attack taps."
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "attack_min_interval")); from: 0.1; to: 1.0; onSaved: function(value) { root.saveValue("settings", "attack_min_interval", value) } }
                        }
                        FieldRow {
                            label: "Projectile Speed (px/s)"
                            hint: "Used for lead-aim travel-time estimate."
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "projectile_speed_px_s")); from: 400.0; to: 2400.0; onSaved: function(value) { root.saveValue("settings", "projectile_speed_px_s", value) } }
                        }
                        FieldRow {
                            label: "Run For Minutes"
                            hint: "0 disables the session timer."
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "run_for_minutes")); onSaved: function(value) { root.saveValue("settings", "run_for_minutes", value) } }
                        }
                        FieldRow {
                            label: "Emulator Auto Restart"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "emulator_autorestart"); onToggled: function(value) { root.saveValue("settings", "emulator_autorestart", value) } } }
                        }
                        FieldRow {
                            label: "Trio Movement"
                            Row { spacing: 8; ChoicePill { label: "Follow"; selected: root.value("settings", "showdown_playstyle_mode") === "follow"; onClicked: root.saveValue("settings", "showdown_playstyle_mode", "follow") } ChoicePill { label: "Hide"; selected: root.value("settings", "showdown_playstyle_mode") === "hide"; onClicked: root.saveValue("settings", "showdown_playstyle_mode", "hide") } }
                        }
                        FieldRow {
                            label: "Longpress Star Drop"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "long_press_star_drop"); onToggled: function(value) { root.saveValue("settings", "long_press_star_drop", value) } } }
                        }
                        FieldRow {
                            label: "Save Terminal Log"
                            hint: "Writes timestamped logs to logs/."
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "terminal_logging"); onToggled: function(value) { root.saveValue("settings", "terminal_logging", value) } } }
                        }
                        FieldRow {
                            label: "Terminal Verbosity"
                            hint: "Restart bot to apply."
                            Row {
                                spacing: 8
                                Repeater {
                                    model: ["quiet", "normal", "verbose", "debug"]
                                    delegate: ChoicePill {
                                        label: modelData
                                        selected: root.value("settings", "terminal_verbosity") === modelData
                                        onClicked: root.saveValue("settings", "terminal_verbosity", modelData)
                                    }
                                }
                            }
                        }
                        FieldRow {
                            label: "Movement Debug"
                            hint: "Rate-limited movement trace. Independent of Debug Screen."
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "movement_debug"); onToggled: function(value) { root.saveValue("settings", "movement_debug", value) } } }
                        }
                        FieldRow {
                            label: "Debug Screen"
                            hint: "Overlay only. Does not flood the terminal."
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "visual_debug"); onToggled: function(value) { root.saveValue("settings", "visual_debug", value); statusText = "Restart bot to apply Debug Screen changes."; statusOk = true; statusToastTimer.restart() } } }
                        }
                        FieldRow {
                            label: "Advanced Visuals"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "advanced_visuals"); onToggled: function(value) { root.saveValue("settings", "advanced_visuals", value) } } }
                        }
                        FieldRow {
                            label: "Pause Menu IPS Graph"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "pause_menu_ips_graph"); onToggled: function(value) { root.saveValue("settings", "pause_menu_ips_graph", value) } } }
                        }
                        FieldRow {
                            label: "Pause Session Strip"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "pause_menu_session_strip"); onToggled: function(value) { root.saveValue("settings", "pause_menu_session_strip", value) } } }
                        }
                        FieldRow {
                            label: "Auto-Reopen Pause Menu"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "pause_menu_auto_reopen"); onToggled: function(value) { root.saveValue("settings", "pause_menu_auto_reopen", value) } } }
                        }
                        FieldRow {
                            label: "Console Status Line"
                            hint: "In-place IPS summary instead of scrolling lines."
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "console_ips"); onToggled: function(value) { root.saveValue("settings", "console_ips", value) } } }
                        }
                        FieldRow {
                            label: "Status Summary Seconds"
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "terminal_summary_seconds")); onSaved: function(value) { root.saveValue("settings", "terminal_summary_seconds", value) } }
                        }
                        FieldRow {
                            label: "Pause Graph Samples"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "pause_menu_graph_samples")); from: 30; to: 120; integer: true; onSaved: function(value) { root.saveValue("settings", "pause_menu_graph_samples", value) } }
                        }
                        FieldRow {
                            label: "Capture Vision Frames"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "capture_bad_vision_frames"); onToggled: function(value) { root.saveValue("settings", "capture_bad_vision_frames", value) } } }
                        }
                    }

                    FormPanel {
                        title: "CAPTURE / DEBUG"
                        FieldRow { label: "Scrcpy Width"; ConfigInput { anchors.fill: parent; value: String(root.value("settings", "scrcpy_max_width")); onSaved: function(value) { root.saveValue("settings", "scrcpy_max_width", value) } } }
                        FieldRow { label: "Scrcpy Bitrate"; ConfigInput { anchors.fill: parent; value: String(root.value("settings", "scrcpy_bitrate")); onSaved: function(value) { root.saveValue("settings", "scrcpy_bitrate", value) } } }
                        FieldRow { label: "Debug Scale"; NumericSlider { anchors.fill: parent; value: String(root.value("settings", "visual_debug_scale")); from: 0.5; to: 2.0; onSaved: function(value) { root.saveValue("settings", "visual_debug_scale", value) } } }
                        FieldRow { label: "Debug Max FPS"; ConfigInput { anchors.fill: parent; value: String(root.value("settings", "visual_debug_max_fps")); onSaved: function(value) { root.saveValue("settings", "visual_debug_max_fps", value) } } }
                        FieldRow { label: "Debug Max Boxes"; ConfigInput { anchors.fill: parent; value: String(root.value("settings", "visual_debug_max_boxes")); onSaved: function(value) { root.saveValue("settings", "visual_debug_max_boxes", value) } } }
                        FieldRow { label: "Super Debug"; CenterRow { ToggleSwitch { checked: root.boolValue("settings", "super_debug"); onToggled: function(value) { root.saveValue("settings", "super_debug", value) } } } }
                        FieldRow { label: "Wall Stuck Debug"; hint: "Movement escape trace."; CenterRow { ToggleSwitch { checked: root.boolValue("settings", "wall_stuck_debug"); onToggled: function(value) { root.saveValue("settings", "wall_stuck_debug", value) } } } }
                    }

                    FormPanel {
                        title: "PERFORMANCE"
                        FieldRow {
                            label: "Inference Device"
                            Row { spacing: 8; Repeater { model: ["auto", "directml", "amd", "cuda", "openvino", "cpu"]; delegate: ChoicePill { label: modelData; selected: root.value("settings", "cpu_or_gpu") === modelData; onClicked: root.saveValue("settings", "cpu_or_gpu", modelData) } } }
                        }
                        FieldRow {
                            label: "DirectML GPU ID"
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "directml_device_id")); onSaved: function(value) { root.saveValue("settings", "directml_device_id", value) } }
                        }
                        FieldRow {
                            label: "Max IPS"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "max_ips")); from: 0; to: 120; integer: true; onSaved: function(value) { root.saveValue("settings", "max_ips", value) } }
                        }
                        FieldRow {
                            label: "Scrcpy Max FPS"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "scrcpy_max_fps")); from: 5; to: 120; integer: true; onSaved: function(value) { root.saveValue("settings", "scrcpy_max_fps", value) } }
                        }
                        FieldRow {
                            label: "Used Threads"
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "used_threads")); onSaved: function(value) { root.saveValue("settings", "used_threads", value) } }
                        }
                        FieldRow {
                            label: "Trophy Multiplier"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "trophies_multiplier")); from: 1; to: 10; integer: true; onSaved: function(value) { root.saveValue("settings", "trophies_multiplier", value) } }
                        }
                        FieldRow {
                            label: "OCR Scale"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "ocr_scale_down_factor")); from: 0.1; to: 1.0; onSaved: function(value) { root.saveValue("settings", "ocr_scale_down_factor", value) } }
                        }
                        FieldRow {
                            label: "Current Playstyle"
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "current_playstyle")); onSaved: function(value) { root.saveValue("settings", "current_playstyle", value) } }
                        }
                        FieldRow {
                            label: "Performance Profile"
                            Row {
                                spacing: 8
                                ChoicePill { label: "balanced"; selected: root.performanceProfile === "balanced"; onClicked: root.performanceProfile = "balanced" }
                                ChoicePill { label: "low-end"; selected: root.performanceProfile === "low-end"; onClicked: root.performanceProfile = "low-end" }
                                ChoicePill { label: "quality"; selected: root.performanceProfile === "quality"; onClicked: root.performanceProfile = "quality" }
                                ChoicePill { label: "high-ips"; selected: root.performanceProfile === "high_ips"; onClicked: root.performanceProfile = "high_ips" }
                            }
                        }
                        FieldRow {
                            label: "Auto-Tune IPS"
                            hint: "Step capture settings between matches when IPS stays below target."
                            CenterRow {
                                ToggleSwitch {
                                    checked: root.boolValue("settings", "performance_autotune")
                                    onToggled: function(value) { root.saveValue("settings", "performance_autotune", value) }
                                }
                            }
                        }
                        ActionRow {
                            HubButton {
                                label: "Apply Performance Mode"
                                onClicked: root.runAction("profile-" + root.performanceProfile)
                            }
                            HubButton {
                                label: "Calibrate"
                                secondary: true
                                onClicked: applyBridgeResult(hubBridge.calibratePerformance())
                            }
                        }
                    }
                    Text { text: root.statusText; color: root.statusOk ? theme.muted : theme.danger; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                }

                TabPage {
                    visible: root.activeTab === "Discord"
                    FormPanel {
                        title: "DISCORD NOTIFICATIONS"
                        tutorialId: "discord"
                        FieldRow { label: "Webhook URL"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "webhook_url")); secret: true; onSaved: function(value) { root.saveValue("discord", "webhook_url", value) } } }
                        FieldRow { label: "Discord ID"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_id")); onSaved: function(value) { root.saveValue("discord", "discord_id", value) } } }
                        FieldRow { label: "Webhook Name"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "username")); onSaved: function(value) { root.saveValue("discord", "username", value) } } }
                        FieldRow { label: "Send Match Summary"; hint: "Post a match report embed after every finished game."; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "send_match_summary"); onToggled: function(value) { root.saveValue("discord", "send_match_summary", value) } } } }
                        FieldRow { label: "Include Screenshots"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "include_screenshot"); onToggled: function(value) { root.saveValue("discord", "include_screenshot", value) } } } }
                        FieldRow { label: "Ping When Stuck"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "ping_when_stuck"); onToggled: function(value) { root.saveValue("discord", "ping_when_stuck", value) } } } }
                        FieldRow { label: "Notify On Recovery"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "notify_on_recovery"); onToggled: function(value) { root.saveValue("discord", "notify_on_recovery", value) } } } }
                        FieldRow { label: "Recovery Alert Threshold"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "recovery_alert_threshold")); onSaved: function(value) { root.saveValue("discord", "recovery_alert_threshold", value) } } }
                        FieldRow { label: "Ping On Target"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "ping_when_target_is_reached"); onToggled: function(value) { root.saveValue("discord", "ping_when_target_is_reached", value) } } } }
                        FieldRow { label: "Ping Every X Matches"; hint: "Mention your Discord ID on every Nth match summary (0 = no mention)."; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "ping_every_x_match")); onSaved: function(value) { root.saveValue("discord", "ping_every_x_match", value) } } }
                        FieldRow { label: "Heartbeat Every X Minutes"; hint: "Optional still-running ping (0 = off). Does not replace match summaries."; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "ping_every_x_minutes")); onSaved: function(value) { root.saveValue("discord", "ping_every_x_minutes", value) } } }
                        FieldRow { label: "Daily Digest"; hint: "One summary message per day instead of noisy recovery pings."; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "daily_digest_enabled"); onToggled: function(value) { root.saveValue("discord", "daily_digest_enabled", value) } } } }
                        FieldRow { label: "Digest Hour (0-23)"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "daily_digest_hour")); onSaved: function(value) { root.saveValue("discord", "daily_digest_hour", value) } } }
                    }
                    FormPanel {
                        title: "REMOTE CONTROL"
                        FieldRow { label: "Enable Discord Control"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "discord_control_enabled"); onToggled: function(value) { root.saveValue("discord", "discord_control_enabled", value) } } } }
                        FieldRow { label: "Bot Token"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_bot_token")); secret: true; onSaved: function(value) { root.saveValue("discord", "discord_bot_token", value) } } }
                        FieldRow { label: "Allowed User ID"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_control_user_id")); onSaved: function(value) { root.saveValue("discord", "discord_control_user_id", value) } } }
                        FieldRow { label: "Allowed Channel ID"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_control_channel_id")); onSaved: function(value) { root.saveValue("discord", "discord_control_channel_id", value) } } }
                        FieldRow { label: "Guild ID"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_control_guild_id")); onSaved: function(value) { root.saveValue("discord", "discord_control_guild_id", value) } } }
                    }
                    ActionRow {
                        HubButton { label: "Send Discord Test"; onClicked: root.runAction("discord-test") }
                        HubButton { label: "Webhook Guide"; secondary: true; onClicked: root.runAction("discord-webhook-guide") }
                        HubButton { label: "Developer Portal"; secondary: true; onClicked: root.runAction("discord-developer-portal") }
                    }
                    Text { text: root.statusText; color: root.statusOk ? theme.muted : theme.danger; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                }

                TabPage {
                    visible: root.activeTab === "Telegram"
                    FormPanel {
                        title: "TELEGRAM BOT"
                        tutorialId: "telegram"
                        FieldRow { label: "Enable Telegram"; CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "enabled"); onToggled: function(value) { root.saveValue("telegram", "enabled", value) } } } }
                        FieldRow { label: "Bot Token"; ConfigInput { anchors.fill: parent; value: String(root.value("telegram", "bot_token")); secret: true; onSaved: function(value) { root.saveValue("telegram", "bot_token", value) } } }
                        FieldRow { label: "Notification Chat IDs"; ConfigInput { anchors.fill: parent; value: String(root.value("telegram", "notification_chat_ids")); onSaved: function(value) { root.saveValue("telegram", "notification_chat_ids", value) } } }
                        FieldRow { label: "Send Match Summary"; CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "send_match_summary"); onToggled: function(value) { root.saveValue("telegram", "send_match_summary", value) } } } }
                        FieldRow { label: "Include Screenshots"; CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "include_screenshot"); onToggled: function(value) { root.saveValue("telegram", "include_screenshot", value) } } } }
                        FieldRow { label: "Multiple Chats"; CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "allow_multiple_notification_chat_ids"); onToggled: function(value) { root.saveValue("telegram", "allow_multiple_notification_chat_ids", value) } } } }
                        FieldRow { label: "Remote Control"; CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "remote_control_enabled"); onToggled: function(value) { root.saveValue("telegram", "remote_control_enabled", value) } } } }
                        FieldRow { label: "Notify On Recovery"; CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "notify_on_recovery"); onToggled: function(value) { root.saveValue("telegram", "notify_on_recovery", value) } } } }
                        FieldRow { label: "Recovery Alert Threshold"; ConfigInput { anchors.fill: parent; value: String(root.value("telegram", "recovery_alert_threshold")); onSaved: function(value) { root.saveValue("telegram", "recovery_alert_threshold", value) } } }
                        FieldRow { label: "Poll Timeout"; ConfigInput { anchors.fill: parent; value: String(root.value("telegram", "poll_timeout_seconds")); onSaved: function(value) { root.saveValue("telegram", "poll_timeout_seconds", value) } } }
                    }
                    ActionRow {
                        HubButton { label: "Find Chats"; onClicked: root.runAction("telegram-find-chats") }
                        HubButton { label: "Send Telegram Test"; onClicked: root.runAction("telegram-test") }
                        HubButton { label: "Open @BotFather"; secondary: true; onClicked: root.runAction("telegram-botfather") }
                    }
                    Text { text: root.statusText; color: root.statusOk ? theme.muted : theme.danger; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                }

                TabPage {
                    visible: root.activeTab === "API"
                    FormPanel {
                        title: "BRAWL STARS API"
                        tutorialId: "api"
                        FieldRow { label: "Player Tag"; ConfigInput { anchors.fill: parent; value: String(root.value("api", "player_tag")); onSaved: function(value) { root.saveValue("api", "player_tag", value) } } }
                        FieldRow { label: "Auto Refresh Token"; CenterRow { ToggleSwitch { checked: root.boolValue("api", "auto_refresh_token"); onToggled: function(value) { root.saveValue("api", "auto_refresh_token", value) } } } }
                        FieldRow { label: "Developer Email"; ConfigInput { anchors.fill: parent; value: String(root.value("api", "developer_email")); onSaved: function(value) { root.saveValue("api", "developer_email", value) } } }
                        FieldRow { label: "Developer Password"; ConfigInput { anchors.fill: parent; value: String(root.value("api", "developer_password")); secret: true; onSaved: function(value) { root.saveValue("api", "developer_password", value) } } }
                        FieldRow { label: "API Token"; ConfigInput { anchors.fill: parent; value: String(root.value("api", "api_token")); secret: true; onSaved: function(value) { root.saveValue("api", "api_token", value) } } }
                        FieldRow { label: "Timeout Seconds"; ConfigInput { anchors.fill: parent; value: String(root.value("api", "timeout_seconds")); onSaved: function(value) { root.saveValue("api", "timeout_seconds", value) } } }
                        FieldRow { label: "Public IP Service"; ConfigInput { anchors.fill: parent; value: String(root.value("api", "public_ip_service")); onSaved: function(value) { root.saveValue("api", "public_ip_service", value) } } }
                        FieldRow { label: "Key Name Prefix"; ConfigInput { anchors.fill: parent; value: String(root.value("api", "key_name_prefix")); onSaved: function(value) { root.saveValue("api", "key_name_prefix", value) } } }
                        FieldRow { label: "Delete Old Tokens"; CenterRow { ToggleSwitch { checked: root.boolValue("api", "delete_old_auto_tokens"); onToggled: function(value) { root.saveValue("api", "delete_old_auto_tokens", value) } } } }
                        FieldRow { label: "Sync Trophies After Match"; CenterRow { ToggleSwitch { checked: root.boolValue("api", "sync_trophies_after_match"); onToggled: function(value) { root.saveValue("api", "sync_trophies_after_match", value) } } } }
                    }
                    ActionRow {
                        HubButton { label: "Test API Config"; onClicked: root.runAction("api-test") }
                        HubButton { label: "Developer Portal"; secondary: true; onClicked: root.runAction("brawl-stars-developer") }
                    }
                    Text { text: root.statusText; color: root.statusOk ? theme.muted : theme.danger; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                }

                TabPage {
                    visible: root.activeTab === "Timers"
                    FormPanel {
                        title: "TIMERS"
                        tutorialId: "timers"
                        FieldRow { label: "Super Delay"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "super")); from: 0.05; to: 10; onSaved: function(value) { root.saveValue("timers", "super", value) } } }
                        FieldRow { label: "Hypercharge Delay"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "hypercharge")); from: 0.05; to: 10; onSaved: function(value) { root.saveValue("timers", "hypercharge", value) } } }
                        FieldRow { label: "Gadget Delay"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "gadget")); from: 0.05; to: 10; onSaved: function(value) { root.saveValue("timers", "gadget", value) } } }
                        FieldRow { label: "Wall Detection"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "wall_detection")); from: 0.05; to: 10; onSaved: function(value) { root.saveValue("timers", "wall_detection", value) } } }
                        FieldRow { label: "No Detection Proceed"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "no_detection_proceed")); from: 0.1; to: 20; onSaved: function(value) { root.saveValue("timers", "no_detection_proceed", value) } } }
                        FieldRow { label: "Low IPS Recovery"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "low_ips_recovery_seconds")); from: 5; to: 90; integer: true; onSaved: function(value) { root.saveValue("timers", "low_ips_recovery_seconds", value) } } }
                        FieldRow { label: "Low IPS Cooldown"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "low_ips_recovery_cooldown")); from: 5; to: 90; integer: true; onSaved: function(value) { root.saveValue("timers", "low_ips_recovery_cooldown", value) } } }
                        FieldRow { label: "App Restart Attempt"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "low_ips_app_restart_after")); from: 1; to: 6; integer: true; onSaved: function(value) { root.saveValue("timers", "low_ips_app_restart_after", value) } } }
                        FieldRow { label: "Emulator Restart Attempt"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "low_ips_emulator_restart_after")); from: 1; to: 10; integer: true; onSaved: function(value) { root.saveValue("timers", "low_ips_emulator_restart_after", value) } } }
                        FieldRow { label: "Lobby Stuck Restart"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "lobby_stuck_restart")); from: 30; to: 300; onSaved: function(value) { root.saveValue("timers", "lobby_stuck_restart", value) } } }
                        FieldRow { label: "Visual Freeze Restart"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "visual_freeze_restart")); from: 10; to: 120; onSaved: function(value) { root.saveValue("timers", "visual_freeze_restart", value) } } }
                        FieldRow { label: "Global Freeze Restart"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "global_freeze_restart")); from: 10; to: 180; onSaved: function(value) { root.saveValue("timers", "global_freeze_restart", value) } } }
                        FieldRow { label: "Emulator Restart Cooldown"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "emulator_restart_cooldown")); from: 30; to: 600; onSaved: function(value) { root.saveValue("timers", "emulator_restart_cooldown", value) } } }
                        FieldRow { label: "State Check"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "state_check")); from: 0.1; to: 5; onSaved: function(value) { root.saveValue("timers", "state_check", value) } } }
                        FieldRow { label: "Idle Timeout"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "idle")); from: 5; to: 120; onSaved: function(value) { root.saveValue("timers", "idle", value) } } }
                        FieldRow { label: "Low IPS Threshold"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "low_ips_recovery_threshold")); from: 1; to: 10; onSaved: function(value) { root.saveValue("timers", "low_ips_recovery_threshold", value) } } }
                    }
                }

                TabPage {
                    visible: root.activeTab === "Match History"

                    FormPanel {
                        title: "MATCH HISTORY"
                        tutorialId: "match-history"
                        ActionRow {
                            HubButton { label: "Export CSV"; secondary: true; onClicked: root.runAction("export-history") }
                            HubButton { label: "Reset Stats"; secondary: true; onClicked: root.runAction("reset-history") }
                            HubButton { label: "Refresh"; secondary: true; onClicked: root.runAction("refresh-history") }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 72
                        radius: 10
                        color: theme.panel
                        border.width: 1
                        border.color: theme.borderSoft
                        Column {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 4
                            Text {
                                text: "Lifetime: " + ((hubState.history && hubState.history.summary) ? hubState.history.summary.games : 0) + " games"
                                color: theme.text
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                            Text {
                                text: "W " + ((hubState.history && hubState.history.summary) ? hubState.history.summary.victory : 0)
                                    + " / L " + ((hubState.history && hubState.history.summary) ? hubState.history.summary.defeat : 0)
                                    + " / D " + ((hubState.history && hubState.history.summary) ? hubState.history.summary.draw : 0)
                                    + " | " + ((hubState.history && hubState.history.summary) ? hubState.history.summary.winRate : 0) + "% win"
                                color: theme.muted
                                font.pixelSize: 11
                            }
                        }
                    }
                    RowLayout {
                        spacing: 8
                        Repeater {
                            model: ["games", "winRate", "name"]
                            delegate: ChoicePill {
                                label: modelData
                                selected: root.historySort === modelData
                                onClicked: root.historySort = modelData
                            }
                        }
                    }
                    Text { text: root.statusText; color: root.statusOk ? theme.muted : theme.danger; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Text { text: "Recent Matches"; color: theme.faint; font.pixelSize: 11 }
                    FormPanel {
                        title: "EFFICIENCY (LAST 7 DAYS)"
                        visible: !!(hubState.history && hubState.history.efficiency && hubState.history.efficiency.length)
                        Flow {
                            Layout.fillWidth: true
                            spacing: 10
                            Repeater {
                                model: (hubState.history && hubState.history.efficiency) ? hubState.history.efficiency.slice(0, 12) : []
                                delegate: Rectangle {
                                    width: 150
                                    height: modelData.stuck ? 92 : 78
                                    radius: 8
                                    color: theme.panel2
                                    border.width: 1
                                    border.color: modelData.stuck ? theme.danger : theme.borderSoft
                                    Column {
                                        anchors.fill: parent
                                        anchors.margins: 8
                                        spacing: 4
                                        Text {
                                            width: parent.width
                                            text: modelData.brawler
                                            color: theme.text
                                            font.pixelSize: 12
                                            font.bold: true
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            text: modelData.trophiesPerHour + " trophies/hr"
                                            color: theme.ok
                                            font.pixelSize: 11
                                        }
                                        Text {
                                            text: modelData.winRate + "% win · " + modelData.matches + " matches"
                                            color: theme.muted
                                            font.pixelSize: 10
                                        }
                                        Text {
                                            visible: !!modelData.stuck
                                            text: "Stuck"
                                            color: theme.danger
                                            font.pixelSize: 10
                                            font.bold: true
                                        }
                                    }
                                }
                            }
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Repeater {
                            model: (hubState.history && hubState.history.recent) ? hubState.history.recent.slice(0, 8) : []
                            delegate: Text {
                                Layout.fillWidth: true
                                text: modelData.brawler + " " + modelData.result + " (" + modelData.delta + ")"
                                color: theme.muted
                                font.pixelSize: 11
                            }
                        }
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 12
                        Repeater {
                            model: root.sortedHistoryItems()
                            delegate: Rectangle {
                                width: 158
                                height: 176
                                radius: 10
                                color: theme.panel
                                border.width: 1
                                border.color: theme.borderSoft

                                Column {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 8
                                    Rectangle {
                                        width: 64
                                        height: 64
                                        radius: 10
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        color: theme.panel2
                                        border.width: 1
                                        border.color: theme.borderSoft
                                        clip: true

                                        Image {
                                            anchors.fill: parent
                                            anchors.margins: 4
                                            source: modelData.icon
                                            fillMode: Image.PreserveAspectFit
                                            smooth: true
                                            visible: modelData.icon !== ""
                                        }

                                        Text {
                                            anchors.centerIn: parent
                                            text: modelData.brawler ? modelData.brawler.charAt(0).toUpperCase() : "?"
                                            color: theme.faint
                                            font.pixelSize: 22
                                            font.weight: Font.Bold
                                            visible: modelData.icon === ""
                                        }
                                    }
                                    Text {
                                        width: parent.width
                                        text: modelData.brawler
                                        color: theme.text
                                        font.pixelSize: 13
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }
                                    Text { text: modelData.games + " games"; color: theme.muted; font.pixelSize: 11 }
                                    Row {
                                        spacing: 10
                                        Text { text: modelData.winRate + "% win"; color: theme.ok; font.pixelSize: 12; font.weight: Font.DemiBold }
                                        Text { text: modelData.defeat + " losses"; color: theme.faint; font.pixelSize: 12 }
                                    }
                                }
                            }
                        }
                    }
                    Text {
                        visible: !root.hubState.history || !root.hubState.history.items || root.hubState.history.items.length === 0
                        text: "No match history yet."
                        color: theme.faint
                        font.pixelSize: 12
                    }
                }

                TabPage {
                    visible: root.activeTab === "Help"

                    FormPanel {
                        title: "FEATURE GUIDES"
                        Text {
                            Layout.fillWidth: true
                            text: "Quick guides for every Hub tab. Click Open guide for a summary, or Open full guide for the markdown tutorial."
                            color: theme.faint
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        FieldRow {
                            label: "Search Guides"
                            ConfigInput {
                                anchors.fill: parent
                                live: true
                                value: root.helpFilter
                                onSaved: function(value) { root.helpFilter = value }
                            }
                        }
                        ActionRow {
                            HubButton {
                                label: "Open Tutorial Index"
                                secondary: true
                                onClicked: root.openTutorialDoc("docs/TUTORIAL.md")
                            }
                            HubButton {
                                label: "Show Setup Wizard Again"
                                secondary: true
                                onClicked: root.runAction("reset-setup-wizard")
                            }
                        }
                    }

                    Repeater {
                        model: root.filteredHelpTopics()
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            radius: 10
                            color: theme.panel
                            border.width: 1
                            border.color: theme.borderSoft
                            implicitHeight: helpTopicColumn.implicitHeight + 20

                            ColumnLayout {
                                id: helpTopicColumn
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 6

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.title
                                        color: theme.text
                                        font.pixelSize: 13
                                        font.weight: Font.Bold
                                    }
                                    Text {
                                        text: modelData.tab || "Help"
                                        color: theme.faint
                                        font.pixelSize: 10
                                    }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: {
                                        const summary = String(modelData.summary || "")
                                        const firstLine = summary.split("\n")[0] || summary
                                        return firstLine
                                    }
                                    color: theme.muted
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                }
                                RowLayout {
                                    spacing: 8
                                    HubButton {
                                        label: "Open guide"
                                        compact: true
                                        onClicked: root.openTutorial(modelData.id)
                                    }
                                    HubButton {
                                        label: "Full doc"
                                        secondary: true
                                        compact: true
                                        visible: !!modelData.doc
                                        onClicked: root.openTutorialDoc(modelData.doc)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                id: startBar
                Layout.fillWidth: true
                Layout.preferredHeight: 56
                color: theme.chrome
                border.width: 1
                border.color: theme.borderSoft

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    spacing: 12

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            text: (hubState.preflight && hubState.preflight.ready) ? "Ready to start" : "Run pre-flight checks on Overview"
                            color: (hubState.preflight && hubState.preflight.ready) ? theme.ok : theme.muted
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                        }
                        Text {
                            visible: root.statusText !== ""
                            Layout.fillWidth: true
                            text: root.statusText
                            color: root.statusOk ? theme.faint : theme.danger
                            font.pixelSize: 10
                            elide: Text.ElideRight
                            maximumLineCount: 1
                        }
                    }

                    Rectangle {
                        id: startButton
                        visible: !settingsOnly
                        Layout.preferredWidth: 168
                        Layout.preferredHeight: 44
                        radius: 12
                        color: (hubState.preflight && hubState.preflight.ready)
                            ? (startMouse.containsMouse ? theme.accentHover : theme.accent)
                            : theme.disabled
                        opacity: (hubState.preflight && hubState.preflight.ready && !root.hubBusy) ? 1.0 : 0.85
                        border.width: 1
                        border.color: (hubState.preflight && hubState.preflight.ready) ? theme.accentBorder : theme.borderSoft
                        scale: startMouse.pressed ? 0.97 : 1.0

                        Behavior on color { ColorAnimation { duration: root.durFast } }
                        Behavior on scale { NumberAnimation { duration: root.durFast; easing.type: Easing.OutCubic } }

                        Text {
                            anchors.centerIn: parent
                            text: "START"
                            color: "#ffffff"
                            font.pixelSize: 15
                            font.weight: Font.Bold
                        }

                        MouseArea {
                            id: startMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            enabled: !root.hubBusy
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: root.startBot()
                        }
                    }

                    Rectangle {
                        id: closeSettingsButton
                        visible: settingsOnly
                        Layout.preferredWidth: 168
                        Layout.preferredHeight: 44
                        radius: 12
                        color: closeSettingsMouse.containsMouse ? theme.panel3 : theme.panel2
                        border.width: 1
                        border.color: theme.border
                        scale: closeSettingsMouse.pressed ? 0.97 : 1.0

                        Behavior on color { ColorAnimation { duration: root.durFast } }
                        Behavior on scale { NumberAnimation { duration: root.durFast; easing.type: Easing.OutCubic } }

                        Text {
                            anchors.centerIn: parent
                            text: "CLOSE"
                            color: theme.text
                            font.pixelSize: 15
                            font.weight: Font.Bold
                        }

                        MouseArea {
                            id: closeSettingsMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: hubBridge.closeHub()
                        }
                    }

                    HubButton {
                        label: "Checks"
                        secondary: true
                        compact: true
                        onClicked: {
                            root.activeTab = "Overview"
                            root.runAction("preflight-check")
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                color: theme.chrome
                border.width: 1
                border.color: theme.borderSoft

                Row {
                    anchors.centerIn: parent
                    spacing: 16
                    Text { text: hubBrand ? hubBrand.footerNotice : "Pyla is free, public, and open-source."; color: theme.faint; font.pixelSize: 11 }
                    Text { text: "\u00b7"; color: theme.muted; font.pixelSize: 13; font.weight: Font.Bold }
                    FooterLink {
                        label: "Join Discord"
                        onClicked: hubBridge.openDiscord()
                    }
                    Text { text: "\u00b7"; color: theme.muted; font.pixelSize: 13; font.weight: Font.Bold }
                    FooterLink {
                        label: "Support on Patreon"
                        onClicked: hubBridge.openPatreon()
                    }
                    Text { text: "\u00b7"; color: theme.muted; font.pixelSize: 13; font.weight: Font.Bold }
                    Text { text: "Pyla-RL"; color: theme.faint; font.pixelSize: 11 }
                }
            }
        }

        WindowResizeGrip {}
    }

    Rectangle {
        anchors.fill: parent
        opacity: root.showWizard ? 1 : 0
        visible: opacity > 0.01
        color: theme.scrim
        z: 99

        Behavior on opacity { NumberAnimation { duration: root.durFast } }

        Rectangle {
            anchors.centerIn: parent
            width: 420
            radius: 14
            color: theme.panel3
            border.width: 1
            border.color: theme.border
            implicitHeight: wizardColumn.implicitHeight + 32
            scale: root.showWizard ? 1 : 0.94

            Behavior on scale { NumberAnimation { duration: root.durMed; easing.type: Easing.OutCubic } }

            ColumnLayout {
                id: wizardColumn
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12
                Text {
                    text: root.wizardStep === 0 ? "Step 1: Free Use License"
                        : (root.wizardStep === 1 ? "Step 2: Environment"
                        : (root.wizardStep === 2 ? "Step 3: Optional Setup" : "Step 4: Farm Plan"))
                    color: theme.text
                    font.pixelSize: 16
                    font.weight: Font.Bold
                }
                Text {
                    Layout.fillWidth: true
                    text: root.wizardStep === 0
                        ? ((hubBrand ? hubBrand.productName : "Pyla-RL") + " is free and open source under CC BY-NC 4.0. You may use and modify it, but you must not sell or resell it.")
                        : (root.wizardStep === 1
                            ? "Start your emulator, open Brawl Stars, then run pre-flight checks on Overview. Full guides for every feature are in the Help tab."
                            : (root.wizardStep === 2
                                ? "Optional: configure Discord, Telegram, or API tabs for notifications and remote control. See the Help tab for setup tutorials."
                                : "Build a farm plan on the Farm Plan tab, or use the legacy brawler picker after START if the queue is empty. Open Help anytime for full guides."))
                    color: theme.muted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
                RowLayout {
                    visible: root.wizardStep === 0
                    spacing: 8
                    Layout.fillWidth: true

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 36
                        radius: 8
                        color: licenseRowMouse.containsMouse ? theme.hover : theme.panel2
                        border.width: 1
                        border.color: root.licenseTermsAccepted ? theme.accentBorder : theme.borderSoft

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 10
                            Rectangle {
                                Layout.preferredWidth: 18
                                Layout.preferredHeight: 18
                                radius: 4
                                color: root.licenseTermsAccepted ? theme.accentSoft : theme.panel
                                border.width: 1
                                border.color: theme.borderSoft
                                Text {
                                    anchors.centerIn: parent
                                    visible: root.licenseTermsAccepted
                                    text: "\u2713"
                                    color: theme.text
                                    font.pixelSize: 11
                                    font.weight: Font.Bold
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "I understand Pyla-RL is free and I will not sell it."
                                color: theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                        }

                        MouseArea {
                            id: licenseRowMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.licenseTermsAccepted = !root.licenseTermsAccepted
                        }
                    }
                }
                Text {
                    visible: root.wizardStep === 0 && !root.licenseTermsAccepted
                    Layout.fillWidth: true
                    text: "Select the agreement above to enable Next."
                    color: theme.faint
                    font.pixelSize: 10
                }
                RowLayout {
                    spacing: 8
                    HubButton {
                        label: "Back"
                        secondary: true
                        visible: root.wizardStep > 0
                        onClicked: root.wizardStep -= 1
                    }
                    HubButton {
                        label: "Run Checks"
                        secondary: true
                        visible: root.wizardStep === 1
                        onClicked: root.runAction("preflight-check")
                    }
                    HubButton {
                        label: "Open Help"
                        secondary: true
                        visible: root.wizardStep >= 2
                        onClicked: {
                            root.showWizard = false
                            root.activeTab = "Help"
                        }
                    }
                    Item { Layout.fillWidth: true }
                    HubButton {
                        label: root.wizardStep < 3 ? "Next" : "Finish"
                        clickable: root.wizardStep !== 0 || root.licenseTermsAccepted
                        onClicked: {
                            if (root.wizardStep === 0) {
                                root.runAction("accept-license")
                                if (hubState.meta && hubState.meta.firstRunWizard) {
                                    root.wizardStep = 1
                                } else {
                                    root.showWizard = false
                                }
                                return
                            }
                            if (root.wizardStep < 3) {
                                root.wizardStep += 1
                            } else {
                                root.runAction("complete-wizard")
                                root.showWizard = false
                            }
                        }
                    }
                }
            }
        }
    }

    TutorialOverlay {}

    Rectangle {
        anchors.fill: parent
        opacity: root.showBrawlerPicker ? 1 : 0
        visible: opacity > 0.01
        color: theme.scrim
        z: 100

        Behavior on opacity { NumberAnimation { duration: root.durFast } }

        MouseArea {
            anchors.fill: parent
            onClicked: root.showBrawlerPicker = false
        }

        Rectangle {
            anchors.centerIn: parent
            width: Math.min(620, root.width - 40)
            height: Math.min(520, root.height - 48)
            radius: 14
            color: theme.panel3
            border.width: 1
            border.color: theme.border
            clip: true
            scale: root.showBrawlerPicker ? 1 : 0.94

            Behavior on scale { NumberAnimation { duration: root.durMed; easing.type: Easing.OutCubic } }

            MouseArea {
                anchors.fill: parent
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 10

                Text {
                    text: "Add Brawler"
                    color: theme.text
                    font.pixelSize: 15
                    font.weight: Font.Bold
                }
                Text {
                    Layout.fillWidth: true
                    text: "Search and click a brawler, then set the trophy target before adding."
                    color: theme.faint
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
                FieldRow {
                    label: "Search"
                    Layout.fillWidth: true
                    ConfigInput {
                        anchors.fill: parent
                        live: true
                        value: root.pickerFilter
                        onSaved: function(value) { root.pickerFilter = value }
                    }
                }
                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded
                    contentWidth: availableWidth
                    contentHeight: pickerGrid.implicitHeight

                    Flow {
                        id: pickerGrid
                        width: parent.width
                        spacing: 8
                        Repeater {
                            model: root.filteredPickerOptions
                            delegate: BrawlerPickTile {
                                name: modelData.name
                                iconSource: modelData.icon
                                selected: root.pickerBrawler === modelData.name
                                onClicked: root.pickerBrawler = modelData.name
                            }
                        }
                    }
                }
                Text {
                    visible: root.filteredPickerOptions.length === 0
                    Layout.fillWidth: true
                    text: "No brawlers match your search."
                    color: theme.faint
                    font.pixelSize: 11
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Text {
                        text: "Target"
                        color: theme.muted
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: root.trophyTargetPresets
                            delegate: ChoicePill {
                                label: modelData
                                selected: root.pickerTarget === modelData
                                onClicked: root.pickerTarget = modelData
                            }
                        }
                    }
                    ConfigInput {
                        Layout.fillWidth: true
                        id: pickerTargetInput
                        value: root.pickerTarget
                        onSaved: function(value) { root.pickerTarget = value }
                    }
                }
                RowLayout {
                    spacing: 8
                    HubButton {
                        label: "Cancel"
                        secondary: true
                        onClicked: root.showBrawlerPicker = false
                    }
                    Item { Layout.fillWidth: true }
                    HubButton {
                        label: "Add"
                        clickable: root.pickerBrawler !== ""
                        onClicked: {
                            var target = root.trophyTargetFromUi(pickerTargetInput.editText, root.pickerTarget)
                            if (target <= 0) {
                                root.statusText = "Enter a valid trophy target."
                                root.statusOk = false
                                return
                            }
                            root.runActionWithPayload("add-to-queue", {
                                brawler: root.pickerBrawler,
                                push_until: target,
                                trophies: 0,
                                wins: 0,
                                type: root.pickerType,
                                automatically_pick: true,
                                selection_method: "named_brawler",
                                win_streak: 0
                            })
                            root.showBrawlerPicker = false
                        }
                    }
                }
            }
        }
    }

    FileDialog {
        id: importQueueDialog
        title: "Import Farm Plan"
        nameFilters: ["JSON files (*.json)", "All files (*)"]
        fileMode: FileDialog.OpenFile
        onAccepted: {
            if (selectedFile) {
                root.runActionWithPayload("import-queue", { path: selectedFile.toString() })
            }
        }
    }

    FileDialog {
        id: exportQueueDialog
        title: "Export Farm Plan"
        nameFilters: ["JSON files (*.json)", "All files (*)"]
        fileMode: FileDialog.SaveFile
        defaultSuffix: "json"
        onAccepted: {
            if (selectedFile) {
                root.runActionWithPayload("export-queue", { path: selectedFile.toString() })
            }
        }
    }
}
