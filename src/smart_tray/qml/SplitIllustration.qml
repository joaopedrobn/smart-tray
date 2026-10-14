import QtQuick

Item {
    id: split
    property bool powered: false
    property bool animate: false
    property string temperature: ""
    property string fan: ""
    property real flowSpeed: fan === "strength" ? 1.5 : fan === "high" ? 1.2 : fan === "mid" ? 1 : fan === "mute" ? 0.55 : 0.75
    readonly property bool flowRunning: animate && (powered || airflow.opacity > 0.01)
    implicitHeight: 206
    Item {
        id: body
        width: Math.min(300, parent.width * 0.82)
        height: 80
        anchors.horizontalCenter: parent.horizontalCenter
        y: 25
        Rectangle { x: 6; y: 8; width: parent.width; height: parent.height; radius: 18; color: "#07101B"; opacity: 0.55 }
        Rectangle {
            anchors.fill: parent
            radius: 17
            gradient: Gradient { GradientStop { position: 0; color: "#FFFFFF" } GradientStop { position: 0.45; color: "#EDF1F4" } GradientStop { position: 1; color: "#B8C6D0" } }
            border.color: "#EFF5FA"
            Rectangle { x: 12; y: 12; width: parent.width - 24; height: 1; color: "#FFFFFF"; opacity: 0.8 }
            Rectangle { x: 14; y: parent.height - 20; width: parent.width - 28; height: 11; radius: 3; color: "#17212A" }
            Rectangle {
                x: 16; y: split.powered ? parent.height - 12 : parent.height - 17
                width: parent.width - 32; height: split.powered ? 3 : 7; radius: 2; color: "#D6DFE6"
                Behavior on y { NumberAnimation { duration: smart.reducedMotion ? 0 : 250 } }
                Behavior on height { NumberAnimation { duration: smart.reducedMotion ? 0 : 250 } }
            }
            Text { anchors.right: parent.right; anchors.rightMargin: 24; y: 22; text: split.powered ? split.temperature : ""; color: "#59C8DE"; font.family: "Segoe UI"; font.pixelSize: 15 }
            Rectangle { x: 23; y: 25; width: 3; height: 3; radius: 2; color: split.powered ? "#65C7C1" : "#9BABB9" }
        }
    }
    Item {
        id: airflow
        anchors.horizontalCenter: body.horizontalCenter
        y: body.y + body.height - 6
        width: body.width - 40
        height: 95
        objectName: "airflow"
        opacity: split.powered ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: smart.reducedMotion ? 0 : 650; easing.type: Easing.InOutCubic } }
        Canvas {
            id: ribbons
            anchors.fill: parent
            property real phase: 0
            onPhaseChanged: requestPaint()
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                let c = getContext("2d"); c.reset(); c.lineCap = "round"
                // Two depths of curved streams share one continuous clock.
                // Sine motion wraps without pauses; highlights fade at both ends.
                for (let i = 0; i < 18; i++) {
                    let depth = i % 2, u = (i + .5) / 18
                    let origin = u * width, spread = (u - .5) * 40
                    let bend = Math.sin(phase * Math.PI * 2 + i * .65) * (5 + depth * 3)
                    let end = height * (.78 + depth * .22)
                    let gradient = c.createLinearGradient(0,0,0,end)
                    gradient.addColorStop(0,"rgba(153,220,246,0)")
                    gradient.addColorStop(.22,depth ? "rgba(120,207,239,.24)" : "rgba(160,225,249,.12)")
                    gradient.addColorStop(1,"rgba(120,207,239,0)")
                    c.strokeStyle = gradient; c.lineWidth = depth ? 1.1 : .7
                    c.beginPath(); c.moveTo(origin,0)
                    c.bezierCurveTo(origin + bend*.25, end*.32, origin + spread*.6 + bend, end*.7, origin+spread,end)
                    c.stroke()
                    let t = (phase * 2 + i * .137) % 1
                    let p = (z) => ({x: origin + spread*z*z + bend*Math.sin(z*Math.PI)*z, y: z*end})
                    let a = p(Math.max(0,t-.10)), b = p(t), d = p(Math.min(1,t+.10))
                    c.strokeStyle = "rgba(174,232,251," + (Math.sin(t*Math.PI)*.28) + ")"
                    c.beginPath(); c.moveTo(a.x,a.y); c.quadraticCurveTo(b.x,b.y,d.x,d.y); c.stroke()
                }
            }
        }
        Timer { interval: 33; repeat: true; running: split.flowRunning; onTriggered: ribbons.phase = (ribbons.phase + .033 * split.flowSpeed / 5) % 1 }
    }
}
