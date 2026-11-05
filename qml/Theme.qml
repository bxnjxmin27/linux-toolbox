pragma Singleton
import QtQuick

QtObject {
    readonly property color bg: "#0e0f14"
    readonly property color surface: "#15171e"
    readonly property color raised: "#1c1f29"
    readonly property color hover: "#232733"
    readonly property color border: "#272b37"
    readonly property color text: "#e9ebf2"
    readonly property color dim: "#8d93a6"
    readonly property color faint: "#5b6174"
    readonly property color accent: "#7c6cff"
    readonly property color accent2: "#5aa0ff"
    readonly property color danger: "#ff5d6c"
    readonly property color ok: "#3ecf8e"
    readonly property int radius: 12
    readonly property string font: "Inter, Cantarell, Noto Sans, sans-serif"
    readonly property string mono: "JetBrains Mono, Fira Code, DejaVu Sans Mono, monospace"
    readonly property var catColors: ({
        "video": "#ff6b6b", "audio": "#f5a524", "images": "#3ecf8e", "docs": "#4da3ff",
        "text": "#b56cff", "files": "#ffd24d", "system": "#38d1d1", "dev": "#ff7ac6"
    })
    function cat(id) { return catColors[id] || accent }
}
