import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

MenuItem {
    id: root
    implicitWidth: 216
    implicitHeight: 38
    leftPadding: 12
    rightPadding: 12
    contentItem: Text {
        text: root.text
        color: root.enabled ? themeState.foreground : themeState.muted
        font.pixelSize: Theme.textBody
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.highlighted ? themeState.hover : "transparent"
        border.width: root.visualFocus ? 1 : 0
        border.color: themeState.accent
    }
}
