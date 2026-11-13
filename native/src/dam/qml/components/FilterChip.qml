import QtQuick
import QtQuick.Controls

// Pill that selects one filter in a row of filters; the selected chip is filled with the accent.
// Set choice to false for a pill-shaped action that selects nothing.
Button {
    id: root
    property bool selected: false
    property bool choice: true
    height: 36
    leftPadding: 14
    rightPadding: 14
    Accessible.name: text
    Accessible.checkable: choice
    Accessible.checked: selected
    contentItem: Text {
        text: root.text
        textFormat: Text.PlainText
        color: root.selected ? themeState.onAccent : themeState.foreground
        font: root.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: height / 2
        color: root.selected ? themeState.accent : root.hovered ? themeState.hover : themeState.surface
        border.width: root.visualFocus ? 2 : 0
        border.color: root.selected ? themeState.foreground : themeState.accent
    }
}
