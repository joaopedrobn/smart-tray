import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ContentScroll {
    id: page
    objectName: "settingsScroll"
    ColumnLayout {
        width: page.availableWidth; spacing: 18
        RowLayout { Layout.fillWidth: true
            Text { text: "Do seu jeito"; color: "#EDF5FE"; font.pixelSize: 27; font.weight: Font.Light; font.family: "Segoe UI" }
            Item { Layout.fillWidth: true }
            ActionButton { text: "Voltar"; Layout.preferredWidth: 90; implicitWidth: 90; onClicked: smart.navigate("climate") }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: additional.implicitHeight + page.cardPadding * 2; radius: 20; color: "#172335"; border.color: "#2C405A"
            ColumnLayout {
                id: additional; x: page.cardPadding; y: page.cardPadding; width: parent.width - page.cardPadding * 2; spacing: 16
                Text { text: "Controles adicionais"; color: "#DCEBFC"; font.pixelSize: 17; font.family: "Segoe UI" }
                Text { Layout.fillWidth: true; text: "Libera cor, brilho e funções identificadas que ainda aguardam confirmação física. Os comandos seguem os valores conhecidos do aparelho. Funções desconhecidas ficam indisponíveis."; color: "#94A8C2"; wrapMode: Text.WordWrap; font.pixelSize: 12; font.family: "Segoe UI" }
                Text { Layout.fillWidth: true; text: "Ao escolher uma cor, o aplicativo pode ativar cor fixa e depois aplicar a cor, com leitura entre as etapas. Uma falha interrompe a operação; não há repetição nem restauração automática."; color: "#94A8C2"; wrapMode: Text.WordWrap; font.pixelSize: 12; font.family: "Segoe UI" }
                CheckBox {
                    id: acknowledge; objectName: "riskAcknowledgement"; visible: !smart.experimentalEnabled
                    text: "Entendo e quero testar esses recursos"; wheelEnabled: false; font.pixelSize: 12; font.family: "Segoe UI"
                    contentItem: Text { text: acknowledge.text; leftPadding: acknowledge.indicator.width + acknowledge.spacing; color: "#BBD0E6"; font: acknowledge.font; verticalAlignment: Text.AlignVCenter; wrapMode: Text.WordWrap }
                    Layout.fillWidth: true
                }
                ActionButton { objectName: "experimentalToggle"; Layout.fillWidth: true; text: smart.experimentalEnabled ? "Desativar controles adicionais" : "Ativar controles adicionais"; enabled: smart.experimentalEnabled || acknowledge.checked; accent: !smart.experimentalEnabled
                    onClicked: { smart.enableExperimental(!smart.experimentalEnabled, acknowledge.checked); acknowledge.checked = false }
                }
                Text { text: smart.experimentalEnabled ? "Ativos · operação direta, sem confirmações repetitivas" : "Desativados · controles validados continuam disponíveis"; color: "#81AFB3"; font.pixelSize: 11; font.family: "Segoe UI"; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            }
        }
        ActionButton { objectName: "reduceMotion"; Layout.fillWidth: true; text: "Reduzir animações · " + (smart.reducedMotion ? "Ativo" : "Desativado"); onClicked: smart.reduceMotion(!smart.reducedMotion) }
        ActionButton { objectName: "startupToggle"; Layout.fillWidth: true; text: "Iniciar com Windows · " + (smart.startupEnabled ? "Ativo" : "Desativado"); onClicked: smart.setStartup(!smart.startupEnabled) }
        ActionButton { objectName: "resetPosition"; Layout.fillWidth: true; text: "Restaurar posição perto do tray"; onClicked: smart.resetPosition() }
        Text { Layout.fillWidth: true; text: "Arraste o cabeçalho para posicionar a janela. A escolha fica salva e respeita os limites dos seus monitores."; color: "#8A9FB8"; wrapMode: Text.WordWrap; font.pixelSize: 12; font.family: "Segoe UI" }
        Text { text: "Smart Tray " + smart.version; color: "#C0D3E8"; font.pixelSize: 14; font.family: "Segoe UI" }
        Text { Layout.fillWidth: true; text: "Credenciais protegidas pelo Windows\nNenhuma alteração nos aparelhos ao abrir ou reconectar.\nA confirmação de estado não substitui a observação física."; color: "#7289A4"; wrapMode: Text.WordWrap; font.pixelSize: 11; font.family: "Segoe UI" }
        Text { text: "Atividade recente"; color: "#D4E4F8"; font.pixelSize: 18; font.family: "Segoe UI" }
        Text { visible: smart.history.length === 0; text: "Nenhuma ação registrada."; color: "#8196B1"; font.pixelSize: 12; font.family: "Segoe UI" }
        Repeater {
            model: smart.history
            ColumnLayout { required property var modelData; Layout.fillWidth: true; spacing: 4
                Text { text: modelData.title; color: "#BACDE4"; font.pixelSize: 12; font.family: "Segoe UI" }
                Text { Layout.fillWidth: true; text: modelData.detail; color: "#748DA8"; font.pixelSize: 11; font.family: "Segoe UI"; wrapMode: Text.WordWrap }
            }
        }
    }
}
