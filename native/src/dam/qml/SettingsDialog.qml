import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Theme.js" as Theme
import "components"

Popup {
    id: root
    objectName: "settingsDialog"
    property var sections: []
    property Item currentPage
    property alias pageArea: pageArea
    anchors.centerIn: Overlay.overlay
    width: Math.min(1040, Overlay.overlay ? Overlay.overlay.width - 32 : 1040)
    height: Math.min(760, Overlay.overlay ? Overlay.overlay.height - 32 : 760)
    padding: 16
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    background: Rectangle { radius: Theme.radiusLarge; color: themeState.surface; border.color: themeState.border }
    function showPage(page) {
        currentPage = page
        open()
    }
    contentItem: ColumnLayout {
        spacing: Theme.spacingLarge
        RowLayout {
            Layout.fillWidth: true
            Label { text: "Settings"; font.pixelSize: 20; font.bold: true; color: themeState.foreground; Layout.fillWidth: true }
            IconButton { objectName: "closeSettings"; iconName: "close"; tip: "Close Settings"; implicitWidth: 36; implicitHeight: 36; onClicked: root.close() }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.spacingLarge
            ScrollView {
                id: navigation
                objectName: "settingsNavigation"
                Layout.preferredWidth: root.width < 700 ? 144 : 184
                Layout.fillHeight: true
                contentWidth: availableWidth
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                Column {
                    width: navigation.availableWidth
                    spacing: Theme.spacingLarge
                    Repeater {
                        model: root.sections
                        Column {
                            required property var modelData
                            width: parent.width
                            spacing: 4
                            Label { width: parent.width; leftPadding: 12; bottomPadding: 4; text: modelData.title; wrapMode: Text.Wrap; font.pixelSize: Theme.textBody; font.bold: true; color: themeState.foreground }
                            Repeater {
                                model: modelData.pages
                                Button {
                                    required property var modelData
                                    objectName: "settingsNav-" + modelData.objectName
                                    width: parent.width
                                    implicitHeight: Math.max(40, contentItem.implicitHeight + 16)
                                    padding: 12
                                    text: modelData.title
                                    checkable: true
                                    autoExclusive: true
                                    checked: root.currentPage === modelData
                                    Accessible.name: text
                                    onClicked: root.showPage(modelData)
                                    contentItem: Text { text: parent.text; font.pixelSize: 13; color: themeState.foreground; wrapMode: Text.Wrap; verticalAlignment: Text.AlignVCenter }
                                    background: Rectangle {
                                        radius: 9
                                        color: parent.checked ? themeState.selected : parent.hovered ? themeState.hover : "transparent"
                                        border.width: parent.visualFocus ? 2 : parent.checked ? 1 : 0
                                        border.color: themeState.accent
                                    }
                                }
                            }
                        }
                    }
                }
            }
            Rectangle { Layout.fillHeight: true; width: 1; color: themeState.border }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.fillHeight: true
                spacing: Theme.spacingLarge
                Label {
                    Layout.fillWidth: true
                    visible: root.currentPage && !root.currentPage.ownHeading
                    text: root.currentPage ? root.currentPage.title : ""
                    font.pixelSize: 18; font.bold: true; color: themeState.foreground; wrapMode: Text.Wrap
                }
                Item { id: pageArea; objectName: "settingsPageArea"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true }
            }
        }
    }
}
