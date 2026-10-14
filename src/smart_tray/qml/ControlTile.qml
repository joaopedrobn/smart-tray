import QtQuick
import QtQuick.Controls

Button {
    id: control
    property string title: ""
    property string value: ""
    property string iconName: "cold"
    property bool selectable: true
    hoverEnabled: true
    wheelEnabled: false
    implicitHeight: 89
    implicitWidth: 88
    background: Rectangle {
        radius: 16
        color: control.down ? "#283F52" : control.highlighted ? "#183342" : control.hovered && control.enabled ? "#263343" : "#192330"
        border.color: control.visualFocus ? "#8ACFFF" : control.highlighted ? "#37647A" : "#2B3849"
        Behavior on color { ColorAnimation { duration: smart.reducedMotion ? 0 : 200 } }
    }
    contentItem: Column {
        spacing: 4
        AppIcon { name: control.iconName; ink: control.enabled ? "#80D5F6" : "#768598"; width: 21; height: 21 }
        Text { text: control.title; color: "#8F9EB3"; font.pixelSize: 11; font.family: "Segoe UI" }
        Text { width: parent.width; text: control.value; color: control.enabled ? "#F0F5FC" : "#94A2B4"; font.pixelSize: 12; font.family: "Segoe UI"; elide: Text.ElideRight }
    }
    padding: 10
    AppIcon { anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 10; width: 12; height: 12; name: "chevron"; ink: "#7F96B4"; visible: control.selectable && control.enabled }
    Accessible.name: title + ", " + value
}
