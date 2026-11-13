import QtQuick
import QtQuick.Controls
import "components"
import "Theme.js" as Theme

Rectangle {
    id: root
    signal queueRequested()
    signal importRequested()
    signal expandRequested()
    property bool expanded: false
    function focusExpandToggle() { expandToggle.forceActiveFocus() }
    height: 92; radius: Theme.radiusMedium
    color: themeState.surface; border.color: themeState.border
    MouseArea { objectName: "playerBarBackground"; anchors.fill: parent; z: -2; enabled: playerState.hasTrack; cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: root.expandRequested() }
    ItemDelegate {
        objectName: "playerTrackToggle"
        x: 8; width: parent.width * 0.30 - 8; height: parent.height
        enabled: playerState.hasTrack
        Accessible.name: root.expanded ? "Return to Browsing" : "Open Immersive Player"
        background: Rectangle { radius: Theme.radiusMedium; color: "transparent"; border.width: parent.visualFocus ? 2 : 0; border.color: themeState.accent }
        onClicked: root.expandRequested()
    }
    Cover { x: 16; y: 12; width: 68; height: 68; artwork: playerState.track.artwork_url || "" }
    Column { x: 96; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.30 - 96; spacing: 5
        AppText { width: parent.width; text: playerState.track.title || "Nothing playing"; font.bold: true }
        AppText { width: parent.width; text: playerState.track.artist || "Choose a downloaded song"; color: themeState.secondary; font.pixelSize: 12 }
    }
    Item {
        anchors.horizontalCenter: parent.horizontalCenter; width: parent.width * 0.30; height: parent.height
        Row { anchors.horizontalCenter: parent.horizontalCenter; y: 7; spacing: 4
            IconButton { iconName: "previous"; tip: "Previous Song"; enabled: playerState.hasTrack; onClicked: playerState.previous() }
            IconButton {
                objectName: "playPauseButton"
                iconName: playerState.playing ? "pause" : "play"; tip: playerState.playing ? "Pause" : "Play"; iconColor: themeState.onAccent
                enabled: playerState.hasTrack
                background: Rectangle { radius: 22; color: parent.hovered ? themeState.accentHover : themeState.accent; opacity: parent.enabled ? 1 : 0.5; border.width: parent.visualFocus ? 2 : 0; border.color: themeState.foreground }
                onClicked: playerState.toggle()
            }
            IconButton { iconName: "next"; tip: "Next Song"; enabled: playerState.hasTrack; onClicked: playerState.next() }
        }
        AccentSlider { id: seek; objectName: "playbackSeek"; x: 0; y: 49; width: parent.width; height: 22; from: 0; to: Math.max(1, playerState.duration); value: playerState.position; enabled: playerState.hasTrack && playerState.duration > 0; Accessible.name: "Playback position"; onMoved: playerState.seek(value) }
        AppText { x: 4; y: 72; text: Theme.timeLabel(playerState.position); font.pixelSize: 11; color: themeState.secondary }
        AppText { anchors.right: parent.right; anchors.rightMargin: 4; y: 72; text: Theme.timeLabel(playerState.duration); font.pixelSize: 11; color: themeState.secondary }
    }
    Row {
        anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter; spacing: 2
        IconButton { iconName: "plus"; tip: "Import Music"; onClicked: root.importRequested() }
        IconButton { objectName: "runQueueButton"; iconName: "download"; tip: appState.queueRunning ? "Downloading" : appState.queuePauseReason ? "Resume Downloads" : "Downloads Start Automatically"; enabled: Boolean(appState.queuePauseReason) && !appState.busy && !appState.queueRunning && appState.hasQueuedDownloads; onClicked: appState.startQueue() }
        IconButton { objectName: "queueToggle"; iconName: "queue"; tip: "Download Queue"; onClicked: root.queueRequested() }
        IconButton { iconName: playerState.volume ? "volume" : "muted"; tip: playerState.volume ? "Mute" : "Unmute"; onClicked: playerState.setVolume(playerState.volume ? 0 : 0.7) }
        AccentSlider { anchors.verticalCenter: parent.verticalCenter; width: root.width < 1000 ? 60 : 80; height: 30; from: 0; to: 1; value: playerState.volume; Accessible.name: "Volume"; onMoved: playerState.setVolume(value) }
        IconButton { id: expandToggle; objectName: "immersiveToggle"; iconName: root.expanded ? "down" : "up"; tip: root.expanded ? "Return to Browsing" : "Open Immersive Player"; enabled: playerState.hasTrack; onClicked: root.expandRequested() }
    }
}
