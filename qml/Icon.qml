import QtQuick

Image {
    id: root
    property string name: "circle-help"
    property color color: "#ffffff"
    property int size: 20
    width: size
    height: size
    sourceSize: Qt.size(size * 2, size * 2)
    source: "image://icons/" + name + "/" + String(color).replace("#", "").substring(0, 6)
    asynchronous: false
    cache: true
    smooth: true
    mipmap: true
    fillMode: Image.PreserveAspectFit
}
