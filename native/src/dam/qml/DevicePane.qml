import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ColumnLayout {
    id: root
    signal chooseDevice()
    spacing: 16
    AppText { text: "Take your music with you"; font.pixelSize: 28; font.bold: true; Layout.margins: 24; Layout.bottomMargin: 0; Layout.fillWidth: true }
    AppText { text: "Choose a device or its Music folder. Exports live inside its own Digital Audio Manager folder."; wrapMode: Text.WordWrap; elide: Text.ElideNone; color: themeState.secondary; Layout.leftMargin: 24; Layout.rightMargin: 24; Layout.fillWidth: true }
    RowLayout {
        Layout.fillWidth: true; Layout.leftMargin: 24; Layout.rightMargin: 24
        AppText { text: appState.mountPath || "No device selected"; color: themeState.secondary; Layout.fillWidth: true }
        ThemeActionButton { text: "Choose device"; enabled: !appState.busy; onClicked: root.chooseDevice() }
        ThemeActionButton { text: "Preview"; enabled: Boolean(appState.mountPath) && !appState.busy && !appState.queueRunning; onClicked: appState.run("sync_preview", {mount_path:appState.mountPath}) }
    }
    AppText { text: "Collections to export"; font.pixelSize: 18; font.bold: true; Layout.leftMargin: 24 }
    ListView {
        id: collections
        WheelScroll { view: collections }
        Layout.fillHeight: true; Layout.fillWidth: true; Layout.leftMargin: 24; Layout.rightMargin: 24; clip: true
        model: appState.playlists.filter(function(p) { return p.kind !== "unsorted" })
        ScrollBar.vertical: ScrollBar {}
        delegate: CheckDelegate {
            id: collection
            required property var modelData
            width: ListView.view.width; height: 56
            text: modelData.title + " · " + modelData.track_count + " tracks"
            checked: Boolean(modelData.loaded); enabled: !appState.busy
            onToggled: appState.run("set_loaded_playlist", {playlist_id:modelData.id, loaded:checked})
            contentItem: AppText { text: collection.text; verticalAlignment: Text.AlignVCenter; rightPadding: 50 }
            background: Rectangle { color: collection.hovered ? themeState.hover : "transparent"; radius: 8; border.width: collection.visualFocus ? 2 : 0; border.color: themeState.accent }
        }
    }
    Rectangle {
        visible: appState.preview.physical_files_after !== undefined
        Layout.fillWidth: true; Layout.leftMargin: 24; Layout.rightMargin: 24; Layout.bottomMargin: 24
        implicitHeight: summary.implicitHeight + 32; color: themeState.surface; radius: 16
        ColumnLayout {
            id: summary; anchors.fill: parent; anchors.margins: 16; spacing: 10
            AppText { text: "Sync preview"; font.pixelSize: 18; font.bold: true }
            AppText { text: (appState.preview.files_to_copy || 0) + " to add · " + (appState.preview.files_to_remove || 0) + " to remove · " + (appState.preview.physical_files_after || 0) + " / 8,000 files"; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            AppText { text: (appState.preview.warnings || []).join("\n"); visible: Boolean(text); color: themeState.error; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; maximumLineCount: 4 }
            ThemeActionButton { text: "Sync device"; primary: true; enabled: !appState.busy && !appState.queueRunning && !(appState.preview.warnings || []).length; onClicked: appState.run("sync_apply", {mount_path:appState.mountPath}) }
        }
    }
    AppText { visible: appState.busy === "sync_apply"; text: "Syncing · " + (appState.syncProgress.completed || 0) + " / " + (appState.syncProgress.total || 0); Layout.margins: 24; color: themeState.accent }
}
