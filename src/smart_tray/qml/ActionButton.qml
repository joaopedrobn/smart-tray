import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool accent: false
    property color tint: "#60C9F1"
    property string iconName: ""
    hoverEnabled: true
    wheelEnabled: false
    implicitHeight: 42
    implicitWidth: 120
    font.family: "Segoe UI"
    font.pixelSize: 13
    opacity: enabled ? 1 : 0.38
    Behavior on opacity { NumberAnimation { duration: smart.reducedMotion ? 0 : 170 } }
    background: Rectangle {
        radius: height / 2
        color: control.down ? "#35495F" : control.accent ? control.tint : control.hovered ? "#283547" : "#1B2432"
        border.color: control.visualFocus ? "#8ACFFF" : control.accent ? Qt.lighter(control.tint, 1.15) : "#303D50"
        border.width: control.visualFocus ? 2 : 1
        Behavior on color { ColorAnimation { duration: smart.reducedMotion ? 0 : 180 } }
        scale: control.down ? 0.97 : 1
        Behavior on scale { NumberAnimation { duration: smart.reducedMotion ? 0 : 150; easing.type: Easing.OutCubic } }
    }
    contentItem: Item {
        implicitWidth: label.implicitWidth + (control.iconName !== "" ? 28 : 0)
        implicitHeight: 22
        Row {
            anchors.centerIn: parent; spacing: control.text !== "" && control.iconName !== "" ? 7 : 0
            // An icon-only row keeps its natural width so it stays centered,
            // even when the style adds extra horizontal button padding.
            width: control.text === "" ? implicitWidth : Math.min(parent.width, implicitWidth)
            AppIcon { objectName: control.objectName !== "" ? control.objectName + "Icon" : ""; visible: control.iconName !== ""; name: control.iconName; width: 19; height: 19; anchors.verticalCenter: parent.verticalCenter; ink: control.accent ? "#092233" : "#C4D7EB" }
            Text { id: label; visible: control.text !== ""; text: control.text; color: control.accent ? "#092233" : "#E7EDF6"; font: control.font; width: Math.max(0, Math.min(implicitWidth, control.availableWidth - (control.iconName !== "" ? 28 : 0))); elide: Text.ElideRight; anchors.verticalCenter: parent.verticalCenter }
        }
    }
    Accessible.name: text
}
