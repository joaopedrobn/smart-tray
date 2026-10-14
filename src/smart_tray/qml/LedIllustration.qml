import QtQuick

// Read-only landscape model from references/led-reference-2.jpg.heic.
// Coordinates follow the oriented 1600 x 901 review image.
// Cubic curves retain the actual bends; no scene/segment payload is inferred.
Item {
    id: led
    property bool online: false
    property bool powered: false
    property bool powerKnown: false
    property bool colourKnown: false
    property string mode: ""
    property color colour: "#485064"
    property real brightness: 0
    readonly property var route: [
        [583,183],
        [573,178,570,188,571,207],
        [568,254,583,285,621,280],
        [651,275,656,303,675,315],
        [690,330,708,307,724,317],
        [743,329,754,334,775,334],
        [806,337,780,367,790,385],
        [799,406,821,396,834,420],
        [849,447,843,468,866,480],
        [880,490,906,479,922,503],
        [944,537,941,580,959,602],
        [979,631,1015,654,1000,680],
        [989,698,969,706,971,725],
        [974,748,1004,757,1018,775],
        [1033,791,1027,818,1029,835]
    ]
    readonly property bool fixedColourVisible: online && powerKnown && powered && colourKnown && mode === "colour"
    readonly property color confirmedColour: fixedColourVisible ? colour : "#556272"
    readonly property real lightLevel: fixedColourVisible ? Math.max(0, Math.min(1, brightness / 100)) : 0
    implicitHeight: 238
    Rectangle {
        anchors.fill: parent; radius: 15; color: "#0E1723"; border.color: "#253547"
        gradient: Gradient { GradientStop { position: 0; color: "#172635" } GradientStop { position: 1; color: "#101923" } }
    }
    Canvas {
        id: strip
        anchors.fill: parent
        property color stateColour: led.confirmedColour
        property real intensity: led.lightLevel
        Behavior on stateColour { ColorAnimation { duration: smart.reducedMotion ? 0 : 260; easing.type: Easing.OutCubic } }
        Behavior on intensity { NumberAnimation { duration: smart.reducedMotion ? 0 : 260; easing.type: Easing.OutCubic } }
        onStateColourChanged: requestPaint()
        onIntensityChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections { target: led; function onRouteChanged() { strip.requestPaint() } }
        onPaint: {
            let c=getContext("2d"); c.reset(); c.lineJoin="round"; c.lineCap="round"
            // Fit the complete landscape scene without stretching either axis.
            let scale = Math.min((width-20)/1600, (height-36)/900)
            c.translate((width-1600*scale)/2, 8)
            c.scale(scale,scale)
            function roundRect(x,y,w,h,r) {
                c.beginPath(); c.moveTo(x+r,y); c.lineTo(x+w-r,y); c.quadraticCurveTo(x+w,y,x+w,y+r)
                c.lineTo(x+w,y+h-r); c.quadraticCurveTo(x+w,y+h,x+w-r,y+h)
                c.lineTo(x+r,y+h); c.quadraticCurveTo(x,y+h,x,y+h-r); c.lineTo(x,y+r); c.quadraticCurveTo(x,y,x+r,y); c.closePath()
            }
            function plane(points,fill) {
                c.beginPath(); c.moveTo(points[0][0],points[0][1])
                for(let i=1;i<points.length;i++) c.lineTo(points[i][0],points[i][1])
                c.closePath(); c.fillStyle=fill; c.fill()
            }
            roundRect(8,12,1584,880,35); c.fillStyle="#070F18"; c.fill()
            c.save(); roundRect(0,0,1584,880,35); c.clip()
            let wall=c.createLinearGradient(400,140,1130,880)
            wall.addColorStop(0,"#65737D"); wall.addColorStop(1,"#3C4E5D")
            plane([[0,0],[1584,0],[1584,880],[0,880]],"#344653")
            plane([[140,0],[1380,0],[1130,140],[390,150]],"#364753")
            plane([[390,150],[1130,140],[1190,880],[355,880]],wall)
            plane([[0,0],[390,150],[355,880],[0,880]],"#293D4B")
            plane([[1130,140],[1380,0],[1584,0],[1584,880],[1190,880]],"#495D6A")
            // Closet to the left, shuttered window to the right, as in the photo.
            for(let x of [95,225,365]) {
                c.beginPath(); c.moveTo(x,0); c.lineTo(x-25,880); c.strokeStyle="#8796A1"; c.lineWidth=5; c.globalAlpha=.35; c.stroke()
            }
            c.globalAlpha=1
            plane([[1300,280],[1584,125],[1584,820],[1335,750]],"#96A1A4")
            plane([[1320,304],[1584,164],[1584,788],[1350,730]],"#324450")
            for(let y=325;y<735;y+=40) {
                c.beginPath(); c.moveTo(1335,y); c.lineTo(1584,y-105); c.strokeStyle="#637681"; c.lineWidth=10; c.stroke()
            }
            for(let trim of [[0,22,"#A8B4BB"],[18,9,"#75858F"],[30,5,"#BBC4C9"]]) {
                c.beginPath(); c.moveTo(390,148+trim[0]); c.lineTo(1125,140+trim[0]); c.lineTo(1260,0); c.lineWidth=trim[1]; c.strokeStyle=trim[2]; c.stroke()
            }
            // Full split alongside the strip; purely architectural, no invented state.
            roundRect(898,160,255,110,18); c.fillStyle="rgba(7,15,24,.32)"; c.fill()
            let casing=c.createLinearGradient(0,150,0,260)
            casing.addColorStop(0,"#EDF0F1"); casing.addColorStop(1,"#A7B4BE")
            roundRect(890,150,255,110,18); c.fillStyle=casing; c.fill()
            c.beginPath(); c.moveTo(904,235); c.lineTo(1131,235); c.strokeStyle="#586976"; c.lineWidth=7; c.stroke()
            c.beginPath(); c.moveTo(906,246); c.lineTo(1127,246); c.strokeStyle="#D0D9DF"; c.lineWidth=8; c.stroke()
            function path(dx,dy) {
                c.beginPath()
                c.moveTo(led.route[0][0]+dx,led.route[0][1]+dy)
                for(let i=1;i<led.route.length;i++) {
                    let p=led.route[i]; c.bezierCurveTo(p[0]+dx,p[1]+dy,p[2]+dx,p[3]+dy,p[4]+dx,p[5]+dy)
                }
            }
            path(4,5); c.strokeStyle="rgba(4,10,16,.45)"; c.lineWidth=15; c.stroke()
            if (led.fixedColourVisible) {
                for(let j=4;j>0;j--) { path(0,0); c.globalAlpha=(.025 + intensity*.05); c.strokeStyle=stateColour; c.lineWidth=12+j*20; c.stroke() }
            }
            c.globalAlpha=1; path(0,0); c.strokeStyle="#273541"; c.lineWidth=13; c.stroke()
            path(0,-1); c.strokeStyle=stateColour; c.lineWidth=9; c.stroke()
            c.restore()
        }
    }
    Text {
        objectName: "ledPreviewStatus"
        anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 10
        text: !led.online || !led.powerKnown ? "Sem confirmação" : !led.powered ? "Desligada" : led.mode === "scene" || led.mode === "music" ? "Efeito ativo no aparelho · prévia indisponível" : led.mode !== "colour" || !led.colourKnown ? "Cor sem confirmação" : "Cor atual · " + Math.round(led.brightness) + "%"
        color: "#90A6BA"; font.family: "Segoe UI"; font.pixelSize: 10
    }
}
