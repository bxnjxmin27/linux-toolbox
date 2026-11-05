import QtQuick

Rectangle {
    id: root
    property var categories: []
    property var counts: ({})
    property string current: "all"
    property int totalCount: 0
    signal picked(string id)
    signal settingsClicked()
    color: "transparent"

    component Item_: Rectangle {
        id: it
        property string label
        property string icon
        property string key
        property int count: -1
        property color tint: Theme.dim
        readonly property bool active: root.current === key
        width: parent.width; height: 36; radius: 9
        color: active ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.16)
                      : (ma.containsMouse ? Theme.raised : "transparent")
        Behavior on color { ColorAnimation { duration: 90 } }
        Row {
            anchors.left: parent.left; anchors.leftMargin: 11
            anchors.verticalCenter: parent.verticalCenter
            spacing: 11
            Icon { name: it.icon; size: 17; color: it.active ? it.tint : Theme.dim
                   anchors.verticalCenter: parent.verticalCenter }
            Text { text: it.label; color: it.active ? Theme.text : Theme.dim
                   font.family: Theme.font; font.pixelSize: 13
                   font.weight: it.active ? Font.DemiBold : Font.Normal
                   anchors.verticalCenter: parent.verticalCenter }
        }
        Text {
            visible: it.count >= 0
            anchors.right: parent.right; anchors.rightMargin: 11
            anchors.verticalCenter: parent.verticalCenter
            text: it.count; color: Theme.faint
            font.family: Theme.font; font.pixelSize: 11
        }
        MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor; onClicked: root.picked(it.key) }
    }

    Flickable {
        anchors.fill: parent
        anchors.bottomMargin: 52
        contentHeight: col.height
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        Column {
            id: col
            width: parent.width
            spacing: 2
            Item_ { label: "Alle Werkzeuge"; icon: "layout-grid"; key: "all"; count: root.totalCount; tint: Theme.accent }
            Item_ { label: "Favoriten"; icon: "star"; key: "fav"; tint: "#ffd24d" }
            Item_ { label: "Zuletzt benutzt"; icon: "history"; key: "recent"; tint: Theme.accent2 }
            Item { width: 1; height: 14 }
            Text {
                text: "KATEGORIEN"
                leftPadding: 11
                color: Theme.faint
                font.family: Theme.font; font.pixelSize: 10; font.weight: Font.Bold
                font.letterSpacing: 1.2
            }
            Item { width: 1; height: 4 }
            Repeater {
                model: root.categories
                delegate: Item_ {
                    required property var modelData
                    label: modelData.name; icon: modelData.icon; key: modelData.id
                    count: root.counts[modelData.id] || 0
                    tint: Theme.cat(modelData.id)
                    width: col.width
                }
            }
        }
    }

    Rectangle { anchors.left: parent.left; anchors.right: parent.right
                anchors.bottom: parent.bottom; anchors.bottomMargin: 50
                height: 1; color: Theme.border }
    Item_ {
        anchors.bottom: parent.bottom
        width: parent.width
        label: "Einstellungen"; icon: "settings"; key: "settings"
        tint: Theme.accent
    }
}
