import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ScrollView {
    id: root
    signal chooseMusic()
    signal importSession()
    signal resetLibrary()
    clip: true
    contentWidth: availableWidth
    ColumnLayout {
        width: root.availableWidth; spacing: 20
        AppText { text: "Settings"; font.pixelSize: 28; font.bold: true; Layout.margins: 24; Layout.bottomMargin: 0 }
        Rectangle {
            Layout.fillWidth: true; Layout.leftMargin: 24; Layout.rightMargin: 24; implicitHeight: accountContent.implicitHeight + 40; radius: 16; color: themeState.surface
            ColumnLayout {
                id: accountContent; anchors.fill: parent; anchors.margins: 20; spacing: 12
                AppText { text: "YouTube Music"; font.pixelSize: 20; font.bold: true }
                AppText { text: account.connected ? "Connected as " + (account.profile.name || "your account") : "Connect using your browser’s YouTube Music sign-in."; color: themeState.secondary; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                AppText { text: account.message; visible: Boolean(text); color: account.reconnect ? themeState.error : themeState.secondary; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone }
                Flow {
                    Layout.fillWidth: true; spacing: 8; Layout.preferredHeight: childrenRect.height
                    ThemeActionButton { text: account.connected ? "Reconnect" : "Connect account"; primary: true; enabled: !account.busy && !account.signingIn && !appState.busy && !appState.queueRunning; onClicked: account.signIn() }
                    ThemeActionButton { text: "Import browser.json"; enabled: !account.busy && !appState.busy && !appState.queueRunning; onClicked: root.importSession() }
                    ThemeActionButton { text: "Sync my playlists"; visible: account.connected; enabled: !appState.busy && !account.busy; onClicked: appState.run("import_account_library", {}) }
                    ThemeActionButton { text: "Sign out"; visible: account.connected || account.reconnect; enabled: !account.busy && !appState.busy && !appState.queueRunning; onClicked: account.signOut() }
                    ThemeActionButton { text: "Cancel sign-in"; visible: account.signingIn; onClicked: account.cancelSignIn() }
                }
                AppText { text: "Your session is stored in your system keyring. Downloads remain available when you’re offline or signed out."; color: themeState.secondary; font.pixelSize: 12; wrapMode: Text.WordWrap; elide: Text.ElideNone; Layout.fillWidth: true }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.leftMargin: 24; Layout.rightMargin: 24; spacing: 12
            AppText { text: "Appearance"; font.pixelSize: 20; font.bold: true }
            AppText { text: "The same themes and controls as Tubify."; color: themeState.secondary }
            ThemedComboBox { Layout.fillWidth: true; Layout.maximumWidth: 360; model: themeState.themes; textRole: "name"; valueRole: "id"; currentIndex: { for (var i=0; i < count; ++i) { if (valueAt(i) === themeState.activeThemeId) return i } return 0 } onActivated: themeState.selectTheme(currentValue); Accessible.name: "Color theme" }
            CheckBox { text: "Reduce motion"; checked: appState.reducedMotion; onToggled: appState.setReducedMotion(checked) }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            AppText { text: "Download folder"; font.pixelSize: 20; font.bold: true }
            AppText { text: appState.data.health.library_root || "Loading…"; color: themeState.secondary; wrapMode: Text.WrapAnywhere; elide: Text.ElideNone; Layout.fillWidth: true }
            AppText { visible: appState.data.health.storage_available === false; text: "Reconnect this drive to download music, or choose another Music folder."; color: themeState.error; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            AppText { text: "Choose a Music folder on this computer or another device. New downloads go in Digital Audio Manager/Library. Existing downloads stay in their current locations."; color: themeState.secondary; wrapMode: Text.WordWrap; elide: Text.ElideNone; Layout.fillWidth: true }
            RowLayout { ThemeActionButton { text: "Choose Music folder"; enabled: !appState.busy && !appState.queueRunning; onClicked: root.chooseMusic() } ThemeActionButton { text: "Open folder"; onClicked: appState.openLibrary() } }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            AppText { text: "Import music"; font.pixelSize: 20; font.bold: true }
            AppText { text: "Public playlists and albums work without signing in."; color: themeState.secondary }
            RowLayout {
                Layout.fillWidth: true
                ThemedTextField { id: importUrl; Layout.fillWidth: true; placeholderText: "YouTube Music playlist or album URL"; Accessible.name: placeholderText }
                ThemeActionButton { text: "Import & queue"; primary: true; enabled: Boolean(importUrl.text.trim()) && !appState.busy; onClicked: appState.run("import_to_unsorted", {url:importUrl.text}) }
            }
            AppText { text: "Public profile"; font.bold: true }
            RowLayout {
                Layout.fillWidth: true
                ThemedTextField { id: profileUrl; Layout.fillWidth: true; text: appState.data.public_profile_url || ""; placeholderText: "YouTube channel or @handle URL"; Accessible.name: placeholderText }
                ThemeActionButton { text: "Sync profile"; enabled: Boolean(profileUrl.text.trim()) && !appState.busy; onClicked: appState.run("import_public_profile", {url:profileUrl.text}) }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: themeState.border }
            AppText { text: "Tools & maintenance"; font.pixelSize: 20; font.bold: true }
            Repeater {
                model: Object.keys(appState.data.health.dependencies || {})
                RowLayout {
                    required property string modelData
                    Layout.fillWidth: true
                    AppText { text: modelData; Layout.fillWidth: true }
                    AppText { text: appState.data.health.dependencies[modelData].available ? "Ready" : "Missing"; color: appState.data.health.dependencies[modelData].available ? themeState.accent : themeState.error }
                }
            }
            Flow {
                Layout.fillWidth: true; spacing: 8; Layout.preferredHeight: childrenRect.height
                ThemeActionButton { text: "Set up tools"; enabled: !appState.busy && !appState.queueRunning; onClicked: appState.run("bootstrap_dependencies", {}) }
                ThemeActionButton { text: "Repair metadata"; enabled: !appState.busy && !appState.queueRunning; onClicked: appState.run("repair_library_metadata", {}) }
                ThemeActionButton { text: "Reset local library"; enabled: !appState.busy && !appState.queueRunning; onClicked: root.resetLibrary() }
            }
            Item { height: 24 }
        }
    }
}
