import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic

Window {
    id: win
    width: 1240
    height: 800
    minimumWidth: 900
    minimumHeight: 600
    visible: true
    title: "Toolbox"
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint

    readonly property bool maxed: visibility === Window.Maximized || visibility === Window.FullScreen
    function toggleMax() { if (maxed) showNormal(); else showMaximized() }

    property var tools: JSON.parse(backend.toolsJson)
    property var categories: JSON.parse(backend.categoriesJson)
    property var filters: JSON.parse(backend.filtersJson)
    property var favs: JSON.parse(backend.favorites)
    property var recents: JSON.parse(backend.recent)
    property string section: "all"          // all | fav | recent | <kategorie> | settings
    property var currentTool: null
    property var pageTool: null   // bleibt beim Schließen erhalten (verhindert Binding-Fehler)

    Connections {
        target: backend
        function onFavoritesChanged() { win.favs = JSON.parse(backend.favorites) }
        function onRecentChanged() { win.recents = JSON.parse(backend.recent) }
    }

    property var counts: {
        var c = {}
        for (var i = 0; i < tools.length; i++) c[tools[i].cat] = (c[tools[i].cat] || 0) + 1
        return c
    }

    property var shown: {
        var out = []
        if (section === "recent") {
            for (var r = 0; r < recents.length; r++)
                for (var j = 0; j < tools.length; j++) if (tools[j].id === recents[r]) out.push(tools[j])
            return out
        }
        for (var i = 0; i < tools.length; i++) {
            var t = tools[i]
            if (section === "all" || t.cat === section || (section === "fav" && favs.indexOf(t.id) >= 0)) out.push(t)
        }
        return out
    }
    readonly property string sectionTitle: {
        if (section === "all") return "Alle Werkzeuge"
        if (section === "fav") return "Favoriten"
        if (section === "recent") return "Zuletzt benutzt"
        for (var i = 0; i < categories.length; i++) if (categories[i].id === section) return categories[i].name
        return ""
    }

    function openTool(t) { pageTool = t; currentTool = t; section = section === "settings" ? "all" : section }
    function pickSection(s) { currentTool = null; section = s }

    OverlayWindow {
        id: overlay
        onDone: backend.overlayClosed()
    }
    Connections {
        target: backend
        function onOverlayRequested(json) { overlay.openWith(JSON.parse(json)) }
    }

    Shortcut { sequence: "Ctrl+K"; onActivated: palette.open() }
    Shortcut { sequence: "Ctrl+F"; onActivated: palette.open() }
    Shortcut { sequences: ["Escape", "Alt+Left"]; enabled: !palette.visible && win.currentTool !== null
               onActivated: win.currentTool = null }
    Shortcut { sequence: "Ctrl+Q"; onActivated: win.close() }

    // ---- Fenster-Hülle ------------------------------------------------
    Rectangle {
        id: shell
        anchors.fill: parent
        radius: win.maxed ? 0 : 14
        color: Theme.bg
        border.color: win.maxed ? "transparent" : Theme.border
        border.width: 1

        TitleBar {
            id: titlebar
            win: win
            anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
            anchors.margins: 1
            onSearchClicked: palette.open()
            onHomeClicked: win.pickSection("all")
        }

        Sidebar {
            id: sidebar
            anchors.top: titlebar.bottom; anchors.bottom: parent.bottom; anchors.left: parent.left
            anchors.leftMargin: 12; anchors.bottomMargin: 12; anchors.topMargin: 4
            width: 206
            categories: win.categories
            counts: win.counts
            totalCount: win.tools.length
            current: win.section
            onPicked: (id) => win.pickSection(id)
        }

        Item {
            id: content
            anchors.top: titlebar.bottom; anchors.bottom: parent.bottom; anchors.right: parent.right
            anchors.left: sidebar.right
            anchors.leftMargin: 14; anchors.rightMargin: 18; anchors.bottomMargin: 16; anchors.topMargin: 4

            // Raster
            Item {
                anchors.fill: parent
                visible: !win.currentTool && win.section !== "settings"

                Row {
                    id: gridHead
                    height: 54
                    spacing: 12
                    Text { text: win.sectionTitle; color: Theme.text; anchors.verticalCenter: parent.verticalCenter
                           font.family: Theme.font; font.pixelSize: 24; font.weight: Font.Bold }
                    Text { text: win.shown.length; color: Theme.faint; anchors.verticalCenter: parent.verticalCenter
                           font.family: Theme.font; font.pixelSize: 14; topPadding: 4 }
                }

                GridView {
                    id: grid
                    anchors.top: gridHead.bottom; anchors.bottom: parent.bottom
                    anchors.left: parent.left; anchors.right: parent.right
                    readonly property int cols: Math.max(2, Math.floor(width / 232))
                    cellWidth: Math.floor(width / cols)
                    cellHeight: 138
                    model: win.shown
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    cacheBuffer: 600
                    ScrollBar.vertical: ScrollBar { }
                    delegate: Item {
                        required property var modelData
                        width: grid.cellWidth; height: grid.cellHeight
                        ToolCard {
                            anchors.fill: parent; anchors.margins: 6
                            tool: modelData
                            fav: win.favs.indexOf(modelData.id) >= 0
                            onOpened: win.openTool(modelData)
                            onFavToggled: backend.toggleFavorite(modelData.id)
                        }
                    }
                    Text {
                        visible: win.shown.length === 0
                        anchors.centerIn: parent
                        text: win.section === "fav" ? "Noch keine Favoriten – tippe auf den Stern an einem Werkzeug."
                                                    : "Noch nichts benutzt."
                        color: Theme.faint; font.family: Theme.font; font.pixelSize: 13
                    }
                }
            }

            // Werkzeug
            Loader {
                anchors.fill: parent
                active: !!win.currentTool
                sourceComponent: ToolPage {
                    tool: win.pageTool
                    filters: win.filters
                    fav: win.favs.indexOf(win.pageTool.id) >= 0
                    onBack: win.currentTool = null
                    onFavToggled: backend.toggleFavorite(win.pageTool.id)
                }
            }

            SettingsPage {
                anchors.fill: parent
                visible: win.section === "settings" && !win.currentTool
                filters: win.filters
            }
        }

        CommandPalette {
            objectName: "palette"
            id: palette
            anchors.fill: parent
            anchors.topMargin: 1
            tools: win.tools
            onPicked: (t) => win.openTool(t)
        }
    }

    // ---- Größenänderung an den Rändern (rahmenloses Fenster) ----------
    component Edge: MouseArea {
        property int edges
        hoverEnabled: true
        enabled: !win.maxed
        onPressed: win.startSystemResize(edges)
    }
    Edge { edges: Qt.LeftEdge;   width: 5; anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
           anchors.topMargin: 10; anchors.bottomMargin: 10; cursorShape: Qt.SizeHorCursor }
    Edge { edges: Qt.RightEdge;  width: 5; anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
           anchors.topMargin: 10; anchors.bottomMargin: 10; cursorShape: Qt.SizeHorCursor }
    Edge { edges: Qt.TopEdge;    height: 5; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
           anchors.leftMargin: 10; anchors.rightMargin: 10; cursorShape: Qt.SizeVerCursor }
    Edge { edges: Qt.BottomEdge; height: 5; anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
           anchors.leftMargin: 10; anchors.rightMargin: 10; cursorShape: Qt.SizeVerCursor }
    Edge { edges: Qt.TopEdge | Qt.LeftEdge;     width: 10; height: 10; anchors.left: parent.left; anchors.top: parent.top; cursorShape: Qt.SizeFDiagCursor }
    Edge { edges: Qt.TopEdge | Qt.RightEdge;    width: 10; height: 10; anchors.right: parent.right; anchors.top: parent.top; cursorShape: Qt.SizeBDiagCursor }
    Edge { edges: Qt.BottomEdge | Qt.LeftEdge;  width: 10; height: 10; anchors.left: parent.left; anchors.bottom: parent.bottom; cursorShape: Qt.SizeBDiagCursor }
    Edge { edges: Qt.BottomEdge | Qt.RightEdge; width: 10; height: 10; anchors.right: parent.right; anchors.bottom: parent.bottom; cursorShape: Qt.SizeFDiagCursor }
}
