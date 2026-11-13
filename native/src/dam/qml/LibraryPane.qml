import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "Theme.js" as Theme

ColumnLayout {
    id: root
    signal removeCollection(string identifier, string title)
    spacing: 16
    readonly property var collection: appState.collection
    readonly property var rows: appState.tracks
    readonly property bool hasCollection: Boolean(collection.id)
    readonly property bool downloads: appState.view === "downloads"

    RowLayout {
        Layout.fillWidth: true; Layout.leftMargin: 24; Layout.rightMargin: 24; Layout.topMargin: 28; spacing: 22
        Cover { Layout.preferredWidth: root.hasCollection ? 128 : 72; Layout.preferredHeight: width; artwork: root.hasCollection && root.rows.length ? (root.rows[0].artwork_url || "") : ""; symbol: root.downloads ? "download" : "library" }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 8
            AppText { text: root.hasCollection ? "PLAYLIST" : "YOUR MUSIC"; font.pixelSize: 11; font.bold: true; color: themeState.secondary }
            AppText { text: root.hasCollection ? root.collection.title : root.downloads ? "Downloads" : "Library"; font.pixelSize: 30; font.bold: true; Layout.fillWidth: true }
            AppText { text: root.rows.length + " tracks" + (root.hasCollection ? " · " + root.collection.source : " · On your terms"); color: themeState.secondary; Layout.fillWidth: true }
        }
    }
    RowLayout {
        Layout.fillWidth: true; Layout.leftMargin: 24; Layout.rightMargin: 24; spacing: 8
        ThemeActionButton { visible: root.hasCollection; text: "Add missing to queue"; primary: true; enabled: !appState.busy; onClicked: appState.run("queue_playlist", {playlist_id:root.collection.id, missing_only:true}) }
        ThemeActionButton { visible: !root.hasCollection; text: "Import music"; primary: true; onClicked: appState.navigate("settings") }
        ThemeActionButton { text: "Run queue"; enabled: !appState.busy && !appState.queueRunning && (appState.data.jobs || []).length > 0; onClicked: appState.startQueue() }
        Item { Layout.fillWidth: true }
        ThemeActionButton { text: "Refresh"; enabled: !appState.busy; flat: true; onClicked: appState.refresh() }
        ThemeActionButton { visible: root.hasCollection && root.collection.kind !== "unsorted"; text: "Remove"; enabled: !appState.busy; flat: true; onClicked: root.removeCollection(root.collection.id, root.collection.title) }
    }
    ListView {
        visible: !root.hasCollection && !root.downloads && appState.playlists.length > 0
        Layout.fillWidth: true; Layout.preferredHeight: 126; Layout.leftMargin: 24; Layout.rightMargin: 24
        orientation: ListView.Horizontal; clip: true; spacing: 12; model: appState.playlists
        ScrollBar.horizontal: ScrollBar {}
        delegate: Button {
            id: card
            required property var modelData
            width: 200; height: 112; padding: 16
            Accessible.name: modelData.title + ", " + modelData.track_count + " tracks"
            background: Rectangle { radius: 12; color: card.hovered ? themeState.hover : themeState.surface; border.width: card.visualFocus ? 2 : 0; border.color: themeState.accent }
            contentItem: ColumnLayout { spacing: 8; Symbol { name: "music"; color: themeState.accent } AppText { text: card.modelData.title; font.bold: true; Layout.fillWidth: true } AppText { text: card.modelData.track_count + " tracks"; color: themeState.secondary; font.pixelSize: 12 } }
            onClicked: appState.selectCollection(modelData.id)
        }
    }
    RowLayout {
        Layout.fillWidth: true; Layout.leftMargin: 40; Layout.rightMargin: 40
        AppText { text: "TITLE"; color: themeState.secondary; font.pixelSize: 11; Layout.fillWidth: true }
        AppText { text: "STATUS"; color: themeState.secondary; font.pixelSize: 11; Layout.preferredWidth: 120 }
        AppText { text: "TIME"; color: themeState.secondary; font.pixelSize: 11; Layout.preferredWidth: 50 }
        Item { Layout.preferredWidth: 86 }
    }
    Rectangle { Layout.fillWidth: true; Layout.leftMargin: 24; Layout.rightMargin: 24; height: 1; color: themeState.border }
    ListView {
        id: trackList
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.leftMargin: 24; Layout.rightMargin: 24
        clip: true; reuseItems: true; model: root.rows; spacing: 2
        ScrollBar.vertical: ScrollBar {}
        delegate: ItemDelegate {
            id: row
            required property int index
            required property var modelData
            width: ListView.view.width; height: 64; leftPadding: 12; rightPadding: 12
            Accessible.name: modelData.title + ", " + modelData.artist + ", " + modelData.local_status
            background: Rectangle { radius: 8; color: row.hovered || row.visualFocus ? themeState.hover : "transparent"; border.width: row.visualFocus ? 2 : 0; border.color: themeState.accent }
            contentItem: RowLayout {
                spacing: 12
                Cover { Layout.preferredWidth: 44; Layout.preferredHeight: 44; artwork: row.modelData.artwork_url || "" }
                ColumnLayout { Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 4; AppText { objectName: "trackTitle"; text: row.modelData.title; Layout.fillWidth: true } AppText { text: row.modelData.artist; color: themeState.secondary; font.pixelSize: 12; Layout.fillWidth: true } }
                AppText { text: row.modelData.local_status === "ready" ? "Downloaded" : row.modelData.local_status; color: row.modelData.local_status === "ready" ? themeState.accent : themeState.secondary; font.pixelSize: 12; Layout.preferredWidth: 120 }
                AppText { text: row.modelData.duration || "—"; color: themeState.secondary; font.pixelSize: 12; Layout.preferredWidth: 50 }
                ThemeActionButton { text: row.modelData.local_status === "ready" ? "Open" : "Queue"; Layout.preferredWidth: 86; enabled: !appState.busy && row.modelData.local_status !== "unavailable"; onClicked: row.modelData.local_status === "ready" ? appState.openTrack(row.modelData.id) : appState.run("queue_track", {video_id:row.modelData.video_id}) }
            }
            onClicked: trackList.currentIndex = index
        }
        ColumnLayout {
            visible: root.rows.length === 0
            anchors.centerIn: parent; width: Math.min(360, parent.width - 32); spacing: 14
            Symbol { name: root.downloads ? "download" : "music"; Layout.alignment: Qt.AlignHCenter; width: 40; height: 40; color: themeState.secondary }
            AppText { text: root.downloads ? "No downloads yet" : "Make room for your music"; font.pixelSize: 22; font.bold: true; Layout.alignment: Qt.AlignHCenter }
            AppText { text: root.downloads ? "Queue a track or playlist to keep it on this device." : "Connect YouTube Music or import a public playlist to get started. If you’re searching, try another title or artist."; color: themeState.secondary; wrapMode: Text.WordWrap; elide: Text.ElideNone; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
            ThemeActionButton { text: "Import music"; primary: true; Layout.alignment: Qt.AlignHCenter; onClicked: appState.navigate("settings") }
        }
    }
}
