import QtQuick
import QtQuick.Window

Item {
    id: root
    property var win
    property alias searchText: searchLabel.text
    signal searchClicked()
    signal homeClicked()
    height: 44

    // Ziehen zum Verschieben, Doppelklick maximiert
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        onPressed: root.win.startSystemMove()
        onDoubleClicked: root.win.toggleMax()
    }

    Row {
        id: brand
        anchors.left: parent.left
        anchors.leftMargin: 14
        anchors.verticalCenter: parent.verticalCenter
        spacing: 10
        Image {
            source: Qt.resolvedUrl("../assets/toolbox.svg")
            width: 22; height: 22
            sourceSize: Qt.size(44, 44)
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: "Toolbox"
            color: Theme.text
            font.family: Theme.font
            font.pixelSize: 14
            font.weight: Font.Bold
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    MouseArea {
        anchors.fill: brand
        cursorShape: Qt.PointingHandCursor
        onClicked: root.homeClicked()
    }

    // Suchfeld (öffnet Palette)
    Rectangle {
        anchors.centerIn: parent
        width: Math.min(420, parent.width - 400)
        height: 30
        radius: 9
        color: sm.containsMouse ? Theme.hover : Theme.raised
        border.color: Theme.border
        Behavior on color { ColorAnimation { duration: 90 } }
        Row {
            anchors.left: parent.left
            anchors.leftMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            Icon { name: "search"; size: 14; color: Theme.dim; anchors.verticalCenter: parent.verticalCenter }
            Text {
                id: searchLabel
                text: "Werkzeug suchen"
                color: Theme.dim
                font.family: Theme.font
                font.pixelSize: 13
                anchors.verticalCenter: parent.verticalCenter
            }
        }
        Rectangle {
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            width: kbd.implicitWidth + 12; height: 18; radius: 5
            color: Theme.bg
            Text {
                id: kbd
                anchors.centerIn: parent
                text: "Strg K"
                color: Theme.faint
                font.family: Theme.font
                font.pixelSize: 10
            }
        }
        MouseArea {
            id: sm
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.searchClicked()
        }
    }

    // Fenster-Knöpfe
    Row {
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2
        IconButton { icon: "minus"; onClicked: root.win.showMinimized() }
        IconButton {
            icon: root.win.visibility === Window.Maximized ? "copy" : "square"
            iconSize: root.win.visibility === Window.Maximized ? 14 : 13
            onClicked: root.win.toggleMax()
        }
        IconButton {
            icon: "x"
            hoverColor: Theme.danger
            hoverIconColor: "white"
            iconSize: 17
            onClicked: root.win.close()
        }
    }
}
