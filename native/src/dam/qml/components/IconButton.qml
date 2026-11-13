import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

ToolButton {
    id: root
    property string iconName: "more"
    property string tip: ""
    property color iconColor: themeState.foreground
    // A disabled button that still reports a state, such as a finished download, can keep its colour.
    property color disabledIconColor: themeState.muted
    property int iconSize: 24
    property bool outlined: false
    // No hover fill or focus ring, for buttons inside rows that draw their own highlight.
    property bool quiet: false
    implicitWidth: 44
    implicitHeight: 44
    Accessible.name: tip
    ToolTip.text: tip
    ToolTip.visible: hovered && tip.length > 0
    ToolTip.delay: 600
    background: Rectangle {
        radius: width / 2
        color: !root.quiet && root.down ? themeState.border : !root.quiet && root.hovered ? themeState.hover : Qt.alpha(themeState.hover, 0)
        Behavior on color { enabled: typeof appState === "undefined" || !appState.reducedMotion; ColorAnimation { duration: Theme.motionFast } }
        border.width: root.visualFocus && !root.quiet ? 2 : root.outlined ? 1 : 0
        border.color: root.visualFocus ? themeState.accent : themeState.border
    }
    contentItem: Item {
        Symbol {
            anchors.centerIn: parent
            width: root.iconSize
            height: root.iconSize
            name: root.iconName
            color: root.enabled ? root.iconColor : root.disabledIconColor
        }
    }
}
