import QtQuick

Rectangle {
    id: root
    property string icon: ""
    property color iconColor: Theme.dim
    property color hoverColor: Theme.hover
    property color hoverIconColor: Theme.text
    property int iconSize: 16
    property string tip: ""
    signal clicked()
    implicitWidth: 40
    implicitHeight: 32
    radius: 8
    color: ma.containsMouse ? hoverColor : "transparent"
    Behavior on color { ColorAnimation { duration: 90 } }

    Icon {
        anchors.centerIn: parent
        name: root.icon
        size: root.iconSize
        color: ma.containsMouse ? root.hoverIconColor : root.iconColor
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
