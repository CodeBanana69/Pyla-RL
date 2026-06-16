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
    title: settingsOnly ? root.t("app.settings_title") : root.t("app.hub_title")
    color: theme.bg
    flags: Qt.FramelessWindowHint | Qt.Window

    property string mode: hubBridge ? hubBridge.mode() : "showdown-trio"
    property string emulator: hubBridge ? hubBridge.emulator() : "ldplayer"
    property string activeTab: "Overview"
    property var hubState: ({ settings: {}, discord: {}, telegram: {}, api: {}, timers: {}, history: { items: [], summary: {}, recent: [] }, queue: [], preflight: { ready: false, checks: [] }, updateStatus: { status: "unknown" } })
    property var preflightChecks: []
    property string statusText: ""
    property bool statusOk: true
    property string performanceProfile: "balanced"
    property string settingsFilter: ""
    property bool hubBusy: false
    property bool hubStateReady: false
    property bool showWizard: false
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
    property string language: (hubState.language !== undefined) ? hubState.language : "en"
    property string bootTab: (typeof initialTab !== "undefined" && initialTab) ? initialTab : ""
    readonly property var queueSortOptions: [
        { id: "cups_desc", label: root.t("sort.cups_desc") },
        { id: "cups_asc", label: root.t("sort.cups_asc") },
        { id: "gap_asc", label: root.t("sort.gap_asc") },
        { id: "gap_desc", label: root.t("sort.gap_desc") },
        { id: "target_desc", label: root.t("sort.target_desc") },
        { id: "target_asc", label: root.t("sort.target_asc") },
        { id: "name_asc", label: root.t("sort.name_asc") },
        { id: "name_desc", label: root.t("sort.name_desc") },
        { id: "efficiency", label: root.t("sort.efficiency") }
    ]

    function t(key, replacements) {
        var strings = hubState.strings || {}
        var template = strings[key]
        if (template === undefined || template === null || template === "") {
            template = key
        }
        if (!replacements) {
            return template
        }
        var text = String(template)
        for (var name in replacements) {
            text = text.replace("{" + name + "}", replacements[name])
        }
        return text
    }

    readonly property string updatePillStatus: (hubState.updateStatus && hubState.updateStatus.status)
        ? hubState.updateStatus.status
        : "unknown"

    function updateStatusValue() {
        return updatePillStatus
    }

    function updatePillLabel() {
        var status = updatePillStatus
        if (status === "available") {
            return t("update.pill_available")
        }
        if (status === "current") {
            return t("update.pill_ok")
        }
        return t("update.pill_unknown")
    }

    function updatePillGlyph() {
        if (updatePillStatus === "available") {
            return "\u2B06"
        }
        if (updatePillStatus === "current") {
            return "\u2713"
        }
        return "\u21BB"
    }

    function updatePillDotColor() {
        if (updatePillStatus === "current") {
            return theme.ok
        }
        if (updatePillStatus === "available") {
            return theme.accent
        }
        return theme.muted
    }

    function updatePillTooltip() {
        var status = updateStatusValue()
        if (status === "available") {
            return t("update.tooltip_available")
        }
        if (status === "current") {
            return t("update.tooltip_current")
        }
        return t("update.tooltip_unknown")
    }

    function updatePopoverHeadline() {
        var status = updateStatusValue()
        if (status === "available") {
            return t("update.status_available")
        }
        if (status === "current") {
            return t("update.status_current")
        }
        return t("update.status_unknown")
    }

    function tabKey(tab) {
        if (tab === "Overview") return "nav.overview"
        if (tab === "Instances") return "nav.instances"
        if (tab === "Farm Plan") return "nav.farm_plan"
        if (tab === "Settings") return "nav.settings"
        if (tab === "Discord") return "nav.discord"
        if (tab === "Telegram") return "nav.telegram"
        if (tab === "API") return "nav.api"
        if (tab === "Timers") return "nav.timers"
        if (tab === "Match History") return "nav.match_history"
        if (tab === "Help") return "nav.help"
        return tab
    }

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
        root.restartBackdropMotion()
    }

    function restartBackdropMotion() {
        if (typeof backdropCanvas === "undefined" || !backdropCanvas) {
            return
        }
        backdropCanvas.requestPaint()
        if (root.animationsEnabled) {
            backdropFade.restart()
            paletteCycle.restart()
        } else {
            backdropCanvas.opacity = 1
        }
    }

    function setLanguage(code) {
        root.saveValue("settings", "ui_language", code)
        root.reloadState()
        root.applyTheme()
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
            return count > 0 ? root.t("nav.farm_plan_count", { count: count }) : root.t("nav.farm_plan")
        }
        return root.t(root.tabKey(tab))
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
            if (root.statusOk && !root.hubBusy) {
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
            statusToastTimer.stop()
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
        if (!item || !item.readiness) return root.t("common.unknown")
        const status = item.readiness.status || ""
        if (status === "ready") return root.t("common.ready")
        if (status === "needs_farm_plan") return root.t("instances.needs_farm_plan")
        if (status === "port_conflict") return root.t("instances.port_conflict")
        if (status === "no_emulator") return root.t("instances.no_emulator")
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
            statusText = root.t("common.saved")
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
        if (root.hubBusy) {
            statusText = root.t("msg.hub_action_busy")
            statusOk = false
            return
        }
        statusText = root.t("msg.working")
        statusOk = true
        const result = applyBridgeResult(hubBridge.runAction(action))
        if (result.ok && !result.pending) {
            statusToastTimer.restart()
        }
    }

    function runActionWithPayload(action, payload) {
        if (root.hubBusy) {
            statusText = root.t("msg.hub_action_busy")
            statusOk = false
            return
        }
        statusText = root.t("msg.working")
        statusOk = true
        const result = applyBridgeResult(hubBridge.runActionWithPayload(action, JSON.stringify(payload || {})))
        if (result.ok && !result.pending) {
            statusToastTimer.restart()
        }
    }

    function startBot() {
        if (root.hubBusy) {
            statusText = root.t("msg.hub_action_busy")
            statusOk = false
            return
        }
        if (!(hubState.preflight && hubState.preflight.ready)) {
            root.activeTab = "Overview"
            statusText = root.t("msg.run_preflight_before_start")
            statusOk = false
            return
        }
        statusText = root.t("msg.checking_preflight")
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

    function syncWizardVisibility() {
        if (settingsOnly) {
            showWizard = false
            return
        }
        if (!hubStateReady) {
            showWizard = false
            return
        }
        const needsLicense = !(hubState.meta && hubState.meta.licenseAccepted)
        const needsWizard = !!(hubState.meta && hubState.meta.firstRunWizard)
        showWizard = needsLicense || needsWizard
        wizardStep = needsLicense ? 0 : 1
    }

    Component.onCompleted: {
        applyTheme()
        reloadState()
        hubStateReady = true
        if (bootTab !== "") {
            activeTab = bootTab
        }
        if (typeof hubCaptureMode !== "undefined" && hubCaptureMode) {
            Qt.callLater(function() {
                animationsEnabled = false
            })
        }
        runAction("ensure-brawler-icons")
        if (settingsOnly) {
            activeTab = "Farm Plan"
            return
        }
        syncWizardVisibility()
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
        function onUpdateStatusRefreshed() {
            reloadState()
        }
        function onStateChanged(nextMode, nextEmulator) {
            root.mode = nextMode
            root.emulator = nextEmulator
            reloadState()
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
        Behavior on glowA { ColorAnimation { duration: root.durSlow } }
        Behavior on glowB { ColorAnimation { duration: root.durSlow } }
        Behavior on glowC { ColorAnimation { duration: root.durSlow } }
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
        property bool _programmaticText: false
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
            onTextChanged: {
                if (inputBox._programmaticText || !inputBox.live) {
                    return
                }
                if (text !== inputBox.value) {
                    inputBox.saved(text)
                }
            }
            onEditingFinished: if (!inputBox.live) inputBox.saved(text)
        }

        Component.onCompleted: field.text = inputBox.value

        onValueChanged: {
            if (field.text !== inputBox.value) {
                inputBox._programmaticText = true
                field.text = inputBox.value
                inputBox._programmaticText = false
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
                text: inputBox.revealed ? root.t("common.hide") : root.t("common.show")
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
                    text: topic ? topic.title : root.t("common.guide")
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
                        label: root.t("common.open_full_guide")
                        secondary: true
                        visible: !!(topic && topic.doc)
                        onClicked: {
                            root.openTutorialDoc(topic.doc)
                            root.closeTutorial()
                        }
                    }
                    HubButton {
                        label: root.t("common.close_panel")
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
                    text: root.t("common.active")
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
                                text: root.t("common.custom")
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

        function settleForCapture() {
            farmPageBody.opacity = 1
            farmPageShift.y = 0
        }

        onVisibleChanged: {
            if (!visible) {
                return
            }
            if (typeof hubCaptureMode !== "undefined" && hubCaptureMode) {
                settleForCapture()
                return
            }
            farmEnterAnim.restart()
        }

        Component.onCompleted: {
            if (visible && typeof hubCaptureMode !== "undefined" && hubCaptureMode) {
                settleForCapture()
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
                        text: root.t("common.editing_farm_plan_for")
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
                        text: root.t("common.other_instances_hint")
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
                            text: root.t("common.push_all")
                            color: theme.text
                            font.pixelSize: 12
                            font.weight: Font.Bold
                        }
                        Item { Layout.fillWidth: true }
                        TutorialHelpButton { tutorialId: "farm-plan" }
                        HubButton {
                            label: root.t("common.tutorial")
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
                        label: root.t("common.custom_target")
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
                            label: root.t("common.build_queue")
                            compact: true
                            enabled: !root.hubBusy
                            onClicked: {
                                var target = root.trophyTargetFromUi(pushAllTargetInput.editText, root.pushAllTarget)
                                if (target <= 0) {
                                    root.statusText = root.t("common.enter_valid_target")
                                    root.statusOk = false
                                    return
                                }
                                root.runActionWithPayload("build-push-all", { target: target })
                            }
                        }
                        HubButton { label: root.t("common.import"); secondary: true; compact: true; onClicked: importQueueDialog.open() }
                        HubButton {
                            label: root.t("common.export")
                            secondary: true
                            compact: true
                            onClicked: {
                                if (!(root.hubState.queue && root.hubState.queue.length)) {
                                    root.statusText = root.t("common.farm_plan_empty")
                                    root.statusOk = false
                                    return
                                }
                                exportQueueDialog.open()
                            }
                        }
                        HubButton {
                            id: queueSortButton
                            label: root.t("common.sort")
                            secondary: true
                            compact: true
                            onClicked: {
                                if (!(root.hubState.queue && root.hubState.queue.length)) {
                                    root.statusText = root.t("common.farm_plan_empty")
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
                                    text: root.t("common.sort_farm_plan")
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
                        HubButton { label: root.t("common.clear"); secondary: true; compact: true; onClicked: root.runAction("clear-queue") }
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
                            text: root.t("common.queue")
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
                            label: root.t("common.refresh")
                            secondary: true
                            compact: true
                            onClicked: root.reloadState()
                        }
                        HubButton {
                            label: root.t("common.add")
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
                                text: root.t("common.no_brawlers_in_plan")
                                color: theme.muted
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: root.t("common.build_queue_hint")
                                color: theme.faint
                                font.pixelSize: 11
                            }
                            HubButton {
                                Layout.alignment: Qt.AlignHCenter
                                label: root.t("common.add_brawler")
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
            opacity: 0

            property real driftA: 0
            property real driftB: 0
            property real driftC: 0
            property real colorBlend: 0
            property int paletteIndex: 0

            readonly property var paletteSets: [
                [theme.glowA, theme.glowB, theme.glowC, theme.accent],
                [theme.accent, theme.glowC, theme.glowB, theme.link],
                [theme.glowB, theme.link, theme.glowA, theme.glowC],
                [theme.glowC, theme.glowA, theme.link, theme.accent]
            ]

            function mixColor(from, to, amount) {
                const t = Math.max(0, Math.min(1, amount))
                return Qt.rgba(
                    from.r + (to.r - from.r) * t,
                    from.g + (to.g - from.g) * t,
                    from.b + (to.b - from.b) * t,
                    from.a + (to.a - from.a) * t
                )
            }

            function paletteColor(slot, fallback) {
                const sets = paletteSets
                if (!sets.length) {
                    return fallback
                }
                const current = sets[paletteIndex % sets.length]
                const next = sets[(paletteIndex + 1) % sets.length]
                const from = current[slot % current.length]
                const to = next[slot % next.length]
                return mixColor(from, to, colorBlend)
            }

            function paintGlow(ctx, x, y, radius, glowColor, alphaScale) {
                const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius)
                const core = Qt.rgba(glowColor.r, glowColor.g, glowColor.b, alphaScale)
                gradient.addColorStop(0, String(core))
                gradient.addColorStop(0.42, String(Qt.rgba(glowColor.r, glowColor.g, glowColor.b, alphaScale * 0.35)))
                gradient.addColorStop(1, String(Qt.rgba(glowColor.r, glowColor.g, glowColor.b, 0)))
                ctx.fillStyle = gradient
                ctx.beginPath()
                ctx.arc(x, y, radius, 0, Math.PI * 2)
                ctx.fill()
            }

            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onDriftAChanged: if (root.animationsEnabled) requestPaint()
            onDriftBChanged: if (root.animationsEnabled) requestPaint()
            onDriftCChanged: if (root.animationsEnabled) requestPaint()
            onColorBlendChanged: requestPaint()
            onPaletteIndexChanged: requestPaint()

            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                const span = Math.max(width, height)
                const baseAlpha = root.resolvedTheme === "light" ? 0.24 : 0.17

                const x1 = width * (0.12 + 0.14 * Math.sin(driftA))
                const y1 = height * (0.10 + 0.12 * Math.cos(driftA * 0.85))
                const x2 = width * (0.88 + 0.10 * Math.cos(driftB * 1.1))
                const y2 = height * (0.86 + 0.11 * Math.sin(driftB))
                const x3 = width * (0.72 + 0.16 * Math.sin(driftC * 0.7))
                const y3 = height * (0.18 + 0.13 * Math.cos(driftC))
                const x4 = width * (0.38 + 0.12 * Math.cos(driftA * 0.6 + driftB * 0.4))
                const y4 = height * (0.62 + 0.10 * Math.sin(driftC * 1.15))

                paintGlow(ctx, x1, y1, span * 0.58, paletteColor(0, theme.glowA), baseAlpha)
                paintGlow(ctx, x2, y2, span * 0.62, paletteColor(1, theme.glowB), baseAlpha * 0.95)
                paintGlow(ctx, x3, y3, span * 0.42, paletteColor(2, theme.glowC), baseAlpha * 0.88)
                paintGlow(ctx, x4, y4, span * 0.36, paletteColor(3, theme.accent), baseAlpha * 0.72)
            }

            NumberAnimation {
                id: driftAnimA
                target: backdropCanvas
                property: "driftA"
                from: 0
                to: Math.PI * 2
                duration: 24000
                loops: Animation.Infinite
                running: root.animationsEnabled
            }

            NumberAnimation {
                id: driftAnimB
                target: backdropCanvas
                property: "driftB"
                from: 0
                to: Math.PI * 2
                duration: 31000
                loops: Animation.Infinite
                running: root.animationsEnabled
            }

            NumberAnimation {
                id: driftAnimC
                target: backdropCanvas
                property: "driftC"
                from: 0
                to: Math.PI * 2
                duration: 27000
                loops: Animation.Infinite
                running: root.animationsEnabled
            }

            SequentialAnimation {
                id: paletteCycle
                running: root.animationsEnabled
                loops: Animation.Infinite

                NumberAnimation {
                    target: backdropCanvas
                    property: "colorBlend"
                    from: 0
                    to: 1
                    duration: 7000
                    easing.type: Easing.InOutSine
                }
                ScriptAction {
                    script: {
                        backdropCanvas.paletteIndex = (backdropCanvas.paletteIndex + 1) % 4
                        backdropCanvas.colorBlend = 0
                    }
                }
                PauseAnimation { duration: 1200 }
            }

            Timer {
                id: backdropFrameTimer
                interval: 32
                running: root.animationsEnabled
                repeat: true
                onTriggered: backdropCanvas.requestPaint()
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

            Component.onCompleted: {
                requestPaint()
                if (!root.animationsEnabled) {
                    opacity = 1
                }
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
                        text: settingsOnly ? root.t("app.settings_running") : root.t("app.hub_title")
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
                    Row {
                        spacing: 2
                        Repeater {
                            model: ["en", "ru"]
                            delegate: Rectangle {
                                width: 28
                                height: 28
                                radius: 8
                                color: langMouse.containsMouse ? theme.hover : (root.language === modelData ? theme.accentSoft : "transparent")
                                border.width: root.language === modelData ? 1 : 0
                                border.color: theme.accentBorder

                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.toUpperCase()
                                    color: root.language === modelData ? theme.text : theme.muted
                                    font.pixelSize: 10
                                    font.weight: Font.Bold
                                }

                                MouseArea {
                                    id: langMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.setLanguage(modelData)
                                }

                                ToolTip.visible: langMouse.containsMouse
                                ToolTip.delay: 500
                                ToolTip.text: root.t("language.tooltip")
                            }
                        }
                    }
                    Rectangle {
                        id: updatePill
                        z: 2
                        width: Math.max(updatePillRow.implicitWidth + 16, 62)
                        height: 28
                        radius: 8
                        color: {
                            if (root.updatePillStatus === "available") {
                                return updateMouse.containsMouse ? theme.accentSoft : theme.warnSoft
                            }
                            if (updateMouse.containsMouse) {
                                return theme.hover
                            }
                            return theme.panel2
                        }
                        border.width: 1
                        border.color: root.updatePillStatus === "available" ? theme.accentBorder : theme.borderSoft

                        Row {
                            id: updatePillRow
                            anchors.centerIn: parent
                            spacing: 5
                            Rectangle {
                                width: 6
                                height: 6
                                radius: 3
                                color: root.updatePillDotColor()
                            }
                            Text {
                                text: root.updatePillGlyph()
                                color: root.updatePillStatus === "available" ? theme.accent : theme.muted
                                font.pixelSize: 11
                                font.weight: Font.Bold
                            }
                            Text {
                                text: root.updatePillLabel()
                                color: root.updatePillStatus === "available" ? theme.accent : theme.text
                                font.pixelSize: 10
                                font.weight: Font.DemiBold
                            }
                        }

                        MouseArea {
                            id: updateMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: updatePopover.open()
                        }

                        ToolTip.visible: updateMouse.containsMouse
                        ToolTip.delay: 500
                        ToolTip.text: root.updatePillTooltip()
                    }
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
                        ToolTip.text: root.t("common.theme_tooltip", { mode: root.themeMode })

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
                    visible: correctZoom === false
                    text: root.t("common.scaling_warning")
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
                        title: root.t("instances.multi_instance_title")
                        tutorialId: "multi-instance"
                        Text {
                            Layout.fillWidth: true
                            text: root.t("instances.multi_instance_hint")
                            color: theme.faint
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        FieldRow {
                            label: root.t("instances.enable_multi_instance")
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
                            label: root.t("instances.auto_restart_crashed")
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
                            text: root.t("instances.single_instance_hint")
                            color: theme.faint
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: !!(hubState.multiInstance && hubState.multiInstance.enabled)
                            text: root.t("instances.multi_instance_active_hint")
                            color: theme.ok
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        ActionRow {
                            HubButton { label: root.t("instances.scan_emulators"); secondary: true; visible: !!(hubState.multiInstance && hubState.multiInstance.enabled); onClicked: applyBridgeResult(hubBridge.listAvailableEmulators()) }
                            HubButton { label: root.t("common.refresh"); secondary: true; onClicked: applyBridgeResult(hubBridge.refreshInstances()) }
                            HubButton { label: root.t("instances.start_all_ready"); visible: !!(hubState.multiInstance && hubState.multiInstance.enabled); onClicked: applyBridgeResult(hubBridge.startAllReadyInstances()) }
                            HubButton { label: root.t("instances.stop_all"); secondary: true; visible: !!(hubState.multiInstance && hubState.multiInstance.enabled); onClicked: applyBridgeResult(hubBridge.stopAllInstances()) }
                            HubButton { label: root.t("instances.align_windows"); secondary: true; visible: !!(hubState.multiInstance && hubState.multiInstance.enabled); onClicked: applyBridgeResult(hubBridge.alignWindows()) }
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
                        title: root.t("instances.quick_setup_title")
                        visible: !!(hubState.multiInstance && hubState.multiInstance.enabled) && root.showMultiInstanceSetup && !hubState.multiInstance.setupWizardDismissed
                        Text {
                            Layout.fillWidth: true
                            text: root.t("instances.quick_setup_steps")
                            color: theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            Layout.fillWidth: true
                            text: root.t("instances.unassigned_emulators", { count: String((hubState.multiInstance.unassignedEmulators || []).length) })
                            color: theme.faint
                            font.pixelSize: 11
                        }
                        ActionRow {
                            HubButton { label: root.t("instances.quick_add_all_unassigned"); onClicked: root.quickAddUnassignedInstances() }
                            HubButton { label: root.t("common.done"); secondary: true; onClicked: root.dismissMultiInstanceSetup() }
                        }
                    }

                    FormPanel {
                        title: root.t("instances.add_instance_title")
                        visible: !!(hubState.multiInstance && hubState.multiInstance.enabled)
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            ActionRow {
                                HubButton { label: root.t("instances.quick_add_all_unassigned"); onClicked: root.quickAddUnassignedInstances() }
                                HubButton { label: showAddInstanceForm ? root.t("instances.hide_manual_form") : root.t("instances.manual_add"); secondary: true; onClicked: showAddInstanceForm = !showAddInstanceForm }
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
                                        label: root.t("common.use")
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
                                    label: root.t("instances.detected_emulator")
                                    visible: root.instanceFormEmulatorName !== ""
                                    Text {
                                        text: root.instanceFormEmulatorName + " · port " + root.instanceFormPort
                                        color: theme.muted
                                        font.pixelSize: 11
                                    }
                                }
                                FieldRow {
                                    label: root.t("instances.instance_id")
                                    ConfigInput { anchors.fill: parent; live: true; value: root.instanceFormId; onSaved: function(value) { root.instanceFormId = value } }
                                }
                                FieldRow {
                                    label: root.t("instances.display_name")
                                    ConfigInput { anchors.fill: parent; live: true; value: root.instanceFormName; onSaved: function(value) { root.instanceFormName = value } }
                                }
                                FieldRow {
                                    label: root.t("instances.player_tag")
                                    ConfigInput { anchors.fill: parent; live: true; value: root.instanceFormPlayerTag; onSaved: function(value) { root.instanceFormPlayerTag = value } }
                                }
                                HubButton {
                                    label: showAdvancedInstanceForm ? root.t("instances.hide_advanced") : root.t("instances.advanced")
                                    secondary: true
                                    onClicked: showAdvancedInstanceForm = !showAdvancedInstanceForm
                                }
                                ColumnLayout {
                                    visible: showAdvancedInstanceForm
                                    spacing: 8
                                    FieldRow {
                                        label: root.t("overview.emulator_title")
                                        RowLayout {
                                            anchors.fill: parent
                                            spacing: 8
                                            HubButton { label: root.t("game.ldplayer"); secondary: root.instanceFormEmulator !== "ldplayer"; onClicked: root.setInstanceFormEmulator("ldplayer") }
                                            HubButton { label: root.t("game.mumu"); secondary: root.instanceFormEmulator !== "mumu"; onClicked: root.setInstanceFormEmulator("mumu") }
                                        }
                                    }
                                    FieldRow {
                                        label: root.t("instances.adb_port")
                                        ConfigInput { anchors.fill: parent; live: true; value: root.instanceFormPort; onSaved: function(value) { root.instanceFormPort = value } }
                                    }
                                }
                                ActionRow {
                                    HubButton { label: root.t("instances.save_instance"); onClicked: root.saveNewInstance() }
                                }
                            }
                        }
                    }

                    FormPanel {
                        title: root.t("instances.configured_instances_title")
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
                                                ToolTip.text: (modelData.health && modelData.health.message) ? modelData.health.message : root.t("common.health_unknown")
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
                                                text: root.t("common.recent_recoveries")
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
                                            HubButton { label: root.t("common.start_instance"); visible: !modelData.running; onClicked: applyBridgeResult(hubBridge.startInstance(modelData.id)) }
                                            HubButton { label: root.t("common.stop"); secondary: true; visible: !!modelData.running; onClicked: applyBridgeResult(hubBridge.stopInstance(modelData.id)) }
                                            HubButton { label: root.t("common.restart"); secondary: true; visible: !!modelData.running; onClicked: applyBridgeResult(hubBridge.restartInstance(modelData.id)) }
                                            HubButton { label: root.t("instances.edit_farm_plan"); secondary: true; onClicked: root.editInstanceFarmPlan(modelData.id) }
                                            HubButton {
                                                label: root.t("instances.copy_default_plan")
                                                secondary: true
                                                visible: !!(modelData.readiness && modelData.readiness.status === "needs_farm_plan" && modelData.readiness.can_copy_default)
                                                onClicked: root.copyInstanceFarmPlan(modelData.id)
                                            }
                                            HubButton {
                                                label: root.t("common.delete")
                                                secondary: true
                                                visible: modelData.id !== String((hubState.multiInstance && hubState.multiInstance.defaultInstance) || "default")
                                                onClicked: applyBridgeResult(hubBridge.deleteInstanceProfile(modelData.id))
                                            }
                                        }
                                        Text {
                                            text: root.t("instances.match_notifications")
                                            color: theme.faint
                                            font.pixelSize: 10
                                            font.bold: true
                                        }
                                        FieldRow {
                                            label: root.t("instances.webhook_url")
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
                                            label: root.t("instances.ping_discord_id")
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
                                                label: root.t("instances.test_webhook")
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
                        title: root.t("common.unofficial_copy")
                        Text {
                            Layout.fillWidth: true
                            text: (hubBrand ? hubBrand.freeNotice : root.t("settings.license_line", { notice: "Pyla-RL is free.", license: "CC BY-NC 4.0" })) + " " + root.t("common.download_official")
                            color: theme.accent
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                        }
                        ActionRow {
                            HubButton { label: root.t("common.official_github"); secondary: true; onClicked: hubBridge.openOfficialRepo() }
                            HubButton { label: root.t("common.pyla_discord"); secondary: true; onClicked: hubBridge.openDiscord() }
                        }
                    }

                    FormPanel {
                        title: root.t("overview.preflight_title")
                        tutorialId: "overview"
                        Text {
                            Layout.fillWidth: true
                            text: root.t("overview.preflight_hint")
                            color: theme.faint
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        RowLayout {
                            spacing: 10
                            HubButton { label: root.t("common.run_checks"); secondary: true; enabled: !root.hubBusy; onClicked: root.runAction("preflight-check") }
                            HubButton { label: root.t("common.test_connection"); secondary: true; enabled: !root.hubBusy; onClicked: root.runAction("test-emulator") }
                            HubButton { label: root.t("common.recovery_log"); secondary: true; onClicked: root.runAction("read-recovery-log") }
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
                                        enabled: !root.hubBusy
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
                        title: root.t("overview.performance_title")
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
                        title: root.t("overview.game_mode_title")
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: 12
                            rowSpacing: 12
                            OptionCard {
                                Layout.fillWidth: true
                                label: root.t("game.brawl_ball")
                                selected: root.mode === "brawl-ball"
                                onClicked: hubBridge.updateSetting("mode", "brawl-ball")
                            }
                            OptionCard {
                                Layout.fillWidth: true
                                label: root.t("game.showdown_trio")
                                selected: root.mode === "showdown-trio"
                                onClicked: hubBridge.updateSetting("mode", "showdown-trio")
                            }
                        }
                    }

                    FormPanel {
                        title: root.t("overview.emulator_title")
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            OptionCard {
                                Layout.fillWidth: true
                                label: root.t("game.ldplayer")
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
                                label: root.t("game.mumu")
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
                        title: root.t("settings.hub_title")
                        tutorialId: "settings"
                        FieldRow {
                            label: root.t("settings.search_settings")
                            pinnedInSettingsSearch: true
                            ConfigInput {
                                anchors.fill: parent
                                live: true
                                value: root.settingsFilter
                                onSaved: function(value) { root.settingsFilter = value }
                            }
                        }
                        ActionRow {
                            HubButton { label: root.t("common.open_cfg_folder"); secondary: true; onClicked: root.runAction("open-config-folder") }
                            HubButton {
                                label: root.t("common.show_setup_wizard_again")
                                secondary: true
                                onClicked: root.runAction("reset-setup-wizard")
                            }
                        }
                    }

                    FormPanel {
                        title: root.t("settings.appearance_title")
                        FieldRow {
                            label: root.t("language.label")
                            hint: root.t("language.restart_hint")
                            Row {
                                spacing: 8
                                Repeater {
                                    model: ["en", "ru"]
                                    delegate: ChoicePill {
                                        label: modelData.toUpperCase()
                                        selected: root.language === modelData
                                        onClicked: root.setLanguage(modelData)
                                    }
                                }
                            }
                        }
                        FieldRow {
                            label: root.t("theme.label")
                            hint: root.t("theme.hint")
                            Row {
                                spacing: 8
                                Repeater {
                                    model: ["light", "dark", "system"]
                                    delegate: ChoicePill {
                                        label: root.t("theme." + modelData)
                                        selected: root.themeMode === modelData
                                        onClicked: root.setThemeMode(modelData)
                                    }
                                }
                            }
                        }
                        FieldRow {
                            label: root.t("settings.ui_animations")
                            hint: root.t("settings.ui_animations_hint")
                            CenterRow { ToggleSwitch { checked: root.animationsEnabled; onToggled: function(value) { root.setAnimationsEnabled(value) } } }
                        }
                    }

                    FormPanel {
                        title: root.t("settings.about_title")
                        Text {
                            Layout.fillWidth: true
                            text: root.t("settings.version_line", {
                                product: (hubBrand ? hubBrand.productName : "Pyla-RL"),
                                version: hubVersion,
                                commit: ((hubState.meta && hubState.meta.buildInfo && hubState.meta.buildInfo.commit) ? hubState.meta.buildInfo.commit : root.t("common.unknown"))
                            })
                            color: theme.text
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                        }
                        Text {
                            Layout.fillWidth: true
                            text: hubBrand
                                ? ((hubBrand.freeNotice) + " Licensed under " + hubBrand.licenseName + ".")
                                : root.t("settings.license_line", { notice: "Pyla-RL is free.", license: "CC BY-NC 4.0" })
                            color: theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            visible: root.unofficialCopy
                            Layout.fillWidth: true
                            text: (hubState.meta && hubState.meta.sourceStatus) ? hubState.meta.sourceStatus.reason : root.t("settings.unofficial_detected")
                            color: theme.accent
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        ActionRow {
                            HubButton { label: root.t("common.official_github"); secondary: true; onClicked: hubBridge.openOfficialRepo() }
                            HubButton { label: root.t("common.pyla_discord"); secondary: true; onClicked: hubBridge.openDiscord() }
                            HubButton { label: root.t("common.check_updates"); secondary: true; onClicked: root.runAction("check-updates") }
                            HubButton { label: root.t("common.report_reseller"); secondary: true; onClicked: root.runAction("report-reseller") }
                        }
                        RowLayout {
                            visible: root.hubStateReady && !root.licenseAccepted
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
                                text: root.t("wizard.license_checkbox")
                                color: theme.muted
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                            HubButton {
                                label: root.t("common.accept")
                                clickable: root.licenseTermsAccepted
                                onClicked: root.runAction("accept-license")
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: root.t("settings.patreon_hint")
                            color: theme.faint
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }
                    }

                    FormPanel {
                        title: root.t("settings.detection_title")
                        FieldRow {
                            label: root.t("settings.close_tile_detector")
                            hint: root.t("settings.close_tile_detector_hint")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "close_tile_detector_enabled"); onToggled: function(value) { root.saveValue("settings", "close_tile_detector_enabled", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.wall_confidence")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "wall_detection_confidence")); from: 0.1; to: 1.0; onSaved: function(value) { root.saveValue("settings", "wall_detection_confidence", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.player_confidence")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "entity_detection_confidence")); from: 0.1; to: 1.0; onSaved: function(value) { root.saveValue("settings", "entity_detection_confidence", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.super_pixels")
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "super_pixels_minimum")); onSaved: function(value) { root.saveValue("settings", "super_pixels_minimum", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.gadget_pixels")
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "gadget_pixels_minimum")); onSaved: function(value) { root.saveValue("settings", "gadget_pixels_minimum", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.hypercharge_pixels")
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "hypercharge_pixels_minimum")); onSaved: function(value) { root.saveValue("settings", "hypercharge_pixels_minimum", value) } }
                        }
                    }

                    FormPanel {
                        title: root.t("settings.behavior_title")
                        FieldRow {
                            label: root.t("settings.minimum_movement_delay")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "minimum_movement_delay")); from: 0.05; to: 3.0; onSaved: function(value) { root.saveValue("settings", "minimum_movement_delay", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.unstuck_delay")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "unstuck_movement_delay")); from: 0.5; to: 10.0; onSaved: function(value) { root.saveValue("settings", "unstuck_movement_delay", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.unstuck_duration")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "unstuck_movement_hold_time")); from: 0.2; to: 5.0; onSaved: function(value) { root.saveValue("settings", "unstuck_movement_hold_time", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.after_round")
                            Row { spacing: 8; ChoicePill { label: root.t("common.return_to_lobby"); selected: root.value("settings", "post_match_action") === "lobby"; onClicked: root.saveValue("settings", "post_match_action", "lobby") } ChoicePill { label: root.t("common.play_again"); selected: root.value("settings", "post_match_action") === "play_again"; onClicked: root.saveValue("settings", "post_match_action", "play_again") } }
                        }
                        FieldRow {
                            label: root.t("settings.play_again_on_win")
                            hint: root.t("settings.play_again_on_win_hint")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "play_again_on_win"); onToggled: function(value) { root.saveValue("settings", "play_again_on_win", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.use_gadgets")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "bot_uses_gadgets"); onToggled: function(value) { root.saveValue("settings", "bot_uses_gadgets", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.enemy_spacing")
                            hint: root.t("settings.enemy_spacing_hint")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "enemy_spacing_enabled"); onToggled: function(value) { root.saveValue("settings", "enemy_spacing_enabled", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.spacing_aggression")
                            hint: root.t("settings.spacing_aggression_hint")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "enemy_spacing_blend")); from: 0.0; to: 1.0; onSaved: function(value) { root.saveValue("settings", "enemy_spacing_blend", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.spacing_tolerance")
                            hint: root.t("settings.spacing_tolerance_hint")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "enemy_spacing_tolerance")); from: 10.0; to: 120.0; onSaved: function(value) { root.saveValue("settings", "enemy_spacing_tolerance", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.strafe_in_range")
                            hint: root.t("settings.strafe_in_range_hint")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "enemy_spacing_hold_strafe"); onToggled: function(value) { root.saveValue("settings", "enemy_spacing_hold_strafe", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.multi_enemy_threat")
                            hint: root.t("settings.multi_enemy_threat_hint")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "multi_enemy_flee_weight")); from: 0.0; to: 1.0; onSaved: function(value) { root.saveValue("settings", "multi_enemy_flee_weight", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.dodge_under_fire")
                            hint: root.t("settings.dodge_under_fire_hint")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "combat_los_dodge_enabled"); onToggled: function(value) { root.saveValue("settings", "combat_los_dodge_enabled", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.dodge_blend")
                            hint: root.t("settings.dodge_blend_hint")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "combat_dodge_blend")); from: 0.0; to: 1.0; onSaved: function(value) { root.saveValue("settings", "combat_dodge_blend", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.dodge_jitter")
                            hint: root.t("settings.dodge_jitter_hint")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "combat_dodge_jitter_degrees")); from: 5.0; to: 45.0; onSaved: function(value) { root.saveValue("settings", "combat_dodge_jitter_degrees", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.dodge_commit")
                            hint: root.t("settings.dodge_commit_hint")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "combat_dodge_commit_seconds")); from: 0.2; to: 2.0; onSaved: function(value) { root.saveValue("settings", "combat_dodge_commit_seconds", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.smart_aim")
                            hint: root.t("settings.smart_aim_hint")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "smart_aim_enabled"); onToggled: function(value) { root.saveValue("settings", "smart_aim_enabled", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.attack_interval")
                            hint: root.t("settings.attack_interval_hint")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "attack_min_interval")); from: 0.1; to: 1.0; onSaved: function(value) { root.saveValue("settings", "attack_min_interval", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.projectile_speed")
                            hint: root.t("settings.projectile_speed_hint")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "projectile_speed_px_s")); from: 400.0; to: 2400.0; onSaved: function(value) { root.saveValue("settings", "projectile_speed_px_s", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.run_for_minutes")
                            hint: root.t("settings.run_for_minutes_hint")
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "run_for_minutes")); onSaved: function(value) { root.saveValue("settings", "run_for_minutes", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.emulator_auto_restart")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "emulator_autorestart"); onToggled: function(value) { root.saveValue("settings", "emulator_autorestart", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.trio_movement")
                            Row { spacing: 8; ChoicePill { label: root.t("common.follow"); selected: root.value("settings", "showdown_playstyle_mode") === "follow"; onClicked: root.saveValue("settings", "showdown_playstyle_mode", "follow") } ChoicePill { label: root.t("common.hide_mode"); selected: root.value("settings", "showdown_playstyle_mode") === "hide"; onClicked: root.saveValue("settings", "showdown_playstyle_mode", "hide") } }
                        }
                        FieldRow {
                            label: root.t("settings.longpress_star_drop")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "long_press_star_drop"); onToggled: function(value) { root.saveValue("settings", "long_press_star_drop", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.save_terminal_log")
                            hint: root.t("settings.save_terminal_log_hint")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "terminal_logging"); onToggled: function(value) { root.saveValue("settings", "terminal_logging", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.terminal_verbosity")
                            hint: root.t("settings.terminal_verbosity_hint")
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
                            label: root.t("settings.movement_debug")
                            hint: root.t("settings.movement_debug_hint")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "movement_debug"); onToggled: function(value) { root.saveValue("settings", "movement_debug", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.debug_screen")
                            hint: root.t("settings.debug_screen_hint")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "visual_debug"); onToggled: function(value) { root.saveValue("settings", "visual_debug", value); statusText = root.t("settings.debug_screen_restart"); statusOk = true; statusToastTimer.restart() } } }
                        }
                        FieldRow {
                            label: root.t("settings.advanced_visuals")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "advanced_visuals"); onToggled: function(value) { root.saveValue("settings", "advanced_visuals", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.pause_ips_graph")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "pause_menu_ips_graph"); onToggled: function(value) { root.saveValue("settings", "pause_menu_ips_graph", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.pause_session_strip")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "pause_menu_session_strip"); onToggled: function(value) { root.saveValue("settings", "pause_menu_session_strip", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.auto_reopen_pause")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "pause_menu_auto_reopen"); onToggled: function(value) { root.saveValue("settings", "pause_menu_auto_reopen", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.console_status_line")
                            hint: root.t("settings.console_status_line_hint")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "console_ips"); onToggled: function(value) { root.saveValue("settings", "console_ips", value) } } }
                        }
                        FieldRow {
                            label: root.t("settings.status_summary_seconds")
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "terminal_summary_seconds")); onSaved: function(value) { root.saveValue("settings", "terminal_summary_seconds", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.pause_graph_samples")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "pause_menu_graph_samples")); from: 30; to: 120; integer: true; onSaved: function(value) { root.saveValue("settings", "pause_menu_graph_samples", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.capture_vision_frames")
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "capture_bad_vision_frames"); onToggled: function(value) { root.saveValue("settings", "capture_bad_vision_frames", value) } } }
                        }
                    }

                    FormPanel {
                        title: root.t("settings.capture_debug_title")
                        FieldRow { label: root.t("settings.scrcpy_width"); ConfigInput { anchors.fill: parent; value: String(root.value("settings", "scrcpy_max_width")); onSaved: function(value) { root.saveValue("settings", "scrcpy_max_width", value) } } }
                        FieldRow { label: root.t("settings.scrcpy_bitrate"); ConfigInput { anchors.fill: parent; value: String(root.value("settings", "scrcpy_bitrate")); onSaved: function(value) { root.saveValue("settings", "scrcpy_bitrate", value) } } }
                        FieldRow { label: root.t("settings.debug_scale"); NumericSlider { anchors.fill: parent; value: String(root.value("settings", "visual_debug_scale")); from: 0.5; to: 2.0; onSaved: function(value) { root.saveValue("settings", "visual_debug_scale", value) } } }
                        FieldRow { label: root.t("settings.debug_max_fps"); ConfigInput { anchors.fill: parent; value: String(root.value("settings", "visual_debug_max_fps")); onSaved: function(value) { root.saveValue("settings", "visual_debug_max_fps", value) } } }
                        FieldRow { label: root.t("settings.debug_max_boxes"); ConfigInput { anchors.fill: parent; value: String(root.value("settings", "visual_debug_max_boxes")); onSaved: function(value) { root.saveValue("settings", "visual_debug_max_boxes", value) } } }
                        FieldRow { label: root.t("settings.super_debug"); CenterRow { ToggleSwitch { checked: root.boolValue("settings", "super_debug"); onToggled: function(value) { root.saveValue("settings", "super_debug", value) } } } }
                        FieldRow { label: root.t("settings.wall_stuck_debug"); hint: root.t("settings.wall_stuck_debug_hint"); CenterRow { ToggleSwitch { checked: root.boolValue("settings", "wall_stuck_debug"); onToggled: function(value) { root.saveValue("settings", "wall_stuck_debug", value) } } } }
                    }

                    FormPanel {
                        title: root.t("settings.performance_title")
                        FieldRow {
                            label: root.t("settings.inference_device")
                            Row { spacing: 8; Repeater { model: ["auto", "directml", "amd", "cuda", "openvino", "cpu"]; delegate: ChoicePill { label: modelData; selected: root.value("settings", "cpu_or_gpu") === modelData; onClicked: root.saveValue("settings", "cpu_or_gpu", modelData) } } }
                        }
                        FieldRow {
                            label: root.t("settings.directml_gpu_id")
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "directml_device_id")); onSaved: function(value) { root.saveValue("settings", "directml_device_id", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.max_ips")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "max_ips")); from: 0; to: 120; integer: true; onSaved: function(value) { root.saveValue("settings", "max_ips", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.scrcpy_max_fps")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "scrcpy_max_fps")); from: 5; to: 120; integer: true; onSaved: function(value) { root.saveValue("settings", "scrcpy_max_fps", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.used_threads")
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "used_threads")); onSaved: function(value) { root.saveValue("settings", "used_threads", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.trophy_multiplier")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "trophies_multiplier")); from: 1; to: 10; integer: true; onSaved: function(value) { root.saveValue("settings", "trophies_multiplier", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.ocr_scale")
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "ocr_scale_down_factor")); from: 0.1; to: 1.0; onSaved: function(value) { root.saveValue("settings", "ocr_scale_down_factor", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.current_playstyle")
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "current_playstyle")); onSaved: function(value) { root.saveValue("settings", "current_playstyle", value) } }
                        }
                        FieldRow {
                            label: root.t("settings.performance_profile")
                            Row {
                                spacing: 8
                                ChoicePill { label: root.t("profile.balanced"); selected: root.performanceProfile === "balanced"; onClicked: root.performanceProfile = "balanced" }
                                ChoicePill { label: root.t("profile.low_end"); selected: root.performanceProfile === "low-end"; onClicked: root.performanceProfile = "low-end" }
                                ChoicePill { label: root.t("profile.quality"); selected: root.performanceProfile === "quality"; onClicked: root.performanceProfile = "quality" }
                                ChoicePill { label: root.t("profile.high_ips"); selected: root.performanceProfile === "high_ips"; onClicked: root.performanceProfile = "high_ips" }
                            }
                        }
                        FieldRow {
                            label: root.t("settings.auto_tune_ips")
                            hint: root.t("settings.auto_tune_ips_hint")
                            CenterRow {
                                ToggleSwitch {
                                    checked: root.boolValue("settings", "performance_autotune")
                                    onToggled: function(value) { root.saveValue("settings", "performance_autotune", value) }
                                }
                            }
                        }
                        ActionRow {
                            HubButton {
                                label: root.t("common.apply_performance_mode")
                                onClicked: root.runAction("profile-" + root.performanceProfile)
                            }
                            HubButton {
                                label: root.t("common.calibrate")
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
                        title: root.t("discord.notifications_title")
                        tutorialId: "discord"
                        FieldRow { label: root.t("instances.webhook_url"); ConfigInput { anchors.fill: parent; value: String(root.value("discord", "webhook_url")); secret: true; onSaved: function(value) { root.saveValue("discord", "webhook_url", value) } } }
                        FieldRow { label: root.t("discord.discord_id"); ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_id")); onSaved: function(value) { root.saveValue("discord", "discord_id", value) } } }
                        FieldRow { label: root.t("discord.webhook_name"); ConfigInput { anchors.fill: parent; value: String(root.value("discord", "username")); onSaved: function(value) { root.saveValue("discord", "username", value) } } }
                        FieldRow { label: root.t("discord.send_match_summary"); hint: root.t("discord.send_match_summary_hint"); CenterRow { ToggleSwitch { checked: root.boolValue("discord", "send_match_summary"); onToggled: function(value) { root.saveValue("discord", "send_match_summary", value) } } } }
                        FieldRow { label: root.t("discord.include_screenshots"); CenterRow { ToggleSwitch { checked: root.boolValue("discord", "include_screenshot"); onToggled: function(value) { root.saveValue("discord", "include_screenshot", value) } } } }
                        FieldRow { label: root.t("discord.ping_when_stuck"); CenterRow { ToggleSwitch { checked: root.boolValue("discord", "ping_when_stuck"); onToggled: function(value) { root.saveValue("discord", "ping_when_stuck", value) } } } }
                        FieldRow { label: root.t("discord.notify_on_recovery"); CenterRow { ToggleSwitch { checked: root.boolValue("discord", "notify_on_recovery"); onToggled: function(value) { root.saveValue("discord", "notify_on_recovery", value) } } } }
                        FieldRow { label: root.t("discord.recovery_alert_threshold"); ConfigInput { anchors.fill: parent; value: String(root.value("discord", "recovery_alert_threshold")); onSaved: function(value) { root.saveValue("discord", "recovery_alert_threshold", value) } } }
                        FieldRow { label: root.t("discord.ping_on_target"); CenterRow { ToggleSwitch { checked: root.boolValue("discord", "ping_when_target_is_reached"); onToggled: function(value) { root.saveValue("discord", "ping_when_target_is_reached", value) } } } }
                        FieldRow { label: root.t("discord.ping_every_x_matches"); hint: root.t("discord.ping_every_x_matches_hint"); ConfigInput { anchors.fill: parent; value: String(root.value("discord", "ping_every_x_match")); onSaved: function(value) { root.saveValue("discord", "ping_every_x_match", value) } } }
                        FieldRow { label: root.t("discord.heartbeat_every_x_minutes"); hint: root.t("discord.heartbeat_every_x_minutes_hint"); ConfigInput { anchors.fill: parent; value: String(root.value("discord", "ping_every_x_minutes")); onSaved: function(value) { root.saveValue("discord", "ping_every_x_minutes", value) } } }
                        FieldRow { label: root.t("discord.daily_digest"); hint: root.t("discord.daily_digest_hint"); CenterRow { ToggleSwitch { checked: root.boolValue("discord", "daily_digest_enabled"); onToggled: function(value) { root.saveValue("discord", "daily_digest_enabled", value) } } } }
                        FieldRow { label: root.t("discord.digest_hour"); ConfigInput { anchors.fill: parent; value: String(root.value("discord", "daily_digest_hour")); onSaved: function(value) { root.saveValue("discord", "daily_digest_hour", value) } } }
                    }
                    FormPanel {
                        title: root.t("discord.remote_control_title")
                        FieldRow { label: root.t("discord.enable_discord_control"); CenterRow { ToggleSwitch { checked: root.boolValue("discord", "discord_control_enabled"); onToggled: function(value) { root.saveValue("discord", "discord_control_enabled", value) } } } }
                        FieldRow { label: root.t("discord.bot_token"); ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_bot_token")); secret: true; onSaved: function(value) { root.saveValue("discord", "discord_bot_token", value) } } }
                        FieldRow { label: root.t("discord.allowed_user_id"); ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_control_user_id")); onSaved: function(value) { root.saveValue("discord", "discord_control_user_id", value) } } }
                        FieldRow { label: root.t("discord.allowed_channel_id"); ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_control_channel_id")); onSaved: function(value) { root.saveValue("discord", "discord_control_channel_id", value) } } }
                        FieldRow { label: root.t("discord.guild_id"); ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_control_guild_id")); onSaved: function(value) { root.saveValue("discord", "discord_control_guild_id", value) } } }
                    }
                    ActionRow {
                        HubButton { label: root.t("discord.send_discord_test"); onClicked: root.runAction("discord-test") }
                        HubButton { label: root.t("discord.webhook_guide"); secondary: true; onClicked: root.runAction("discord-webhook-guide") }
                        HubButton { label: root.t("discord.developer_portal"); secondary: true; onClicked: root.runAction("discord-developer-portal") }
                    }
                    Text { text: root.statusText; color: root.statusOk ? theme.muted : theme.danger; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                }

                TabPage {
                    visible: root.activeTab === "Telegram"
                    FormPanel {
                        title: root.t("telegram.bot_title")
                        tutorialId: "telegram"
                        FieldRow { label: root.t("telegram.enable_telegram"); CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "enabled"); onToggled: function(value) { root.saveValue("telegram", "enabled", value) } } } }
                        FieldRow { label: root.t("discord.bot_token"); ConfigInput { anchors.fill: parent; value: String(root.value("telegram", "bot_token")); secret: true; onSaved: function(value) { root.saveValue("telegram", "bot_token", value) } } }
                        FieldRow { label: root.t("telegram.notification_chat_ids"); ConfigInput { anchors.fill: parent; value: String(root.value("telegram", "notification_chat_ids")); onSaved: function(value) { root.saveValue("telegram", "notification_chat_ids", value) } } }
                        FieldRow { label: root.t("discord.send_match_summary"); CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "send_match_summary"); onToggled: function(value) { root.saveValue("telegram", "send_match_summary", value) } } } }
                        FieldRow { label: root.t("discord.include_screenshots"); CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "include_screenshot"); onToggled: function(value) { root.saveValue("telegram", "include_screenshot", value) } } } }
                        FieldRow { label: root.t("telegram.multiple_chats"); CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "allow_multiple_notification_chat_ids"); onToggled: function(value) { root.saveValue("telegram", "allow_multiple_notification_chat_ids", value) } } } }
                        FieldRow { label: root.t("telegram.remote_control"); CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "remote_control_enabled"); onToggled: function(value) { root.saveValue("telegram", "remote_control_enabled", value) } } } }
                        FieldRow { label: root.t("discord.notify_on_recovery"); CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "notify_on_recovery"); onToggled: function(value) { root.saveValue("telegram", "notify_on_recovery", value) } } } }
                        FieldRow { label: root.t("discord.recovery_alert_threshold"); ConfigInput { anchors.fill: parent; value: String(root.value("telegram", "recovery_alert_threshold")); onSaved: function(value) { root.saveValue("telegram", "recovery_alert_threshold", value) } } }
                        FieldRow { label: root.t("telegram.poll_timeout"); ConfigInput { anchors.fill: parent; value: String(root.value("telegram", "poll_timeout_seconds")); onSaved: function(value) { root.saveValue("telegram", "poll_timeout_seconds", value) } } }
                    }
                    ActionRow {
                        HubButton { label: root.t("telegram.find_chats"); onClicked: root.runAction("telegram-find-chats") }
                        HubButton { label: root.t("telegram.send_telegram_test"); onClicked: root.runAction("telegram-test") }
                        HubButton { label: root.t("telegram.open_botfather"); secondary: true; onClicked: root.runAction("telegram-botfather") }
                    }
                    Text { text: root.statusText; color: root.statusOk ? theme.muted : theme.danger; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                }

                TabPage {
                    visible: root.activeTab === "API"
                    FormPanel {
                        id: apiConfigPanel
                        title: root.t("api.title")
                        tutorialId: "api"
                        FieldRow { label: root.t("instances.player_tag"); ConfigInput { anchors.fill: parent; value: String(root.value("api", "player_tag")); onSaved: function(value) { root.saveValue("api", "player_tag", value) } } }
                        FieldRow { label: root.t("api.auto_refresh_token"); CenterRow { ToggleSwitch { checked: root.boolValue("api", "auto_refresh_token"); onToggled: function(value) { root.saveValue("api", "auto_refresh_token", value) } } } }
                        FieldRow { label: root.t("api.developer_email"); ConfigInput { anchors.fill: parent; value: String(root.value("api", "developer_email")); onSaved: function(value) { root.saveValue("api", "developer_email", value) } } }
                        FieldRow { label: root.t("api.developer_password"); ConfigInput { anchors.fill: parent; value: String(root.value("api", "developer_password")); secret: true; onSaved: function(value) { root.saveValue("api", "developer_password", value) } } }
                        FieldRow { label: root.t("api.api_token"); ConfigInput { anchors.fill: parent; value: String(root.value("api", "api_token")); secret: true; onSaved: function(value) { root.saveValue("api", "api_token", value) } } }
                        FieldRow { label: root.t("api.timeout_seconds"); ConfigInput { anchors.fill: parent; value: String(root.value("api", "timeout_seconds")); onSaved: function(value) { root.saveValue("api", "timeout_seconds", value) } } }
                        FieldRow { label: root.t("api.public_ip_service"); ConfigInput { anchors.fill: parent; value: String(root.value("api", "public_ip_service")); onSaved: function(value) { root.saveValue("api", "public_ip_service", value) } } }
                        FieldRow { label: root.t("api.key_name_prefix"); ConfigInput { anchors.fill: parent; value: String(root.value("api", "key_name_prefix")); onSaved: function(value) { root.saveValue("api", "key_name_prefix", value) } } }
                        FieldRow { label: root.t("api.delete_old_tokens"); CenterRow { ToggleSwitch { checked: root.boolValue("api", "delete_old_auto_tokens"); onToggled: function(value) { root.saveValue("api", "delete_old_auto_tokens", value) } } } }
                        FieldRow { label: root.t("api.sync_trophies_after_match"); CenterRow { ToggleSwitch { checked: root.boolValue("api", "sync_trophies_after_match"); onToggled: function(value) { root.saveValue("api", "sync_trophies_after_match", value) } } } }
                    }
                    ActionRow {
                        HubButton {
                            label: root.t("api.test_api_config")
                            onClicked: {
                                apiConfigPanel.forceActiveFocus()
                                Qt.callLater(function() { root.runAction("api-test") })
                            }
                        }
                        HubButton { label: root.t("discord.developer_portal"); secondary: true; onClicked: root.runAction("brawl-stars-developer") }
                    }
                    Text { text: root.statusText; color: root.statusOk ? theme.muted : theme.danger; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                }

                TabPage {
                    visible: root.activeTab === "Timers"
                    FormPanel {
                        title: root.t("timers.title")
                        tutorialId: "timers"
                        FieldRow { label: root.t("timers.super_delay"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "super")); from: 0.05; to: 10; onSaved: function(value) { root.saveValue("timers", "super", value) } } }
                        FieldRow { label: root.t("timers.hypercharge_delay"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "hypercharge")); from: 0.05; to: 10; onSaved: function(value) { root.saveValue("timers", "hypercharge", value) } } }
                        FieldRow { label: root.t("timers.gadget_delay"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "gadget")); from: 0.05; to: 10; onSaved: function(value) { root.saveValue("timers", "gadget", value) } } }
                        FieldRow { label: root.t("timers.wall_detection"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "wall_detection")); from: 0.05; to: 10; onSaved: function(value) { root.saveValue("timers", "wall_detection", value) } } }
                        FieldRow { label: root.t("timers.no_detection_proceed"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "no_detection_proceed")); from: 0.1; to: 20; onSaved: function(value) { root.saveValue("timers", "no_detection_proceed", value) } } }
                        FieldRow { label: root.t("timers.low_ips_recovery"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "low_ips_recovery_seconds")); from: 5; to: 90; integer: true; onSaved: function(value) { root.saveValue("timers", "low_ips_recovery_seconds", value) } } }
                        FieldRow { label: root.t("timers.low_ips_cooldown"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "low_ips_recovery_cooldown")); from: 5; to: 90; integer: true; onSaved: function(value) { root.saveValue("timers", "low_ips_recovery_cooldown", value) } } }
                        FieldRow { label: root.t("timers.app_restart_attempt"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "low_ips_app_restart_after")); from: 1; to: 6; integer: true; onSaved: function(value) { root.saveValue("timers", "low_ips_app_restart_after", value) } } }
                        FieldRow { label: root.t("timers.emulator_restart_attempt"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "low_ips_emulator_restart_after")); from: 1; to: 10; integer: true; onSaved: function(value) { root.saveValue("timers", "low_ips_emulator_restart_after", value) } } }
                        FieldRow { label: root.t("timers.lobby_stuck_restart"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "lobby_stuck_restart")); from: 30; to: 300; onSaved: function(value) { root.saveValue("timers", "lobby_stuck_restart", value) } } }
                        FieldRow { label: root.t("timers.visual_freeze_restart"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "visual_freeze_restart")); from: 10; to: 120; onSaved: function(value) { root.saveValue("timers", "visual_freeze_restart", value) } } }
                        FieldRow { label: root.t("timers.global_freeze_restart"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "global_freeze_restart")); from: 10; to: 180; onSaved: function(value) { root.saveValue("timers", "global_freeze_restart", value) } } }
                        FieldRow { label: root.t("timers.emulator_restart_cooldown"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "emulator_restart_cooldown")); from: 30; to: 600; onSaved: function(value) { root.saveValue("timers", "emulator_restart_cooldown", value) } } }
                        FieldRow { label: root.t("timers.state_check"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "state_check")); from: 0.1; to: 5; onSaved: function(value) { root.saveValue("timers", "state_check", value) } } }
                        FieldRow { label: root.t("timers.idle_timeout"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "idle")); from: 5; to: 120; onSaved: function(value) { root.saveValue("timers", "idle", value) } } }
                        FieldRow { label: root.t("timers.low_ips_threshold"); NumericSlider { anchors.fill: parent; value: String(root.value("timers", "low_ips_recovery_threshold")); from: 1; to: 10; onSaved: function(value) { root.saveValue("timers", "low_ips_recovery_threshold", value) } } }
                    }
                }

                TabPage {
                    visible: root.activeTab === "Match History"

                    FormPanel {
                        title: root.t("history.title")
                        tutorialId: "match-history"
                        ActionRow {
                            HubButton { label: root.t("common.export_csv"); secondary: true; onClicked: root.runAction("export-history") }
                            HubButton { label: root.t("common.reset_stats"); secondary: true; onClicked: root.runAction("reset-history") }
                            HubButton { label: root.t("common.refresh"); secondary: true; onClicked: root.runAction("refresh-history") }
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
                                text: root.t("common.lifetime", { count: (hubState.history && hubState.history.summary) ? hubState.history.summary.games : 0 })
                                color: theme.text
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                            Text {
                                text: root.t("common.win_loss_draw", {
                                    wins: (hubState.history && hubState.history.summary) ? hubState.history.summary.victory : 0,
                                    losses: (hubState.history && hubState.history.summary) ? hubState.history.summary.defeat : 0,
                                    draws: (hubState.history && hubState.history.summary) ? hubState.history.summary.draw : 0,
                                    winRate: (hubState.history && hubState.history.summary) ? hubState.history.summary.winRate : 0
                                })
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
                                label: root.t("history.sort_" + (modelData === "winRate" ? "win_rate" : modelData))
                                selected: root.historySort === modelData
                                onClicked: root.historySort = modelData
                            }
                        }
                    }
                    Text { text: root.statusText; color: root.statusOk ? theme.muted : theme.danger; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Text { text: root.t("common.recent_matches"); color: theme.faint; font.pixelSize: 11 }
                    FormPanel {
                        title: root.t("history.efficiency_title")
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
                                            text: root.t("common.trophies_per_hour", { rate: modelData.trophiesPerHour })
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
                                            text: root.t("common.stuck")
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
                        text: root.t("common.no_match_history")
                        color: theme.faint
                        font.pixelSize: 12
                    }
                }

                TabPage {
                    visible: root.activeTab === "Help"

                    FormPanel {
                        title: root.t("help.feature_guides_title")
                        Text {
                            Layout.fillWidth: true
                            text: root.t("help.feature_guides_hint")
                            color: theme.faint
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        FieldRow {
                            label: root.t("help.search_guides")
                            ConfigInput {
                                anchors.fill: parent
                                live: true
                                value: root.helpFilter
                                onSaved: function(value) { root.helpFilter = value }
                            }
                        }
                        ActionRow {
                            HubButton {
                                label: root.t("help.open_tutorial_index")
                                secondary: true
                                onClicked: root.openTutorialDoc("docs/TUTORIAL.md")
                            }
                            HubButton {
                                label: root.t("common.show_setup_wizard_again")
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
                                        label: root.t("common.open_guide")
                                        compact: true
                                        onClicked: root.openTutorial(modelData.id)
                                    }
                                    HubButton {
                                        label: root.t("common.full_doc")
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
                            text: (hubState.preflight && hubState.preflight.ready) ? root.t("footer.ready_to_start") : root.t("footer.run_preflight")
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
                            text: root.t("common.start")
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
                            text: root.t("common.close")
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
                        label: root.t("common.checks")
                        secondary: true
                        compact: true
                        enabled: !root.hubBusy
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
                    Text { text: hubBrand ? hubBrand.footerNotice : root.t("footer.notice"); color: theme.faint; font.pixelSize: 11 }
                    Text { text: "\u00b7"; color: theme.muted; font.pixelSize: 13; font.weight: Font.Bold }
                    FooterLink {
                        label: root.t("common.join_discord")
                        onClicked: hubBridge.openDiscord()
                    }
                    Text { text: "\u00b7"; color: theme.muted; font.pixelSize: 13; font.weight: Font.Bold }
                    FooterLink {
                        label: root.t("common.support_patreon")
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
        opacity: (root.hubStateReady && root.showWizard) ? 1 : 0
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
            scale: (root.hubStateReady && root.showWizard) ? 1 : 0.94

            Behavior on scale { NumberAnimation { duration: root.durMed; easing.type: Easing.OutCubic } }

            ColumnLayout {
                id: wizardColumn
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12
                Text {
                    text: root.wizardStep === 0 ? root.t("wizard.step1_title")
                        : (root.wizardStep === 1 ? root.t("wizard.step2_title")
                        : (root.wizardStep === 2 ? root.t("wizard.step3_title") : root.t("wizard.step4_title")))
                    color: theme.text
                    font.pixelSize: 16
                    font.weight: Font.Bold
                }
                Text {
                    Layout.fillWidth: true
                    text: root.wizardStep === 0
                        ? root.t("wizard.step1_body", { product: (hubBrand ? hubBrand.productName : "Pyla-RL") })
                        : (root.wizardStep === 1
                            ? root.t("wizard.step2_body")
                            : (root.wizardStep === 2
                                ? root.t("wizard.step3_body")
                                : root.t("wizard.step4_body")))
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
                                text: root.t("wizard.license_checkbox")
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
                    text: root.t("wizard.license_enable_next")
                    color: theme.faint
                    font.pixelSize: 10
                }
                RowLayout {
                    spacing: 8
                    HubButton {
                        label: root.t("common.back")
                        secondary: true
                        visible: root.wizardStep > 0
                        onClicked: root.wizardStep -= 1
                    }
                    HubButton {
                        label: root.t("common.run_checks")
                        secondary: true
                        visible: root.wizardStep === 1
                        enabled: !root.hubBusy
                        onClicked: root.runAction("preflight-check")
                    }
                    HubButton {
                        label: root.t("common.open_help")
                        secondary: true
                        visible: root.wizardStep >= 2
                        onClicked: {
                            root.showWizard = false
                            root.activeTab = "Help"
                        }
                    }
                    Item { Layout.fillWidth: true }
                    HubButton {
                        label: root.wizardStep < 3 ? root.t("common.next") : root.t("common.finish")
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
                    text: root.t("common.add_brawler")
                    color: theme.text
                    font.pixelSize: 15
                    font.weight: Font.Bold
                }
                Text {
                    Layout.fillWidth: true
                    text: root.t("picker.hint")
                    color: theme.faint
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
                FieldRow {
                    label: root.t("common.search")
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
                    text: root.t("picker.no_match")
                    color: theme.faint
                    font.pixelSize: 11
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Text {
                        text: root.t("common.target")
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
                        label: root.t("common.cancel")
                        secondary: true
                        onClicked: root.showBrawlerPicker = false
                    }
                    Item { Layout.fillWidth: true }
                    HubButton {
                        label: root.t("common.add")
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
        title: root.t("common.import_farm_plan")
        nameFilters: [root.t("common.json_filter"), root.t("common.all_files_filter")]
        fileMode: FileDialog.OpenFile
        onAccepted: {
            if (selectedFile) {
                root.runActionWithPayload("import-queue", { path: selectedFile.toString() })
            }
        }
    }

    FileDialog {
        id: exportQueueDialog
        title: root.t("common.export_farm_plan")
        nameFilters: [root.t("common.json_filter"), root.t("common.all_files_filter")]
        fileMode: FileDialog.SaveFile
        defaultSuffix: "json"
        onAccepted: {
            if (selectedFile) {
                root.runActionWithPayload("export-queue", { path: selectedFile.toString() })
            }
        }
    }

    Popup {
        id: updatePopover
        parent: Overlay.overlay
        width: Math.max(updatePopoverColumn.implicitWidth + 24, 300)
        height: Math.max(updatePopoverColumn.implicitHeight + 24, 120)
        padding: 12
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        function repositionWithinOverlay() {
            var overlay = Overlay.overlay
            if (!overlay) {
                return
            }
            var margin = 8
            var belowPos = updatePill.mapToItem(overlay, 0, updatePill.height)
            var abovePos = updatePill.mapToItem(overlay, 0, 0)
            var buttonRightPos = updatePill.mapToItem(overlay, updatePill.width, 0)
            var popupW = updatePopover.width
            var popupH = updatePopover.height
            var maxX = Math.max(margin, overlay.width - popupW - margin)
            var maxY = Math.max(margin, overlay.height - popupH - margin)

            var nextX = belowPos.x
            if (nextX + popupW > overlay.width - margin) {
                nextX = buttonRightPos.x - popupW
            }
            updatePopover.x = Math.max(margin, Math.min(nextX, maxX))

            var nextY = belowPos.y + 4
            if (nextY + popupH > overlay.height - margin) {
                nextY = abovePos.y - popupH - 4
            }
            updatePopover.y = Math.max(margin, Math.min(nextY, maxY))
        }

        onOpened: repositionWithinOverlay()

        background: Rectangle {
            radius: 12
            color: theme.panel3
            border.width: 1
            border.color: theme.borderSoft
        }

        Column {
            id: updatePopoverColumn
            spacing: 10
            width: parent.availableWidth

            Text {
                text: root.updatePopoverHeadline()
                color: theme.text
                font.pixelSize: 14
                font.weight: Font.Bold
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                visible: !!(hubState.updateStatus && hubState.updateStatus.currentVersion)
                text: root.t("update.installed_version", { version: hubState.updateStatus.currentVersion })
                color: theme.muted
                font.pixelSize: 11
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                visible: !!(hubState.updateStatus && hubState.updateStatus.localSha)
                text: root.t("update.local_commit", { sha: hubState.updateStatus.localSha })
                color: theme.muted
                font.pixelSize: 11
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                visible: !!(hubState.updateStatus && hubState.updateStatus.remoteSha)
                text: root.t("update.latest_commit", { sha: hubState.updateStatus.remoteSha })
                color: theme.muted
                font.pixelSize: 11
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                visible: !!(hubState.updateStatus && hubState.updateStatus.updatedAt)
                text: root.t("update.last_updated", { date: hubState.updateStatus.updatedAt })
                color: theme.faint
                font.pixelSize: 10
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                visible: !!(hubState.updateStatus && hubState.updateStatus.latestReleaseVersion)
                text: root.t("update.release_version", { version: hubState.updateStatus.latestReleaseVersion })
                color: theme.faint
                font.pixelSize: 10
            }

            Flow {
                spacing: 8
                width: parent.width
                HubButton {
                    label: root.t("update.run_updater")
                    onClicked: {
                        root.runAction("launch-updater")
                        updatePopover.close()
                    }
                }
                HubButton {
                    label: root.t("update.refresh_status")
                    secondary: true
                    onClicked: {
                        root.runAction("refresh-update-status")
                        updatePopover.close()
                    }
                }
            }
        }
    }
}
