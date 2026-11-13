import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ColumnLayout {
    id: root
    property bool compact: false
    spacing: 16
    RowLayout {
        Layout.fillWidth: true; Layout.margins: 24; Layout.bottomMargin: 0
        AppText { text: "Download queue"; font.pixelSize: root.compact ? 18 : 28; font.bold: true; Layout.fillWidth: true }
        AppText { text: (appState.data.jobs || []).length; color: themeState.secondary }
    }
    ThemeActionButton { text: appState.queueRunning ? "Downloading…" : "Run queue"; primary: true; Layout.leftMargin: 24; enabled: !appState.busy && !appState.queueRunning && (appState.data.jobs || []).length > 0; onClicked: appState.startQueue() }
    AppText { visible: !root.compact; text: "Downloads stay queued across restarts. Retry a failed track when you’re ready."; color: themeState.secondary; Layout.leftMargin: 24; Layout.rightMargin: 24; Layout.fillWidth: true; wrapMode: Text.WordWrap }
    ListView {
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.margins: 16; clip: true; reuseItems: true
        model: appState.data.jobs || []; spacing: 8
        ScrollBar.vertical: ScrollBar {}
        delegate: Rectangle {
            id: job
            required property var modelData
            width: ListView.view.width
            height: details.implicitHeight + 24
            radius: 12; color: themeState.surface
            ColumnLayout {
                id: details; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 6
                AppText { text: job.modelData.title; font.bold: true; Layout.fillWidth: true }
                AppText { text: job.modelData.artist; color: themeState.secondary; font.pixelSize: 12; Layout.fillWidth: true }
                AppText { text: job.modelData.state === "failed" ? (job.modelData.error_message || "Needs attention") : job.modelData.state; color: job.modelData.state === "failed" ? themeState.error : themeState.accent; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: 12; Layout.fillWidth: true }
                ThemeActionButton { text: job.modelData.state === "failed" ? "Retry" : "Cancel"; flat: true; enabled: !appState.busy; onClicked: job.modelData.state === "failed" ? appState.run("retry_job", {job_id:job.modelData.id}) : appState.cancelJob(job.modelData.id) }
            }
        }
        ColumnLayout {
            visible: !(appState.data.jobs || []).length
            anchors.centerIn: parent; width: parent.width - 24; spacing: 12
            Symbol { name: "queue"; color: themeState.secondary; Layout.alignment: Qt.AlignHCenter; width: 36; height: 36 }
            AppText { text: "All caught up"; font.pixelSize: 18; font.bold: true; Layout.alignment: Qt.AlignHCenter }
            AppText { text: "Tracks you queue will appear here."; color: themeState.secondary; wrapMode: Text.WordWrap; elide: Text.ElideNone; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
        }
    }
}
