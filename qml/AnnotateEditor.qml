import QtQuick
import QtQuick.Controls.Basic

// Zeichen-Editor für Beschriften / Schwärzen. Koordinaten werden relativ zum Bild (0..1) gespeichert.
Item {
    id: ed
    property string source: ""
    property var tools: ["arrow", "rect", "text"]
    property var shapes: []
    property string tool: tools.length ? tools[0] : "rect"
    property color pen: "#ff3b30"
    property string label: "Text"
    property var draft: null
    signal changed(string json)

    readonly property var meta: ({
        arrow: ["move-up-right", "Pfeil"], rect: ["square", "Rahmen"], ellipse: ["circle", "Kreis"],
        text: ["type", "Text"], num: ["list-ordered", "Nummer"], pen: ["pencil", "Stift"],
        redact: ["rectangle-horizontal", "Schwärzen"], pixel: ["grid-3x3", "Verpixeln"], blur: ["droplet", "Weichzeichnen"]
    })
    readonly property var swatches: ["#ff3b30", "#ff9500", "#ffcc00", "#34c759", "#0a84ff", "#bf5af2", "#ffffff", "#000000"]
    readonly property bool colored: ["arrow", "rect", "ellipse", "text", "num", "pen"].indexOf(tool) >= 0

    onSourceChanged: { shapes = []; draft = null; canvas.requestPaint(); emitChanged() }
    function emitChanged() { changed(JSON.stringify(shapes)); canvas.requestPaint() }
    function undo() { var a = shapes.slice(); a.pop(); shapes = a; emitChanged() }
    function clearAll() { shapes = []; emitChanged() }
    function numCount() { var n = 0; for (var i = 0; i < shapes.length; i++) if (shapes[i].t === "num") n++; return n }

    // ---- Werkzeugleiste -----------------------------------------------
    Rectangle {
        id: bar
        anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
        height: 48; radius: 12; color: Theme.raised; border.color: Theme.border

        Row {
            anchors.left: parent.left; anchors.leftMargin: 8; anchors.verticalCenter: parent.verticalCenter
            spacing: 4
            Repeater {
                model: ed.tools
                delegate: Rectangle {
                    required property string modelData
                    width: 36; height: 34; radius: 9
                    readonly property bool on: ed.tool === modelData
                    color: on ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.25) : (hm.containsMouse ? Theme.hover : "transparent")
                    Icon { anchors.centerIn: parent; name: ed.meta[modelData][0]; size: 17; color: parent.on ? Theme.text : Theme.dim }
                    MouseArea { id: hm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: ed.tool = modelData }
                    ToolTip.visible: hm.containsMouse; ToolTip.text: ed.meta[modelData][1]; ToolTip.delay: 500
                }
            }
            Rectangle { width: 1; height: 24; color: Theme.border; anchors.verticalCenter: parent.verticalCenter
                        visible: ed.colored }
            Repeater {
                model: ed.colored ? ed.swatches : []
                delegate: Rectangle {
                    required property string modelData
                    width: 22; height: 22; radius: 11; anchors.verticalCenter: parent.verticalCenter
                    color: modelData
                    border.width: ed.pen === modelData ? 3 : 1
                    border.color: ed.pen === modelData ? Theme.accent : Theme.border
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: ed.pen = modelData }
                }
            }
            TextField {
                visible: ed.tool === "text"
                width: 130; height: 30; anchors.verticalCenter: parent.verticalCenter
                text: ed.label; placeholderText: "Text"
                color: Theme.text; font.family: Theme.font; font.pixelSize: 12
                background: Rectangle { radius: 8; color: Theme.bg; border.color: parent.activeFocus ? Theme.accent : Theme.border }
                onTextEdited: ed.label = text
            }
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
            spacing: 4
            IconButton { icon: "undo-2"; opacity: ed.shapes.length ? 1 : 0.35; onClicked: ed.undo() }
            IconButton { icon: "trash-2"; opacity: ed.shapes.length ? 1 : 0.35; onClicked: ed.clearAll() }
        }
    }

    // ---- Bühne ---------------------------------------------------------
    Rectangle {
        id: stage
        anchors.top: bar.bottom; anchors.topMargin: 10
        anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
        radius: 12; color: Theme.bg; border.color: Theme.border; clip: true

        Image {
            id: img
            anchors.fill: parent; anchors.margins: 10
            source: ed.source ? "file://" + encodeURI(ed.source) : ""
            fillMode: Image.PreserveAspectFit
            asynchronous: true; cache: false; smooth: true
            sourceSize.width: 2400
            onPaintedWidthChanged: canvas.requestPaint()
            onStatusChanged: canvas.requestPaint()
        }
        Text {
            visible: ed.source === ""
            anchors.centerIn: parent; text: "Wähle links zuerst ein Bild"
            color: Theme.faint; font.family: Theme.font; font.pixelSize: 13
        }

        readonly property real px: img.x + (img.width - img.paintedWidth) / 2
        readonly property real py: img.y + (img.height - img.paintedHeight) / 2
        readonly property real pw: img.paintedWidth
        readonly property real ph: img.paintedHeight

        Canvas {
            id: canvas
            anchors.fill: parent
            renderTarget: Canvas.FramebufferObject
            onPaint: {
                var c = getContext("2d")
                c.reset()
                if (stage.pw <= 0) return
                var all = ed.shapes.slice()
                if (ed.draft) all.push(ed.draft)
                var base = Math.max(stage.pw, stage.ph)
                for (var i = 0; i < all.length; i++) {
                    var s = all[i]
                    c.strokeStyle = s.color || "#ff3b30"; c.fillStyle = s.color || "#ff3b30"
                    c.lineWidth = Math.max(2, (s.width || 0.004) * base); c.lineCap = "round"; c.lineJoin = "round"
                    var X = function (v) { return stage.px + v * stage.pw }
                    var Y = function (v) { return stage.py + v * stage.ph }
                    if (s.t === "rect") {
                        c.strokeRect(X(s.x), Y(s.y), s.w * stage.pw, s.h * stage.ph)
                    } else if (s.t === "ellipse") {
                        c.beginPath(); c.ellipse(X(s.x), Y(s.y), s.w * stage.pw, s.h * stage.ph); c.stroke()
                    } else if (s.t === "arrow" || s.t === "line") {
                        var x1 = X(s.x1), y1 = Y(s.y1), x2 = X(s.x2), y2 = Y(s.y2)
                        c.beginPath(); c.moveTo(x1, y1); c.lineTo(x2, y2); c.stroke()
                        var a = Math.atan2(y2 - y1, x2 - x1), hl = c.lineWidth * 5
                        c.beginPath()
                        c.moveTo(x2 + hl * Math.cos(a + 2.618), y2 + hl * Math.sin(a + 2.618)); c.lineTo(x2, y2)
                        c.lineTo(x2 + hl * Math.cos(a - 2.618), y2 + hl * Math.sin(a - 2.618)); c.stroke()
                    } else if (s.t === "pen") {
                        c.beginPath()
                        for (var k = 0; k < s.pts.length; k++) {
                            if (k === 0) c.moveTo(X(s.pts[k][0]), Y(s.pts[k][1])); else c.lineTo(X(s.pts[k][0]), Y(s.pts[k][1]))
                        }
                        c.stroke()
                    } else if (s.t === "text") {
                        c.font = "bold " + Math.max(10, s.size * stage.ph) + "px sans-serif"
                        c.textBaseline = "top"; c.fillText(s.text, X(s.x), Y(s.y))
                    } else if (s.t === "num") {
                        var r = Math.max(12, s.size * stage.ph)
                        c.beginPath(); c.arc(X(s.x), Y(s.y), r, 0, 6.2832); c.fill()
                        c.fillStyle = "#fff"; c.font = "bold " + (r * 1.2) + "px sans-serif"
                        c.textAlign = "center"; c.textBaseline = "middle"; c.fillText(String(s.n), X(s.x), Y(s.y) + 1)
                        c.textAlign = "left"
                    } else if (s.t === "redact" || s.t === "blur" || s.t === "pixel") {
                        c.fillStyle = s.t === "redact" ? "#000" : "rgba(124,108,255,0.38)"
                        c.fillRect(X(s.x), Y(s.y), s.w * stage.pw, s.h * stage.ph)
                        if (s.t !== "redact") { c.strokeStyle = "#7c6cff"; c.lineWidth = 1.5
                            c.strokeRect(X(s.x), Y(s.y), s.w * stage.pw, s.h * stage.ph) }
                    }
                }
            }
        }

        MouseArea {
            anchors.fill: parent
            enabled: ed.source !== "" && stage.pw > 0
            cursorShape: Qt.CrossCursor
            property real sx: 0
            property real sy: 0
            function nx(x) { return Math.max(0, Math.min(1, (x - stage.px) / stage.pw)) }
            function ny(y) { return Math.max(0, Math.min(1, (y - stage.py) / stage.ph)) }
            onPressed: (m) => {
                sx = nx(m.x); sy = ny(m.y)
                var t = ed.tool, col = String(ed.pen).substring(0, 7)
                if (t === "text") {
                    var a = ed.shapes.slice()
                    a.push({ t: "text", x: sx, y: sy, text: ed.label || "Text", size: 0.045, color: col })
                    ed.shapes = a; ed.emitChanged()
                } else if (t === "num") {
                    var b = ed.shapes.slice()
                    b.push({ t: "num", x: sx, y: sy, n: ed.numCount() + 1, size: 0.028, color: col })
                    ed.shapes = b; ed.emitChanged()
                } else if (t === "pen") {
                    ed.draft = { t: "pen", pts: [[sx, sy]], color: col, width: 0.004 }
                } else if (t === "arrow") {
                    ed.draft = { t: "arrow", x1: sx, y1: sy, x2: sx, y2: sy, color: col, width: 0.005 }
                } else {
                    ed.draft = { t: t, x: sx, y: sy, w: 0, h: 0, color: col, width: 0.004 }
                }
            }
            onPositionChanged: (m) => {
                if (!ed.draft) return
                var d = ed.draft, x = nx(m.x), y = ny(m.y)
                if (d.t === "pen") d.pts.push([x, y])
                else if (d.t === "arrow") { d.x2 = x; d.y2 = y }
                else { d.x = Math.min(sx, x); d.y = Math.min(sy, y); d.w = Math.abs(x - sx); d.h = Math.abs(y - sy) }
                canvas.requestPaint()
            }
            onReleased: {
                if (!ed.draft) return
                var d = ed.draft
                var tiny = (d.t === "arrow") ? (Math.abs(d.x2 - d.x1) + Math.abs(d.y2 - d.y1) < 0.01)
                         : (d.t === "pen") ? d.pts.length < 2 : (d.w < 0.005 || d.h < 0.005)
                if (!tiny) { var a = ed.shapes.slice(); a.push(d); ed.shapes = a }
                ed.draft = null
                ed.emitChanged()
            }
        }
    }
}
