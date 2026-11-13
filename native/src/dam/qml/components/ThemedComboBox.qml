import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

// Dropdown whose button and list match the app's context menus.
ComboBox {
    id: root
    implicitHeight: 40
    leftPadding: 12
    rightPadding: 40
    font.pixelSize: Theme.textBody
    contentItem: Text {
        text: root.displayText; textFormat: Text.PlainText
        color: root.enabled ? themeState.foreground : themeState.muted
        font: root.font; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
    }
    indicator: Symbol { x: root.width - width - 12; anchors.verticalCenter: parent.verticalCenter; width: 18; height: 18; name: "down"; color: themeState.secondary }
    background: Rectangle { radius: Theme.radiusSmall; color: root.hovered || root.down ? themeState.hover : themeState.surface; border.width: root.visualFocus ? 2 : 1; border.color: root.visualFocus ? themeState.accent : themeState.border }
    delegate: ItemDelegate {
        id: option
        required property var model
        required property int index
        width: ListView.view.width
        implicitHeight: 38
        leftPadding: 12; rightPadding: 12
        highlighted: root.highlightedIndex === index
        contentItem: Text {
            text: root.textRole ? option.model[root.textRole] : option.model.modelData
            textFormat: Text.PlainText
            color: themeState.foreground; font: root.font
            verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
        }
        background: Rectangle { radius: Theme.radiusSmall; color: option.highlighted || option.hovered ? themeState.hover : "transparent" }
    }
    popup: Popup {
        y: root.height + 4
        width: root.width
        implicitHeight: Math.min(contentItem.implicitHeight + topPadding + bottomPadding, 320)
        padding: 8
        contentItem: ListView {
            clip: true
            spacing: 2
            implicitHeight: contentHeight
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
            ScrollBar.vertical: ScrollBar {}
        }
        background: Rectangle { radius: Theme.radiusMedium; color: themeState.surface; border.color: themeState.border; border.width: 1 }
    }
}
