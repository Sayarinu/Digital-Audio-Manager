import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "Theme.js" as Theme

Item {
    id: root
    objectName: "libraryPane"
    signal importMusic()
    signal removeCollection(string id, string title)
    signal removeDownload(string id, string title)
    property var collection: appState.collection
    readonly property bool hasCollection: Boolean(collection.id)
    readonly property bool downloads: appState.view === "downloads"
    property bool songsSelected: false
    readonly property bool rows: hasCollection || downloads || songsSelected || appState.searchQuery.length > 0
    property real gutter: Theme.gutter(width)
    property var menuTrack: ({})
    property var menuCollection: ({})
    function collectionMenu(item, button) { menuCollection = item; collectionOptions.popup(button, 0, button.height, null) }
    Component {
        id: controls
        Item {
            width: parent.width
            height: 158
            Row {
                height: 52; spacing: 24
                Repeater { model: ["Library", "Downloads"]
                    Button {
                        id: tab; required property string modelData
                        text: modelData; flat: true; height: 52
                        palette.windowText: root.downloads === (modelData === "Downloads") ? themeState.foreground : themeState.secondary
                        onClicked: appState.navigate(modelData.toLowerCase())
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: themeState.accent; visible: root.downloads === (tab.modelData === "Downloads") }
                    }
                }
            }
            Rectangle { y: 52; height: 1; width: parent.width; color: themeState.border }
            Row { y: 84; spacing: 12
                FilterChip { text: root.downloads ? "Songs" : "Playlists"; selected: root.downloads || !root.rows; onClicked: { root.songsSelected = false; appState.search("") } }
                FilterChip { text: "Songs"; visible: !root.downloads; selected: root.songsSelected || appState.searchQuery.length > 0; onClicked: root.songsSelected = true }
            }
            IconButton { x: parent.width - width; y: 80; iconName: "more"; tip: "Library Options"; onClicked: libraryOptions.popup(this, width - libraryOptions.implicitWidth, height, null) }
        }
    }
    GridView {
        id: grid
        objectName: "libraryGrid"
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.gutter
        visible: !root.rows; clip: true; reuseItems: true; cacheBuffer: 0; bottomMargin: 32
        property int columns: Math.max(1, Math.floor((width + 24) / (Theme.cardWidth + 24)))
        cellWidth: width / columns; cellHeight: cellWidth + 84
        model: appState.playlistModel
        header: Loader { width: grid.width; height: 158; sourceComponent: controls }
        WheelScroll { view: grid }
        ScrollBar.vertical: ScrollBar {}
        delegate: ItemDelegate {
            id: card
            required property var modelData
            width: grid.cellWidth - 24; height: grid.cellHeight - 24; padding: 0
            Accessible.name: modelData.title + ", " + modelData.track_count + " tracks"
            background: Item {}
            contentItem: Item {
                Cover {
                    id: cover; width: parent.width; height: width; radius: Theme.radiusMedium
                    artwork: card.modelData.artwork_url || ""
                    Rectangle { anchors.fill: parent; anchors.margins: -4; radius: parent.radius + 4; color: "transparent"; border.width: 2; border.color: themeState.accent; visible: card.visualFocus }
                    IconButton { anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 6; width: 32; height: 32; iconSize: 20; iconName: "more"; tip: "Playlist Options"; visible: card.hovered || card.visualFocus || hovered; onClicked: root.collectionMenu(card.modelData, this) }
                    IconButton {
                        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 10
                        iconName: "download"; tip: "Queue Playlist"; iconColor: themeState.onAccent
                        opacity: card.hovered || card.visualFocus || hovered ? 1 : 0
                        enabled: opacity > 0 && !appState.busy
                        scale: opacity ? 1 : 0.85
                        Behavior on opacity { NumberAnimation { duration: Theme.duration(Theme.motionFast, appState.reducedMotion) } }
                        Behavior on scale { NumberAnimation { duration: Theme.duration(Theme.motionMedium, appState.reducedMotion); easing.type: Easing.OutBack } }
                        background: Rectangle { radius: 22; color: parent.hovered ? themeState.accentHover : themeState.accent }
                        onClicked: appState.run("queue_playlist", {playlist_id:card.modelData.id})
                    }
                }
                AppText { anchors.top: cover.bottom; anchors.topMargin: 10; width: parent.width; text: card.modelData.title; font.weight: Font.DemiBold }
                AppText { y: cover.height + 31; width: parent.width; text: "Playlist • " + card.modelData.track_count + " tracks"; color: themeState.secondary; font.pixelSize: 13 }
            }
            onClicked: appState.selectCollection(modelData.id)
        }
    }
    ListView {
        id: songs
        objectName: "librarySongs"
        anchors.fill: parent; anchors.leftMargin: root.gutter; anchors.rightMargin: root.gutter
        visible: root.rows; clip: true; reuseItems: true; cacheBuffer: 0; bottomMargin: 24
        model: appState.trackModel
        WheelScroll { view: songs }
        ScrollBar.vertical: ScrollBar {}
        header: Column {
            width: songs.width
            Loader { width: parent.width; height: root.hasCollection ? 0 : 158; active: !root.hasCollection; sourceComponent: controls }
            Item {
                visible: root.hasCollection; width: parent.width; height: visible ? 220 : 0
                Cover { id: heroCover; anchors.verticalCenter: parent.verticalCenter; width: parent.width < 600 ? 140 : 180; height: width; radius: Theme.radiusMedium; artwork: root.collection.artwork_url || "" }
                Column { anchors.left: heroCover.right; anchors.leftMargin: 28; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 12
                    AppText { width: parent.width; text: "PLAYLIST"; font.pixelSize: 12; color: themeState.secondary }
                    AppText { width: parent.width; text: root.collection.title || ""; font.pixelSize: root.width < 800 ? 28 : 36; font.bold: true; wrapMode: Text.Wrap; maximumLineCount: 2 }
                    AppText { width: parent.width; text: "Your music • " + (root.collection.track_count || 0) + " tracks"; color: themeState.secondary }
                }
            }
            Row {
                visible: root.hasCollection; height: visible ? 64 : 0; spacing: 12
                ThemeActionButton { anchors.verticalCenter: parent.verticalCenter; text: "Play"; primary: true; enabled: appState.hasPlayableTracks; onClicked: appState.playCollection() }
                ThemeActionButton { anchors.verticalCenter: parent.verticalCenter; text: "Download"; primary: true; visible: root.collection.source !== "Local files"; enabled: !appState.busy; onClicked: appState.run("queue_playlist", {playlist_id:root.collection.id}) }
                IconButton { anchors.verticalCenter: parent.verticalCenter; iconName: "more"; tip: "Playlist Options"; onClicked: root.collectionMenu(root.collection, this) }
            }
            Item {
                width: parent.width; height: 40
                AppText { x: 8; anchors.verticalCenter: parent.verticalCenter; text: "#"; color: themeState.secondary; font.pixelSize: 12 }
                AppText { x: 96; anchors.verticalCenter: parent.verticalCenter; text: "TITLE"; color: themeState.secondary; font.pixelSize: 12 }
                AppText { anchors.right: parent.right; anchors.rightMargin: 94; anchors.verticalCenter: parent.verticalCenter; text: "TIME"; color: themeState.secondary; font.pixelSize: 12 }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: themeState.border }
            }
        }
        delegate: ItemDelegate {
            id: row
            required property int index
            required property var modelData
            width: ListView.view.width; height: 64; padding: 0
            Accessible.name: modelData.title + ", " + modelData.artist + ", " + modelData.local_status
            background: Rectangle { radius: Theme.radiusSmall; color: row.hovered || row.visualFocus ? themeState.hover : "transparent"; border.width: row.visualFocus ? 2 : 0; border.color: themeState.accent }
            contentItem: Item {
                AppText { x: 8; width: 28; anchors.verticalCenter: parent.verticalCenter; text: row.index + 1; color: themeState.secondary; font.pixelSize: 13 }
                Cover { x: 44; anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40; artwork: row.modelData.artwork_url || "" }
                Column { x: 96; width: parent.width - 250; anchors.verticalCenter: parent.verticalCenter; spacing: 4
                    AppText { objectName: "trackTitle"; width: parent.width; text: row.modelData.title }
                    AppText { width: parent.width; text: row.modelData.artist; font.pixelSize: 13; color: themeState.secondary }
                }
                AppText { anchors.right: download.left; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: row.modelData.duration || "—"; color: themeState.secondary; font.pixelSize: 13 }
                IconButton {
                    id: download; anchors.right: more.left; anchors.verticalCenter: parent.verticalCenter; width: 36; height: 36; iconSize: 20
                    iconName: row.modelData.local_status === "ready" ? "check" : "download"
                    iconColor: ["ready", "queued", "downloading"].indexOf(row.modelData.local_status) >= 0 ? themeState.accent : themeState.foreground
                    disabledIconColor: iconColor
                    tip: String(row.modelData.video_id).indexOf("local:") === 0 ? "Local File" : row.modelData.local_status === "ready" ? "Downloaded" : row.modelData.local_status === "queued" ? "Queued" : row.modelData.local_status === "downloading" ? "Downloading" : "Download"
                    enabled: !appState.busy && String(row.modelData.video_id).indexOf("local:") !== 0 && ["ready", "unavailable", "queued", "downloading"].indexOf(row.modelData.local_status) < 0
                    onClicked: appState.run("queue_track", {video_id:row.modelData.video_id})
                }
                IconButton { id: more; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: 36; height: 36; iconSize: 20; iconName: "more"; tip: "Song Options"; onClicked: { root.menuTrack = row.modelData; trackOptions.popup(this, width - trackOptions.implicitWidth, height, null) } }
            }
            onClicked: { songs.currentIndex = index; if (modelData.local_status === "ready") appState.openTrack(modelData.id) }
        }
    }
    Column {
        visible: root.rows ? songs.count === 0 : grid.count === 0
        anchors.centerIn: parent; width: Math.min(380, parent.width - 80); spacing: 20
        AppText { width: parent.width; text: appState.busy ? "Loading your library…" : appState.searchQuery ? "No songs match your search." : root.downloads ? "Your downloaded music will appear here." : "Import a playlist or connect YouTube Music to build your library."; color: themeState.secondary; wrapMode: Text.Wrap; elide: Text.ElideNone; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 16 }
        ThemeActionButton { anchors.horizontalCenter: parent.horizontalCenter; text: "Import Music"; visible: !appState.busy && !appState.searchQuery; onClicked: root.importMusic() }
    }
    ThemedMenu { id: libraryOptions
        ContextMenuItem { text: "Import Music"; onTriggered: root.importMusic() }
        ContextMenuItem { text: "Open Download Folder"; onTriggered: appState.openLibrary() }
        ContextMenuItem { text: "Refresh"; enabled: !appState.busy; onTriggered: appState.refresh() }
    }
    ThemedMenu { id: collectionOptions
        ContextMenuItem { text: "Download Playlist"; enabled: !appState.busy && root.menuCollection.source !== "Local files"; onTriggered: appState.run("queue_playlist", {playlist_id:root.menuCollection.id}) }
        ContextMenuItem { text: "Refresh Library"; enabled: !appState.busy; onTriggered: appState.refresh() }
        ThemedMenuSeparator {}
        ContextMenuItem { text: "Remove from Library"; enabled: !appState.busy && root.menuCollection.kind !== "unsorted"; onTriggered: root.removeCollection(root.menuCollection.id, root.menuCollection.title) }
    }
    ThemedMenu { id: trackOptions
        ContextMenuItem { text: "Play"; enabled: root.menuTrack.local_status === "ready"; onTriggered: appState.openTrack(root.menuTrack.id) }
        ContextMenuItem { text: "Download"; enabled: !appState.busy && ["ready", "queued", "downloading", "unavailable"].indexOf(root.menuTrack.local_status) < 0 && String(root.menuTrack.video_id || "").indexOf("local:") !== 0; onTriggered: appState.run("queue_track", {video_id:root.menuTrack.video_id}) }
        ContextMenuItem { text: "Remove Download"; enabled: !appState.busy && !appState.queueRunning && Boolean(root.menuTrack.media_path) && String(root.menuTrack.video_id || "").indexOf("local:") !== 0; onTriggered: root.removeDownload(root.menuTrack.video_id, root.menuTrack.title) }
    }
    Connections { target: appState; function onNavigationChanged() { songs.positionViewAtBeginning() } }
}
