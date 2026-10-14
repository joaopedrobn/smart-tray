import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ContentScroll {
    id: page
    objectName: "switchScroll"
    property var device
    ColumnLayout {
        width: page.availableWidth; spacing: 16
        Text { text: "Interruptor Nova Digital"; color: "#EEF5FF"; font.pixelSize: 23; font.weight: Font.Light; font.family: "Segoe UI" }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 316; radius: 22; border.color: "#2B3D4E"
            gradient: Gradient { GradientStop { position: 0; color: "#20313D" } GradientStop { position: 1; color: "#131D28" } }
            SwitchIllustration {
                objectName: "switchIllustration"; anchors.fill: parent
                touchKnown: page.device.online && page.device.channels[0].known
                socketKnown: page.device.online && page.device.channels[1].known
                touchOn: touchKnown && page.device.channels[0].power === true
                socketOn: socketKnown && page.device.channels[1].power === true
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 12
            Repeater {
                model: page.device.channels
                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true; Layout.preferredWidth: 1; implicitHeight: 158; radius: 19
                    color: modelData.known && modelData.power ? "#1A3033" : "#161F2B"
                    border.color: modelData.known && modelData.power ? "#345459" : "#29384B"
                    Behavior on color { ColorAnimation { duration: smart.reducedMotion ? 0 : 240 } }
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 15; spacing: 8
                        RowLayout { Layout.fillWidth: true
                            AppIcon { name: modelData.number === 1 ? "touch" : "socket"; ink: modelData.power === true ? "#91D6DC" : "#8C9FB8" }
                            Text { text: modelData.number === 1 ? "Botão touch" : "Tomada"; color: "#E6EEF8"; font.pixelSize: 14; font.family: "Segoe UI" }
                        }
                        Text { text: !modelData.known ? "Sem confirmação" : modelData.power ? "Ligado" : "Desligado"; color: "#91AABC"; font.pixelSize: 12; font.family: "Segoe UI" }
                        Item { Layout.fillHeight: true }
                        ActionButton { objectName: "channelPower" + modelData.number; Layout.fillWidth: true; implicitHeight: 37; text: modelData.power ? "Desligar" : "Ligar"; iconName: "power"; accent: modelData.power === true; tint: "#9BD3D3"; enabled: modelData.enabled; onClicked: smart.toggle("novadigital", modelData.number) }
                    }
                }
            }
        }
        Text { Layout.fillWidth: true; text: page.device.message; visible: text !== ""; color: "#89B8B2"; font.pixelSize: 11; font.family: "Segoe UI"; wrapMode: Text.WordWrap }
    }
}
