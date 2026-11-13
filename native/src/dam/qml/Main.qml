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
    onClosing: function(close) { close.accepted = appState.canClose() }
    color: themeState.background
    palette.window: themeState.background
    palette.windowText: themeState.foreground
    palette.text: themeState.foreground
    palette.buttonText: themeState.foreground
    palette.base: themeState.surface
    palette.highlight: themeState.accent
    palette.highlightedText: themeState.onAccent
    property bool showQueue: true
    property bool navigationOpen: true
    property string confirmOperation: ""
    property var confirmPayload: ({})
    property string confirmTitle: ""
    property string confirmMessage: ""

    function confirm(operation, payload, title, message) {
        confirmOperation = operation; confirmPayload = payload
        confirmTitle = title; confirmMessage = message; confirmation.open()
    }

    FolderDialog { id: musicFolder; title: "Choose your Music folder"; onAccepted: appState.setMusicFolder(selectedFolder) }
    FolderDialog { id: deviceFolder; title: "Choose a device or its Music folder"; onAccepted: appState.setDevice(selectedFolder) }
    FileDialog { id: sessionFile; title: "Import YouTube Music browser.json"; nameFilters: ["Session export (*.json)"]; onAccepted: account.importFile(selectedFile) }

    Dialog {
        id: confirmation
        anchors.centerIn: parent
        width: Math.min(480, window.width - 48)
        modal: true; focus: true
        title: window.confirmTitle
        standardButtons: Dialog.Cancel | Dialog.Ok
        background: Rectangle { color: themeState.surface; radius: 16; border.color: themeState.border }
        contentItem: AppText { text: window.confirmMessage; wrapMode: Text.WordWrap; elide: Text.ElideNone }
        onAccepted: appState.run(window.confirmOperation, window.confirmPayload)
    }

    ColumnLayout {
        anchors.fill: parent; spacing: 0
        RowLayout {
            Layout.fillWidth: true; Layout.preferredHeight: 76; spacing: 20
            ThemeActionButton { text: window.navigationOpen ? "Hide sidebar" : "Show sidebar"; flat: true; Layout.leftMargin: 16; onClicked: window.navigationOpen = !window.navigationOpen }
            ThemedTextField {
                id: search
                Layout.fillWidth: true; Layout.maximumWidth: 620
                placeholderText: "Search your library"
                Accessible.name: "Search your library"
                enabled: appState.view === "library" || appState.view === "downloads"
                onTextEdited: appState.search(text)
                Connections { target: appState; function onChanged() { if (appState.view !== "library" && appState.view !== "downloads") search.clear() } }
            }
            Item { Layout.fillWidth: true }
            ThemeActionButton { text: account.connected ? (account.profile.name || "Your account") : "Connect account"; Layout.rightMargin: 24; onClicked: appState.navigate("settings") }
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            ColumnLayout {
                visible: window.navigationOpen
                Layout.preferredWidth: window.width < 1100 ? 200 : 240
                Layout.minimumWidth: Layout.preferredWidth
                Layout.maximumWidth: Layout.preferredWidth
                Layout.fillHeight: true; spacing: 4
                AppText { text: "Digital Audio\nManager"; elide: Text.ElideNone; font.pixelSize: 23; font.bold: true; Layout.margins: 24; Layout.bottomMargin: 20 }
                Repeater {
                    model: [{key:"library", title:"Library", icon:"library"}, {key:"downloads", title:"Downloads", icon:"download"}, {key:"queue", title:"Queue", icon:"queue"}, {key:"device", title:"Devices", icon:"music"}]
                    NavButton { required property var modelData; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; text: modelData.title; symbol: modelData.icon; selected: appState.view === modelData.key; onClicked: { search.clear(); appState.navigate(modelData.key) } }
                }
                Rectangle { Layout.fillWidth: true; Layout.margins: 20; height: 1; color: themeState.border }
                RowLayout {
                    Layout.fillWidth: true; Layout.leftMargin: 24; Layout.rightMargin: 16
                    AppText { text: "YOUR PLAYLISTS"; color: themeState.secondary; font.pixelSize: 11; font.bold: true; Layout.fillWidth: true }
                    ThemeActionButton { text: "+"; Accessible.name: "Import a playlist"; flat: true; onClicked: appState.navigate("settings") }
                }
                ListView {
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.leftMargin: 12; Layout.rightMargin: 12
                    clip: true; model: appState.playlists; spacing: 2
                    ScrollBar.vertical: ScrollBar {}
                    delegate: NavButton { required property var modelData; width: ListView.view.width; text: modelData.title; symbol: "music"; selected: appState.collection.id === modelData.id; onClicked: { search.clear(); appState.selectCollection(modelData.id) } }
                }
                NavButton { text: "Settings"; symbol: "settings"; selected: appState.view === "settings"; Layout.fillWidth: true; Layout.margins: 12; onClicked: appState.navigate("settings") }
            }
            Rectangle { visible: window.navigationOpen; Layout.fillHeight: true; width: 1; color: themeState.border }
            ColumnLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
                Rectangle {
                    visible: Boolean(appState.error) || account.reconnect
                    Layout.fillWidth: true; Layout.preferredHeight: bannerRow.implicitHeight + 24
                    color: themeState.surface
                    RowLayout {
                        id: bannerRow; anchors.fill: parent; anchors.margins: 12
                        AppText { text: appState.error || account.message; color: themeState.error; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; Accessible.role: Accessible.AlertMessage }
                        ThemeActionButton { text: account.reconnect ? "Reconnect" : "Dismiss"; onClicked: account.reconnect ? appState.navigate("settings") : appState.dismissError() }
                    }
                }
                Loader {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    sourceComponent: appState.view === "settings" ? settingsPage : appState.view === "device" ? devicePage : appState.view === "queue" ? queuePage : libraryPage
                }
            }
            Rectangle { visible: window.showQueue && window.width >= 1220 && appState.view !== "queue" && appState.view !== "settings"; width: 1; Layout.fillHeight: true; color: themeState.border }
            QueuePane { visible: window.showQueue && window.width >= 1220 && appState.view !== "queue" && appState.view !== "settings"; Layout.minimumWidth: 280; Layout.maximumWidth: 280; Layout.preferredWidth: 280; Layout.fillHeight: true; compact: true }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 72
            color: themeState.surface
            RowLayout {
                anchors.fill: parent; anchors.margins: 16; spacing: 16
                Symbol { name: appState.queueRunning ? "download" : "check"; color: themeState.accent }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    AppText { text: appState.data.activity ? appState.data.activity.label : appState.busy ? "Working…" : appState.queueRunning ? "Downloading your music" : "Your music, ready to go"; font.bold: true }
                    AppText { text: appState.data.activity && appState.data.activity.total ? appState.data.activity.completed + " / " + appState.data.activity.total : (appState.data.health.library_root || "Loading your library…"); color: themeState.secondary; font.pixelSize: 12; Layout.fillWidth: true }
                }
                BusyIndicator { running: Boolean(appState.busy) || appState.queueRunning; visible: running; Layout.preferredWidth: 30; Layout.preferredHeight: 30 }
                ThemeActionButton { text: "Open folder"; onClicked: appState.openLibrary() }
                ThemeActionButton { text: "Queue · " + (appState.data.jobs || []).length; onClicked: { if (window.width >= 1220) window.showQueue = !window.showQueue; else appState.navigate("queue") } }
            }
        }
    }
    Component { id: libraryPage; LibraryPane { onRemoveCollection: function(id, title) { window.confirm("delete_library_collection", {playlist_id:id}, "Remove " + title + "?", "Remove this collection from your library? Downloaded audio and queued jobs are kept.") } } }
    Component { id: queuePage; QueuePane {} }
    Component { id: settingsPage; SettingsPane { onChooseMusic: musicFolder.open(); onImportSession: sessionFile.open(); onResetLibrary: window.confirm("reset_and_resync_library", {}, "Reset local library?", "Delete the current download folder, catalog and queue? Device exports and downloads in previously chosen folders are kept.") } }
    Component { id: devicePage; DevicePane { onChooseDevice: deviceFolder.open() } }
}
