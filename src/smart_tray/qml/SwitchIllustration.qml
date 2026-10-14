import QtQuick

// Original pseudo-3D glass plate, drawn from interruptor-reference.png.png.
// Touch at the top, NBR 14136 outlet below. No control handlers in the model.
Item {
    id: model
    property bool touchKnown: false
    property bool socketKnown: false
    property bool touchOn: false
    property bool socketOn: false
    implicitHeight: 295
    Item {
        id: plate
        width: 164; height: 274
        anchors.centerIn: parent
        Rectangle { x: 9; y: 12; width: parent.width; height: parent.height; radius: 6; color: "#050B12"; opacity: .5 }
        Rectangle { x: 3; y: 3; width: parent.width; height: parent.height; radius: 4; color: "#72868B"; border.color: "#A0B0B4" }
        Rectangle {
            anchors.fill: parent; radius: 4; border.color: "#DAE5E6"; border.width: 1
            gradient: Gradient { GradientStop { position: 0; color: "#DEE5E4" } GradientStop { position: .45; color: "#C6D0D0" } GradientStop { position: 1; color: "#B2C0C0" } }
            Rectangle { x: 2; y: 2; width: parent.width-4; height: 1; color: "#F3F7F4" }
            Rectangle { x: 2; y: 2; width: 1; height: parent.height-4; color: "#E6EDEC" }
            Rectangle { x: 4; y: 4; width: parent.width-8; height: parent.height-8; radius: 2; color: "transparent"; border.color: "#90B3B7"; opacity: .22 }
            Rectangle {
                objectName: "touchIndicator"
                x: (parent.width-width)/2; y: 80; width: 31; height: 31; radius: 16
                color: model.touchKnown && model.touchOn ? "#D8EEF1" : "#C8D2D2"
                border.color: !model.touchKnown ? "#829698" : model.touchOn ? "#42BFE5" : "#576467"
                border.width: 1.5
                Behavior on color { ColorAnimation { duration: smart.reducedMotion ? 0 : 280 } }
                Behavior on border.color { ColorAnimation { duration: smart.reducedMotion ? 0 : 280 } }
                Rectangle { anchors.centerIn: parent; width: parent.width+10; height: width; radius: width/2; color: "transparent"; border.width: 3; border.color: "#75D3E5"; opacity: model.touchKnown && model.touchOn ? .15 : 0; Behavior on opacity { NumberAnimation { duration: smart.reducedMotion ? 0 : 350 } } }
            }
            Rectangle {
                x: 29; y: 151; width: 108; height: 73; radius: 5; color: "#9CA8A8"; border.color: "#B8C6C6"
                Rectangle {
                    x: 3; y: 5; width: parent.width-6; height: parent.height-7; radius: 4; border.color: "#F1EDE5"
                    gradient: Gradient { GradientStop { position: 0; color: "#ECEAE2" } GradientStop { position: 1; color: "#CECFC5" } }
                    Canvas {
                        anchors.centerIn: parent; width: 89; height: 48
                        onPaint: {
                            let c=getContext("2d"); c.reset(); c.beginPath(); c.moveTo(18,2); c.lineTo(71,2); c.lineTo(88,23); c.lineTo(72,46); c.lineTo(17,46); c.lineTo(1,24); c.closePath()
                            let g=c.createLinearGradient(0,0,0,height); g.addColorStop(0,"#AAA99F"); g.addColorStop(1,"#CECDC3"); c.fillStyle=g; c.fill(); c.strokeStyle="#EDECE6"; c.lineWidth=1; c.stroke()
                            // Three circular holes in the Brazilian triangular layout.
                            for(let p of [[22,25],[44.5,17],[67,25]]) { c.beginPath(); c.arc(p[0],p[1],5.4,0,Math.PI*2); c.fillStyle="#F4F0E7"; c.fill(); c.beginPath(); c.arc(p[0],p[1]-1,4.2,0,Math.PI*2); c.fillStyle="#101515"; c.fill() }
                        }
                    }
                    Rectangle { objectName: "socketIndicator"; x: 17; y: 10; width: 3; height: 3; radius: 2; color: !model.socketKnown ? "#89918F" : model.socketOn ? "#54AEB5" : "#687572"; Behavior on color { ColorAnimation { duration: smart.reducedMotion ? 0 : 280 } } }
                }
            }
            Text { anchors.right: parent.right; anchors.rightMargin: 10; y: parent.height-19; text: "NOVADIGITAL"; color: "#3E4C50"; font.pixelSize: 7; font.bold: true; font.italic: true; font.family: "Segoe UI" }
        }
    }
}
