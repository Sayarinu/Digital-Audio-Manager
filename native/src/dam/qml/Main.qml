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
            ThemeActionButton { Layout.fillWidth: true; flat: true; text: "Connection Settings"; onClicked: { importDialog.close(); accountDialog.open() } }
        }
    }
    SettingsDialog {
        id: settingsDialog
        currentPage: appearanceSettings
        sections: [{title:"General", pages:[appearanceSettings, downloadSettings]}, {title:"Library", pages:[importSettings]}, {title:"Support", pages:[maintenanceSettings]}]
    }
    SettingsPage { id: appearanceSettings; objectName: "appearance"; host: settingsDialog; title: "Appearance"; SettingsPane { anchors.fill: parent; section: "appearance" } }
    SettingsPage { id: downloadSettings; objectName: "downloads"; host: settingsDialog; title: "Downloads"; SettingsPane { anchors.fill: parent; section: "downloads"; onChooseMusic: musicFolder.open() } }
    SettingsPage { id: importSettings; objectName: "library"; host: settingsDialog; title: "Library"; SettingsPane { anchors.fill: parent; section: "library"; onConnectAccount: accountDialog.open(); onImportMusic: importDialog.open() } }
    SettingsPage { id: maintenanceSettings; objectName: "maintenance"; host: settingsDialog; title: "Troubleshooting"; SettingsPane { anchors.fill: parent; section: "maintenance"; onResetLibrary: window.confirm("reset_and_resync_library", {}, "Reset local library?", "Delete the current download folder, catalog and queue? Device exports and downloads in previously chosen folders are kept.") } }

    Rectangle {
        id: sidebar
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
        objectName: "mainHeader"
        anchors.left: sidebar.right; anchors.right: parent.right; anchors.rightMargin: queueDock.shown ? queueDock.width + 12 : 0
        height: 64
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: themeState.border }
        IconButton { x: header.width < 600 ? 8 : 40; y: 10; iconName: "back"; tip: "Back"; outlined: true; onClicked: appState.back() }
        ThemedTextField {
            id: search
            objectName: "searchField"
            x: header.width < 600 ? 60 : 96; y: 11
            width: Math.max(80, Math.min(480, settingsButton.x - x - 24)); height: 42
            leftPadding: 42; rightPadding: text.length ? 40 : 16; radius: Theme.radiusMedium
            font.pixelSize: 16; placeholderText: width < 300 ? "Search library" : "Search songs, albums, artists"
            Accessible.name: "Search library"
            enabled: appState.view === "library" || appState.view === "downloads"
            Symbol { x: 14; anchors.verticalCenter: parent.verticalCenter; name: "search"; width: 20; height: 20; color: themeState.secondary }
            IconButton { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: 36; height: 36; iconSize: 20; iconName: "close"; tip: "Clear Search"; visible: search.text.length > 0; onClicked: { search.clear(); appState.search(""); search.forceActiveFocus() } }
            onTextEdited: appState.search(text)
            Connections { target: appState; function onNavigationChanged() { search.text = appState.searchQuery } function onTracksChanged() { if (search.text !== appState.searchQuery) search.text = appState.searchQuery } }
        }
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
        anchors.left: sidebar.right; anchors.right: parent.right; anchors.rightMargin: queueDock.shown ? queueDock.width + 12 : 0
        anchors.top: header.bottom; anchors.bottom: statusBar.top
        Rectangle {
            id: banner
            width: parent.width; height: visible ? bannerRow.implicitHeight + 24 : 0
            visible: Boolean(appState.error) || account.reconnect
            color: themeState.surface
            RowLayout { id: bannerRow; anchors.fill: parent; anchors.margins: 12
                AppText { text: appState.error || account.message; color: themeState.error; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; Accessible.role: Accessible.AlertMessage }
                ThemeActionButton { text: account.reconnect ? "Reconnect" : "Dismiss"; onClicked: account.reconnect ? accountDialog.open() : appState.dismissError() }
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
            LibraryPane { anchors.fill: parent; visible: ["library", "downloads", "settings"].indexOf(appState.view) >= 0; onImportMusic: importDialog.open(); onRemoveCollection: (id, title) => window.confirm("delete_library_collection", {playlist_id:id}, "Remove " + title + "?", "Remove this collection from your library? Downloaded audio and queued jobs are kept.") }
            QueuePane { anchors.fill: parent; visible: appState.view === "queue" }
            DevicePane { anchors.fill: parent; visible: appState.view === "device"; onChooseDevice: deviceFolder.open() }
        }
    }
    DockPanel {
        id: queueDock
        anchors.right: parent.right; anchors.rightMargin: 12; anchors.top: parent.top; anchors.topMargin: 12; anchors.bottom: statusBar.top; anchors.bottomMargin: 12
        width: 300; radius: Theme.radiusLarge; color: themeState.surface; border.color: themeState.border
        shown: window.showQueue && window.width >= 1100 && appState.view !== "queue"
        QueuePane { anchors.fill: parent; compact: true; onCloseRequested: window.showQueue = false }
    }
    Rectangle {
        id: statusBar
        objectName: "statusBar"
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 12
        height: 92; radius: Theme.radiusMedium; color: themeState.surface; border.color: themeState.border
        Cover { x: 16; y: 12; width: 68; height: 68; symbol: appState.queueRunning ? "download" : "music" }
        Column { x: 96; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.30 - 96; spacing: 5
            AppText { width: parent.width; text: appState.data.activity ? appState.data.activity.label : appState.busy ? "Working…" : appState.queueRunning ? "Downloading your music" : "Your music"; font.bold: true }
            AppText { width: parent.width; text: appState.queueRunning ? "Download queue is running" : (appState.data.jobs || []).length + " tracks in queue"; color: themeState.secondary; font.pixelSize: 12 }
        }
        Column {
            anchors.centerIn: parent; spacing: 7
            IconButton {
                objectName: "runQueueButton"
                anchors.horizontalCenter: parent.horizontalCenter; iconName: "download"; tip: appState.queueRunning ? "Downloading" : "Run Download Queue"; iconColor: themeState.onAccent
                enabled: !appState.busy && !appState.queueRunning && (appState.data.jobs || []).length > 0
                background: Rectangle { radius: 22; color: parent.down || parent.hovered ? themeState.accentHover : themeState.accent; opacity: parent.enabled ? 1 : 0.5; border.width: parent.visualFocus ? 2 : 0; border.color: themeState.foreground }
                onClicked: appState.startQueue()
            }
            AppText { text: appState.queueRunning ? "Downloading…" : "Download queue"; color: themeState.secondary; font.pixelSize: 12 }
        }
        Row { anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter; spacing: 8
            BusyIndicator { width: 32; height: 44; running: Boolean(appState.busy) || appState.queueRunning; visible: running }
            IconButton { iconName: "folder"; tip: "Open Download Folder"; onClicked: appState.openLibrary() }
            IconButton { objectName: "queueToggle"; iconName: "queue"; tip: "Download Queue"; iconColor: window.showQueue || appState.view === "queue" ? themeState.accent : themeState.foreground; onClicked: { if (window.width >= 1100) window.showQueue = !window.showQueue; else appState.navigate("queue") } }
            IconButton { iconName: "device"; tip: "Devices"; onClicked: appState.navigate("device") }
        }
    }
    Shortcut { sequence: "Ctrl+F"; onActivated: search.forceActiveFocus() }
    Shortcut { sequence: "Alt+Left"; onActivated: appState.back() }
    Component.onCompleted: if (appState.view === "settings") settingsDialog.open()
}
