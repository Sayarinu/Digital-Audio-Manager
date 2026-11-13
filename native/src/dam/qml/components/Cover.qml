import QtQuick
import QtQuick.Window
import QtQuick.Effects
import "../Theme.js" as Theme

Rectangle {
    id: root
    property string artwork: ""
    property string symbol: "music"
    property color accent: themeState.selected
    readonly property bool software: GraphicsInfo.api === GraphicsInfo.Software
    radius: Theme.radiusSmall
    clip: true
    gradient: Gradient { GradientStop { position: 0; color: root.accent } GradientStop { position: 1; color: Qt.darker(root.accent, 2.4) } }
    Symbol { anchors.centerIn: parent; width: Math.min(parent.width * 0.4, 54); height: width; name: root.symbol; color: "#66ffffff"; visible: picture.status !== Image.Ready }
    Image {
        id: picture
        anchors.fill: parent; source: root.artwork; asynchronous: true; retainWhileLoading: true; fillMode: Image.PreserveAspectCrop
        sourceSize: Qt.size(Math.ceil(root.width * Screen.devicePixelRatio), Math.ceil(root.height * Screen.devicePixelRatio))
        visible: !root.software
        onStatusChanged: if (root.software) paintAfterLoad.restart()
        layer.enabled: visible && root.radius > 0
        layer.effect: MultiEffect { maskEnabled: true; maskSource: roundedMask; autoPaddingEnabled: false }
        opacity: status === Image.Ready ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.duration(Theme.motionMedium, appState.reducedMotion); easing.type: Easing.OutCubic } }
    }
    Image {
        id: roundedMask
        visible: false
        sourceSize: picture.sourceSize
        source: "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="' + root.width + '" height="' + root.height + '"><rect width="' + root.width + '" height="' + root.height + '" rx="' + root.radius + '" fill="white"/></svg>')
    }
    Timer { id: paintAfterLoad; interval: 16; onTriggered: softwareMask.requestPaint() }
    Canvas {
        id: softwareMask
        anchors.fill: parent
        visible: root.software && picture.status === Image.Ready
        antialiasing: true
        readonly property real pixelRatio: Screen.devicePixelRatio
        canvasSize: Qt.size(Math.ceil(width * pixelRatio), Math.ceil(height * pixelRatio))
        onVisibleChanged: if (visible) requestPaint()
        onAvailableChanged: if (available && visible) requestPaint()
        onWidthChanged: if (visible) requestPaint()
        onHeightChanged: if (visible) requestPaint()
        Connections { target: root; function onRadiusChanged() { softwareMask.requestPaint() } }
        onPaint: {
            if (!visible) return
            var ctx = getContext("2d")
            ctx.reset()
            ctx.clearRect(0, 0, canvasSize.width, canvasSize.height)
            ctx.scale(pixelRatio, pixelRatio)
            ctx.beginPath()
            ctx.roundedRect(0, 0, width, height, root.radius, root.radius)
            ctx.clip()
            ctx.drawImage(picture, (width - picture.paintedWidth) / 2, (height - picture.paintedHeight) / 2, picture.paintedWidth, picture.paintedHeight)
        }
    }
}
