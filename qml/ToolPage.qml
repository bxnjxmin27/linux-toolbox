import QtQuick
import QtQuick.Controls.Basic

Item {
    id: root
    objectName: "toolPage"
    property var tool
    property bool fav: false
    property var filters: ({})
    signal back()
    signal favToggled()

    property var values: ({})
    property int rev: 0
    property string state: "idle"      // idle | running | done | error
    property real progress: 0
    property string lastLog: ""
    property var result: ({})
    property bool rerun: false
    readonly property color tint: Theme.cat(tool.cat)
    readonly property var annField: {
        for (var i = 0; i < tool.fields.length; i++) if (tool.fields[i].type === "annotate") return tool.fields[i]
        return null
    }
    property string srcFile: ""

    function defaultFor(f) {
        if (f.type === "file" || f.type === "files") return []
        if (f.default !== null && f.default !== undefined) return f.default
        if (f.type === "bool") return false
        if (f.type === "number" || f.type === "slider") return f.min
        if (f.type === "choice") return f.options.length ? f.options[0][0] : ""
        if (f.type === "color") return "#ffffff"
        return ""
    }
    function isShown(f) {
        rev
        if (!f.showIf) return true
        var p = f.showIf.split("=")
        return String(values[p[0]]) === p[1]
    }
    function setVal(key, v) {
        values[key] = v
        if (key === "file") srcFile = (v && v.length) ? v[0] : ""
        rev++
        if (tool.live) liveTimer.restart()
    }
    function start() {
        if (backend.running) { rerun = true; return }
        for (var i = 0; i < tool.fields.length; i++) {
            var f = tool.fields[i]
            if ((f.type === "file" || f.type === "files") && !f.optional && isShown(f)
                    && (!values[f.key] || values[f.key].length === 0)) {
                if (!tool.live) {
                    result = { ok: false, message: "Wähle zuerst " + (f.type === "files" ? "Dateien" : "eine Datei") + " aus." }
                    state = "error"
                }
                return
            }
        }
        state = "running"; progress = 0; lastLog = ""
        backend.markRecent(tool.id)
        backend.run(tool.id, JSON.stringify(values))
    }

    Component.onCompleted: {
        var v = {}
        for (var i = 0; i < tool.fields.length; i++) v[tool.fields[i].key] = defaultFor(tool.fields[i])
        values = v; rev++
        if (tool.live) liveTimer.restart()
    }

    Timer { id: liveTimer; interval: 140; onTriggered: root.start() }

    Connections {
        target: backend
        function onProgressChanged(p) { root.progress = p }
        function onLogLine(s) { root.lastLog = s }
        function onFinished(json) {
            var r = JSON.parse(json)
            root.result = r
            if (!(root.tool.live && r.ok === false && r.message === "")) root.state = r.ok ? "done" : "error"
            if (root.rerun) { root.rerun = false; root.start() }
        }
    }

    // ---- Kopf ---------------------------------------------------------
    Item {
        id: head
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        height: 76
        IconButton { id: backBtn; x: 0; anchors.verticalCenter: parent.verticalCenter
                     width: 36; height: 36; icon: "arrow-left"; iconSize: 18; onClicked: root.back() }
        Rectangle {
            id: hb; x: 48; anchors.verticalCenter: parent.verticalCenter
            width: 46; height: 46; radius: 13
            color: Qt.rgba(root.tint.r, root.tint.g, root.tint.b, 0.15)
            Icon { anchors.centerIn: parent; name: root.tool.icon; size: 24; color: root.tint }
        }
        Column {
            anchors.left: hb.right; anchors.leftMargin: 14
            anchors.right: starBtn.left; anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            spacing: 3
            Text { text: root.tool.name; color: Theme.text; width: parent.width; elide: Text.ElideRight
                   font.family: Theme.font; font.pixelSize: 20; font.weight: Font.Bold }
            Text { text: root.tool.desc; color: Theme.dim; width: parent.width; elide: Text.ElideRight
                   font.family: Theme.font; font.pixelSize: 12 }
        }
        IconButton { id: starBtn; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                     width: 36; height: 36; icon: "star"; iconSize: 18
                     iconColor: root.fav ? "#ffd24d" : Theme.faint; hoverIconColor: "#ffd24d"
                     onClicked: root.favToggled() }
    }

    // Fehlende Programme
    Rectangle {
        id: warn
        visible: root.tool.missing.length > 0
        anchors.top: head.bottom; anchors.left: parent.left; anchors.right: parent.right
        height: visible ? 40 : 0; radius: 10
        color: Qt.rgba(0.96, 0.65, 0.14, 0.12); border.color: Qt.rgba(0.96, 0.65, 0.14, 0.4)
        Row {
            anchors.verticalCenter: parent.verticalCenter; x: 12; spacing: 10
            Icon { name: "triangle-alert"; size: 16; color: "#f5a524"; anchors.verticalCenter: parent.verticalCenter }
            Text { text: "Benötigt: " + root.tool.missing.join(", ") + " – bitte installieren (siehe README)."
                   color: "#f5c46b"; font.family: Theme.font; font.pixelSize: 12
                   anchors.verticalCenter: parent.verticalCenter }
        }
    }

    // ---- Formular -----------------------------------------------------
    Rectangle {
        id: formCard
        anchors.top: warn.visible ? warn.bottom : head.bottom
        anchors.topMargin: 10
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        width: Math.min(440, Math.max(340, parent.width * 0.42))
        radius: Theme.radius; color: Theme.surface; border.color: Theme.border

        Flickable {
            id: fl
            anchors.fill: parent; anchors.margins: 18
            anchors.bottomMargin: tool.live ? 18 : 74
            contentWidth: width; contentHeight: fcol.height
            clip: true; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { }
            Column {
                id: fcol
                width: fl.width - 6
                spacing: 16
                Repeater {
                    model: root.tool.fields
                    delegate: FieldEditor {
                        required property var modelData
                        field: modelData
                        filters: root.filters
                        width: fcol.width
                        visible: root.isShown(modelData)
                        height: visible ? implicitHeight : 0
                        value: root.defaultFor(modelData)
                        onEdited: (v) => root.setVal(modelData.key, v)
                    }
                }
                Text {
                    visible: root.tool.fields.length === 0
                    text: "Keine Einstellungen nötig."
                    color: Theme.faint; font.family: Theme.font; font.pixelSize: 13
                }
            }
        }

        Row {
            visible: !root.tool.live
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            anchors.margins: 18
            spacing: 10
            Btn {
                width: parent.width; height: 44
                primary: true
                enabled: !backend.running && root.tool.missing.length === 0
                text: backend.running ? "Läuft …" : "Starten"
                icon: backend.running ? "loader" : "play"
                onClicked: root.start()
            }
        }
    }

    // ---- Ergebnis -----------------------------------------------------
    Rectangle {
        anchors.top: formCard.top; anchors.bottom: parent.bottom
        anchors.left: formCard.right; anchors.leftMargin: 12; anchors.right: parent.right
        radius: Theme.radius; color: Theme.surface; border.color: Theme.border
        clip: true

        // Zeichen-Editor (Beschriften / Schwärzen)
        AnnotateEditor {
            id: editor
            visible: root.annField !== null && root.state !== "running" && root.state !== "done"
            anchors.fill: parent; anchors.margins: 12
            anchors.topMargin: root.state === "error" ? 56 : 12
            source: root.srcFile
            tools: root.annField ? root.annField.options : []
            onChanged: (json) => root.annField && root.setVal(root.annField.key, json)
        }
        Rectangle {
            visible: root.annField !== null && root.state === "error"
            x: 12; y: 12; width: parent.width - 24; height: 36; radius: 9
            color: Qt.rgba(1, 0.36, 0.42, 0.14); border.color: Qt.rgba(1, 0.36, 0.42, 0.5)
            Text { anchors.centerIn: parent; width: parent.width - 20; text: root.result.message || ""
                   color: "#ff8a95"; elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter
                   font.family: Theme.font; font.pixelSize: 12 }
        }

        // Leerlauf
        Column {
            visible: root.annField === null && (root.state === "idle" || (root.tool.live && root.state !== "error" && !root.result.text))
            anchors.centerIn: parent; spacing: 10
            Icon { anchors.horizontalCenter: parent.horizontalCenter
                   name: root.tool.live ? "keyboard" : "sparkles"; size: 30; color: Theme.faint }
            Text { anchors.horizontalCenter: parent.horizontalCenter
                   text: root.tool.live ? "Das Ergebnis erscheint beim Tippen" : "Das Ergebnis erscheint hier"
                   color: Theme.faint; font.family: Theme.font; font.pixelSize: 13 }
        }

        // Läuft
        Column {
            visible: root.state === "running" && !root.tool.live
            anchors.centerIn: parent; width: Math.min(parent.width - 80, 380); spacing: 14
            Text { text: Math.round(root.progress * 100) + " %"; anchors.horizontalCenter: parent.horizontalCenter
                   color: Theme.text; font.family: Theme.font; font.pixelSize: 34; font.weight: Font.Bold
                   visible: root.progress > 0 }
            Rectangle {
                width: parent.width; height: 6; radius: 3; color: Theme.border; clip: true
                Rectangle {
                    height: parent.height; radius: 3; color: Theme.accent
                    width: root.progress > 0 ? parent.width * root.progress : parent.width * 0.3
                    x: 0
                    Behavior on width { NumberAnimation { duration: 140 } }
                    SequentialAnimation on x {
                        running: root.progress <= 0 && root.state === "running"
                        loops: Animation.Infinite
                        NumberAnimation { from: -120; to: 380; duration: 1100; easing.type: Easing.InOutQuad }
                    }
                }
            }
            Text { width: parent.width; text: root.lastLog; elide: Text.ElideMiddle; horizontalAlignment: Text.AlignHCenter
                   color: Theme.faint; font.family: Theme.font; font.pixelSize: 11; visible: text !== "" }
            Row {
                anchors.horizontalCenter: parent.horizontalCenter; spacing: 10
                Btn { visible: root.tool.stoppable; primary: true; text: "Beenden & speichern"; icon: "square"
                      onClicked: backend.stop() }
                Btn { text: "Abbrechen"; danger: true; onClicked: backend.cancel() }
            }
        }

        // Fehler
        Column {
            visible: root.state === "error" && root.annField === null
            anchors.centerIn: parent; width: parent.width - 60; spacing: 12
            Icon { anchors.horizontalCenter: parent.horizontalCenter; name: "circle-alert"; size: 30; color: Theme.danger }
            Text { width: parent.width; text: root.result.message || ""; color: Theme.text
                   wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
                   font.family: Theme.font; font.pixelSize: 13 }
        }

        // Fertig
        Item {
            visible: root.state === "done" || (root.tool.live && root.state === "running")
            anchors.fill: parent; anchors.margins: 18

            Row {
                id: okRow
                spacing: 10
                visible: !root.tool.live
                Icon { name: "circle-check"; size: 20; color: Theme.ok; anchors.verticalCenter: parent.verticalCenter }
                Text { text: root.result.message || ""; color: Theme.text; font.family: Theme.font
                       font.pixelSize: 14; font.weight: Font.DemiBold; anchors.verticalCenter: parent.verticalCenter }
            }

            // Textausgabe
            Rectangle {
                id: textBox
                visible: (root.result.text || "") !== ""
                anchors.top: okRow.visible ? okRow.bottom : parent.top
                anchors.topMargin: okRow.visible ? 12 : 0
                anchors.left: parent.left; anchors.right: parent.right
                anchors.bottom: filesCol.visible ? filesCol.top : parent.bottom
                anchors.bottomMargin: filesCol.visible ? 12 : 0
                radius: 10; color: Theme.bg; border.color: Theme.border
                Flickable {
                    anchors.fill: parent; anchors.margins: 2
                    contentWidth: width; contentHeight: out.height; clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { }
                    TextEdit {
                        id: out
                        width: parent.width
                        padding: 12
                        text: root.result.text || ""
                        readOnly: true; selectByMouse: true
                        color: Theme.text; selectionColor: Theme.accent
                        font.family: Theme.mono; font.pixelSize: 12
                        wrapMode: TextEdit.Wrap
                    }
                }
                Btn {
                    anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 8
                    implicitHeight: 28; text: "Kopieren"; icon: "copy"
                    onClicked: backend.copy(root.result.text)
                }
            }

            // Dateien
            Column {
                id: filesCol
                visible: !!(root.result.files && root.result.files.length > 0)
                anchors.left: parent.left; anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.top: textBox.visible ? undefined : okRow.bottom
                anchors.topMargin: 12
                spacing: 6
                Flickable {
                    width: parent.width
                    height: textBox.visible ? Math.min(contentHeight, 150) : filesCol.height - 56
                    contentHeight: flist.height; contentWidth: width; clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { }
                    Column {
                        id: flist
                        width: parent.width - 8; spacing: 6
                        Repeater {
                            model: root.result.files || []
                            delegate: Rectangle {
                                required property string modelData
                                width: flist.width; height: 40; radius: 9; color: fm.containsMouse ? Theme.hover : Theme.raised
                                Icon { x: 12; anchors.verticalCenter: parent.verticalCenter
                                       name: "file-check"; size: 16; color: Theme.ok }
                                Text { x: 38; width: parent.width - 100; anchors.verticalCenter: parent.verticalCenter
                                       text: backend.fileName(modelData); color: Theme.text; elide: Text.ElideMiddle
                                       font.family: Theme.font; font.pixelSize: 12 }
                                IconButton { anchors.right: parent.right; anchors.rightMargin: 4
                                             anchors.verticalCenter: parent.verticalCenter
                                             icon: "folder-open"; onClicked: backend.reveal(modelData) }
                                MouseArea { id: fm; anchors.fill: parent; hoverEnabled: true; z: -1
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: backend.openPath(modelData) }
                            }
                        }
                    }
                }
                Row {
                    spacing: 8
                    Btn {
                        visible: !textBox.visible
                        text: "Ausgabeordner öffnen"; icon: "folder-open"
                        onClicked: backend.openPath(root.result.dir)
                    }
                    Btn {
                        visible: root.annField !== null
                        text: "Weiter bearbeiten"; icon: "pencil"
                        onClicked: root.state = "idle"
                    }
                }
            }
        }
    }
}
