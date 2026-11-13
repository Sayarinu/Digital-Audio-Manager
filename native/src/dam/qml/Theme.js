.pragma library

// The app font (Roboto, 14 px) is set once in app.py; components inherit it.
var cardWidth = 208
var cardHeight = 260
function gutter(width) { return width > 1200 ? 40 : 24 }
function timeLabel(value) {
    var seconds = Math.max(0, Math.floor(value || 0))
    return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0")
}
// Corner radii: rows and menu items, fields and cards, dialogs and popups.
var radiusSmall = 8
var radiusMedium = 12
var radiusLarge = 16
// Spacing between related controls, groups and sections.
var spacingSmall = 8
var spacingMedium = 12
var spacingLarge = 16
// Text sizes: captions, body text, dialog titles and page headings.
var textSmall = 12
var textBody = 14
var textTitle = 15
var textHeading = 28
// Motion: every animation passes appState.reducedMotion so it can switch off entirely.
var motionFast = 120
var motionMedium = 200
var motionSlow = 280
function duration(ms, reduced) { return reduced ? 0 : ms }
