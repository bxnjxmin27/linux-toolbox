import QtQuick

Rectangle {
    id: root
    property var tool
    property bool fav: false
    signal opened()
    signal favToggled()
    readonly property color tint: Theme.cat(tool.cat)

    radius: Theme.radius
    color: ma.containsMouse ? Theme.raised : Theme.surface
    border.color: ma.containsMouse ? Qt.rgba(tint.r, tint.g, tint.b, 0.55) : Theme.border
    Behavior on color { ColorAnimation { duration: 100 } }
    Behavior on border.color { ColorAnimation { duration: 100 } }

    Rectangle {
        id: badge
        x: 16; y: 16
        width: 40; height: 40; radius: 11
        color: Qt.rgba(root.tint.r, root.tint.g, root.tint.b, 0.14)
        Icon { anchors.centerIn: parent; name: root.tool.icon; size: 21; color: root.tint }
    }

    Rectangle {
        visible: root.tool.isnew
        anchors.top: parent.top; anchors.right: parent.right
        anchors.margins: 14
        width: nt.implicitWidth + 12; height: 18; radius: 9
        color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.2)
        Text { id: nt; anchors.centerIn: parent; text: "NEU"; color: Theme.accent
               font.pixelSize: 9; font.weight: Font.Bold; font.family: Theme.font }
    }

    Text {
        x: 16; y: 66
        width: parent.width - 32
        text: root.tool.name
        color: Theme.text
        font.family: Theme.font; font.pixelSize: 14; font.weight: Font.DemiBold
        elide: Text.ElideRight
    }
    Text {
        x: 16; y: 88
        width: parent.width - 32
        height: parent.height - 100
        text: root.tool.desc
        color: Theme.dim
        font.family: Theme.font; font.pixelSize: 12
        wrapMode: Text.Wrap
        maximumLineCount: 2
        elide: Text.ElideRight
        lineHeight: 1.15
    }

    Icon {
        visible: root.tool.missing.length > 0
        anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 12
        name: "triangle-alert"; size: 14; color: "#f5a524"
    }

    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.opened()
    }
    IconButton {
        visible: ma.containsMouse || root.fav || starMa.containsMouse
        anchors.right: parent.right
        anchors.rightMargin: root.tool.isnew ? 52 : 6
        anchors.top: parent.top
        anchors.topMargin: 8
        width: 28; height: 28
        icon: "star"
        iconColor: root.fav ? "#ffd24d" : Theme.faint
        hoverIconColor: "#ffd24d"
        onClicked: root.favToggled()
        MouseArea { id: starMa; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
    }
}
