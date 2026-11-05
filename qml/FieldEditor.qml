import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs

Item {
    id: root
    property var field
    property var value
    property var filters: ({})
    signal edited(var v)

    implicitHeight: col.implicitHeight
    height: implicitHeight

    function setValue(v) { value = v; edited(v) }
    readonly property string token: "f" + Math.random().toString(36).substring(2, 10)
    property var fallback: null
    function choose(dlg, multiple, folder, title) {
        fallback = dlg
        backend.pick(token, title || "Auswählen", filters[field.filter] || "", multiple, folder)
    }
    Connections {
        target: backend
        function onPickerResult(tok, json) {
            if (tok !== root.token) return
            var r = JSON.parse(json)
            if (!r.ok) { if (root.fallback) root.fallback.open(); return }
            if (r.paths.length === 0) return
            if (field.type === "folder") root.setValue(r.paths[0])
            else root.addFiles(r.paths.map(function (p) { return "file://" + p }))
        }
    }
    function toPath(u) { return decodeURIComponent(u.toString().replace(/^file:\/\//, "")) }
    function addFiles(list) {
        var cur = (field.type === "files" && value) ? value.slice() : []
        for (var i = 0; i < list.length; i++) {
            var p = toPath(list[i])
            if (cur.indexOf(p) < 0) cur.push(p)
        }
        setValue(field.type === "file" ? cur.slice(-1) : cur)
    }

    Column {
        id: col
        width: parent.width
        spacing: 7

        Text {
            visible: field.label !== "" && field.type !== "bool" && field.type !== "annotate"
            text: field.label
            color: Theme.dim
            font.family: Theme.font; font.pixelSize: 12; font.weight: Font.DemiBold
        }

        Loader {
            width: parent.width
            sourceComponent: {
                switch (field.type) {
                case "file": case "files": return fileC
                case "folder": return folderC
                case "text": return textC
                case "textarea": return areaC
                case "choice": return choiceC
                case "number": return numberC
                case "slider": return sliderC
                case "bool": return boolC
                case "color": return colorC
                case "annotate": return noneC
                }
                return textC
            }
        }

        Text {
            visible: field.hint !== "" && field.hint !== "mono"
            width: parent.width
            text: field.hint
            color: Theme.faint
            wrapMode: Text.Wrap
            font.family: Theme.font; font.pixelSize: 11
        }
    }

    Component { id: noneC; Item { width: 1; height: 0 } }

    // ---- Dateien ------------------------------------------------------
    Component {
        id: fileC
        Rectangle {
            id: zone
            width: parent ? parent.width : 300
            height: inner.height + 24
            radius: 12
            color: drop.containsDrag ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.12) : Theme.bg
            border.color: drop.containsDrag ? Theme.accent : Theme.border
            border.width: 1

            Canvas {   // gestrichelter Rahmen
                anchors.fill: parent
                visible: !root.value || root.value.length === 0
                onPaint: {
                    var c = getContext("2d"); c.reset()
                    c.strokeStyle = drop.containsDrag ? "#7c6cff" : "#323746"
                    c.lineWidth = 1.5; c.setLineDash([5, 5])
                    c.beginPath(); c.roundedRect(1, 1, width - 2, height - 2, 12, 12); c.stroke()
                }
                Connections { target: drop; function onContainsDragChanged() { requestPaint() } }
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
            }

            Column {
                id: inner
                x: 12; y: 12
                width: parent.width - 24
                spacing: 8

                Column {
                    visible: !root.value || root.value.length === 0
                    width: parent.width
                    spacing: 6
                    topPadding: 6; bottomPadding: 6
                    Icon { anchors.horizontalCenter: parent.horizontalCenter
                           name: "upload"; size: 24; color: Theme.dim }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: field.type === "files" ? "Dateien hierher ziehen" : "Datei hierher ziehen"
                        color: Theme.text; font.family: Theme.font; font.pixelSize: 13; font.weight: Font.DemiBold
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "oder klicken zum Auswählen"
                        color: Theme.faint; font.family: Theme.font; font.pixelSize: 11
                    }
                }

                Repeater {
                    model: root.value ? root.value : []
                    delegate: Rectangle {
                        required property string modelData
                        required property int index
                        width: inner.width; height: 30; radius: 8; color: Theme.raised
                        Icon { x: 9; anchors.verticalCenter: parent.verticalCenter
                               name: "file"; size: 14; color: Theme.dim }
                        Text {
                            x: 31; width: parent.width - 66
                            anchors.verticalCenter: parent.verticalCenter
                            text: backend.fileName(modelData)
                            color: Theme.text; elide: Text.ElideMiddle
                            font.family: Theme.font; font.pixelSize: 12
                        }
                        IconButton {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            width: 28; height: 28; icon: "x"; iconSize: 13
                            onClicked: { var a = root.value.slice(); a.splice(index, 1); root.setValue(a) }
                        }
                    }
                }

                Row {
                    visible: root.value && root.value.length > 0
                    spacing: 8
                    Btn { text: field.type === "files" ? "Weitere hinzufügen" : "Andere Datei"
                             icon: "plus"; implicitHeight: 30; onClicked: root.choose(dlg, field.type === "files", false, field.label) }
                    Btn { visible: field.type === "files"; text: "Leeren"; implicitHeight: 30
                             onClicked: root.setValue([]) }
                }
            }

            MouseArea {
                anchors.fill: parent
                enabled: !root.value || root.value.length === 0
                cursorShape: Qt.PointingHandCursor
                onClicked: root.choose(dlg, field.type === "files", false, field.label)
            }
            DropArea {
                id: drop
                anchors.fill: parent
                onDropped: (d) => { if (d.hasUrls) root.addFiles(d.urls) }
            }
            FileDialog {
                id: dlg
                title: field.label || "Datei wählen"
                fileMode: field.type === "files" ? FileDialog.OpenFiles : FileDialog.OpenFile
                nameFilters: root.filters[field.filter]
                             ? [root.filters[field.filter], "Alle Dateien (*)"] : ["Alle Dateien (*)"]
                onAccepted: root.addFiles(selectedFiles)
            }
        }
    }

    // ---- Ordner -------------------------------------------------------
    Component {
        id: folderC
        Rectangle {
            width: parent ? parent.width : 300
            height: 40; radius: 10; color: Theme.bg; border.color: Theme.border
            Icon { x: 12; anchors.verticalCenter: parent.verticalCenter; name: "folder"; size: 16; color: Theme.dim }
            Text {
                x: 38; width: parent.width - 50; anchors.verticalCenter: parent.verticalCenter
                text: root.value ? root.value : "Ordner wählen …"
                color: root.value ? Theme.text : Theme.faint; elide: Text.ElideMiddle
                font.family: Theme.font; font.pixelSize: 12
            }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.choose(fd, false, true, field.label) }
            FolderDialog { id: fd; onAccepted: root.setValue(root.toPath(selectedFolder)) }
        }
    }

    // ---- Text ---------------------------------------------------------
    Component {
        id: textC
        TextField {
            width: parent ? parent.width : 300
            height: 40
            text: root.value === undefined || root.value === null ? "" : root.value
            placeholderText: field.placeholder
            color: Theme.text; placeholderTextColor: Theme.faint
            selectionColor: Theme.accent
            font.family: Theme.font; font.pixelSize: 13
            leftPadding: 12; rightPadding: 12
            background: Rectangle { radius: 10; color: Theme.bg
                border.color: parent.activeFocus ? Theme.accent : Theme.border }
            onTextEdited: root.setValue(text)
        }
    }

    Component {
        id: areaC
        Rectangle {
            width: parent ? parent.width : 300
            height: Math.max(160, Math.min(320, ta.contentHeight + 24))
            radius: 10; color: Theme.bg
            border.color: ta.activeFocus ? Theme.accent : Theme.border
            Flickable {
                anchors.fill: parent; anchors.margins: 2
                contentWidth: width; contentHeight: ta.height
                clip: true; boundsBehavior: Flickable.StopAtBounds
                TextArea.flickable: TextArea {
                    id: ta
                    text: root.value === undefined || root.value === null ? "" : root.value
                    placeholderText: field.placeholder
                    color: Theme.text; placeholderTextColor: Theme.faint
                    selectionColor: Theme.accent
                    font.family: field.hint.indexOf("mono") >= 0 ? Theme.mono : Theme.font
                    font.pixelSize: 13
                    wrapMode: TextArea.Wrap
                    leftPadding: 10; rightPadding: 10; topPadding: 10; bottomPadding: 10
                    background: null
                    onTextChanged: if (text !== root.value) root.setValue(text)
                }
                ScrollBar.vertical: ScrollBar { }
            }
        }
    }

    // ---- Auswahl ------------------------------------------------------
    Component {
        id: choiceC
        Flow {
            width: parent ? parent.width : 300
            spacing: 6
            Repeater {
                model: field.options
                delegate: Rectangle {
                    required property var modelData
                    readonly property bool on: root.value === modelData[0]
                    width: lbl.implicitWidth + 24; height: 32; radius: 9
                    color: on ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.2)
                              : (pm.containsMouse ? Theme.hover : Theme.raised)
                    border.color: on ? Theme.accent : Theme.border
                    Text { id: lbl; anchors.centerIn: parent; text: modelData[1]
                           color: on ? Theme.text : Theme.dim
                           font.family: Theme.font; font.pixelSize: 12
                           font.weight: on ? Font.DemiBold : Font.Normal }
                    MouseArea { id: pm; anchors.fill: parent; hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.setValue(modelData[0]) }
                }
            }
        }
    }

    Component {
        id: numberC
        Row {
            spacing: 8
            TextField {
                width: 110; height: 40
                text: root.value === undefined || root.value === null ? "" : String(root.value)
                color: Theme.text; selectionColor: Theme.accent
                font.family: Theme.font; font.pixelSize: 13
                leftPadding: 12
                validator: DoubleValidator { notation: DoubleValidator.StandardNotation; locale: "C" }
                inputMethodHints: Qt.ImhFormattedNumbersOnly
                background: Rectangle { radius: 10; color: Theme.bg
                    border.color: parent.activeFocus ? Theme.accent : Theme.border }
                onTextEdited: { var n = parseFloat(text); if (!isNaN(n)) root.setValue(n) }
            }
            Text {
                visible: field.placeholder !== ""
                anchors.verticalCenter: parent.verticalCenter
                text: field.placeholder; color: Theme.faint
                font.family: Theme.font; font.pixelSize: 12
            }
        }
    }

    Component {
        id: sliderC
        Row {
            width: parent ? parent.width : 300
            spacing: 12
            Slider {
                id: sl
                width: parent.width - 60; height: 28
                from: field.min; to: field.max; stepSize: field.step
                value: root.value === undefined || root.value === null ? field.min : root.value
                onMoved: root.setValue(value)
                background: Rectangle {
                    x: sl.leftPadding; y: sl.topPadding + sl.availableHeight / 2 - 2
                    width: sl.availableWidth; height: 4; radius: 2; color: Theme.border
                    Rectangle { width: sl.visualPosition * parent.width; height: 4; radius: 2; color: Theme.accent }
                }
                handle: Rectangle {
                    x: sl.leftPadding + sl.visualPosition * (sl.availableWidth - width)
                    y: sl.topPadding + sl.availableHeight / 2 - height / 2
                    width: 16; height: 16; radius: 8; color: "white"
                    border.color: Theme.accent; border.width: sl.pressed ? 3 : 2
                }
            }
            Text {
                width: 48; anchors.verticalCenter: parent.verticalCenter
                text: (Math.round(sl.value * 100) / 100) + (field.placeholder || "")
                color: Theme.text; font.family: Theme.font; font.pixelSize: 12
            }
        }
    }

    Component {
        id: boolC
        Item {
            width: parent ? parent.width : 300
            height: 30
            Rectangle {
                id: track
                width: 38; height: 22; radius: 11
                anchors.verticalCenter: parent.verticalCenter
                color: root.value ? Theme.accent : Theme.border
                Behavior on color { ColorAnimation { duration: 120 } }
                Rectangle {
                    y: 3; width: 16; height: 16; radius: 8; color: "white"
                    x: root.value ? 19 : 3
                    Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                }
            }
            Text {
                anchors.left: track.right; anchors.leftMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                text: field.label; color: Theme.text
                font.family: Theme.font; font.pixelSize: 13
            }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        onClicked: root.setValue(!root.value) }
        }
    }

    Component {
        id: colorC
        Row {
            spacing: 10
            Rectangle {
                width: 40; height: 40; radius: 10; color: root.value || "#ffffff"
                border.color: Theme.border
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: cd.open() }
            }
            TextField {
                width: 110; height: 40
                text: root.value || "#ffffff"
                color: Theme.text; font.family: Theme.mono; font.pixelSize: 13
                leftPadding: 12
                background: Rectangle { radius: 10; color: Theme.bg
                    border.color: parent.activeFocus ? Theme.accent : Theme.border }
                onTextEdited: if (/^#[0-9a-fA-F]{6}$/.test(text)) root.setValue(text)
            }
            ColorDialog { id: cd; selectedColor: root.value || "#ffffff"
                          onAccepted: root.setValue(String(selectedColor).substring(0, 7)) }
        }
    }
}
