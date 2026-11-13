import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Window
import "components"
import "Theme.js" as Theme

FocusScope {
    id: root
    objectName: "expandedPlayer"
    property real rightInset: 0
    property real slidingInset: rightInset
    readonly property real stageWidth: width - rightInset
    readonly property var track: playerState.track
    readonly property bool software: GraphicsInfo.api === GraphicsInfo.Software
    readonly property real coverSize: Math.max(80, Math.min(stageWidth - 48, height - metadata.height - 64, 720))
    signal closeRequested()
    function focusStage() { closeButton.forceActiveFocus() }
    clip: true

    Rectangle { anchors.fill: parent; gradient: Gradient { GradientStop { position: 0; color: themeState.selected } GradientStop { position: 1; color: themeState.background } } }
    Image {
        id: backdrop
        anchors.fill: parent; asynchronous: true; visible: root.software; opacity: 0.45
        source: root.track.artwork_url || ""; sourceSize: Qt.size(640, 240)
        fillMode: Image.PreserveAspectCrop
    }
    MultiEffect {
        anchors.fill: parent; source: backdrop
        visible: !root.software && backdrop.status === Image.Ready
        blurEnabled: true; blur: 0.8; blurMax: 32; autoPaddingEnabled: false; opacity: 0.45
    }
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.alpha(themeState.background, 0.13) }
            GradientStop { position: 0.55; color: Qt.alpha(themeState.background, 0.6) }
            GradientStop { position: 1; color: themeState.background }
        }
    }
    Column {
        x: (root.width - root.slidingInset - width) / 2
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(root.stageWidth - 48, 760); spacing: 24
        Cover {
            objectName: "immersiveArtwork"
            anchors.horizontalCenter: parent.horizontalCenter
            width: root.coverSize; height: width; radius: Theme.radiusMedium
            artwork: root.track.artwork_url || ""
            Accessible.role: Accessible.Graphic
            Accessible.name: "Artwork for " + (root.track.title || "current song")
        }
        Column {
            id: metadata
            width: parent.width; spacing: 4
            AppText {
                objectName: "immersiveTrackTitle"
                width: parent.width; horizontalAlignment: Text.AlignHCenter
                text: root.track.title || "Nothing Playing"
                font.pixelSize: root.stageWidth < 600 ? 24 : 32; font.bold: true
                wrapMode: Text.Wrap; maximumLineCount: 2
            }
            AppText { width: parent.width; height: 36; horizontalAlignment: Text.AlignHCenter; text: root.track.artist || ""; font.pixelSize: 16 }
            AppText { width: parent.width; height: 36; horizontalAlignment: Text.AlignHCenter; visible: Boolean(text); text: root.track.album || ""; color: themeState.secondary }
        }
    }
    IconButton { id: closeButton; objectName: "closeExpandedPlayer"; x: 16; y: 12; iconName: "down"; tip: "Return to Browsing"; onClicked: root.closeRequested() }
}
