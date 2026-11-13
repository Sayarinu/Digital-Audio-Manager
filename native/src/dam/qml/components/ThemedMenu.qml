import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

// Context menu shell shared by every menu; fill it with ContextMenuItem and ThemedMenuSeparator.
Menu {
    implicitWidth: 232
    padding: 8
    spacing: 2
    background: Rectangle { radius: Theme.radiusMedium; color: themeState.surface; border.color: themeState.border; border.width: 1 }
}
