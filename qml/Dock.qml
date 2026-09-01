import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "ui"

// A docked tool window: header + the active panel's content. Switching panels on a side is the
// strip's job (one icon per panel); the header only carries the panel's own actions and Hide.
Rectangle {
    id: dockItem
    property string side
    property var dock
    color: app.theme.panel
    objectName: "dock_" + side

    // The active panel may contribute header actions by setting `headerActions` on its root
    // (a Component); `headerSubtitle` likewise. Both are optional.
    readonly property var panelItem: content.item

    ColumnLayout {
        anchors.fill: parent; spacing: 0
        ToolWindowHeader {
            Layout.fillWidth: true
            title: dockItem.dock.active ? app.content.titleFor(dockItem.dock.active) : ""
            subtitle: dockItem.panelItem && dockItem.panelItem.headerSubtitle !== undefined ? dockItem.panelItem.headerSubtitle : ""
            Loader { sourceComponent: dockItem.panelItem && dockItem.panelItem.headerActions !== undefined ? dockItem.panelItem.headerActions : null }
            IconButton { objectName: "dockHide_" + dockItem.side; icon: "hide"; tip: "Hide"; onClicked: app.layout.setDockMode(dockItem.side, "strip") }
        }
        Divider { Layout.fillWidth: true }
        Loader {
            id: content
            objectName: "dockContent_" + dockItem.side
            Layout.fillWidth: true; Layout.fillHeight: true
            source: dockItem.dock.active ? app.content.qmlFor(dockItem.dock.active) : ""
        }
    }
    Rectangle {  // edge line toward the center
        color: app.theme.border
        width: side === "bottom" ? parent.width : 1
        height: side === "bottom" ? 1 : parent.height
        x: side === "left" ? parent.width - 1 : 0
    }
}
