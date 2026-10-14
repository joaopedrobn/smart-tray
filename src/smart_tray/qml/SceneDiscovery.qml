import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: capture
    property var discovery: smart.sceneDiscovery
    spacing: 16
    Text { Layout.fillWidth: true; text: "Cenas e atmosferas"; color: "#EAF2FE"; font.pixelSize: 21; font.family: "Segoe UI"; wrapMode: Text.WordWrap }
    Rectangle {
        Layout.fillWidth: true; implicitHeight: body.implicitHeight + 40
        radius: 20; color: "#172335"; border.color: "#2C405A"
        ColumnLayout {
            id: body; x: 20; y: 20; width: parent.width-40; spacing: 12
            Text { Layout.fillWidth: true; text: "Descobrir efeito"; color: "#EDF5FF"; font.pixelSize: 17; font.family: "Segoe UI" }
            Text { Layout.fillWidth: true; text: "Escolha a cena no celular. O Smart Tray observa e salva as alterações, sem enviar comandos."; color: "#95A8C0"; font.pixelSize: 12; font.family: "Segoe UI"; wrapMode: Text.WordWrap }
            ComboBox {
                id: sceneName; objectName: "sceneNameSelector"; Layout.fillWidth: true
                implicitHeight: 42; model: smart.discoverySceneNames
                currentIndex: capture.discovery.sceneIndex
                enabled: !capture.discovery.active; wheelEnabled: false
                onActivated: smart.selectDiscoveryScene(currentIndex)
                Accessible.name: "Nome do efeito a observar"
                contentItem: Text { text: sceneName.displayText; color: "#E6EFFA"; font.family: "Segoe UI"; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; leftPadding: 12; rightPadding: 32; elide: Text.ElideRight }
                indicator: AppIcon { x: sceneName.width-width-12; y: (sceneName.height-height)/2; width: 14; height: 14; name: "chevron" }
                background: Rectangle { radius: 12; color: "#111C2B"; border.color: sceneName.visualFocus ? "#8ACFFF" : "#304159" }
                delegate: ItemDelegate {
                    required property string modelData
                    required property int index
                    width: sceneName.width
                    text: modelData
                    contentItem: Text { text: parent.text; color: "#E6EFFA"; font.family: "Segoe UI"; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { color: parent.highlighted ? "#283F52" : "#182536" }
                    highlighted: sceneName.highlightedIndex === index
                }
                popup.background: Rectangle { color: "#182536"; radius: 12; border.color: "#304159" }
            }
            Text { objectName: "discoveryInstruction"; Layout.fillWidth: true; text: capture.discovery.instruction; color: "#BDD2E8"; font.pixelSize: 12; font.family: "Segoe UI"; wrapMode: Text.WordWrap }
            ProgressBar { Layout.fillWidth: true; visible: capture.discovery.phase === "observing"; value: capture.discovery.progress; implicitHeight: 5
                background: Rectangle { radius: 3; color: "#26364A" }
                contentItem: Item { Rectangle { width: parent.width * capture.discovery.progress; height: parent.height; radius: 3; color: "#73CBED" } }
            }
            Text { Layout.fillWidth: true; visible: capture.discovery.active; text: capture.discovery.sampleCount + " leituras" + (capture.discovery.phase === "observing" ? " · " + capture.discovery.secondsRemaining + " s restantes" : " · somente observação"); color: "#819BB6"; font.pixelSize: 11; font.family: "Segoe UI" }
            ActionButton { objectName: "captureSceneBaseline"; Layout.fillWidth: true; text: "Capturar estado inicial"; accent: capture.discovery.canStart; enabled: capture.discovery.canStart; onClicked: smart.startSceneCapture() }
            ActionButton { objectName: "concludeSceneCapture"; Layout.fillWidth: true; text: "Concluir captura"; accent: capture.discovery.canConclude; enabled: capture.discovery.canConclude; onClicked: smart.concludeSceneCapture() }
            RowLayout { Layout.fillWidth: true; spacing: 8
                ActionButton { objectName: "nextSceneCapture"; Layout.fillWidth: true; text: "Próximo efeito"; enabled: capture.discovery.canNext; onClicked: smart.nextDiscoveryScene() }
                ActionButton { objectName: "cancelSceneCapture"; Layout.fillWidth: true; text: "Cancelar"; enabled: capture.discovery.active && capture.discovery.phase !== "cancelling"; onClicked: smart.cancelSceneCapture() }
            }
            Text { Layout.fillWidth: true; visible: capture.discovery.note !== ""; text: capture.discovery.note; color: "#C6A587"; wrapMode: Text.WordWrap; font.pixelSize: 12; font.family: "Segoe UI" }
        }
    }
    Text { objectName: "sceneCaptureResult"; Layout.fillWidth: true; visible: text !== ""; text: capture.discovery.resultText; textFormat: Text.PlainText; wrapMode: Text.WrapAnywhere; color: "#BDD0E4"; font.family: "Consolas"; font.pixelSize: 11 }
    Text { Layout.fillWidth: true; visible: capture.discovery.savedPath !== ""; text: "Salvo em: " + capture.discovery.savedPath; textFormat: Text.PlainText; wrapMode: Text.WrapAnywhere; font.family: "Segoe UI"; font.pixelSize: 10; color: "#8299B4" }
    ActionButton { objectName: "openScenesFolder"; Layout.fillWidth: true; text: "Abrir catálogo local"; onClicked: smart.openScenesFolder() }
    Repeater {
        model: capture.discovery.catalog
        ColumnLayout { required property var modelData; Layout.fillWidth: true; spacing: 4
            Text { Layout.fillWidth: true; text: modelData.name; color: "#D1E1F2"; font.pixelSize: 13; font.family: "Segoe UI" }
            Text { Layout.fillWidth: true; text: modelData.detail; wrapMode: Text.WordWrap; color: "#8399B3"; font.pixelSize: 11; font.family: "Segoe UI" }
        }
    }
    Text { Layout.fillWidth: true; text: "Uma correlação ainda precisa de teste autorizado e confirmação visual antes de virar um efeito com um clique."; wrapMode: Text.WordWrap; color: "#8399B3"; font.pixelSize: 12; font.family: "Segoe UI" }
}
