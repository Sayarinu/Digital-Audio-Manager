import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "Theme.js" as Theme
import "components"

// Sign in through the browser or a session export, and sign out.
ThemedDialog {
    id: accountDialog
    objectName: "accountDialog"
    width: Math.min(parent ? parent.width - 64 : 440, 440)
    title: "Connection Settings"
    contentItem: ColumnLayout {
        spacing: 14
        Label { Layout.fillWidth: true; text: "Current User:"; horizontalAlignment: Text.AlignHCenter; color: themeState.secondary; font.pixelSize: 13 }
        Label { Layout.fillWidth: true; text: accountState.profile.name || "Not Signed In"; horizontalAlignment: Text.AlignHCenter; color: themeState.foreground; font.pixelSize: 21; font.bold: true; elide: Text.ElideRight }
        ThemeActionButton {
            objectName: "browserSignIn"
            Layout.fillWidth: true; Layout.preferredHeight: 44
            primary: true
            font.pixelSize: Theme.textBody; font.bold: true
            text: accountState.signingIn ? "Waiting for Browser Sign-In…" : "Sign in via Browser"
            visible: accountState.signInAvailable && !accountState.connected; enabled: !appState.busy && !appState.queueRunning && !accountState.busy && !accountState.signingIn
            onClicked: accountState.signIn()
        }
        ThemeActionButton {
            Layout.alignment: Qt.AlignHCenter
            flat: true
            objectName: "cancelBrowserSignIn"
            text: "Cancel"; visible: accountState.signingIn && !accountState.connected
            onClicked: accountState.cancelSignIn()
        }
        ThemeActionButton {
            Layout.fillWidth: true; Layout.preferredHeight: 44
            font.pixelSize: Theme.textBody
            text: "Choose Browser Session File"
            enabled: !appState.busy && !appState.queueRunning && !accountState.busy && !accountState.fixtureMode
            onClicked: sessionPicker.open()
        }
        BusyIndicator { Layout.alignment: Qt.AlignHCenter; running: accountState.busy || accountState.signingIn; visible: running }
        Label { Layout.fillWidth: true; text: accountState.message; textFormat: Text.PlainText; visible: text.length > 0 && !accountState.connected; wrapMode: Text.Wrap; color: themeState.secondary }
        ThemeActionButton {
            Layout.fillWidth: true
            text: "Sign Out"; visible: accountState.connected
            enabled: !appState.busy && !appState.queueRunning
            onClicked: { accountState.signOut(); accountDialog.close() }
        }
        ThemeActionButton {
            Layout.fillWidth: true
            flat: true
            text: "Export Instructions"
            onClicked: Qt.openUrlExternally("https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html")
        }
    }
    FileDialog {
        id: sessionPicker
        title: "Choose a YouTube Music Session Export"
        nameFilters: ["JSON session files (*.json)", "All files (*)"]
        onAccepted: accountState.importFile(selectedFile)
    }
}
