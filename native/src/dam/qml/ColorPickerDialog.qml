import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme
import "components"

// Colour picker for one role of a custom theme: saturation/value field, hue slider, hex entry and a palette.
ThemedDialog {
    id: palettePicker
    objectName: "colorPickerDialog"
    // The theme role that Apply changes.
    property string role: ""
    // The pipette closes the picker so the screen can be sampled.
    signal screenPickRequested()
    width: Math.min(parent ? parent.width - 48 : 430, 430)
    height: Math.min(implicitHeight, parent ? parent.height - 48 : implicitHeight)
    title: "Choose a Color"
    headerAction: Component {
        IconButton {
            iconName: "pipette"; tip: "Pick a Color from the Screen"; iconSize: 19; implicitWidth: 34; implicitHeight: 34
            onClicked: { palettePicker.close(); palettePicker.screenPickRequested() }
        }
    }
    property string draftHex: "#A78BFA"
    property color previewColor: "#A78BFA"
    property real hue: 0.72
    property real saturation: 0.42
    property real value: 0.98
    property string statusMessage: ""
    function setDraft(hex) {
        draftHex = hex.toUpperCase()
        statusMessage = ""
        if (!/^#[0-9A-F]{6}$/.test(draftHex)) return
        var red = parseInt(draftHex.slice(1, 3), 16) / 255
        var green = parseInt(draftHex.slice(3, 5), 16) / 255
        var blue = parseInt(draftHex.slice(5, 7), 16) / 255
        var high = Math.max(red, green, blue)
        var low = Math.min(red, green, blue)
        var delta = high - low
        value = high
        saturation = high === 0 ? 0 : delta / high
        if (delta === 0) hue = 0
        else if (high === red) hue = ((green - blue) / delta + (green < blue ? 6 : 0)) / 6
        else if (high === green) hue = ((blue - red) / delta + 2) / 6
        else hue = ((red - green) / delta + 4) / 6
        previewColor = draftHex
    }
    function updateFromField() {
        previewColor = Qt.hsva(hue, saturation, value, 1)
        draftHex = previewColor.toString().toUpperCase()
    }
    function applyColor() {
        if (/^#[0-9A-Fa-f]{6}$/.test(draftHex)) {
            themeState.setColor(palettePicker.role, draftHex)
            close()
        }
    }
    contentItem: ScrollView {
        id: colorPickerScroll
        clip: true
        implicitHeight: colorPickerContent.implicitHeight
        ColumnLayout {
            id: colorPickerContent
            width: colorPickerScroll.availableWidth
            spacing: 14
            RowLayout {
                Layout.fillWidth: true; spacing: Theme.spacingMedium
                Rectangle { Layout.preferredWidth: 38; Layout.preferredHeight: 38; radius: Theme.radiusMedium; color: palettePicker.previewColor; border.color: themeState.border; border.width: 1 }
                ThemedTextField {
                    Layout.fillWidth: true
                    text: palettePicker.draftHex
                    maximumLength: 7
                    horizontalAlignment: TextInput.AlignHCenter
                    Accessible.name: "Hex color"
                    onTextEdited: {
                        if (/^#[0-9A-Fa-f]{6}$/.test(text)) palettePicker.setDraft(text)
                    }
                    onAccepted: palettePicker.applyColor()
                }
            }
            Rectangle {
                id: saturationValueField
                Layout.fillWidth: true; Layout.preferredHeight: 156
                radius: 10; clip: true
                color: Qt.hsva(palettePicker.hue, 1, 1, 1)
                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: "white" }
                        GradientStop { position: 1; color: "transparent" }
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        GradientStop { position: 0; color: "transparent" }
                        GradientStop { position: 1; color: "black" }
                    }
                }
                Rectangle {
                    x: palettePicker.saturation * (parent.width - width)
                    y: (1 - palettePicker.value) * (parent.height - height)
                    width: 14; height: 14; radius: 7
                    color: "transparent"; border.color: "white"; border.width: 2
                    Rectangle { anchors.centerIn: parent; width: 4; height: 4; radius: 2; color: "transparent"; border.color: "#55000000"; border.width: 1 }
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.CrossCursor
                    function selectPoint(mouse) {
                        palettePicker.saturation = Math.max(0, Math.min(1, mouse.x / width))
                        palettePicker.value = 1 - Math.max(0, Math.min(1, mouse.y / height))
                        palettePicker.updateFromField()
                    }
                    onPressed: function(mouse) { selectPoint(mouse) }
                    onPositionChanged: function(mouse) { if (pressed) selectPoint(mouse) }
                }
            }
            Slider {
                id: hueSlider
                Layout.fillWidth: true; Layout.preferredHeight: 26
                from: 0; to: 1; value: palettePicker.hue
                onMoved: { palettePicker.hue = value; palettePicker.updateFromField() }
                background: Rectangle {
                    x: hueSlider.leftPadding; y: hueSlider.topPadding + (hueSlider.availableHeight - height) / 2
                    width: hueSlider.availableWidth; height: 10; radius: 5
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: "#ff0000" }
                        GradientStop { position: 0.17; color: "#ffff00" }
                        GradientStop { position: 0.33; color: "#00ff00" }
                        GradientStop { position: 0.5; color: "#00ffff" }
                        GradientStop { position: 0.67; color: "#0000ff" }
                        GradientStop { position: 0.83; color: "#ff00ff" }
                        GradientStop { position: 1; color: "#ff0000" }
                    }
                }
                handle: Rectangle {
                    x: hueSlider.leftPadding + hueSlider.visualPosition * (hueSlider.availableWidth - width)
                    y: hueSlider.topPadding + (hueSlider.availableHeight - height) / 2
                    width: 18; height: 18; radius: 9; color: "white"
                    border.color: themeState.border; border.width: 2
                }
            }
            Label { text: "Palette"; color: themeState.secondary; font.pixelSize: 13 }
            GridView {
                id: presetColors
                Layout.fillWidth: true; Layout.preferredHeight: 160
                clip: true; cellWidth: width / 8; cellHeight: 40
                model: ["#EF4444", "#F97316", "#F59E0B", "#EAB308", "#84CC16", "#22C55E", "#10B981", "#14B8A6", "#06B6D4", "#0EA5E9", "#3B82F6", "#6366F1", "#8B5CF6", "#A855F7", "#D946EF", "#EC4899", "#F43F5E", "#FB7185", "#FDBA74", "#FDE047", "#BEF264", "#86EFAC", "#5EEAD4", "#67E8F9", "#7DD3FC", "#93C5FD", "#A5B4FC", "#C4B5FD", "#D8B4FE", "#F0ABFC", "#F9A8D4", "#FDA4AF"]
                delegate: Button {
                    required property string modelData
                    width: 32; height: 32; padding: 2
                    Accessible.name: modelData
                    background: Rectangle { anchors.centerIn: parent; width: 27; height: 27; radius: 14; color: modelData; border.color: palettePicker.draftHex.toUpperCase() === modelData ? themeState.foreground : themeState.border; border.width: palettePicker.draftHex.toUpperCase() === modelData ? 2 : 1 }
                    onClicked: palettePicker.setDraft(modelData)
                }
            }
            Label { Layout.fillWidth: true; text: palettePicker.statusMessage; visible: text.length > 0; color: themeState.secondary; font.pixelSize: Theme.textSmall; wrapMode: Text.Wrap }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ThemeActionButton { text: "Cancel"; onClicked: palettePicker.close() }
                ThemeActionButton {
                    text: "Apply"; primary: true
                    enabled: /^#[0-9A-Fa-f]{6}$/.test(palettePicker.draftHex)
                    onClicked: palettePicker.applyColor()
                }
            }
        }
    }
}
