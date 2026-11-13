import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Theme.js" as Theme

// Modal dialog matching the app's popups: rounded surface card, bold title with a close button.
// `headerAction` adds an optional control (such as an icon button) before the close button.
Dialog {
    id: root
    property Component headerAction: null
    anchors.centerIn: Overlay.overlay
    modal: true
    focus: true
    padding: 20
    topPadding: 4
    standardButtons: Dialog.NoButton
    background: Rectangle { radius: Theme.radiusLarge; color: themeState.surface; border.color: themeState.border; border.width: 1 }
    header: RowLayout {
        spacing: Theme.spacingSmall
        Label {
            Layout.fillWidth: true; Layout.leftMargin: 20; Layout.topMargin: Theme.spacingLarge
            text: root.title; textFormat: Text.PlainText; elide: Text.ElideRight
            color: themeState.foreground; font.pixelSize: Theme.textTitle; font.bold: true
        }
        Loader { Layout.topMargin: Theme.spacingMedium; active: !!root.headerAction; visible: active; sourceComponent: root.headerAction }
        IconButton { Layout.rightMargin: Theme.spacingMedium; Layout.topMargin: Theme.spacingMedium; iconName: "close"; tip: "Close"; iconSize: 18; implicitWidth: 34; implicitHeight: 34; onClicked: root.reject() }
    }
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.5) }
}
