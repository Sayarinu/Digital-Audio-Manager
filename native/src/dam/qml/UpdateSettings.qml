import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "Theme.js" as Theme

SettingsPage {
    id: root
    objectName: "updateSettings"
    property alias scrollView: scroll
    title: "Updates"
    contentItem: ScrollView {
        id: scroll
        contentWidth: availableWidth
        implicitHeight: body.implicitHeight
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            id: body
            width: scroll.availableWidth
            spacing: Theme.spacingLarge
            Label { objectName: "installedVersion"; text: maintenanceState.versionName; textFormat: Text.PlainText; color: themeState.foreground; font.bold: true }
            Label { objectName: "updateStatus"; Layout.fillWidth: true; text: maintenanceState.status; textFormat: Text.PlainText; color: themeState.foreground; wrapMode: Text.Wrap }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6
                Label { text: "Update Channel"; color: themeState.foreground }
                ThemedComboBox {
                    objectName: "updateChannelOption"
                    Layout.fillWidth: true
                    model: ["Stable", "Experimental"]
                    currentIndex: ["stable", "experimental"].indexOf(maintenanceState.channel)
                    enabled: !maintenanceState.busy
                    Accessible.name: "Update channel"
                    onActivated: maintenanceState.setChannel(["stable", "experimental"][currentIndex])
                }
            }
            Label {
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: Theme.textSmall
                text: "Experimental builds get new features first and may have rough edges. Change the channel at any time to switch builds and restart."
            }
            SettingsCheckBox {
                text: "Check Automatically for Updates"
                checked: maintenanceState.automaticChecks
                onToggled: maintenanceState.setAutomaticChecks(checked)
            }
            ProgressBar { Layout.fillWidth: true; visible: maintenanceState.downloading; value: maintenanceState.progress / 100 }
            Flow {
                Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: Theme.spacingSmall
                ThemeActionButton { objectName: "checkReleaseButton"; text: "Check for Updates"; enabled: !maintenanceState.busy; onClicked: maintenanceState.checkRelease() }
                ThemeActionButton { objectName: "installUpdateButton"; text: maintenanceState.switchingChannel ? "Switch & Restart" : "Update & Restart"; visible: maintenanceState.updateAvailable && maintenanceState.installSupported; enabled: !maintenanceState.busy; onClicked: maintenanceState.installUpdate() }
                ThemeActionButton { text: "Cancel Download"; visible: maintenanceState.downloading; onClicked: maintenanceState.cancelUpdate() }
                ThemeActionButton { text: "Release Details"; visible: !!maintenanceState.releaseUrl; onClicked: Qt.openUrlExternally(maintenanceState.releaseUrl) }
            }
            Label { Layout.fillWidth: true; text: maintenanceState.updateGuidance; color: themeState.secondary; wrapMode: Text.Wrap; font.pixelSize: Theme.textSmall }
            Label { text: "About"; color: themeState.foreground; font.bold: true }
            Label { Layout.fillWidth: true; text: "Digital Audio Manager is open source under the MIT License. It is not affiliated with Google or YouTube."; color: themeState.secondary; wrapMode: Text.Wrap }
            Flow {
                Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: Theme.spacingSmall
                ThemeActionButton { objectName: "licensesButton"; text: "Open-Source Licenses"; onClicked: Qt.openUrlExternally(maintenanceState.noticesUrl) }
                ThemeActionButton { text: "Project Page"; onClicked: Qt.openUrlExternally("https://github.com/Sayarinu/Digital-Audio-Manager") }
            }
        }
    }
}
