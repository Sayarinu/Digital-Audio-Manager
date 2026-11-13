import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "Theme.js" as Theme

// Asks whether to install a newer release or switch to the build on the chosen channel; the button runs the verified installer.
ThemedDialog {
    id: root
    objectName: "updateDialog"
    title: maintenanceState.switchingChannel ? (maintenanceState.channel === "stable" ? "Switch to Stable" : "Switch to Experimental") : "Update Available"
    width: Math.min(460, (parent ? parent.width : 460) - 32)
    contentItem: ColumnLayout {
        spacing: 14
        Label {
            Layout.fillWidth: true
            text: (maintenanceState.latestName || "Digital Audio Manager") + " is ready to install."
            textFormat: Text.PlainText; wrapMode: Text.Wrap
            color: themeState.foreground; font.pixelSize: 18; font.bold: true
        }
        Label {
            Layout.fillWidth: true
            text: "You have " + maintenanceState.versionName + ". " + (maintenanceState.downgrading ? "Switching to the latest stable release keeps your settings, queue and downloaded music; features only in experimental builds go away." : maintenanceState.switchingChannel ? "Switching keeps your settings, queue and downloaded music." : "Updating keeps your settings, queue and downloaded music.")
            textFormat: Text.PlainText; wrapMode: Text.Wrap; color: themeState.secondary
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(notes.implicitHeight + 24, 180)
            visible: !!maintenanceState.releaseNotes
            radius: 10; color: themeState.background
            ScrollView {
                anchors.fill: parent; anchors.margins: 12
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                Label {
                    id: notes
                    objectName: "updateNotes"
                    width: parent.width
                    text: maintenanceState.releaseNotes
                    textFormat: Text.PlainText; wrapMode: Text.Wrap
                    color: themeState.foreground; font.pixelSize: 13
                }
            }
        }
        ProgressBar {
            Layout.fillWidth: true
            visible: maintenanceState.downloading
            value: maintenanceState.progress / 100
        }
        Label {
            Layout.fillWidth: true
            visible: maintenanceState.busy || maintenanceState.downloading || !maintenanceState.installSupported
            text: maintenanceState.installSupported ? maintenanceState.status : maintenanceState.updateGuidance
            textFormat: Text.PlainText; wrapMode: Text.Wrap; color: themeState.secondary; font.pixelSize: 13
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSmall
            ThemeActionButton { text: "Release Notes"; visible: !!maintenanceState.releaseUrl; onClicked: Qt.openUrlExternally(maintenanceState.releaseUrl) }
            Item { Layout.fillWidth: true }
            ThemeActionButton { objectName: "updateLater"; text: maintenanceState.downloading ? "Cancel" : "Later"; onClicked: { if (maintenanceState.downloading) maintenanceState.cancelUpdate(); else root.close() } }
            ThemeActionButton {
                objectName: "updateNow"
                primary: true
                property bool manual: !maintenanceState.installSupported
                text: manual ? "Download" : maintenanceState.switchingChannel ? "Switch & Restart" : "Update & Restart"
                enabled: !maintenanceState.busy
                onClicked: manual ? Qt.openUrlExternally(maintenanceState.releaseUrl) : maintenanceState.installUpdate()
            }
        }
    }
}
