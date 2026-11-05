import QtQuick

Rectangle {
    id: root
    property string text: ""
    property string icon: ""
    property bool primary: false
    property bool danger: false
    property bool busy: false
    signal clicked()
    implicitHeight: 38
    implicitWidth: row.implicitWidth + 32
    radius: 10
    opacity: enabled ? 1 : 0.45
    color: primary ? (ma.pressed ? Qt.darker(Theme.accent, 1.2) : (ma.containsMouse ? Qt.lighter(Theme.accent, 1.12) : Theme.accent))
                   : (ma.containsMouse ? Theme.hover : Theme.raised)
    border.width: primary ? 0 : 1
    border.color: danger ? Theme.danger : Theme.border
    Behavior on color { ColorAnimation { duration: 90 } }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 8
        Icon {
            visible: root.icon !== ""
            name: root.icon
            size: 16
            color: root.primary ? "white" : (root.danger ? Theme.danger : Theme.text)
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: root.text
            color: root.primary ? "white" : (root.danger ? Theme.danger : Theme.text)
            font.family: Theme.font
            font.pixelSize: 13
            font.weight: Font.DemiBold
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
