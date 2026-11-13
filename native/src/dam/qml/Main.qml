import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "components"
import "Theme.js" as Theme

ApplicationWindow {
    id: window
    visible: true
    title: "Digital Audio Manager"
    width: 1280; height: 820
    minimumWidth: 920; minimumHeight: 620
    onClosing: event => event.accepted = appState.canClose()
    color: themeState.background
    palette.window: themeState.background
    palette.windowText: themeState.foreground
    palette.text: themeState.foreground
    palette.buttonText: themeState.foreground
    palette.base: themeState.surface
    palette.highlight: themeState.accent
    palette.highlightedText: themeState.onAccent
    property bool showQueue: false
    property bool expanded: false
    property var browseFocus: null
    function setExpanded(value) {
        if (value && !playerState.hasTrack || expanded === value) return
        if (value) browseFocus = activeFocusItem
        expanded = value
        Qt.callLater(function() {
            if (window.expanded) immersive.focusStage()
            else if (window.browseFocus && window.browseFocus.visible && window.browseFocus.enabled) window.browseFocus.forceActiveFocus()
            else statusBar.focusExpandToggle()
        })
    }
    Connections { target: playerState; function onChanged() { if (!playerState.hasTrack) window.setExpanded(false) } }
    property real sidebarWidth: 240
    property string confirmOperation: ""
    property var confirmPayload: ({})
    property string confirmMessage: ""
    function confirm(operation, payload, title, message) {
        confirmOperation = operation; confirmPayload = payload
        confirmation.title = title; confirmMessage = message; confirmation.open()
    }
    function openSettings() { settingsDialog.open() }
    function openAccount() { accountDialog.open() }
    function openImport() { importDialog.open() }
    FolderDialog { id: musicFolder; title: "Choose your Music folder"; onAccepted: appState.setMusicFolder(selectedFolder) }
    FolderDialog { id: deviceFolder; title: "Choose a device or its Music folder"; onAccepted: appState.setDevice(selectedFolder) }
    FileDialog { id: localFiles; title: "Add Local Music"; fileMode: FileDialog.OpenFiles; nameFilters: ["Audio files (*.mp3 *.m4a *.flac *.ogg *.opus *.wav *.aac *.wma *.aiff *.aif)", "All files (*)"]; onAccepted: appState.importFiles(selectedFiles) }
    FolderDialog { id: localFolder; title: "Add a Music Folder"; onAccepted: appState.importFiles([selectedFolder]) }
    AccountDialog { id: accountDialog }
    ThemedDialog {
        id: confirmation
        width: Math.min(480, window.width - 48)
        contentItem: ColumnLayout {
            spacing: 20
            AppText { text: window.confirmMessage; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone }
            RowLayout { Layout.alignment: Qt.AlignRight
                ThemeActionButton { text: "Cancel"; onClicked: confirmation.reject() }
                ThemeActionButton { text: "Confirm"; primary: true; onClicked: { appState.run(window.confirmOperation, window.confirmPayload); confirmation.accept() } }
            }
        }
    }
    ThemedDialog {
        id: importDialog
        objectName: "importDialog"
        title: "Import Music"
        width: Math.min(520, window.width - 64)
        contentItem: ColumnLayout {
            spacing: 14
            AppText { text: "Add a public YouTube Music playlist or album."; color: themeState.secondary; Layout.fillWidth: true; wrapMode: Text.Wrap }
            ThemedTextField { id: importUrl; Layout.fillWidth: true; placeholderText: "Playlist or album URL"; Accessible.name: placeholderText; onAccepted: if (importButton.enabled) importButton.clicked() }
            ThemeActionButton { id: importButton; Layout.fillWidth: true; text: "Import & queue"; primary: true; enabled: Boolean(importUrl.text.trim()) && !appState.busy; onClicked: { appState.run("import_to_unsorted", {url:importUrl.text}); importDialog.close() } }
            ThemeActionButton { Layout.fillWidth: true; text: "Sync my YouTube Music playlists"; enabled: account.connected && !account.busy && !appState.busy; onClicked: { appState.run("import_account_library", {}); importDialog.close() } }
            ThemeActionButton { Layout.fillWidth: true; text: "Add Local Audio Files"; enabled: !appState.busy; onClicked: { importDialog.close(); localFiles.open() } }
            ThemeActionButton { Layout.fillWidth: true; text: "Add Music Folder"; enabled: !appState.busy; onClicked: { importDialog.close(); localFolder.open() } }
            ThemeActionButton { Layout.fillWidth: true; flat: true; text: "Connection Settings"; onClicked: { importDialog.close(); accountDialog.open() } }
        }
    }
    SettingsDialog {
        id: settingsDialog
        currentPage: appearanceSettings
        sections: [{title:"General", pages:[appearanceSettings, downloadSettings]}, {title:"Library", pages:[importSettings]}, {title:"Support", pages:[updateSettings, maintenanceSettings]}]
    }
    UpdateSettings { id: updateSettings; host: settingsDialog }
    UpdateDialog { id: updateDialog }
    AppearanceSettings { id: appearanceSettings; host: settingsDialog; dialogParent: window.contentItem }
    SettingsPage { id: downloadSettings; objectName: "downloads"; host: settingsDialog; title: "Downloads"; SettingsPane { anchors.fill: parent; section: "downloads"; onChooseMusic: musicFolder.open() } }
    SettingsPage { id: importSettings; objectName: "library"; host: settingsDialog; title: "Library"; SettingsPane { anchors.fill: parent; section: "library"; onConnectAccount: accountDialog.open(); onImportMusic: importDialog.open() } }
    SettingsPage { id: maintenanceSettings; objectName: "maintenance"; host: settingsDialog; title: "Troubleshooting"; SettingsPane { anchors.fill: parent; section: "maintenance"; onResetLibrary: window.confirm("reset_and_resync_library", {}, "Reset local library?", "Delete the current download folder, catalog and queue? Imported local files, device exports and downloads in previously chosen folders are kept.") } }

    Rectangle {
        id: sidebar
        enabled: !window.expanded
        objectName: "navigationRail"
        width: Math.min(window.sidebarWidth, window.width - (queueDock.shown ? 780 : 480))
        anchors.top: parent.top; anchors.bottom: statusBar.top
        color: themeState.background
        readonly property bool wide: width >= 180
        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: themeState.border }
        Column {
            id: navigation
            x: 8; y: 8; width: parent.width - 16
            Repeater {
                model: [{key:"library",label:"Library",icon:"library"},{key:"downloads",label:"Downloads",icon:"download"},{key:"queue",label:"Queue",icon:"queue"},{key:"device",label:"Devices",icon:"device"}]
                NavButton { required property var modelData; width: navigation.width; text: modelData.label; symbol: modelData.icon; wide: sidebar.wide; selected: appState.view === modelData.key && !appState.collection.id; onClicked: appState.navigate(modelData.key) }
            }
        }
        Rectangle { x: 8; y: navigation.y + navigation.height + 12; width: parent.width - 16; height: 1; color: themeState.border }
        ThemeActionButton { id: newPlaylist; x: 8; y: navigation.y + navigation.height + 24; width: parent.width - 16; height: 40; text: sidebar.wide ? "+  Import Music" : "+"; Accessible.name: "Import Music"; onClicked: importDialog.open() }
        ListView {
            id: sidebarPlaylists
            objectName: "sidebarPlaylists"
            x: 8; width: parent.width - 16
            anchors.top: newPlaylist.bottom; anchors.topMargin: 12; anchors.bottom: parent.bottom
            clip: true; reuseItems: true; model: appState.playlistModel
            WheelScroll { view: sidebarPlaylists }
            ScrollBar.vertical: ScrollBar {}
            delegate: ItemDelegate {
                id: playlist
                required property var modelData
                width: ListView.view.width; height: 56; padding: 0
                Accessible.name: modelData.title
                ToolTip.text: modelData.title; ToolTip.visible: hovered && !sidebar.wide; ToolTip.delay: 600
                background: Rectangle { radius: Theme.radiusSmall; color: playlist.hovered || appState.collection.id === playlist.modelData.id ? themeState.hover : "transparent"; border.color: playlist.visualFocus ? themeState.accent : "transparent" }
                contentItem: Item {
                    Cover { x: 8; anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40; artwork: playlist.modelData.artwork_url || "" }
                    Column { x: 60; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 72; spacing: 4; visible: sidebar.wide
                        AppText { width: parent.width; text: playlist.modelData.title }
                        AppText { width: parent.width; text: playlist.modelData.track_count + " tracks"; color: themeState.secondary; font.pixelSize: 12 }
                    }
                }
                onClicked: appState.selectCollection(modelData.id)
            }
        }
        MouseArea {
            anchors.right: parent.right; width: 8; height: parent.height; cursorShape: Qt.SizeHorCursor; preventStealing: true
            property real startX: 0
            property real startWidth: 0
            onPressed: mouse => { startX = mapToItem(null, mouse.x, mouse.y).x; startWidth = sidebar.width }
            onPositionChanged: mouse => { if (pressed) window.sidebarWidth = Math.max(80, Math.min(320, startWidth + mapToItem(null, mouse.x, mouse.y).x - startX)) }
        }
    }
    Item {
        id: header
        enabled: !window.expanded
        objectName: "mainHeader"
        anchors.left: sidebar.right; anchors.right: parent.right; anchors.rightMargin: queueDock.shown ? queueDock.width + 12 : 0
        height: 64
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: themeState.border }
        IconButton { x: header.width < 600 ? 8 : 40; y: 10; iconName: "back"; tip: "Back"; outlined: true; onClicked: appState.back() }
        ThemedTextField {
            id: search
            objectName: "searchField"
            x: header.width < 600 ? 60 : 96; y: 11
            width: Math.max(80, Math.min(480, (updateButton.visible ? updateButton.x : settingsButton.x) - x - 24)); height: 42
            leftPadding: 42; rightPadding: text.length ? 40 : 16; radius: Theme.radiusMedium
            font.pixelSize: 16; placeholderText: width < 300 ? "Search YouTube Music" : "Search YouTube Music · press Enter"
            Accessible.name: "Search YouTube Music"
            enabled: true
            Symbol { x: 14; anchors.verticalCenter: parent.verticalCenter; name: "search"; width: 20; height: 20; color: themeState.secondary }
            IconButton { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: 36; height: 36; iconSize: 20; iconName: "close"; tip: "Clear Search"; visible: search.text.length > 0; onClicked: { search.clear(); appState.search(""); search.forceActiveFocus() } }
            onTextEdited: if (appState.view !== "search") appState.search(text)
            onAccepted: appState.searchMusic(text)
            Connections { target: appState; function onNavigationChanged() { search.text = appState.view === "search" ? appState.remoteQuery : appState.searchQuery } function onSearchChanged() { if (appState.view === "search") search.text = appState.remoteQuery } function onTracksChanged() { if (appState.view !== "search" && search.text !== appState.searchQuery) search.text = appState.searchQuery } }
        }
        IconButton { id: updateButton; objectName: "updateButton"; anchors.right: settingsButton.left; anchors.rightMargin: 12; y: 10; iconName: "update"; iconColor: themeState.accent; tip: maintenanceState.latestName || "Update Available"; visible: maintenanceState.updateAvailable || maintenanceState.downloading; onClicked: updateDialog.open() }
        IconButton { id: settingsButton; objectName: "settingsButton"; anchors.right: profileButton.left; anchors.rightMargin: 12; y: 10; iconName: "settings"; tip: "Settings"; onClicked: settingsDialog.open() }
        IconButton {
            id: profileButton
            objectName: "profileButton"
            anchors.right: parent.right; anchors.rightMargin: header.width < 600 ? 8 : 32; y: 10
            tip: account.connected ? account.profile.name : "Account"
            onClicked: account.connected ? accountMenu.popup(profileButton, profileButton.width - accountMenu.implicitWidth, profileButton.height, null) : accountDialog.open()
            contentItem: Item { Cover { anchors.centerIn: parent; width: 28; height: 28; radius: 14; symbol: "profile"; artwork: account.profile.avatar || "" } }
        }
        ThemedMenu {
            id: accountMenu; objectName: "accountMenu"; implicitWidth: 252
            ContextMenuItem { text: account.profile.name || "YouTube Music Account"; enabled: false }
            ThemedMenuSeparator {}
            ContextMenuItem { text: "Connection Settings"; onTriggered: accountDialog.open() }
            ThemedMenuSeparator {}
            ContextMenuItem { text: "Sign Out"; enabled: !appState.busy && !appState.queueRunning; onTriggered: account.signOut() }
        }
    }
    Item {
        id: pageArea
        enabled: !window.expanded
        anchors.left: sidebar.right; anchors.right: parent.right; anchors.rightMargin: queueDock.shown ? queueDock.width + 12 : 0
        anchors.top: header.bottom; anchors.bottom: statusBar.top
        Rectangle {
            id: banner
            width: parent.width; height: visible ? bannerRow.implicitHeight + 24 : 0
            visible: Boolean(appState.error) || Boolean(playerState.message) || account.reconnect
            color: themeState.surface
            RowLayout { id: bannerRow; anchors.fill: parent; anchors.margins: 12
                AppText { text: appState.error || playerState.message || account.message; color: themeState.error; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; Accessible.role: Accessible.AlertMessage }
                ThemeActionButton { text: account.reconnect ? "Reconnect" : "Dismiss"; onClicked: account.reconnect ? accountDialog.open() : playerState.message ? playerState.dismissMessage() : appState.dismissError() }
            }
        }
        Item {
            id: pages
            anchors.top: banner.bottom; anchors.bottom: parent.bottom; width: parent.width
            transform: Translate { id: pageShift }
            function enter() {
                if (appState.reducedMotion) { pageEnter.stop(); opacity = 1; pageShift.y = 0; return }
                pageEnter.restart()
            }
            ParallelAnimation {
                id: pageEnter
                NumberAnimation { target: pages; property: "opacity"; from: 0; to: 1; duration: Theme.motionMedium; easing.type: Easing.OutCubic }
                NumberAnimation { target: pageShift; property: "y"; from: 12; to: 0; duration: Theme.motionSlow; easing.type: Easing.OutCubic }
            }
            Connections { target: appState; function onNavigationChanged() { if (appState.view === "settings") settingsDialog.open(); else pages.enter() } }
            // Keep the library viewport alive when opening another page or a popup.
            LibraryPane { anchors.fill: parent; visible: ["library", "downloads", "settings"].indexOf(appState.view) >= 0; onImportMusic: importDialog.open(); onRemoveDownload: (id, title) => window.confirm("remove_download", {video_id:id}, "Remove download?", "Delete the downloaded file and cover for “" + title + "” from this device? The song stays in your library so you can download it again."); onRemoveCollection: (id, title) => window.confirm("delete_library_collection", {collection_id:id}, "Remove " + title + "?", "Remove this collection from your library? Downloaded audio and queued jobs are kept.") }
            SearchPane { anchors.fill: parent; visible: appState.view === "search" }
            QueuePane { anchors.fill: parent; visible: appState.view === "queue" }
            DevicePane { anchors.fill: parent; visible: appState.view === "device"; onChooseDevice: deviceFolder.open() }
        }
    }
    ExpandedPlayer {
        id: immersive
        width: window.width; height: statusBar.y; z: 2
        rightInset: queueDock.shown ? queueDock.width + 24 : 0
        slidingInset: (queueDock.width + 24) * queueDock.revealed
        property real slide: window.expanded ? 0 : 1
        visible: window.expanded || immersiveSlide.running
        enabled: window.expanded
        transform: Translate { y: immersive.slide * immersive.height }
        Behavior on slide { NumberAnimation { id: immersiveSlide; duration: Theme.duration(Theme.motionSlow, appState.reducedMotion); easing.type: window.expanded ? Easing.OutCubic : Easing.InCubic } }
        onCloseRequested: window.setExpanded(false)
    }
    DockPanel {
        id: queueDock
        z: 3
        anchors.right: parent.right; anchors.rightMargin: 12; anchors.top: parent.top; anchors.topMargin: 12; anchors.bottom: statusBar.top; anchors.bottomMargin: 12
        width: 300; radius: Theme.radiusLarge; color: themeState.surface; border.color: themeState.border
        shown: window.showQueue && window.width >= 1100 && appState.view !== "queue"
        QueuePane { anchors.fill: parent; compact: true; onCloseRequested: window.showQueue = false }
    }
    PlayerBar {
        id: statusBar
        z: 4
        expanded: window.expanded
        onExpandRequested: window.setExpanded(!window.expanded)
        objectName: "statusBar"
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 12
        onImportRequested: { window.setExpanded(false); importDialog.open() }
        onQueueRequested: { if (window.width >= 1100) window.showQueue = !window.showQueue; else { window.setExpanded(false); appState.navigate("queue") } }
    }
    Rectangle {
        z: 5
        anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: statusBar.top; anchors.bottomMargin: 16
        width: Math.min(540, window.width - 80); height: activityRow.implicitHeight + 20
        radius: Theme.radiusSmall; color: themeState.hover; visible: Boolean(appState.busy) || appState.queueRunning
        RowLayout { id: activityRow; anchors.fill: parent; anchors.margins: 10; spacing: 12
            BusyIndicator { running: parent.parent.visible; Layout.preferredWidth: 24; Layout.preferredHeight: 24 }
            AppText { Layout.fillWidth: true; text: appState.data.activity ? appState.data.activity.label + (appState.data.activity.total ? " • " + appState.data.activity.completed + " / " + appState.data.activity.total : "") : appState.queueRunning ? "Downloading your music…" : "Working…" }
        }
    }
    Shortcut { sequence: "Ctrl+F"; onActivated: { window.setExpanded(false); search.forceActiveFocus() } }
    Shortcut { sequence: "Alt+Left"; onActivated: window.expanded ? window.setExpanded(false) : appState.back() }
    Shortcut { sequence: "Escape"; enabled: window.expanded; onActivated: window.setExpanded(false) }
    Component.onCompleted: if (appState.view === "settings") settingsDialog.open()
}
