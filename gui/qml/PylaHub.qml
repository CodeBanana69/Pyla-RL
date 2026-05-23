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
    property string statusText: ""
    property bool statusOk: true
    property string performanceProfile: "balanced"
    property string settingsFilter: ""
    property var preflightChecks: []
    property bool showWizard: true
    property int wizardStep: 0
    property bool licenseTermsAccepted: false
    readonly property bool unofficialCopy: !!(hubState.meta && hubState.meta.sourceStatus && hubState.meta.sourceStatus.official === false)
    readonly property bool licenseAccepted: !!(hubState.meta && hubState.meta.licenseAccepted)
    property string pushAllTarget: "1000"
    property bool showBrawlerPicker: false
    property bool showFarmPlanTutorial: false
    property string pickerFilter: ""
    property string pickerBrawler: ""
    property string pickerTarget: "1000"
    property string pickerType: "trophies"
    property string historySort: "games"
    readonly property var queueTargetOptions: ["250", "500", "750", "1000", "1250", "1500"]
    readonly property var navItems: ["Overview", "Instances", "Farm Plan", "Settings", "Discord", "Telegram", "API", "Timers", "Match History"]
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
    property string instanceFormId: ""
    property string instanceFormName: ""
    property string instanceFormEmulator: "ldplayer"
    property string instanceFormPort: "5555"

    function reloadHubState() {
        if (!hubBridge) {
            return
        }
        hubState = JSON.parse(hubBridge.stateJson())
        preflightChecks = (hubState.preflight && hubState.preflight.checks) ? hubState.preflight.checks : []
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
        return result
    }

    function saveNewInstance() {
        const payload = {
            id: instanceFormId.trim(),
            name: instanceFormName.trim() || instanceFormId.trim(),
            emulator: instanceFormEmulator,
            emulator_port: parseInt(instanceFormPort, 10) || 5555,
            enabled: true
        }
        const result = applyBridgeResult(hubBridge.saveInstanceProfile(JSON.stringify(payload)))
        if (result.ok) {
            showAddInstanceForm = false
            instanceFormId = ""
            instanceFormName = ""
            instanceFormEmulator = "ldplayer"
            instanceFormPort = "5555"
        }
        return result
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
    }

    QtObject {
        id: theme
        property color bg: "#0c0c0c"
        property color chrome: "#121212"
        property color panel: "#181818"
        property color panel2: "#1f1f1f"
        property color panel3: "#2a2a2a"
        property color border: "#333333"
        property color borderSoft: "#262626"
        property color text: "#f4f4f4"
        property color muted: "#b8b8b8"
        property color faint: "#6d6d6d"
        property color accent: "#ff9f0a"
        property color accentHover: "#ffb23a"
        property color accentSoft: "#32220c"
        property color accentBorder: "#8f610e"
        property color ok: "#30d158"
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
        radius: 7
        color: selected ? theme.panel3 : (hovered ? "#211f1a" : "transparent")
        border.width: selected ? 1 : 0
        border.color: selected ? theme.border : "transparent"

        Text {
            id: navText
            anchors.centerIn: parent
            text: nav.label
            color: nav.selected ? theme.text : theme.muted
            font.pixelSize: 11
            font.weight: nav.selected ? Font.DemiBold : Font.Medium
            horizontalAlignment: Text.AlignHCenter
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
        property bool hovered: false
        signal clicked()

        height: 58
        radius: 10
        color: selected && !locked ? theme.accentSoft : (hovered ? "#211f1a" : theme.panel)
        border.width: 1
        border.color: selected && !locked ? theme.accentBorder : theme.borderSoft
        opacity: locked ? 0.62 : 1

        Behavior on color { ColorAnimation { duration: 120 } }
        Behavior on border.color { ColorAnimation { duration: 120 } }

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
                color: "#22242d"

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
                color: card.selected && !card.locked ? theme.accent : "transparent"
                border.width: card.selected && !card.locked ? 0 : 1
                border.color: theme.border

                Rectangle {
                    visible: card.selected && !card.locked
                    anchors.centerIn: parent
                    width: 6
                    height: 6
                    radius: 3
                    color: "#ffffff"
                }
            }
        }

        MouseArea {
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
        radius: compact ? 7 : 8
        color: buttonMouse.containsMouse
            ? (secondary ? theme.panel3 : theme.accentHover)
            : (secondary ? theme.panel2 : theme.accent)
        border.width: secondary ? 1 : 0
        border.color: theme.border

        Text {
            id: buttonText
            anchors.centerIn: parent
            text: button.label
            color: theme.text
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
        property bool secret: false
        property bool revealed: false
        property bool live: false
        signal saved(string value)

        implicitHeight: 34
        height: 34
        radius: 8
        color: theme.panel
        border.width: 1
        border.color: field.activeFocus ? theme.accentBorder : theme.borderSoft

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
                    color: theme.text
                    border.width: 2
                    border.color: theme.accent
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
        }

        Rectangle {
            width: 18
            height: 18
            radius: 9
            y: 2
            x: toggle.checked ? 20 : 2
            color: "#ffffff"
            Behavior on x { NumberAnimation { duration: 110 } }
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
        radius: 8
        color: selected ? theme.accentSoft : (pillMouse.containsMouse ? "#211f1a" : theme.panel)
        border.width: 1
        border.color: selected ? theme.accentBorder : theme.borderSoft

        Text {
            id: pillText
            anchors.centerIn: parent
            text: pill.label
            color: pill.selected ? theme.text : theme.muted
            font.pixelSize: 12
            font.weight: pill.selected ? Font.DemiBold : Font.Medium
            elide: Text.ElideRight
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
        radius: 10
        color: selected ? theme.accentSoft : (pickMouse.containsMouse ? "#211f1a" : theme.panel)
        border.width: 1
        border.color: selected ? theme.accentBorder : theme.borderSoft

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

        radius: 8
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
        default property alias content: body.data

        Layout.fillWidth: true
        implicitHeight: body.implicitHeight + 32
        radius: 10
        color: theme.panel
        border.width: 1
        border.color: theme.borderSoft
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

            SectionTitle { title: panel.title }
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

        ColumnLayout {
            id: pageBody
            width: Math.max(320, page.availableWidth - 24)
            x: Math.max(12, (page.availableWidth - width) / 2)
            y: 20
            spacing: 12
        }
    }

    component IconButton: Rectangle {
        id: iconButton
        property string glyph: "×"
        signal clicked()

        width: 28
        height: 28
        radius: 6
        color: iconMouse.containsMouse ? theme.panel3 : "transparent"

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
        radius: 8
        color: hovered ? theme.panel2 : theme.panel
        opacity: isDragSource ? 0.72 : 1.0
        border.width: isDropTarget || rowIndex === 0 ? 2 : 1
        border.color: isDropTarget ? theme.accent : (rowIndex === 0 ? theme.accentBorder : theme.borderSoft)

        Behavior on color { ColorAnimation { duration: 100 } }

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
                    x: targetButton.mapToItem(null, 0, targetButton.height).x
                    y: targetButton.mapToItem(null, 0, targetButton.height).y + 4
                    width: targetPopupRow.implicitWidth + 16
                    height: targetPopupRow.implicitHeight + 16
                    padding: 8
                    modal: true
                    focus: true
                    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

                    background: Rectangle {
                        radius: 8
                        color: theme.panel2
                        border.width: 1
                        border.color: theme.borderSoft
                    }

                    Row {
                        id: targetPopupRow
                        spacing: 6
                        Repeater {
                            model: root.queueTargetOptions
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

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 10

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

                    Text {
                        text: "PUSH ALL"
                        color: theme.text
                        font.pixelSize: 12
                        font.weight: Font.Bold
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: ["250", "500", "750", "1000", "1250", "1500"]
                            delegate: ChoicePill {
                                label: modelData
                                selected: root.pushAllTarget === modelData
                                onClicked: root.pushAllTarget = modelData
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        HubButton {
                            label: "Build Queue"
                            compact: true
                            onClicked: root.runActionWithPayload("build-push-all", { target: parseInt(root.pushAllTarget) })
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
                                NumberAnimation { properties: "x,y"; duration: 120; easing.type: Easing.OutCubic }
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
                color: "#2a220c"
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
                    radius: 10
                    color: theme.panel
                    border.width: 1
                    border.color: theme.border
                    clip: true

                    ScrollView {
                        anchors.fill: parent
                        anchors.margins: 4
                        contentWidth: navRow.implicitWidth
                        contentHeight: navRow.implicitHeight
                        ScrollBar.vertical.policy: ScrollBar.AlwaysOff
                        ScrollBar.horizontal.policy: ScrollBar.AsNeeded

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

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                TabPage {
                    visible: root.activeTab === "Instances"

                    FormPanel {
                        title: "MULTI-INSTANCE MODE"
                        Text {
                            Layout.fillWidth: true
                            text: "Run multiple LDPlayer or MuMu bots in parallel. Each instance needs its own emulator port and farm plan."
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
                                        applyBridgeResult(hubBridge.setMultiInstanceEnabled(value))
                                    }
                                }
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: !(hubState.multiInstance && hubState.multiInstance.enabled)
                            text: "Single-instance mode uses START on Overview. Enable this to run multiple LDPlayer or MuMu bots in parallel from this tab."
                            color: theme.faint
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: !!(hubState.multiInstance && hubState.multiInstance.enabled)
                            text: "Multi-instance mode is active. Start each bot with Start below instead of Overview START."
                            color: theme.ok
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        HubButton {
                            label: "Refresh Instances"
                            secondary: true
                            onClicked: applyBridgeResult(hubBridge.refreshInstances())
                        }
                    }

                    FormPanel {
                        title: "ADD INSTANCE"
                        visible: !!(hubState.multiInstance && hubState.multiInstance.enabled)
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            ActionRow {
                                HubButton {
                                    label: showAddInstanceForm ? "Hide Form" : "Add Instance"
                                    secondary: true
                                    onClicked: showAddInstanceForm = !showAddInstanceForm
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                visible: showAddInstanceForm
                                FieldRow {
                                    label: "Instance ID"
                                    ConfigInput {
                                        anchors.fill: parent
                                        live: true
                                        value: root.instanceFormId
                                        onSaved: function(value) { root.instanceFormId = value }
                                    }
                                }
                                FieldRow {
                                    label: "Display Name"
                                    ConfigInput {
                                        anchors.fill: parent
                                        live: true
                                        value: root.instanceFormName
                                        onSaved: function(value) { root.instanceFormName = value }
                                    }
                                }
                                FieldRow {
                                    label: "Emulator"
                                    RowLayout {
                                        anchors.fill: parent
                                        spacing: 8
                                        HubButton {
                                            label: "LDPlayer"
                                            secondary: root.instanceFormEmulator !== "ldplayer"
                                            onClicked: root.setInstanceFormEmulator("ldplayer")
                                        }
                                        HubButton {
                                            label: "MuMu"
                                            secondary: root.instanceFormEmulator !== "mumu"
                                            onClicked: root.setInstanceFormEmulator("mumu")
                                        }
                                    }
                                }
                                FieldRow {
                                    label: "ADB Port"
                                    ConfigInput {
                                        anchors.fill: parent
                                        live: true
                                        value: root.instanceFormPort
                                        onSaved: function(value) { root.instanceFormPort = value }
                                    }
                                }
                                ActionRow {
                                    HubButton {
                                        label: "Save Instance"
                                        onClicked: root.saveNewInstance()
                                    }
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
                                        Text {
                                            text: modelData.name + " (" + modelData.id + ")"
                                            color: theme.text
                                            font.pixelSize: 13
                                            font.bold: true
                                        }
                                        Text {
                                            text: String(modelData.emulator || "?").toUpperCase() + " · port " + modelData.emulator_port
                                                + (modelData.running ? " · RUNNING" : " · stopped")
                                                + (modelData.brawler ? " · " + modelData.brawler : "")
                                            color: theme.muted
                                            font.pixelSize: 11
                                            wrapMode: Text.WordWrap
                                            Layout.fillWidth: true
                                        }
                                        RowLayout {
                                            spacing: 8
                                            HubButton {
                                                label: "Start"
                                                visible: !modelData.running
                                                onClicked: applyBridgeResult(hubBridge.startInstance(modelData.id))
                                            }
                                            HubButton {
                                                label: "Stop"
                                                secondary: true
                                                visible: !!modelData.running
                                                onClicked: applyBridgeResult(hubBridge.stopInstance(modelData.id))
                                            }
                                            HubButton {
                                                label: "Delete"
                                                secondary: true
                                                visible: modelData.id !== String((hubState.multiInstance && hubState.multiInstance.defaultInstance) || "default")
                                                onClicked: applyBridgeResult(hubBridge.deleteInstanceProfile(modelData.id))
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
                            visible: root.preflightChecks.length > 0
                            Repeater {
                                model: root.preflightChecks
                                delegate: RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Rectangle {
                                        width: 8
                                        height: 8
                                        radius: 4
                                        color: modelData.ok ? theme.ok : (modelData.severity === "required" ? "#ff6b5f" : theme.accent)
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.label + " — " + modelData.detail
                                        color: theme.muted
                                        font.pixelSize: 11
                                        wrapMode: Text.WordWrap
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
                                color: root.statusOk ? theme.muted : "#ff6b5f"
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
                            OptionCard { Layout.fillWidth: true; label: "Brawl Ball"; locked: true }
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
                                onClicked: {
                                    hubBridge.updateSetting("emulator", "ldplayer")
                                    root.runAction("preflight-check")
                                }
                            }
                            OptionCard {
                                Layout.fillWidth: true
                                label: "MuMu"
                                selected: root.emulator === "mumu"
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
                            label: "Terminal Logging"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "terminal_logging"); onToggled: function(value) { root.saveValue("settings", "terminal_logging", value) } } }
                        }
                        FieldRow {
                            label: "Debug Screen"
                            hint: "Restart bot to apply."
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
                            label: "Console IPS Output"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "console_ips"); onToggled: function(value) { root.saveValue("settings", "console_ips", value) } } }
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
                        FieldRow { label: "Wall Stuck Debug"; CenterRow { ToggleSwitch { checked: root.boolValue("settings", "wall_stuck_debug"); onToggled: function(value) { root.saveValue("settings", "wall_stuck_debug", value) } } } }
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
                        ActionRow {
                            HubButton {
                                label: "Apply Performance Mode"
                                onClicked: root.runAction("profile-" + root.performanceProfile)
                            }
                        }
                    }
                    Text { text: root.statusText; color: root.statusOk ? theme.muted : "#ff6b5f"; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                }

                TabPage {
                    visible: root.activeTab === "Discord"
                    FormPanel {
                        title: "DISCORD NOTIFICATIONS"
                        FieldRow { label: "Webhook URL"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "webhook_url")); secret: true; onSaved: function(value) { root.saveValue("discord", "webhook_url", value) } } }
                        FieldRow { label: "Discord ID"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_id")); onSaved: function(value) { root.saveValue("discord", "discord_id", value) } } }
                        FieldRow { label: "Webhook Name"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "username")); onSaved: function(value) { root.saveValue("discord", "username", value) } } }
                        FieldRow { label: "Send Match Summary"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "send_match_summary"); onToggled: function(value) { root.saveValue("discord", "send_match_summary", value) } } } }
                        FieldRow { label: "Include Screenshots"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "include_screenshot"); onToggled: function(value) { root.saveValue("discord", "include_screenshot", value) } } } }
                        FieldRow { label: "Ping When Stuck"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "ping_when_stuck"); onToggled: function(value) { root.saveValue("discord", "ping_when_stuck", value) } } } }
                        FieldRow { label: "Notify On Recovery"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "notify_on_recovery"); onToggled: function(value) { root.saveValue("discord", "notify_on_recovery", value) } } } }
                        FieldRow { label: "Recovery Alert Threshold"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "recovery_alert_threshold")); onSaved: function(value) { root.saveValue("discord", "recovery_alert_threshold", value) } } }
                        FieldRow { label: "Ping On Target"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "ping_when_target_is_reached"); onToggled: function(value) { root.saveValue("discord", "ping_when_target_is_reached", value) } } } }
                        FieldRow { label: "Every X Matches"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "ping_every_x_match")); onSaved: function(value) { root.saveValue("discord", "ping_every_x_match", value) } } }
                        FieldRow { label: "Every X Minutes"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "ping_every_x_minutes")); onSaved: function(value) { root.saveValue("discord", "ping_every_x_minutes", value) } } }
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
                    Text { text: root.statusText; color: root.statusOk ? theme.muted : "#ff6b5f"; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                }

                TabPage {
                    visible: root.activeTab === "Telegram"
                    FormPanel {
                        title: "TELEGRAM BOT"
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
                    Text { text: root.statusText; color: root.statusOk ? theme.muted : "#ff6b5f"; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                }

                TabPage {
                    visible: root.activeTab === "API"
                    FormPanel {
                        title: "BRAWL STARS API"
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
                    Text { text: root.statusText; color: root.statusOk ? theme.muted : "#ff6b5f"; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                }

                TabPage {
                    visible: root.activeTab === "Timers"
                    FormPanel {
                        title: "TIMERS"
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
                    ActionRow {
                        HubButton { label: "Export CSV"; secondary: true; onClicked: root.runAction("export-history") }
                        HubButton { label: "Reset Stats"; secondary: true; onClicked: root.runAction("reset-history") }
                        HubButton { label: "Refresh"; secondary: true; onClicked: root.runAction("refresh-history") }
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
                    Text { text: root.statusText; color: root.statusOk ? theme.muted : "#ff6b5f"; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Text { text: "Recent Matches"; color: theme.faint; font.pixelSize: 11 }
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
                            color: root.statusOk ? theme.faint : "#ff6b5f"
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
                        radius: 10
                        color: (hubState.preflight && hubState.preflight.ready)
                            ? (startMouse.containsMouse ? theme.accentHover : theme.accent)
                            : "#5a5a5a"
                        opacity: (hubState.preflight && hubState.preflight.ready) ? 1.0 : 0.85

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
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.startBot()
                        }
                    }

                    Rectangle {
                        id: closeSettingsButton
                        visible: settingsOnly
                        Layout.preferredWidth: 168
                        Layout.preferredHeight: 44
                        radius: 10
                        color: closeSettingsMouse.containsMouse ? theme.panel3 : theme.panel2
                        border.width: 1
                        border.color: theme.border

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
        visible: root.showWizard
        color: "#cc000000"
        z: 99

        Rectangle {
            anchors.centerIn: parent
            width: 420
            radius: 12
            color: theme.panel
            border.width: 1
            border.color: theme.borderSoft
            implicitHeight: wizardColumn.implicitHeight + 32

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
                            ? "Start your emulator, open Brawl Stars, then run pre-flight checks on Overview."
                            : (root.wizardStep === 2
                                ? "Optional: configure Discord, Telegram, or API tabs for notifications and remote control."
                                : "Build a farm plan on the Farm Plan tab, or use the legacy brawler picker after START if the queue is empty."))
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
                        color: licenseRowMouse.containsMouse ? "#211f1a" : theme.panel2
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

    Rectangle {
        anchors.fill: parent
        visible: root.showFarmPlanTutorial
        color: "#cc000000"
        z: 99

        MouseArea {
            anchors.fill: parent
            onClicked: root.showFarmPlanTutorial = false
        }

        Rectangle {
            anchors.centerIn: parent
            width: Math.min(520, root.width - 48)
            radius: 12
            color: theme.panel
            border.width: 1
            border.color: theme.borderSoft
            implicitHeight: farmTutorialColumn.implicitHeight + 32

            MouseArea {
                anchors.fill: parent
            }

            ColumnLayout {
                id: farmTutorialColumn
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12

                Text {
                    text: "Farm Plan Tutorial"
                    color: theme.text
                    font.pixelSize: 16
                    font.weight: Font.Bold
                }
                Text {
                    Layout.fillWidth: true
                    text: "Quick start:\n"
                        + "1. Fill the API tab (player tag + token) for Push All.\n"
                        + "2. Pick a trophy target and click Build Queue.\n"
                        + "3. Drag the grip to reorder brawlers. The first brawler is active.\n"
                        + "4. Press START on Overview. Restart the bot after changing the plan.\n\n"
                        + "Manual add:\n"
                        + "• Click Add Brawler, search the grid, set target trophies, then add.\n"
                        + "• Click a queue row target to change push-until after adding.\n\n"
                        + "Tips:\n"
                        + "• Push All only includes brawlers below your target from the API.\n"
                        + "• Export/Import saves farm_plan.json for backup.\n"
                        + "• Leave the queue empty to use the legacy picker after START."
                    color: theme.muted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    lineHeight: 1.25
                }
                RowLayout {
                    spacing: 8
                    Item { Layout.fillWidth: true }
                    HubButton {
                        label: "Close"
                        secondary: true
                        onClicked: root.showFarmPlanTutorial = false
                    }
                }
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: root.showBrawlerPicker
        color: "#cc000000"
        z: 100

        MouseArea {
            anchors.fill: parent
            onClicked: root.showBrawlerPicker = false
        }

        Rectangle {
            anchors.centerIn: parent
            width: Math.min(620, root.width - 40)
            height: Math.min(520, root.height - 48)
            radius: 12
            color: theme.panel
            border.width: 1
            border.color: theme.borderSoft
            clip: true

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
                FieldRow {
                    label: "Target"
                    Layout.fillWidth: true
                    RowLayout {
                        anchors.fill: parent
                        spacing: 8
                        Repeater {
                            model: ["250", "500", "750", "1000", "1250", "1500"]
                            delegate: ChoicePill {
                                label: modelData
                                selected: root.pickerTarget === modelData
                                onClicked: root.pickerTarget = modelData
                            }
                        }
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
                            root.runActionWithPayload("add-to-queue", {
                                brawler: root.pickerBrawler,
                                push_until: parseInt(root.pickerTarget),
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
