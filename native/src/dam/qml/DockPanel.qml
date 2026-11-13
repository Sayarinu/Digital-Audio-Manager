import QtQuick
import "Theme.js" as Theme

// The side panel, a card matching the player bar: slides in past the right edge when opened and back out when closed.
Rectangle {
    id: root
    // Whether the panel occupies its place in the layout.
    required property bool shown
    // Keeps the panel drawn while it slides out over the page that has already taken its space.
    readonly property bool leaving: slide.running && !shown
    visible: shown || leaving
    enabled: shown
    radius: Theme.radiusMedium
    color: themeState.surface
    // Clears the margin between the card and the window edge when sliding.
    readonly property real travel: width + anchors.rightMargin
    // How much of the panel's slide is done, from 0 (off screen) to 1 (in place), for what moves along with it.
    readonly property real revealed: visible && travel > 0 ? 1 - shift.x / travel : 0
    transform: Translate { id: shift }
    onShownChanged: {
        var reversing = slide.running
        slide.stop()
        if (appState.reducedMotion) {
            shift.x = 0
            opacity = 1
            return
        }
        // A fresh open starts off the right edge, faded; a reversal continues from where the panel is.
        if (shown && !reversing) { shift.x = travel; opacity = 0 }
        slideX.to = shown ? 0 : travel
        slideX.easing.type = shown ? Easing.OutCubic : Easing.InCubic
        // Closing fades out as it slides, so the page beneath shows through as the panel leaves.
        fade.to = shown ? 1 : 0
        fade.easing.type = shown ? Easing.OutCubic : Easing.InCubic
        slide.start()
    }
    ParallelAnimation {
        id: slide
        NumberAnimation { id: slideX; target: shift; property: "x"; duration: Theme.motionSlow }
        NumberAnimation { id: fade; target: root; property: "opacity"; duration: Theme.motionSlow }
    }
}
