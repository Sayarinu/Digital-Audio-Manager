import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Window
import "Theme.js" as Theme
import "components"

// Appearance page of the settings dialog: theme choice, custom theme editing, import/export and display options.
SettingsPage {
    id: appearanceSettings
    title: "Appearance"
    ownHeading: true
    objectName: "appearanceSettingsDialog"
    // Dialogs open over the whole window rather than inside the settings page.
    required property Item dialogParent
    property bool editingColors: false
    contentItem: ColumnLayout {
        spacing: Theme.spacingMedium
        RowLayout {
            Layout.fillWidth: true
            Label {
                Layout.fillWidth: true
                text: appearanceSettings.editingColors ? "Customize " + themeState.activeThemeName : "Appearance"
                color: themeState.foreground; font.pixelSize: 16; font.bold: true
            }
            ThemeActionButton {
                id: addThemeButton
                objectName: "addThemeButton"
                visible: !appearanceSettings.editingColors
                text: "Add Theme"
                primary: true
                onClicked: addThemeMenu.popup(addThemeButton, addThemeButton.width - addThemeMenu.implicitWidth, addThemeButton.height, null)
            }
            ThemeActionButton {
                visible: appearanceSettings.editingColors
                text: "Back to Themes"
                onClicked: appearanceSettings.editingColors = false
            }
        }
        StackLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            currentIndex: appearanceSettings.editingColors ? 1 : 0
            Item {
                ColumnLayout {
                    anchors.fill: parent; spacing: Theme.spacingSmall
                    ScrollView {
                        id: themeScroll
                        objectName: "themeScroll"
                        Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded
                        ColumnLayout {
                            width: themeScroll.availableWidth
                            spacing: 6
                            Label { text: "Dark Themes"; color: themeState.secondary; font.pixelSize: Theme.textSmall; font.bold: true }
                            GridView {
                                id: darkThemeGrid
                                objectName: "darkThemeGrid"
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.ceil(themeState.darkThemes.length / columns) * 50
                                property int columns: width < 480 ? 1 : 2
                                clip: true; interactive: false; cellWidth: width / columns; cellHeight: 50
                                model: themeState.darkThemes
                                delegate: themeCardDelegate
                            }
                            Label { text: "Light Themes"; color: themeState.secondary; font.pixelSize: Theme.textSmall; font.bold: true }
                            GridView {
                                id: lightThemeGrid
                                objectName: "lightThemeGrid"
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.max(50, Math.ceil(themeState.lightThemes.length / columns) * 50)
                                property int columns: width < 480 ? 1 : 2
                                clip: true; interactive: false; cellWidth: width / columns; cellHeight: 50
                                model: themeState.lightThemes
                                delegate: themeCardDelegate
                            }
                            Flow {
                                Layout.fillWidth: true; Layout.preferredHeight: childrenRect.height; spacing: Theme.spacingSmall
                                ThemeActionButton { objectName: "themeEditColorsButton"; text: "Edit Colors"; enabled: themeState.activeThemeIsCustom; disabledReason: "Create a custom theme before editing colors."; onClicked: appearanceSettings.editingColors = true }
                                ThemeActionButton { objectName: "themeRenameButton"; text: "Rename"; enabled: themeState.activeThemeIsCustom; disabledReason: "Built-in themes cannot be renamed. Create a custom theme first."; onClicked: { themeNameDialog.renameMode = true; themeNameField.text = themeState.activeThemeName; themeNameDialog.open() } }
                                ThemeActionButton { objectName: "themeDeleteButton"; text: "Delete"; enabled: themeState.activeThemeIsCustom; disabledReason: "Built-in themes cannot be deleted. Create a custom theme first."; onClicked: deleteThemeDialog.open() }
                                ThemeActionButton { objectName: "themeExportButton"; text: "Export Current Theme"; enabled: themeState.activeThemeIsCustom; disabledReason: "Only custom themes can be exported. Create a custom theme first."; onClicked: themeExportDialog.open() }
                            }
                            Label { text: "Display & Accessibility"; color: themeState.secondary; font.pixelSize: Theme.textSmall; font.bold: true; Layout.topMargin: 16 }
                            SettingsCheckBox { objectName: "reducedMotionControl"; text: "Reduce Motion"; checked: appState.reducedMotion; onToggled: appState.setReducedMotion(checked) }

                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: !appearanceSettings.editingColors && themeState.message.length > 0
                        text: themeState.message
                        color: themeState.foreground
                        font.pixelSize: Theme.textSmall
                        elide: Text.ElideRight
                    }

                }
            }
            Item {
                ColumnLayout {
                    anchors.fill: parent; spacing: Theme.spacingSmall
                    Label { Layout.fillWidth: true; text: "Adjust every color in this custom theme."; color: themeState.secondary; font.pixelSize: Theme.textSmall; wrapMode: Text.Wrap }
                    GridView {
                        id: colorRoles
                        objectName: "colorRoles"
                        Layout.fillWidth: true; Layout.fillHeight: true
                        property int columns: width < 480 ? 1 : 2
                        clip: true; cellWidth: width / columns; cellHeight: 52
                        model: themeState.palette
                        delegate: RowLayout {
                            required property var modelData
                            width: colorRoles.cellWidth - 8; height: colorRoles.cellHeight - 4; spacing: 7
                            Button {
                                Layout.preferredWidth: 28; Layout.preferredHeight: 28; padding: 0
                                ToolTip.text: "Choose Color"; ToolTip.visible: hovered
                                background: Rectangle { radius: Theme.radiusSmall; color: modelData.value; border.color: themeState.border; border.width: 1 }
                                onClicked: {
                                    palettePicker.role = modelData.key
                                    palettePicker.setDraft(modelData.value)
                                    palettePicker.open()
                                }
                            }
                            Label { Layout.fillWidth: true; text: modelData.label; color: themeState.foreground; elide: Text.ElideRight; font.pixelSize: 11 }
                            ThemedTextField {
                                Layout.preferredWidth: 82
                                implicitHeight: 32
                                leftPadding: 4; rightPadding: 4
                                text: modelData.value
                                maximumLength: 7
                                font.pixelSize: 11; horizontalAlignment: TextInput.AlignHCenter
                                Accessible.name: modelData.label + " hex color"
                                onEditingFinished: themeState.setColor(modelData.key, text)
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Label { Layout.fillWidth: true; text: themeState.message; textFormat: Text.PlainText; visible: text.length > 0; color: themeState.secondary; font.pixelSize: 11; wrapMode: Text.Wrap; maximumLineCount: 2 }
                        ThemeActionButton { text: "View Config"; onClicked: themeState.openConfigFile() }
                    }
                }
            }
        }
    }
    Component {
        id: themeCardDelegate
        Button {
            id: themeCard
            required property var modelData
            objectName: "themeCard-" + modelData.id
            width: GridView.view.cellWidth - 8; height: GridView.view.cellHeight - 6
            padding: 0
            checkable: true
            autoExclusive: true
            checked: modelData.active
            Accessible.name: modelData.name
            onClicked: themeState.selectTheme(modelData.id)
            background: Rectangle {
                radius: 9
                color: themeCard.modelData.active ? themeState.selected : themeCard.hovered ? themeState.hover : themeState.background
                border.color: themeCard.visualFocus || themeCard.modelData.active ? themeState.accent : themeState.border
                border.width: themeCard.visualFocus || themeCard.modelData.active ? 2 : 1
            }
            contentItem: RowLayout {
                anchors.fill: parent; anchors.margins: 9; spacing: 9
                Row {
                    spacing: -5
                    Repeater {
                        model: modelData.swatches
                        delegate: Rectangle {
                            required property string modelData
                            width: 22; height: 22; radius: 11
                            color: modelData; border.color: themeState.foreground; border.width: 1
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 1
                    Text { Layout.fillWidth: true; text: modelData.name; color: themeState.foreground; font.pixelSize: Theme.textSmall; font.bold: true; elide: Text.ElideRight }
                    Text { text: modelData.builtin ? "Built-in" : "Custom"; color: themeState.secondary; font.pixelSize: 10 }
                }
                Rectangle {
                    visible: modelData.active
                    width: 22; height: 22; radius: 11; color: themeState.accent
                    Symbol { anchors.centerIn: parent; name: "check"; width: 16; height: 16; color: themeState.onAccent }
                }
            }
        }
    }
    ThemedMenu {
        id: addThemeMenu
        objectName: "addThemeMenu"
        implicitWidth: 230
        ContextMenuItem { text: "Create from Current"; onTriggered: { themeNameDialog.renameMode = false; themeNameField.text = ""; themeNameDialog.open() } }
        ContextMenuItem { text: "Import Theme…"; onTriggered: themeImportDialog.open() }
    }
    ThemedDialog {
        id: themeNameDialog
        parent: appearanceSettings.dialogParent
        width: 390
        title: renameMode ? "Rename Theme" : "Create Custom Theme"
        property bool renameMode: false
        contentItem: ColumnLayout {
            spacing: 10
            Label { Layout.fillWidth: true; text: themeNameDialog.renameMode ? "Choose a new name for this custom theme." : "Your new theme starts with the current colors."; color: themeState.foreground; wrapMode: Text.Wrap }
            ThemedTextField { id: themeNameField; objectName: "themeNameField"; Layout.fillWidth: true; placeholderText: "Theme name"; maximumLength: 60; onAccepted: themeNameSave.clicked() }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ThemeActionButton { text: "Cancel"; onClicked: themeNameDialog.close() }
                ThemeActionButton {
                    id: themeNameSave; objectName: "themeNameSave"; text: themeNameDialog.renameMode ? "Save" : "Create"; primary: true
                    onClicked: {
                        var ok = themeNameDialog.renameMode
                            ? themeState.renameCustomTheme(themeState.activeThemeId, themeNameField.text)
                            : themeState.createCustomTheme(themeNameField.text)
                        if (ok) { themeNameDialog.close(); appearanceSettings.editingColors = true }
                    }
                }
            }
        }
    }
    ThemedDialog {
        id: deleteThemeDialog
        parent: appearanceSettings.dialogParent
        width: 390
        title: "Delete Custom Theme?"
        contentItem: ColumnLayout {
            spacing: 10
            Label { Layout.fillWidth: true; text: "Delete “" + themeState.activeThemeName + "”? Classic will become active if this is the selected theme."; color: themeState.foreground; wrapMode: Text.Wrap }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ThemeActionButton { text: "Cancel"; onClicked: deleteThemeDialog.close() }
                ThemeActionButton { text: "Delete"; primary: true; onClicked: { themeState.deleteCustomTheme(themeState.activeThemeId); deleteThemeDialog.close() } }
            }
        }
    }
    ThemedDialog {
        id: importThemeDialog
        parent: appearanceSettings.dialogParent
        width: 420
        title: "Import Theme"
        property bool replaceCustom: false
        contentItem: ColumnLayout {
            spacing: 10
            Label { Layout.fillWidth: true; text: importThemeDialog.replaceCustom ? "A custom theme already uses this name. Save to replace it, or choose another name." : "Name this imported custom theme. Built-in themes are protected and cannot be replaced."; color: themeState.foreground; wrapMode: Text.Wrap }
            ThemedTextField { id: importThemeName; Layout.fillWidth: true; placeholderText: "Theme name"; maximumLength: 60 }
            Label { Layout.fillWidth: true; text: themeState.message; visible: text.length > 0; color: themeState.error; wrapMode: Text.Wrap }
            RowLayout {
                Layout.fillWidth: true; Item { Layout.fillWidth: true }
                ThemeActionButton { text: "Cancel"; onClicked: importThemeDialog.close() }
                ThemeActionButton {
                    text: importThemeDialog.replaceCustom ? "Replace" : "Import"; primary: true
                    onClicked: {
                        if (themeState.completeImport(importThemeName.text, importThemeDialog.replaceCustom)) {
                            importThemeDialog.close(); appearanceSettings.editingColors = false
                        }
                    }
                }
            }
        }
    }
    FileDialog {
        id: themeImportDialog
        title: "Import a Theme"; fileMode: FileDialog.OpenFile
        nameFilters: ["Theme files (*.json)", "All files (*)"]
        onAccepted: {
            var result = themeState.inspectImport(selectedFile.toString())
            if (result.ok) {
                importThemeDialog.replaceCustom = !!result.conflict && !result.builtIn
                importThemeName.text = result.name
                importThemeDialog.open()
            }
        }
    }
    FileDialog {
        id: themeExportDialog
        title: "Export Custom Theme"; fileMode: FileDialog.SaveFile
        nameFilters: ["Theme files (*.json)"]
        defaultSuffix: "json"
        onAccepted: themeState.exportTheme(selectedFile.toString())
    }
    ColorPickerDialog {
        id: palettePicker
        parent: appearanceSettings.dialogParent
        onScreenPickRequested: { appearanceSettings.close(); screenPickerOverlay.show() }
    }
    Window {
        id: screenPickerOverlay
        objectName: "screenPickerOverlay"
        visible: false
        flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        color: "#01000000"
        modality: Qt.ApplicationModal
        x: colorSampler.virtualGeometry.x
        y: colorSampler.virtualGeometry.y
        width: colorSampler.virtualGeometry.width
        height: colorSampler.virtualGeometry.height
        Item {
            anchors.fill: parent
            focus: true
            Keys.onEscapePressed: { screenPickerOverlay.hide(); appearanceSettings.open(); palettePicker.open() }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.CrossCursor
                onClicked: function(mouse) {
                    colorSampler.sampleAt(Math.round(screenPickerOverlay.x + mouse.x), Math.round(screenPickerOverlay.y + mouse.y))
                    screenPickerOverlay.hide()
                }
            }
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: parent.top; anchors.topMargin: 28
                width: samplingHint.implicitWidth + 36; height: 44; radius: 22
                color: themeState.surface; border.color: themeState.border; border.width: 1
                Text { id: samplingHint; anchors.centerIn: parent; text: "Click anywhere to sample a color · Esc to cancel"; color: themeState.foreground; font.pixelSize: Theme.textBody }
            }
        }
    }
    Connections {
        target: colorSampler
        function onColorPicked(color) {
            palettePicker.setDraft(color)
            appearanceSettings.open()
            palettePicker.open()
        }
        function onPickFailed(message) {
            palettePicker.statusMessage = message
            appearanceSettings.open()
            palettePicker.open()
        }
    }
}
