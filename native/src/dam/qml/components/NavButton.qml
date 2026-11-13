import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

Button {
    id: root
    property string symbol: "music"
    property bool selected: false
    property bool wide: true
    height: 48
    padding: 0
    leftInset: 0; rightInset: 0; topInset: 0; bottomInset: 0
    Accessible.name: text
    ToolTip.text: text; ToolTip.visible: !wide && hovered; ToolTip.delay: 600
    contentItem: Row {
        leftPadding: 16; spacing: 20
        Symbol { name: root.symbol; anchors.verticalCenter: parent.verticalCenter; color: root.selected ? themeState.accent : themeState.secondary }
        AppText { text: root.text; visible: root.wide; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 16 }
    }
    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.selected ? themeState.selected : root.hovered ? themeState.hover : "transparent"
        border.width: root.visualFocus ? 2 : 0; border.color: themeState.accent
        Rectangle { x: 4; anchors.verticalCenter: parent.verticalCenter; width: 3; height: 24; radius: 2; color: themeState.accent; visible: root.selected }
    }
}
