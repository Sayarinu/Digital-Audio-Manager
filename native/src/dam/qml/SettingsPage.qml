import QtQuick
import QtQuick.Controls

Pane {
    id: root
    required property var host
    property string title: ""
    property bool ownHeading: false
    readonly property bool opened: visible && host.opened
    signal closed()
    parent: host.pageArea
    anchors.fill: parent
    visible: host.visible && host.currentPage === root
    padding: 0
    background: null
    onOpenedChanged: if (!opened) closed()
    function open() { host.showPage(root) }
    function close() { host.close() }
}
