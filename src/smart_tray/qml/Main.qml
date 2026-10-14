import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "smartRoot"
    width: 480; height: 850
    radius: 26
    color: "#0C1018"
    border.color: "#2B394C"
    readonly property int contentInset: 24
    readonly property int sectionGap: 16
    readonly property real contentSpan: Math.max(0, width - contentInset * 2)
    property var ac: smart.state.elgin
    property var led: smart.state.led
    property var channelState: smart.state.novadigital
    property bool motion: smart.panelVisible && !smart.reducedMotion
    property string lightTab: "colour"
    property string notification: ""
    property string selectedFunction: ""
    property string selectedRole: "elgin"
    property var selectionOptions: []

    function openSelection(role, name, options) {
        selectedRole = role; selectedFunction = name; selectionOptions = options; choices.open()
    }
    function safeNumber(value) { return value == null || value === undefined ? "—" : String(value) }

    Connections {
        target: smart
        function onToast(message) { root.notification = message; toastTimer.restart() }
        function onPageChanged() { pageFade.restart(); choices.close() }
        function onChanged() {
            if (!temperatureSlider.pressed) temperatureSlider.value = root.ac.temperatureDraft == null ? 24 : root.ac.temperatureDraft
        }
    }
    Timer { id: toastTimer; interval: 5500; onTriggered: root.notification = "" }
    NumberAnimation { id: pageFade; target: pages; property: "opacity"; from: 0.45; to: 1; duration: smart.reducedMotion ? 0 : 220; easing.type: Easing.OutCubic }

    Item {
        id: header
        objectName: "mainHeader"
        x: root.contentInset; y: 16; width: root.contentSpan; height: 44
        MouseArea {
            objectName: "dragHeader"
            width: parent.width - 140; height: parent.height
            cursorShape: Qt.SizeAllCursor
            onPressed: function(event) { let p = mapToGlobal(event.x, event.y); smart.beginDrag(Math.round(p.x), Math.round(p.y)) }
            onPositionChanged: function(event) { if (pressed) { let p = mapToGlobal(event.x, event.y); smart.moveDrag(Math.round(p.x), Math.round(p.y)) } }
            onReleased: smart.endDrag()
            onCanceled: smart.endDrag()
        }
        Row {
            anchors.verticalCenter: parent.verticalCenter; spacing: 10
            Rectangle { width: 30; height: 30; radius: 10; color: "#3B82F6"; AppIcon { anchors.centerIn: parent; name: "home"; ink: "white"; width: 20; height: 20 } }
            Text { text: "Smart Tray"; color: "#EFF6FF"; font.pixelSize: 19; font.weight: Font.DemiBold; font.family: "Segoe UI"; anchors.verticalCenter: parent.verticalCenter }
        }
        Row { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 6
            ActionButton { objectName: "settingsButton"; width: 38; height: 34; iconName: "settings"; onClicked: smart.navigate("settings"); Accessible.name: "Configurações" }
            ActionButton { objectName: "minimizeButton"; width: 38; height: 34; iconName: "minus"; onClicked: smart.minimize(); Accessible.name: "Minimizar" }
            ActionButton { objectName: "hideButton"; width: 38; height: 34; iconName: "close"; onClicked: smart.hide(); Accessible.name: "Ocultar" }
        }
    }
    Row {
        id: navigation
        objectName: "mainNavigation"
        x: root.contentInset; width: root.contentSpan; height: 42; spacing: 8
        anchors.top: header.bottom; anchors.topMargin: root.sectionGap
        Repeater {
            model: [{name: "Clima", page: "climate"}, {name: "Luz", page: "light"}, {name: "Interruptor", page: "switch"}]
            ActionButton {
                required property var modelData
                objectName: "nav_" + modelData.page
                width: (navigation.width - 16) / 3
                text: modelData.name
                accent: smart.page === modelData.page
                tint: "#73CBED"
                onClicked: smart.navigate(modelData.page)
            }
        }
    }

    StackLayout {
        id: pages
        objectName: "pageStack"
        // The content shares the header grid. The scrollbar gets its own rail
        // in the right margin, without narrowing or shifting the content.
        x: root.contentInset; width: root.contentSpan + climateScroll.rightPadding
        anchors.top: navigation.bottom; anchors.topMargin: root.sectionGap
        anchors.bottom: footer.top; anchors.bottomMargin: 12
        currentIndex: smart.page === "climate" ? 0 : smart.page === "light" ? 1 : smart.page === "switch" ? 2 : 3
        ContentScroll {
            id: climateScroll
            objectName: "climateScroll"
            ColumnLayout {
                width: climateScroll.availableWidth; spacing: 13
                Rectangle {
                    objectName: "climateCard"
                    Layout.fillWidth: true
                    implicitHeight: climateContent.implicitHeight + climateScroll.cardPadding * 2
                    radius: 22
                    gradient: Gradient { GradientStop { position: 0; color: "#1B3045" } GradientStop { position: 0.4; color: "#141E2A" } GradientStop { position: 1; color: "#111822" } }
                    border.color: "#2C4156"
                    ColumnLayout {
                        id: climateContent
                        objectName: "climateContent"
                        x: climateScroll.cardPadding; y: climateScroll.cardPadding
                        width: parent.width - climateScroll.cardPadding * 2; spacing: 12
                        RowLayout {
                            Layout.fillWidth: true
                            ColumnLayout { spacing: 3
                                Text { text: "Elgin Eco Inverter III"; color: "#F0F6FF"; font.pixelSize: 15; font.weight: Font.DemiBold; font.family: "Segoe UI" }
                                Text { text: root.ac.online ? (root.ac.power === true ? "Ligado" : root.ac.power === false ? "Desligado" : "Estado desconhecido") : "Sem confirmação de estado"; color: "#91A7C0"; font.pixelSize: 11; font.family: "Segoe UI" }
                            }
                            Item { Layout.fillWidth: true }
                            ActionButton {
                                objectName: "elginPower"; Layout.preferredWidth: 46; implicitWidth: 46; Layout.preferredHeight: 46; iconName: "power"
                                accent: root.ac.power === true; enabled: root.ac.powerEnabled
                                onClicked: smart.command("elgin", "power", !root.ac.power)
                                Accessible.name: "Elgin liga ou desliga"
                            }
                        }
                        SplitIllustration {
                            objectName: "splitIllustration"
                            Layout.fillWidth: true; Layout.preferredHeight: 200
                            powered: root.ac.online && root.ac.power === true
                            animate: root.motion && smart.page === "climate"
                            temperature: root.safeNumber(root.ac.temperature)
                            fan: root.ac.fan || ""
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Text { objectName: "temperatureReadout"; text: temperatureSlider.pressed ? Math.round(temperatureSlider.value) : root.safeNumber(root.ac.temperatureDraft); color: "#F2F8FF"; font.pixelSize: 62; font.weight: Font.Light; font.family: "Segoe UI" }
                            Text { text: "°C"; color: "#99B0C8"; font.pixelSize: 19; Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: 13 }
                            Item { Layout.fillWidth: true }
                            Column { spacing: 5
                                Text { text: "NO AMBIENTE"; color: "#7C91AB"; font.pixelSize: 9; font.letterSpacing: 1 }
                                Text { text: root.safeNumber(root.ac.ambient) + " °C"; color: "#BDD2E4"; font.pixelSize: 21; font.family: "Segoe UI" }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 9
                            ActionButton { objectName: "temperatureMinus"; Layout.preferredWidth: 36; implicitWidth: 36; Layout.preferredHeight: 36; iconName: "minus"; enabled: root.ac.temperatureEnabled && root.ac.temperatureDraft > 16; onClicked: smart.scheduleTemperature(root.ac.temperatureDraft - 1) }
                            FluidSlider {
                                id: temperatureSlider; objectName: "temperatureSlider"; Layout.fillWidth: true
                                from: 16; to: 32; value: root.ac.temperatureDraft == null ? 24 : root.ac.temperatureDraft
                                enabled: root.ac.temperatureEnabled
                                onMoved: { if (!pressed) smart.scheduleTemperature(Math.round(value)) }
                                onPressedChanged: { if (!pressed && enabled) smart.scheduleTemperature(Math.round(value)) }
                                Accessible.name: "Temperatura configurada"
                            }
                            ActionButton { objectName: "temperaturePlus"; Layout.preferredWidth: 36; implicitWidth: 36; Layout.preferredHeight: 36; iconName: "plus"; enabled: root.ac.temperatureEnabled && root.ac.temperatureDraft < 32; onClicked: smart.scheduleTemperature(root.ac.temperatureDraft + 1) }
                        }
                        RowLayout { Layout.fillWidth: true; Layout.leftMargin: 46; Layout.rightMargin: 46
                            Text { text: "16°"; color: "#6F829B"; font.pixelSize: 10 }
                            Item { Layout.fillWidth: true }
                            Text { text: "32°"; color: "#6F829B"; font.pixelSize: 10 }
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 7
                            ControlTile { objectName: "modeTile"; Layout.fillWidth: true; Layout.preferredWidth: 1; title: "Modo"; value: root.ac.modeTitle; iconName: "cold"; enabled: root.ac.modeEnabled; onClicked: root.openSelection("elgin", "mode", root.ac.modeOptions) }
                            ControlTile { objectName: "fanTile"; Layout.fillWidth: true; Layout.preferredWidth: 1; title: "Ventilação"; value: root.ac.fanTitle; iconName: "fan"; enabled: root.ac.fanEnabled; onClicked: root.openSelection("elgin", "fan", root.ac.fanOptions) }
                            ControlTile { objectName: "sleepTile"; Layout.fillWidth: true; Layout.preferredWidth: 1; title: "Dormir"; value: root.ac.sleep == null ? "Indisponível" : root.ac.sleep ? "Ligado" : "Desligado"; iconName: "moon"; selectable: false; highlighted: root.ac.sleep === true; enabled: root.ac.sleepEnabled; onClicked: smart.command("elgin", "sleep", !root.ac.sleep) }
                            ControlTile { objectName: "swingTile"; Layout.fillWidth: true; Layout.preferredWidth: 1; title: "Oscilação"; value: "Indisponível"; iconName: "swing"; enabled: false; selectable: false }
                        }
                        RowLayout { Layout.fillWidth: true; spacing: 8
                            ActionButton { Layout.fillWidth: true; iconName: "display"; text: "Visor · " + (root.ac.display == null ? "Indisponível" : root.ac.display ? "Ligado" : "Desligado"); enabled: root.ac.displayEnabled; onClicked: smart.command("elgin", "display", !root.ac.display) }
                            ActionButton { Layout.fillWidth: true; iconName: "leaf"; text: "Eco · " + (root.ac.eco == null ? "Indisponível" : root.ac.eco ? "Ligado" : "Desligado"); enabled: root.ac.ecoEnabled; onClicked: smart.command("elgin", "eco", !root.ac.eco) }
                        }
                        Text { Layout.fillWidth: true; text: !root.ac.online ? "Atualize para consultar o aparelho." : root.ac.power !== true ? "Ligue o aparelho para ajustar temperatura e ventilação." : !smart.experimentalEnabled ? "Temperatura e Média disponíveis. Outros controles em Configurações." : root.ac.mode !== "cold" ? "Temperatura e ventilação disponíveis em Resfriar." : ""; color: "#8DA2B9"; font.pixelSize: 11; font.family: "Segoe UI"; wrapMode: Text.WordWrap; visible: text !== "" }
                        Text { Layout.fillWidth: true; text: root.ac.message; visible: text !== ""; color: root.ac.online ? "#8ABEB8" : "#AF9C85"; font.pixelSize: 11; font.family: "Segoe UI"; wrapMode: Text.WordWrap }
                    }
                }
            }
        }

        LightPage { id: lightPage; led: root.led; motion: root.motion && smart.page === "light" }

        SwitchPage { device: root.channelState }

        SettingsPage {}
    }

    RowLayout {
        id: footer
        objectName: "appFooter"
        x: root.contentInset; width: root.contentSpan; height: 36; spacing: 8
        anchors.bottom: parent.bottom; anchors.bottomMargin: root.contentInset
        Item { Layout.fillWidth: true }
        ActionButton {
            objectName: "refreshButton"
            Layout.preferredWidth: 36; Layout.minimumWidth: 36; Layout.maximumWidth: 36
            Layout.preferredHeight: 36; Layout.minimumHeight: 36; Layout.maximumHeight: 36
            leftPadding: 8; rightPadding: 8; topPadding: 8; bottomPadding: 8
            iconName: "refresh"
            onClicked: smart.refresh(); Accessible.name: "Atualizar estados"
        }
    }
    Rectangle {
        visible: root.notification !== ""; x: root.contentInset; width: root.contentSpan; height: toastText.implicitHeight + 26
        y: footer.y - height - 12; radius: 15; color: "#26394D"; border.color: "#526B85"; z: 20
        Text { id: toastText; anchors.centerIn: parent; width: parent.width - 28; text: root.notification; wrapMode: Text.WordWrap; color: "#E8F0F9"; font.pixelSize: 12; font.family: "Segoe UI" }
    }
    Popup {
        id: choices; objectName: "choicePopup"
        x: root.contentInset; y: Math.min(footer.y - implicitHeight - 12, 350); width: root.contentSpan
        padding: 14; modal: false; closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { radius: 22; color: "#182536"; border.color: "#3D536E" }
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: smart.reducedMotion ? 0 : 180 } }
        contentItem: ColumnLayout {
            spacing: 8
            Text { text: root.selectedFunction === "mode" ? "Modo de operação" : "Velocidade do ventilador"; color: "#E8F1FB"; font.pixelSize: 18; font.family: "Segoe UI"; Layout.bottomMargin: 7 }
            Repeater {
                model: root.selectionOptions
                ActionButton {
                    required property var modelData
                    objectName: "choice_" + modelData.value
                    Layout.fillWidth: true; text: modelData.text; enabled: modelData.enabled
                    onClicked: { choices.close(); smart.command(root.selectedRole, root.selectedFunction, modelData.value) }
                }
            }
        }
    }
}
