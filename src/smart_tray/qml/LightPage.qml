import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ContentScroll {
    id: page
    objectName: "lightScroll"
    property var led
    property bool motion: false
    property string tab: "colour"
    property real hue: led.hsv.h
    property real saturation: led.hsv.s
    property real level: led.hsv.v
    property bool colourEditing: false
    function syncColour() { hue = led.hsv.h; saturation = led.hsv.s; level = led.hsv.v }
    function commitColour() {
        // Snapshot the intent before synchronous busy/state signals can reset it.
        const h = Math.round(hue), s = Math.round(saturation), v = Math.max(10, Math.round(level))
        smart.selectHsv(h, s, v)
        colourEditing = false
        if (!led.busy) syncColour()
    }
    Connections {
        target: smart
        function onChanged() {
            if (!page.colourEditing && !page.led.busy) page.syncColour()
            if (!brightnessSlider.pressed) brightnessSlider.value = page.led.brightnessDraft == null ? 100 : page.led.brightnessDraft
        }
    }
    ColumnLayout {
        width: page.availableWidth; spacing: 16
        Rectangle {
            objectName: "ledCard"
            Layout.fillWidth: true; implicitHeight: ledHeader.implicitHeight + page.cardPadding * 2; radius: 22; color: "#172132"; border.color: "#2C3C54"
            ColumnLayout {
                id: ledHeader; objectName: "ledContent"
                x: page.cardPadding; y: page.cardPadding; width: parent.width - page.cardPadding * 2; spacing: 16
                RowLayout {
                    Layout.fillWidth: true
                    Column { spacing: 3
                        Text { text: "Fita Led RGB"; color: "#EEF4FF"; font.pixelSize: 18; font.weight: Font.DemiBold; font.family: "Segoe UI" }
                        Text { objectName: "ledPowerStatus"; text: page.led.online ? (page.led.power ? "Ligada" : "Desligada") : "Sem confirmação"; color: "#8EA2BF"; font.pixelSize: 11; font.family: "Segoe UI" }
                    }
                    Item { Layout.fillWidth: true }
                    ActionButton { objectName: "ledPower"; Layout.preferredWidth: 46; implicitWidth: 46; Layout.preferredHeight: 46; iconName: "power"; accent: page.led.power === true; enabled: page.led.powerEnabled; onClicked: smart.toggle("led", 20); Accessible.name: "Fita liga ou desliga" }
                }
                LedIllustration {
                    objectName: "ledIllustration"; Layout.fillWidth: true
                    online: page.led.online; powered: page.led.power === true
                    powerKnown: typeof page.led.power === "boolean"
                    colourKnown: page.led.colourKnown; mode: page.led.mode || ""
                    colour: page.led.colourHex; brightness: page.led.brightness == null ? 0 : page.led.brightness
                }
            }
        }
        RowLayout {
            objectName: "lightTabs"
            Layout.fillWidth: true; spacing: 8
            Repeater {
                model: [{title:"Cores", value:"colour"}, {title:"Favoritas", value:"favorites"}]
                ActionButton { required property var modelData; objectName: "lightTab_" + modelData.value; Layout.fillWidth: true; text: modelData.title; accent: page.tab === modelData.value; onClicked: { page.tab = modelData.value; page.contentItem.contentY = 0 } }
            }
        }
        ColumnLayout {
            visible: page.tab === "colour"; Layout.fillWidth: true; spacing: 12
            Item {
                Layout.fillWidth: true; implicitHeight: 224
                Item {
                    id: colourWheel; objectName: "colourWheel"; width: 224; height: 224; anchors.centerIn: parent
                    Canvas {
                        anchors.fill: parent
                        onPaint: {
                            let c = getContext("2d"); c.reset()
                            for (let a = 0; a < 360; a += 2) {
                                c.beginPath(); c.lineWidth = 24; c.strokeStyle = Qt.hsva(a / 360, 1, 1, 1).toString()
                                c.arc(width / 2, height / 2, width / 2 - 16, (a - 90) * Math.PI / 180, (a - 87) * Math.PI / 180); c.stroke()
                            }
                        }
                    }
                    Rectangle { anchors.centerIn: parent; width: 170; height: 170; radius: 85; color: "#111C2B"; border.color: "#25374C" }
                    MouseArea {
                        id: hueTouch; objectName: "hueTouch"; anchors.fill: parent; enabled: page.led.colourEnabled
                        preventStealing: true
                        acceptedButtons: Qt.LeftButton
                        function updateHue(mouse) {
                            page.hue = (Math.atan2(mouse.y - height / 2, mouse.x - width / 2) * 180 / Math.PI + 450) % 360
                            if (page.saturation === 0) page.saturation = 1000
                        }
                        onPressed: function(mouse) {
                            const radius = Math.hypot(mouse.x-width/2, mouse.y-height/2)
                            if (radius < 82 || radius > 112) { mouse.accepted = false; return }
                            page.colourEditing = true; updateHue(mouse)
                        }
                        onPositionChanged: function(mouse) { if (pressed) updateHue(mouse) }
                        onReleased: function(mouse) { updateHue(mouse); page.commitColour() }
                        onCanceled: { page.colourEditing = false; page.syncColour() }
                        onWheel: function(wheel) { wheel.accepted = false }
                    }
                    Rectangle {
                        width: 15; height: 15; radius: 8; color: Qt.hsva(page.hue / 360, 1, 1, 1); border.color: "white"; border.width: 3
                        x: parent.width / 2 + Math.sin(page.hue * Math.PI / 180) * (parent.width / 2 - 16) - width / 2
                        y: parent.height / 2 - Math.cos(page.hue * Math.PI / 180) * (parent.width / 2 - 16) - height / 2
                    }
                    Rectangle {
                        id: square; objectName: "colourSquare"; width: 118; height: 118; anchors.centerIn: parent; radius: 9; clip: true
                        color: Qt.hsva(page.hue / 360, 1, 1, 1)
                        Rectangle { anchors.fill: parent; gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: "#FFFFFFFF" } GradientStop { position: 1; color: "#00FFFFFF" } } }
                        Rectangle { anchors.fill: parent; gradient: Gradient { GradientStop { position: 0; color: "#00000000" } GradientStop { position: 1; color: "#FF000000" } } }
                        Rectangle { width: 13; height: 13; radius: 7; color: "transparent"; border.color: "white"; border.width: 2; x: page.saturation / 1000 * (parent.width - width); y: (1 - page.level / 1000) * (parent.height - height) }
                        MouseArea {
                            id: squareTouch; objectName: "squareTouch"; anchors.fill: parent; enabled: page.led.colourEnabled
                            preventStealing: true
                            acceptedButtons: Qt.LeftButton
                            function updateColour(mouse) { page.saturation = Math.round(Math.max(0, Math.min(1, mouse.x / width)) * 1000); page.level = Math.round(Math.max(0.01, Math.min(1, 1 - mouse.y / height)) * 1000) }
                            onPressed: function(mouse) { page.colourEditing = true; updateColour(mouse) }
                            onPositionChanged: function(mouse) { if (pressed) updateColour(mouse) }
                            onReleased: function(mouse) { updateColour(mouse); page.commitColour() }
                            onCanceled: { page.colourEditing = false; page.syncColour() }
                            onWheel: function(wheel) { wheel.accepted = false }
                        }
                    }
                    opacity: page.led.colourEnabled ? 1 : 0.35
                    Behavior on opacity { NumberAnimation { duration: smart.reducedMotion ? 0 : 180 } }
                }
            }
            RowLayout {
                objectName: "colourPalette"
                Layout.fillWidth: true; spacing: 9
                Repeater {
                    model: [{hex:"#FF0000", hsv:"000003e803e8"}, {hex:"#FF8000", hsv:"001e03e803e8"}, {hex:"#FFFF00", hsv:"003c03e803e8"}, {hex:"#00FF00", hsv:"007803e803e8"}, {hex:"#00FFFF", hsv:"00b403e803e8"}, {hex:"#0000FF", hsv:"00f003e803e8"}, {hex:"#FF00FF", hsv:"012c03e803e8"}, {hex:"#FFFFFF", hsv:"0000000003e8"}]
                    Button {
                        required property var modelData
                        objectName: "palette_" + modelData.hsv
                        Layout.fillWidth: true; Layout.preferredWidth: 1; implicitHeight: 32; wheelEnabled: false; enabled: page.led.colourEnabled; opacity: enabled ? 1 : 0.3
                        background: Rectangle { anchors.centerIn: parent; width: 27; height: 27; radius: 14; color: modelData.hex; border.color: parent.down ? "#FFFFFF" : "#70849D"; border.width: parent.down ? 3 : 1 }
                        onClicked: smart.selectColour(modelData.hsv)
                        Accessible.name: "Selecionar cor " + modelData.hex
                    }
                }
            }
            RowLayout { Layout.fillWidth: true
                Text { text: "Brilho"; color: "#C4D3E7"; font.pixelSize: 14; font.family: "Segoe UI" }
                Item { Layout.fillWidth: true }
                Text { objectName: "brightnessReadout"; text: brightnessSlider.pressed ? Math.round(brightnessSlider.value) + "%" : page.led.brightnessDraft == null ? "—" : page.led.brightnessDraft + "%"; color: "#8DB5DC"; font.pixelSize: 14; font.family: "Segoe UI" }
            }
            FluidSlider {
                id: brightnessSlider; objectName: "brightnessSlider"; Layout.fillWidth: true
                from: 1; to: 100; value: page.led.brightnessDraft == null ? 100 : page.led.brightnessDraft
                fillColor: page.led.mode === "colour" ? page.led.colourHex : "#A08CEB"; enabled: page.led.brightnessEnabled
                onMoved: { if (!pressed) smart.scheduleBrightness(Math.round(value)) }
                onPressedChanged: { if (!pressed && enabled) smart.scheduleBrightness(Math.round(value)) }
                Accessible.name: "Brilho da fita"
            }
            RowLayout { Layout.fillWidth: true
                Text { Layout.fillWidth: true; text: page.led.mode === "colour" ? "Cor fixa" : "Escolher uma cor ativa iluminação fixa."; color: "#8196B0"; font.pixelSize: 11; font.family: "Segoe UI"; wrapMode: Text.WordWrap }
                ActionButton { objectName: "saveFavorite"; text: "Salvar"; iconName: "heart"; Layout.preferredWidth: 96; implicitWidth: 96; enabled: page.led.online && page.led.colourKnown && page.led.mode === "colour" && !page.led.busy; onClicked: smart.favorite() }
            }
        }
        ColumnLayout {
            visible: page.tab === "favorites"; Layout.fillWidth: true; spacing: 17
            Text { text: "As suas cores"; color: "#ECF4FF"; font.pixelSize: 24; font.family: "Segoe UI" }
            Text { visible: smart.favorites.length === 0; Layout.fillWidth: true; text: "Escolha uma cor fixa e use Salvar para encontrá-la aqui."; color: "#8A9FB9"; font.pixelSize: 13; font.family: "Segoe UI"; wrapMode: Text.WordWrap }
            Flow {
                Layout.fillWidth: true; spacing: 12
                Repeater {
                    model: smart.favorites
                    Button { required property var modelData; objectName: "favorite_" + modelData.value; width: 78; height: 78; wheelEnabled: false; enabled: page.led.colourEnabled; opacity: enabled ? 1 : 0.35
                        background: Rectangle { radius: 19; color: modelData.colour; border.color: "#7088A8" }
                        onClicked: smart.selectColour(modelData.value)
                        Accessible.name: "Cor favorita"
                    }
                }
            }
        }
        Text { Layout.fillWidth: true; text: !page.led.online ? "Fita sem resposta. Atualize para consultar." : !page.led.power ? "Ligue a fita para escolher uma cor." : !smart.experimentalEnabled ? "Ative os controles adicionais em Configurações para usar cor e brilho." : ""; color: "#B7A68B"; font.pixelSize: 12; font.family: "Segoe UI"; wrapMode: Text.WordWrap; visible: text !== "" }
        ActionButton { objectName: "enableLightControls"; text: "Abrir Configurações"; Layout.fillWidth: true; visible: !smart.experimentalEnabled; onClicked: smart.navigate("settings") }
        Text { Layout.fillWidth: true; text: page.led.transitioning ? "Preparando cor fixa…" : page.led.message; visible: text !== ""; color: "#88B9BA"; font.pixelSize: 11; font.family: "Segoe UI"; wrapMode: Text.WordWrap }
    }
}
