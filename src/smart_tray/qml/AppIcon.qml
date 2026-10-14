import QtQuick

// Original vector strokes; no dependency on symbol fonts or platform glyphs.
Canvas {
    id: icon
    property string name: "home"
    property color ink: "#BCD3E9"
    implicitWidth: 22; implicitHeight: 22
    onNameChanged: requestPaint()
    onInkChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        let c = getContext("2d"); c.reset(); c.scale(width / 24, height / 24)
        c.strokeStyle = ink; c.fillStyle = ink; c.lineWidth = 1.65; c.lineCap = "round"; c.lineJoin = "round"
        function line(x,y,a,b) { c.moveTo(x,y); c.lineTo(a,b) }
        c.beginPath()
        switch (name) {
        case "home": c.moveTo(3,11); c.lineTo(12,3); c.lineTo(21,11); c.moveTo(5,10); c.lineTo(5,21); c.lineTo(10,21); c.lineTo(10,15); c.lineTo(14,15); c.lineTo(14,21); c.lineTo(19,21); c.lineTo(19,10); break
        case "power": c.arc(12,13,8,-Math.PI*.34,Math.PI*1.34); line(12,2,12,11); break
        case "minus": line(5,12,19,12); break
        case "plus": line(5,12,19,12); line(12,5,12,19); break
        case "close": line(6,6,18,18); line(18,6,6,18); break
        case "chevron": line(7,10,12,15); line(12,15,17,10); break
        case "refresh": c.arc(12,12,8,.3,Math.PI*1.9); line(20,4,20,10); line(20,10,14,10); break
        case "settings": for(let i=0;i<32;i++){let a=i*Math.PI/16-Math.PI/2, r=(i%4===0||i%4===3)?9:7; let x=12+r*Math.cos(a),y=12+r*Math.sin(a); if(i===0)c.moveTo(x,y);else c.lineTo(x,y)} c.closePath(); c.moveTo(15,12); c.arc(12,12,3,0,Math.PI*2); break
        case "moon": c.moveTo(16,3); c.bezierCurveTo(3,0,0,20,14,21); c.bezierCurveTo(18,21,21,18,22,15); c.bezierCurveTo(11,20,7,8,16,3); break
        case "cold": for(let i=0;i<6;i++){c.save(); c.translate(12,12); c.rotate(i*Math.PI/3); line(0,0,0,-9); line(0,-5,-3,-7); line(0,-5,3,-7); c.restore()} break
        case "fan": c.arc(12,12,1.8,0,Math.PI*2); for(let i=0;i<3;i++){c.save(); c.translate(12,12); c.rotate(i*Math.PI*2/3); c.moveTo(1.5,-2); c.bezierCurveTo(8,-8,4,-11,0,-8.5); c.bezierCurveTo(-3,-7,-2,-3,1.5,-2); c.restore()} break
        case "swing": line(4,5,20,5); line(6,9,18,9); c.moveTo(5,13); c.quadraticCurveTo(12,22,19,13); line(15,13,19,13); line(19,13,19,17); break
        case "display": c.rect(3,4,18,13); line(8,21,16,21); line(12,17,12,21); break
        case "leaf": c.moveTo(5,19); c.bezierCurveTo(-1,5,17,4,21,2); c.bezierCurveTo(23,17,16,24,5,19); line(5,19,16,9); break
        case "heart": c.moveTo(12,21); c.bezierCurveTo(-5,11,5,-1,12,7); c.bezierCurveTo(19,-1,29,11,12,21); break
        case "socket": c.arc(12,12,9,0,Math.PI*2); c.stroke(); c.beginPath(); for(let p of [[8,13],[12,9],[16,13]]){c.moveTo(p[0]+1,p[1]); c.arc(p[0],p[1],1,0,Math.PI*2)} break
        case "touch": c.arc(12,12,8,0,Math.PI*2); c.moveTo(15,12); c.arc(12,12,3,0,Math.PI*2); break
        default: for(let i=0;i<3;i++){let a=i*Math.PI/3; line(12-9*Math.cos(a),12-9*Math.sin(a),12+9*Math.cos(a),12+9*Math.sin(a))} c.moveTo(6,5); c.lineTo(8,10); c.lineTo(3,10); c.moveTo(21,14); c.lineTo(16,14); c.lineTo(18,19)
        }
        c.stroke()
    }
}
