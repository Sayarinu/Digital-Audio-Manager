import QtQuick

Rectangle {
    id: root
    property string artwork: ""
    property string symbol: "music"
    color: themeState.selected
    radius: 8
    clip: true
    Symbol { anchors.centerIn: parent; width: parent.width * 0.36; height: width; name: root.symbol; color: themeState.secondary; visible: picture.status !== Image.Ready }
    Image { id: picture; anchors.fill: parent; source: root.artwork; asynchronous: true; fillMode: Image.PreserveAspectCrop; sourceSize: Qt.size(root.width * 2, root.height * 2) }
}
