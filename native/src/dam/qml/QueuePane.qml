import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "Theme.js" as Theme

ColumnLayout {
    id: root
    property bool compact: false
    signal closeRequested()
    spacing: 12
    RowLayout {
        Layout.fillWidth: true; Layout.margins: root.compact ? 12 : 24; Layout.bottomMargin: 0
        AppText { text: "Queue"; font.pixelSize: root.compact ? 18 : 28; font.bold: true; Layout.fillWidth: true }
        IconButton { iconName: "download"; tip: "Resume Downloads"; visible: Boolean(appState.queuePauseReason); enabled: !appState.busy && !appState.queueRunning && appState.hasQueuedDownloads; onClicked: appState.startQueue() }
        IconButton { visible: root.compact; iconName: "close"; tip: "Close Queue"; onClicked: root.closeRequested() }
    }
    AppText { text: (appState.data.jobs || []).length + " tracks • " + (appState.queueRunning ? "Downloading" : appState.queuePauseReason ? "Paused" : appState.hasQueuedDownloads ? "Starting automatically…" : "No pending downloads"); color: themeState.secondary; Layout.leftMargin: root.compact ? 16 : 24; Layout.rightMargin: 16; Layout.fillWidth: true; font.pixelSize: 13 }
    AppText { text: appState.queuePauseReason; visible: Boolean(text); color: themeState.error; Layout.leftMargin: root.compact ? 16 : 24; Layout.rightMargin: 16; Layout.fillWidth: true; wrapMode: Text.Wrap; elide: Text.ElideNone; font.pixelSize: 12 }
    ListView {
        id: queue
        objectName: "queueList"
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.margins: root.compact ? 8 : 24
        clip: true; reuseItems: true; model: appState.jobModel
        WheelScroll { view: queue }
        ScrollBar.vertical: ScrollBar {}
        delegate: ItemDelegate {
            id: job
            required property var modelData
            width: ListView.view.width; height: 72; padding: 0
            Accessible.name: modelData.title + ", " + modelData.state
            background: Rectangle { radius: Theme.radiusSmall; color: job.hovered || job.visualFocus ? themeState.hover : "transparent"; border.color: job.visualFocus ? themeState.accent : "transparent" }
            contentItem: Item {
                Cover { x: 8; anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40; symbol: job.modelData.state === "running" ? "download" : "music" }
                Column { x: 60; width: parent.width - 100; anchors.verticalCenter: parent.verticalCenter; spacing: 3
                    AppText { width: parent.width; text: job.modelData.title }
                    AppText { width: parent.width; text: job.modelData.artist; color: themeState.secondary; font.pixelSize: 12 }
                    AppText { width: parent.width; text: job.modelData.state === "failed" ? job.modelData.error_message || "Needs attention" : job.modelData.state; color: job.modelData.state === "failed" ? themeState.error : themeState.secondary; font.pixelSize: 12 }
                }
                IconButton { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: 36; height: 36; iconSize: 18; iconName: job.modelData.state === "failed" ? "refresh" : "close"; tip: job.modelData.state === "failed" ? "Retry Download" : "Cancel Download"; enabled: !appState.busy; onClicked: job.modelData.state === "failed" ? appState.run("retry_job", {job_id:job.modelData.id}) : appState.cancelJob(job.modelData.id) }
            }
            ToolTip.text: modelData.error_message || ""; ToolTip.visible: hovered && ToolTip.text.length > 0; ToolTip.delay: 600
        }
        AppText { visible: queue.count === 0; anchors.centerIn: parent; width: parent.width - 24; text: "Downloads start automatically when you add songs."; color: themeState.secondary; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; elide: Text.ElideNone }
    }
}
