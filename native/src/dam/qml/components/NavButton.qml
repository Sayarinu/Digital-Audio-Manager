import QtQuick
import QtQuick.Controls

Button {
    id: root
    property string symbol: "music"
    property bool selected: false
    implicitHeight: 44
    leftPadding: 16
    rightPadding: 12
    contentItem: Row {
        spacing: 16
        Symbol { name: root.symbol; width: 22; height: 22; anchors.verticalCenter: parent.verticalCenter; color: root.selected ? themeState.accent : themeState.foreground }
        AppText { text: root.text; width: parent.width - 38; anchors.verticalCenter: parent.verticalCenter; font.bold: root.selected }
    }
    background: Rectangle { radius: 8; color: root.selected ? themeState.selected : root.hovered ? themeState.hover : "transparent"; border.width: root.visualFocus ? 2 : 0; border.color: themeState.accent }
}
