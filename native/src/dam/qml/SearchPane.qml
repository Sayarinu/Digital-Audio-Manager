import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "Theme.js" as Theme

Item {
    id: root
    objectName: "searchPane"
    property real gutter: Theme.gutter(width)
    ColumnLayout {
        anchors.fill: parent; anchors.margins: root.gutter; spacing: 16
        AppText { text: "Search results"; font.pixelSize: 28; font.bold: true }
        AppText { text: "Songs from YouTube Music • " + appState.remoteQuery; color: themeState.secondary; Layout.fillWidth: true }
        ListView {
            id: results
            objectName: "searchResults"
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true; reuseItems: true
            model: appState.searchModel
            WheelScroll { view: results }
            ScrollBar.vertical: ScrollBar {}
            delegate: ItemDelegate {
                id: song
                required property var modelData
                width: results.width; height: 64; padding: 8
                Accessible.name: modelData.title + ", " + modelData.artist
                background: Rectangle { radius: Theme.radiusSmall; color: song.hovered || song.visualFocus ? themeState.hover : "transparent"; border.width: song.visualFocus ? 2 : 0; border.color: themeState.accent }
                contentItem: RowLayout { spacing: 12
                    Cover { Layout.preferredWidth: 48; Layout.preferredHeight: 48; artwork: song.modelData.artwork_url || "" }
                    ColumnLayout { Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 4
                        AppText { text: song.modelData.title; Layout.fillWidth: true }
                        AppText { text: song.modelData.artist + (song.modelData.album ? " • " + song.modelData.album : ""); color: themeState.secondary; font.pixelSize: 13; Layout.fillWidth: true }
                    }
                    AppText { text: song.modelData.duration; color: themeState.secondary; font.pixelSize: 13 }
                    IconButton { iconName: "play"; tip: "Play Download"; enabled: song.modelData.local_status === "ready"; onClicked: appState.playSearchTrack(song.modelData.video_id) }
                    IconButton {
                        iconName: song.modelData.local_status === "ready" ? "check" : "download"
                        tip: song.modelData.local_status === "ready" ? "Downloaded" : ["queued", "downloading"].indexOf(song.modelData.local_status) >= 0 ? "Queued" : "Download Song"
                        enabled: !appState.busy && ["ready", "queued", "downloading"].indexOf(song.modelData.local_status) < 0
                        disabledIconColor: themeState.accent
                        onClicked: appState.queueSearchTrack(song.modelData.video_id)
                    }
                }
                onClicked: if (modelData.local_status === "ready") appState.playSearchTrack(modelData.video_id)
            }
        }
    }
    Column {
        anchors.centerIn: parent; width: Math.min(400, parent.width - 64); spacing: 16
        visible: appState.searching || Boolean(appState.searchError) || results.count === 0
        BusyIndicator { anchors.horizontalCenter: parent.horizontalCenter; visible: appState.searching; running: visible }
        AppText { width: parent.width; text: appState.searching ? "Searching YouTube Music…" : appState.searchError || "No songs found. Try another title or artist."; color: themeState.secondary; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideNone }
        ThemeActionButton { anchors.horizontalCenter: parent.horizontalCenter; visible: Boolean(appState.searchError); text: "Retry"; onClicked: appState.searchMusic(appState.remoteQuery) }
    }
}
