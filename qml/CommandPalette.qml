import QtQuick
import QtQuick.Controls.Basic

Item {
    id: root
    property var tools: []
    signal picked(var tool)
    signal closed()
    property var results: []
    visible: false

    function open() { visible = true; input.text = ""; refresh(); input.forceActiveFocus() }
    function close() { visible = false; closed() }

    function refresh() {
        var q = input.text.trim().toLowerCase()
        var out = []
        for (var i = 0; i < tools.length; i++) {
            var t = tools[i]
            var n = t.name.toLowerCase()
            var s = 0
            if (q === "") s = 1
            else if (n.indexOf(q) === 0) s = 100
            else if (n.indexOf(q) > 0) s = 60
            else if ((t.keywords + " " + t.desc).toLowerCase().indexOf(q) >= 0) s = 20
            if (s > 0) out.push({ t: t, s: s })
        }
        if (q !== "") out.sort(function (a, b) { return b.s - a.s })
        results = out.slice(0, 9).map(function (o) { return o.t })
        list.currentIndex = 0
    }

    Rectangle { anchors.fill: parent; color: "#aa05060a"
                MouseArea { anchors.fill: parent; onClicked: root.close() } }

    Rectangle {
        width: Math.min(580, parent.width - 60)
        anchors.horizontalCenter: parent.horizontalCenter
        y: Math.min(110, parent.height * 0.15)
        height: head.height + list.height + 12
        radius: 16; color: Theme.surface; border.color: Theme.border
        clip: true

        Item {
            id: head
            width: parent.width; height: 56
            Icon { x: 18; anchors.verticalCenter: parent.verticalCenter; name: "search"; size: 18; color: Theme.dim }
            TextField {
                id: input
                x: 48; width: parent.width - 66; height: parent.height
                placeholderText: "Werkzeug suchen …"
                color: Theme.text; placeholderTextColor: Theme.faint
                font.family: Theme.font; font.pixelSize: 16
                background: null
                onTextChanged: root.refresh()
                Keys.onDownPressed: list.currentIndex = Math.min(list.count - 1, list.currentIndex + 1)
                Keys.onUpPressed: list.currentIndex = Math.max(0, list.currentIndex - 1)
                Keys.onReturnPressed: if (list.currentItem) { root.picked(root.results[list.currentIndex]); root.close() }
                Keys.onEscapePressed: root.close()
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.border }
        }

        ListView {
            id: list
            y: head.height + 6
            width: parent.width
            height: Math.min(count, 9) * 46
            model: root.results
            interactive: false
            currentIndex: 0
            delegate: Rectangle {
                required property var modelData
                required property int index
                width: list.width - 12; x: 6; height: 44; radius: 10
                color: ListView.isCurrentItem ? Theme.raised : "transparent"
                readonly property color tint: Theme.cat(modelData.cat)
                Rectangle { x: 8; anchors.verticalCenter: parent.verticalCenter
                            width: 30; height: 30; radius: 8
                            color: Qt.rgba(tint.r, tint.g, tint.b, 0.15)
                            Icon { anchors.centerIn: parent; name: modelData.icon; size: 16; color: tint } }
                Text { x: 48; width: parent.width - 60; anchors.verticalCenter: parent.verticalCenter
                       text: modelData.name; color: Theme.text; elide: Text.ElideRight
                       font.family: Theme.font; font.pixelSize: 14 }
                MouseArea { anchors.fill: parent; hoverEnabled: true
                            onEntered: list.currentIndex = index
                            onClicked: { root.picked(modelData); root.close() } }
            }
            Text { visible: parent.count === 0; anchors.centerIn: parent
                   text: "Nichts gefunden"; color: Theme.faint; font.family: Theme.font }
        }
    }
}
