import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

// Pill button used for dialog and page actions. `primary` fills it with the accent;
// `flat` drops the surface and border so it reads as a quiet secondary action.
Button {
    id: root
    property bool primary: false
    property string disabledReason: ""
    implicitHeight: 38
    leftPadding: Theme.spacingLarge
    rightPadding: Theme.spacingLarge
    font.pixelSize: 13
    ToolTip.text: !root.enabled ? root.disabledReason : ""
    ToolTip.visible: !root.enabled && root.disabledReason.length > 0 && disabledHover.hovered
    ToolTip.delay: 450

    HoverHandler {
        id: disabledHover
        objectName: "disabledActionHover"
        enabled: !root.enabled && root.disabledReason.length > 0
    }

    contentItem: Text {
        text: root.text
        color: !root.enabled ? themeState.secondary : root.primary ? themeState.onAccent : themeState.foreground
        font: root.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: height / 2
        color: root.primary ? (!root.enabled ? themeState.surface : root.down ? themeState.accent : root.hovered ? themeState.accentHover : themeState.accent)
            : root.flat ? (root.enabled && (root.down || root.hovered) ? themeState.hover : Qt.alpha(themeState.hover, 0))
            : !root.enabled ? themeState.surface : root.down ? themeState.border : root.hovered ? themeState.hover : themeState.surface
        border.width: root.visualFocus ? 2 : root.primary || root.flat ? 0 : 1
        border.color: root.visualFocus ? themeState.accent : themeState.border
        Behavior on color { enabled: typeof appState === "undefined" || !appState.reducedMotion; ColorAnimation { duration: Theme.motionFast } }
    }
}
