import QtQuick
import QtQuick.Controls

ScrollBar {
    id: control
    implicitWidth: 6
    padding: 1
    anchors.right: parent.right
    anchors.top: parent.top
    anchors.bottom: parent.bottom
    policy: ScrollBar.AsNeeded
    background: Item {}
    contentItem: Rectangle {
        implicitWidth: 4; implicitHeight: 20; radius: 2
        color: control.pressed ? "#6F91BB" : "#34465F"
        opacity: control.size < 1 ? 0.8 : 0
    }
}
