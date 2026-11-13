import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

TextField {
    id: root
    property real radius: Theme.radiusSmall
    implicitHeight: 40
    leftPadding: Theme.spacingMedium
    rightPadding: Theme.spacingMedium
    color: themeState.foreground
    placeholderTextColor: themeState.secondary
    selectionColor: themeState.accent
    selectedTextColor: themeState.onAccent
    selectByMouse: true
    font.pixelSize: Theme.textBody
    background: Rectangle { radius: root.radius; color: themeState.hover; border.width: root.activeFocus ? 2 : 1; border.color: root.activeFocus ? themeState.accent : themeState.border }
}
