import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    width: 820
    height: 560
    minimumWidth: 820
    minimumHeight: 560
    visible: true
    title: "PylaAi-XXZ Hub"
    color: theme.bg
    flags: Qt.FramelessWindowHint | Qt.Window

    property string mode: hubBridge ? hubBridge.mode() : "showdown-trio"
    property string emulator: hubBridge ? hubBridge.emulator() : "ldplayer"
    property string activeTab: "Overview"
    property var hubState: ({ settings: {}, discord: {}, telegram: {}, api: {}, timers: {}, history: [] })
    property string statusText: ""
    property bool statusOk: true
    property string performanceProfile: "balanced"

    function reloadState() {
        if (hubBridge) {
            hubState = JSON.parse(hubBridge.stateJson())
            mode = hubState.mode || mode
            emulator = hubState.emulator || emulator
        }
    }

    function applyBridgeResult(resultText) {
        const result = JSON.parse(resultText)
        if (result.state) {
            hubState = result.state
        }
        if (result.message) {
            statusText = result.message
            statusOk = !!result.ok
        }
        return result
    }

    function saveValue(section, key, value) {
        applyBridgeResult(hubBridge.updateConfig(section, key, String(value)))
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
        applyBridgeResult(hubBridge.runAction(action))
    }

    Component.onCompleted: reloadState()

    Connections {
        target: hubBridge
        function onStateChanged(nextMode, nextEmulator) {
            root.mode = nextMode
            root.emulator = nextEmulator
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
            anchors.fill: parent
            antialiasing: true
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            Connections {
                target: icon
                function onKindChanged() { parent.requestPaint() }
                function onStrokeChanged() { parent.requestPaint() }
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
        property bool selected: root.activeTab === label
        property bool hovered: false
        signal clicked()

        width: 108
        height: 30
        radius: 7
        color: selected ? theme.panel3 : (hovered ? "#211f1a" : "transparent")
        border.width: selected ? 1 : 0
        border.color: selected ? theme.border : "transparent"

        Text {
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
        signal clicked()

        implicitWidth: Math.max(118, buttonText.implicitWidth + 30)
        implicitHeight: 34
        radius: 8
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
            font.pixelSize: 12
            font.weight: Font.DemiBold
        }

        MouseArea {
            id: buttonMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: button.clicked()
        }
    }

    component ConfigInput: Rectangle {
        id: inputBox
        property string value: ""
        property bool secret: false
        property bool revealed: false
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
            text: inputBox.value
            color: theme.text
            selectionColor: theme.accent
            selectedTextColor: "#ffffff"
            font.pixelSize: 12
            echoMode: inputBox.secret && !inputBox.revealed ? TextInput.Password : TextInput.Normal
            clip: true
            onEditingFinished: inputBox.saved(text)
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
                onSaved: sliderBox.saved(value)
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

    component FieldRow: Rectangle {
        id: row
        property string label: ""
        property string hint: ""
        default property alias content: slot.data

        Layout.fillWidth: true
        implicitHeight: Math.max(52, slot.implicitHeight + 18)
        radius: 8
        color: theme.panel2
        border.width: 1
        border.color: theme.borderSoft

        Text {
            id: labelText
            width: 164
            anchors.left: parent.left
            anchors.leftMargin: 14
            anchors.verticalCenter: parent.verticalCenter
            text: row.label
            color: theme.text
            font.pixelSize: 12
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }

        Text {
            visible: row.hint !== ""
            anchors.left: labelText.left
            anchors.right: labelText.right
            anchors.top: labelText.bottom
            anchors.topMargin: 2
            text: row.hint
            color: theme.faint
            font.pixelSize: 10
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
        implicitHeight: body.implicitHeight + 58
        radius: 10
        color: theme.panel
        border.width: 1
        border.color: theme.borderSoft

        ColumnLayout {
            id: body
            anchors.fill: parent
            anchors.margins: 16
            spacing: 4

            SectionTitle { title: panel.title }
        }
    }

    component TabPage: ScrollView {
        id: page
        default property alias content: pageBody.data
        clip: true
        anchors.fill: parent
        contentWidth: availableWidth
        contentHeight: pageBody.y + pageBody.implicitHeight + 72
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        ColumnLayout {
            id: pageBody
            width: 680
            x: Math.max(0, (page.availableWidth - width) / 2)
            y: 26
            spacing: 12
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
                    anchors.fill: parent
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
                        text: "XXZ Hub"
                        color: theme.muted
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 58
                color: theme.chrome
                border.width: 1
                border.color: theme.borderSoft

                Rectangle {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 36, 776)
                    height: 36
                    radius: 10
                    color: theme.panel
                    border.width: 1
                    border.color: theme.border

                    Row {
                        anchors.centerIn: parent
                        spacing: 2
                        Repeater {
                            model: ["Overview", "Settings", "Discord", "Telegram", "API", "Timers", "Match History"]
                            delegate: NavButton {
                                label: modelData
                                onClicked: root.activeTab = modelData
                            }
                        }
                    }
                }
            }

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                Item {
                    anchors.fill: parent
                    visible: root.activeTab === "Overview"

                    ColumnLayout {
                        width: 680
                        anchors.top: parent.top
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.topMargin: 34
                        spacing: 24

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            SectionTitle { title: "GAME MODE" }
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

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            SectionTitle { title: "EMULATOR" }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 12
                                OptionCard {
                                    Layout.fillWidth: true
                                    label: "LDPlayer"
                                    selected: root.emulator === "ldplayer"
                                    onClicked: hubBridge.updateSetting("emulator", "ldplayer")
                                }
                                OptionCard {
                                    Layout.fillWidth: true
                                    label: "MuMu"
                                    selected: root.emulator === "mumu"
                                    onClicked: hubBridge.updateSetting("emulator", "mumu")
                                }
                            }
                        }

                        Rectangle {
                            id: startButton
                            Layout.alignment: Qt.AlignHCenter
                            Layout.topMargin: 4
                            width: 136
                            height: 40
                            radius: 9
                            color: startMouse.containsMouse ? theme.accentHover : theme.accent

                            Text {
                                anchors.centerIn: parent
                                text: "START"
                                color: "#ffffff"
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }

                            MouseArea {
                                id: startMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: hubBridge.startPyla()
                            }
                        }
                    }
                }

                TabPage {
                    visible: root.activeTab === "Settings"

                    FormPanel {
                        title: "DETECTION"
                        FieldRow {
                            label: "Wall Confidence"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "wall_detection_confidence")); from: 0.1; to: 1.0; onSaved: root.saveValue("settings", "wall_detection_confidence", value) }
                        }
                        FieldRow {
                            label: "Player Confidence"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "entity_detection_confidence")); from: 0.1; to: 1.0; onSaved: root.saveValue("settings", "entity_detection_confidence", value) }
                        }
                        FieldRow {
                            label: "Super Pixels"
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "super_pixels_minimum")); onSaved: root.saveValue("settings", "super_pixels_minimum", value) }
                        }
                        FieldRow {
                            label: "Gadget Pixels"
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "gadget_pixels_minimum")); onSaved: root.saveValue("settings", "gadget_pixels_minimum", value) }
                        }
                        FieldRow {
                            label: "Hypercharge Pixels"
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "hypercharge_pixels_minimum")); onSaved: root.saveValue("settings", "hypercharge_pixels_minimum", value) }
                        }
                    }

                    FormPanel {
                        title: "BEHAVIOR"
                        FieldRow {
                            label: "Minimum Movement Delay"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "minimum_movement_delay")); from: 0.05; to: 3.0; onSaved: root.saveValue("settings", "minimum_movement_delay", value) }
                        }
                        FieldRow {
                            label: "Unstuck Delay"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "unstuck_movement_delay")); from: 0.5; to: 10.0; onSaved: root.saveValue("settings", "unstuck_movement_delay", value) }
                        }
                        FieldRow {
                            label: "Unstuck Duration"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "unstuck_movement_hold_time")); from: 0.2; to: 5.0; onSaved: root.saveValue("settings", "unstuck_movement_hold_time", value) }
                        }
                        FieldRow {
                            label: "After Round"
                            Row { spacing: 8; ChoicePill { label: "Return to lobby"; selected: root.value("settings", "post_match_action") === "lobby"; onClicked: root.saveValue("settings", "post_match_action", "lobby") } ChoicePill { label: "Play again"; selected: root.value("settings", "post_match_action") === "play_again"; onClicked: root.saveValue("settings", "post_match_action", "play_again") } }
                        }
                        FieldRow {
                            label: "Trio Movement"
                            Row { spacing: 8; ChoicePill { label: "Follow"; selected: root.value("settings", "showdown_playstyle_mode") === "follow"; onClicked: root.saveValue("settings", "showdown_playstyle_mode", "follow") } ChoicePill { label: "Hide"; selected: root.value("settings", "showdown_playstyle_mode") === "hide"; onClicked: root.saveValue("settings", "showdown_playstyle_mode", "hide") } }
                        }
                        FieldRow {
                            label: "Longpress Star Drop"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "long_press_star_drop"); onToggled: root.saveValue("settings", "long_press_star_drop", value) } }
                        }
                        FieldRow {
                            label: "Terminal Logging"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "terminal_logging"); onToggled: root.saveValue("settings", "terminal_logging", value) } }
                        }
                        FieldRow {
                            label: "Debug Screen"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "visual_debug"); onToggled: root.saveValue("settings", "visual_debug", value) } }
                        }
                        FieldRow {
                            label: "Advanced Visuals"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "advanced_visuals"); onToggled: root.saveValue("settings", "advanced_visuals", value) } }
                        }
                        FieldRow {
                            label: "Pause Menu IPS Graph"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "pause_menu_ips_graph"); onToggled: root.saveValue("settings", "pause_menu_ips_graph", value) } }
                        }
                        FieldRow {
                            label: "Pause Session Strip"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "pause_menu_session_strip"); onToggled: root.saveValue("settings", "pause_menu_session_strip", value) } }
                        }
                        FieldRow {
                            label: "Pause Graph Samples"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "pause_menu_graph_samples")); from: 30; to: 120; integer: true; onSaved: root.saveValue("settings", "pause_menu_graph_samples", value) }
                        }
                        FieldRow {
                            label: "Capture Vision Frames"
                            CenterRow { ToggleSwitch { checked: root.boolValue("settings", "capture_bad_vision_frames"); onToggled: root.saveValue("settings", "capture_bad_vision_frames", value) } }
                        }
                    }

                    FormPanel {
                        title: "PERFORMANCE"
                        FieldRow {
                            label: "Inference Device"
                            Row { spacing: 8; Repeater { model: ["auto", "directml", "amd", "cuda", "openvino", "cpu"]; delegate: ChoicePill { label: modelData; selected: root.value("settings", "cpu_or_gpu") === modelData; onClicked: root.saveValue("settings", "cpu_or_gpu", modelData) } } }
                        }
                        FieldRow {
                            label: "DirectML GPU ID"
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "directml_device_id")); onSaved: root.saveValue("settings", "directml_device_id", value) }
                        }
                        FieldRow {
                            label: "Max IPS"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "max_ips")); from: 0; to: 120; integer: true; onSaved: root.saveValue("settings", "max_ips", value) }
                        }
                        FieldRow {
                            label: "Scrcpy Max FPS"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "scrcpy_max_fps")); from: 5; to: 120; integer: true; onSaved: root.saveValue("settings", "scrcpy_max_fps", value) }
                        }
                        FieldRow {
                            label: "Used Threads"
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "used_threads")); onSaved: root.saveValue("settings", "used_threads", value) }
                        }
                        FieldRow {
                            label: "Trophy Multiplier"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "trophies_multiplier")); from: 1; to: 10; integer: true; onSaved: root.saveValue("settings", "trophies_multiplier", value) }
                        }
                        FieldRow {
                            label: "OCR Scale"
                            NumericSlider { anchors.fill: parent; value: String(root.value("settings", "ocr_scale_down_factor")); from: 0.1; to: 1.0; onSaved: root.saveValue("settings", "ocr_scale_down_factor", value) }
                        }
                        FieldRow {
                            label: "Current Playstyle"
                            ConfigInput { anchors.fill: parent; value: String(root.value("settings", "current_playstyle")); onSaved: root.saveValue("settings", "current_playstyle", value) }
                        }
                        FieldRow {
                            label: "Performance Profile"
                            Row {
                                spacing: 8
                                ChoicePill { label: "balanced"; selected: root.performanceProfile === "balanced"; onClicked: root.performanceProfile = "balanced" }
                                ChoicePill { label: "low-end"; selected: root.performanceProfile === "low-end"; onClicked: root.performanceProfile = "low-end" }
                                ChoicePill { label: "quality"; selected: root.performanceProfile === "quality"; onClicked: root.performanceProfile = "quality" }
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
                        FieldRow { label: "Webhook URL"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "webhook_url")); secret: true; onSaved: root.saveValue("discord", "webhook_url", value) } }
                        FieldRow { label: "Discord ID"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_id")); onSaved: root.saveValue("discord", "discord_id", value) } }
                        FieldRow { label: "Webhook Name"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "username")); onSaved: root.saveValue("discord", "username", value) } }
                        FieldRow { label: "Send Match Summary"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "send_match_summary"); onToggled: root.saveValue("discord", "send_match_summary", value) } } }
                        FieldRow { label: "Include Screenshots"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "include_screenshot"); onToggled: root.saveValue("discord", "include_screenshot", value) } } }
                        FieldRow { label: "Ping When Stuck"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "ping_when_stuck"); onToggled: root.saveValue("discord", "ping_when_stuck", value) } } }
                        FieldRow { label: "Ping On Target"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "ping_when_target_is_reached"); onToggled: root.saveValue("discord", "ping_when_target_is_reached", value) } } }
                        FieldRow { label: "Every X Matches"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "ping_every_x_match")); onSaved: root.saveValue("discord", "ping_every_x_match", value) } }
                        FieldRow { label: "Every X Minutes"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "ping_every_x_minutes")); onSaved: root.saveValue("discord", "ping_every_x_minutes", value) } }
                    }
                    FormPanel {
                        title: "REMOTE CONTROL"
                        FieldRow { label: "Enable Discord Control"; CenterRow { ToggleSwitch { checked: root.boolValue("discord", "discord_control_enabled"); onToggled: root.saveValue("discord", "discord_control_enabled", value) } } }
                        FieldRow { label: "Bot Token"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_bot_token")); secret: true; onSaved: root.saveValue("discord", "discord_bot_token", value) } }
                        FieldRow { label: "Allowed User ID"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_control_user_id")); onSaved: root.saveValue("discord", "discord_control_user_id", value) } }
                        FieldRow { label: "Allowed Channel ID"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_control_channel_id")); onSaved: root.saveValue("discord", "discord_control_channel_id", value) } }
                        FieldRow { label: "Guild ID"; ConfigInput { anchors.fill: parent; value: String(root.value("discord", "discord_control_guild_id")); onSaved: root.saveValue("discord", "discord_control_guild_id", value) } }
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
                        FieldRow { label: "Enable Telegram"; CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "enabled"); onToggled: root.saveValue("telegram", "enabled", value) } } }
                        FieldRow { label: "Bot Token"; ConfigInput { anchors.fill: parent; value: String(root.value("telegram", "bot_token")); secret: true; onSaved: root.saveValue("telegram", "bot_token", value) } }
                        FieldRow { label: "Notification Chat IDs"; ConfigInput { anchors.fill: parent; value: String(root.value("telegram", "notification_chat_ids")); onSaved: root.saveValue("telegram", "notification_chat_ids", value) } }
                        FieldRow { label: "Send Match Summary"; CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "send_match_summary"); onToggled: root.saveValue("telegram", "send_match_summary", value) } } }
                        FieldRow { label: "Include Screenshots"; CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "include_screenshot"); onToggled: root.saveValue("telegram", "include_screenshot", value) } } }
                        FieldRow { label: "Multiple Chats"; CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "allow_multiple_notification_chat_ids"); onToggled: root.saveValue("telegram", "allow_multiple_notification_chat_ids", value) } } }
                        FieldRow { label: "Remote Control"; CenterRow { ToggleSwitch { checked: root.boolValue("telegram", "remote_control_enabled"); onToggled: root.saveValue("telegram", "remote_control_enabled", value) } } }
                        FieldRow { label: "Poll Timeout"; ConfigInput { anchors.fill: parent; value: String(root.value("telegram", "poll_timeout_seconds")); onSaved: root.saveValue("telegram", "poll_timeout_seconds", value) } }
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
                        FieldRow { label: "Player Tag"; ConfigInput { anchors.fill: parent; value: String(root.value("api", "player_tag")); onSaved: root.saveValue("api", "player_tag", value) } }
                        FieldRow { label: "Auto Refresh Token"; CenterRow { ToggleSwitch { checked: root.boolValue("api", "auto_refresh_token"); onToggled: root.saveValue("api", "auto_refresh_token", value) } } }
                        FieldRow { label: "Developer Email"; ConfigInput { anchors.fill: parent; value: String(root.value("api", "developer_email")); onSaved: root.saveValue("api", "developer_email", value) } }
                        FieldRow { label: "Developer Password"; ConfigInput { anchors.fill: parent; value: String(root.value("api", "developer_password")); secret: true; onSaved: root.saveValue("api", "developer_password", value) } }
                        FieldRow { label: "API Token"; ConfigInput { anchors.fill: parent; value: String(root.value("api", "api_token")); secret: true; onSaved: root.saveValue("api", "api_token", value) } }
                        FieldRow { label: "Timeout Seconds"; ConfigInput { anchors.fill: parent; value: String(root.value("api", "timeout_seconds")); onSaved: root.saveValue("api", "timeout_seconds", value) } }
                        FieldRow { label: "Public IP Service"; ConfigInput { anchors.fill: parent; value: String(root.value("api", "public_ip_service")); onSaved: root.saveValue("api", "public_ip_service", value) } }
                        FieldRow { label: "Key Name Prefix"; ConfigInput { anchors.fill: parent; value: String(root.value("api", "key_name_prefix")); onSaved: root.saveValue("api", "key_name_prefix", value) } }
                        FieldRow { label: "Delete Old Tokens"; CenterRow { ToggleSwitch { checked: root.boolValue("api", "delete_old_auto_tokens"); onToggled: root.saveValue("api", "delete_old_auto_tokens", value) } } }
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
                        FieldRow { label: "Super Delay"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "super")); from: 0.05; to: 10; onSaved: root.saveValue("timers", "super", value) } }
                        FieldRow { label: "Hypercharge Delay"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "hypercharge")); from: 0.05; to: 10; onSaved: root.saveValue("timers", "hypercharge", value) } }
                        FieldRow { label: "Gadget Delay"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "gadget")); from: 0.05; to: 10; onSaved: root.saveValue("timers", "gadget", value) } }
                        FieldRow { label: "Wall Detection"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "wall_detection")); from: 0.05; to: 10; onSaved: root.saveValue("timers", "wall_detection", value) } }
                        FieldRow { label: "No Detection Proceed"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "no_detection_proceed")); from: 0.1; to: 20; onSaved: root.saveValue("timers", "no_detection_proceed", value) } }
                        FieldRow { label: "Low IPS Recovery"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "low_ips_recovery_seconds")); from: 5; to: 90; integer: true; onSaved: root.saveValue("timers", "low_ips_recovery_seconds", value) } }
                        FieldRow { label: "Low IPS Cooldown"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "low_ips_recovery_cooldown")); from: 5; to: 90; integer: true; onSaved: root.saveValue("timers", "low_ips_recovery_cooldown", value) } }
                        FieldRow { label: "App Restart Attempt"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "low_ips_app_restart_after")); from: 1; to: 6; integer: true; onSaved: root.saveValue("timers", "low_ips_app_restart_after", value) } }
                        FieldRow { label: "Emulator Restart Attempt"; NumericSlider { anchors.fill: parent; value: String(root.value("timers", "low_ips_emulator_restart_after")); from: 1; to: 10; integer: true; onSaved: root.saveValue("timers", "low_ips_emulator_restart_after", value) } }
                    }
                }

                TabPage {
                    visible: root.activeTab === "Match History"
                    Flow {
                        Layout.fillWidth: true
                        spacing: 12
                        Repeater {
                            model: root.hubState.history || []
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
                        visible: !root.hubState.history || root.hubState.history.length === 0
                        text: "No match history yet."
                        color: theme.faint
                        font.pixelSize: 12
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
                    Text { text: "Pyla is free, public, and open-source."; color: theme.faint; font.pixelSize: 11 }
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
                    Text { text: "XXZ"; color: theme.faint; font.pixelSize: 11 }
                }
            }
        }
    }
}
