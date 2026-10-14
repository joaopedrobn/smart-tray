import QtQuick
import QtQuick.Controls

Slider {
    id: control
    property color fillColor: "#63CBF4"
    wheelEnabled: false
    implicitHeight: 38
    stepSize: 1
    live: true
    opacity: enabled ? 1 : 0.34
    Behavior on opacity { NumberAnimation { duration: smart.reducedMotion ? 0 : 180 } }
    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: control.availableWidth
        height: 8
        radius: 4
        color: "#253143"
        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            radius: 4
            gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: "#3B82F6" } GradientStop { position: 1; color: control.fillColor } }
            Behavior on width { enabled: !control.pressed && !smart.reducedMotion; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        }
    }
    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        implicitWidth: 22
        implicitHeight: 22
        radius: 11
        color: control.pressed ? "#BCEAFE" : "#ECF7FF"
        border.color: control.visualFocus ? "#3B82F6" : "#BBD7EB"
        border.width: control.visualFocus ? 2 : 1
        scale: control.pressed ? 1.14 : 1
        Behavior on scale { NumberAnimation { duration: smart.reducedMotion ? 0 : 170 } }
    }
}
