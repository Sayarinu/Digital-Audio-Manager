import QtQuick

// Qt's own wheel handling restarts a short flick on every notch, so wheeling faster travels less.
// Notches add up to a destination the view eases towards; touchpads keep Qt's direct scrolling.
WheelHandler {
    id: root
    required property Flickable view
    signal scrolled()
    readonly property real notchDistance: 120
    readonly property real easingSeconds: 0.05
    property real destination: 0
    property real lastY: 0
    parent: view
    target: null
    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
    blocking: false
    function clamped(value) {
        var top = view.originY - view.topMargin
        return Math.max(top, Math.min(Math.max(top, view.originY + view.contentHeight - view.height + view.bottomMargin), value))
    }
    function moveTo(value) {
        view.contentY = lastY = value
        root.scrolled()
    }
    onWheel: event => {
        if (event.pixelDelta.y !== 0 || event.angleDelta.y === 0) {
            glide.stop()
            event.accepted = false
            return
        }
        event.accepted = true
        view.cancelFlick()
        destination = clamped((glide.running ? destination : view.contentY) - event.angleDelta.y / 120 * notchDistance)
        if (appState.reducedMotion) {
            moveTo(destination)
            return
        }
        lastY = view.contentY
        glide.start()
    }
    property FrameAnimation glide: FrameAnimation {
        onTriggered: {
            // A scrollbar drag, key press or restored position takes over from the glide.
            if (Math.abs(root.view.contentY - root.lastY) > 2) { stop(); return }
            var goal = root.clamped(root.destination)
            var next = goal + (root.view.contentY - goal) * Math.exp(-frameTime / root.easingSeconds)
            if (Math.abs(goal - next) < 0.5) { next = goal; stop() }
            root.moveTo(next)
        }
    }
}
