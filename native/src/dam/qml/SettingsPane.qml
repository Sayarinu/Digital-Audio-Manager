import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ScrollView {
    id: root
    property string section: "appearance"
    signal chooseMusic()
    signal connectAccount()
    signal importMusic()
    signal resetLibrary()
    clip: true
    contentWidth: availableWidth
    ColumnLayout {
        width: root.availableWidth; spacing: 20
        ColumnLayout {
            visible: root.section === "appearance"; Layout.fillWidth: true; spacing: 12
            AppText { text: "Theme"; font.bold: true }
            ThemedComboBox { Layout.fillWidth: true; Layout.maximumWidth: 360; model: themeState.themes; textRole: "name"; valueRole: "id"; currentIndex: { for (var i=0; i < count; ++i) { if (valueAt(i) === themeState.activeThemeId) return i } return 0 } onActivated: themeState.selectTheme(currentValue); Accessible.name: "Color theme" }
            SettingsCheckBox { text: "Reduce motion"; checked: appState.reducedMotion; onToggled: appState.setReducedMotion(checked) }
            AppText { text: "Turn off transitions and scrolling animations."; color: themeState.secondary; Layout.fillWidth: true; wrapMode: Text.Wrap }
        }
        ColumnLayout {
            visible: root.section === "downloads"; Layout.fillWidth: true; spacing: 12
            AppText { text: "Download folder"; font.bold: true }
            AppText { text: appState.data.health.library_root || "Loading…"; color: themeState.secondary; wrapMode: Text.WrapAnywhere; elide: Text.ElideNone; Layout.fillWidth: true }
            AppText { visible: appState.data.health.storage_available === false; text: "Reconnect this drive to download music, or choose another Music folder."; color: themeState.error; Layout.fillWidth: true; wrapMode: Text.Wrap }
            AppText { text: "New downloads go in Digital Audio Manager/Library inside your Music folder. Existing downloads stay in their current locations."; color: themeState.secondary; wrapMode: Text.Wrap; elide: Text.ElideNone; Layout.fillWidth: true }
            Flow { Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 8
                ThemeActionButton { text: "Choose Music Folder"; enabled: !appState.busy && !appState.queueRunning; onClicked: root.chooseMusic() }
                ThemeActionButton { text: "Open Folder"; onClicked: appState.openLibrary() }
            }
        }
        ColumnLayout {
            visible: root.section === "library"; Layout.fillWidth: true; spacing: 12
            AppText { text: "YouTube Music"; font.bold: true }
            AppText { text: account.connected ? "Connected as " + (account.profile.name || "your account") : "Connect your account or import a public playlist."; color: themeState.secondary; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Flow { Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: 8
                ThemeActionButton { text: "Connection Settings"; onClicked: root.connectAccount() }
                ThemeActionButton { text: "Import Music"; onClicked: root.importMusic() }
                ThemeActionButton { text: "Sync My Playlists"; enabled: account.connected && !account.busy && !appState.busy; onClicked: appState.run("import_account_library", {}) }
            }
            AppText { text: "Public profile"; font.bold: true; Layout.topMargin: 16 }
            ThemedTextField { id: profileUrl; Layout.fillWidth: true; text: appState.data.public_profile_url || ""; placeholderText: "YouTube channel or @handle URL"; Accessible.name: placeholderText }
            ThemeActionButton { text: "Sync Profile"; enabled: Boolean(profileUrl.text.trim()) && !appState.busy; onClicked: appState.run("import_public_profile", {url:profileUrl.text}) }
        }
        ColumnLayout {
            visible: root.section === "maintenance"; Layout.fillWidth: true; spacing: 12
            AppText { text: "Download tools"; font.bold: true }
            Repeater { model: Object.keys(appState.data.health.dependencies || {})
                RowLayout { required property string modelData; Layout.fillWidth: true
                    AppText { text: modelData; Layout.fillWidth: true }
                    AppText { text: appState.data.health.dependencies[modelData].available ? "Ready" : "Missing"; color: appState.data.health.dependencies[modelData].available ? themeState.secondary : themeState.error }
                }
            }
            Flow { Layout.fillWidth: true; spacing: 8; Layout.preferredHeight: childrenRect.height
                ThemeActionButton { text: "Set Up Tools"; enabled: !appState.busy && !appState.queueRunning; onClicked: appState.run("bootstrap_dependencies", {}) }
                ThemeActionButton { text: "Repair Metadata"; enabled: !appState.busy && !appState.queueRunning; onClicked: appState.run("repair_library_metadata", {}) }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border; Layout.topMargin: 12; Layout.bottomMargin: 12 }
            ThemeActionButton { text: "Reset Local Library"; enabled: !appState.busy && !appState.queueRunning; onClicked: root.resetLibrary() }
        }
    }
}
