import QtQuick
import QtQuick.Window

// Vollbild-Overlay: Tastatur reinigen / Pixelfehler-Test
Window {
    id: ov
    property string kind: ""
    property int seconds: 60
    property bool black: false
    property int left: 0
    property int step: 0
    readonly property var colors: ["#000000", "#ffffff", "#ff0000", "#00ff00", "#0000ff"]
    signal done()

    visibility: Window.Hidden
    flags: Qt.Window | Qt.FramelessWindowHint
    color: "#000"

    function openWith(o) {
        kind = o.kind; seconds = o.seconds || 60; black = !!o.black
        left = seconds; step = 0
        visibility = Window.FullScreen
        raise(); requestActivate()
        content.forceActiveFocus()
        if (kind === "cleankeys") tick.restart()
    }
    function finish() {
        tick.stop()
        visibility = Window.Hidden
        kind = ""
        done()
    }
    onClosing: (c) => { c.accepted = false; finish() }

    Timer { id: tick; interval: 1000; repeat: true
            onTriggered: { ov.left--; if (ov.left <= 0) ov.finish() } }

    Rectangle {
        id: content
        anchors.fill: parent
        focus: true
        color: ov.kind === "pixeltest" ? ov.colors[ov.step] : (ov.black ? "#000000" : "#101116")

        // Alle Tasten verschlucken (Reinigen) bzw. bedienen (Test)
        Keys.priority: Keys.BeforeItem
        Keys.onPressed: (e) => {
            e.accepted = true
            if (ov.kind === "pixeltest") {
                if (e.key === Qt.Key_Escape) ov.finish()
                else if (e.key === Qt.Key_Left || e.key === Qt.Key_Backspace) ov.step = (ov.step + ov.colors.length - 1) % ov.colors.length
                else { ov.step++; if (ov.step >= ov.colors.length) ov.finish() }
            }
        }
        Keys.onShortcutOverride: (e) => e.accepted = true

        Column {
            visible: ov.kind === "cleankeys" && !ov.black
            anchors.centerIn: parent
            spacing: 14
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: ov.left
                   color: "#fff"; font.pixelSize: 120; font.weight: Font.Bold; font.family: Theme.font }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Tastatur gesperrt – jetzt abwischen"
                   color: "#8d93a6"; font.pixelSize: 22; font.family: Theme.font }
            Text { anchors.horizontalCenter: parent.horizontalCenter
                   text: "Doppelklick beendet vorzeitig · Die Super-Taste kann nicht gesperrt werden"
                   color: "#5b6174"; font.pixelSize: 14; font.family: Theme.font }
        }
        Text {
            visible: ov.kind === "cleankeys" && ov.black
            anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 12
            text: ov.left; color: "#222"; font.pixelSize: 14
        }
        Text {
            visible: ov.kind === "pixeltest" && ov.step === 0
            anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottomMargin: 40
            text: "Klick oder beliebige Taste: nächste Farbe · Esc beendet"
            color: "#666"; font.pixelSize: 16; font.family: Theme.font
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: ov.kind === "pixeltest" ? Qt.BlankCursor : Qt.ArrowCursor
            onClicked: if (ov.kind === "pixeltest") { ov.step++; if (ov.step >= ov.colors.length) ov.finish() }
            onDoubleClicked: if (ov.kind === "cleankeys") ov.finish()
        }
    }
}
