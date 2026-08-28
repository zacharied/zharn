import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// A docked tool window: header + the active panel's content.
Rectangle {
    id: dockItem
    property string side
    property var dock
    color: app.theme.panel
    objectName: "dock_" + side

    ColumnLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            Layout.fillWidth: true; height: 30; color: app.theme.panel
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 4
                Label { text: dockItem.dock.active ? app.content.titleFor(dockItem.dock.active) : ""; color: app.theme.text; font.bold: true }
                Item { Layout.fillWidth: true }
                Repeater {  // quick switch between panels living on this side
                    model: dockItem.dock.panels.length > 1 ? dockItem.dock.panels : []
                    delegate: Label {
                        text: app.content.iconFor(modelData)
                        color: modelData === dockItem.dock.active ? app.theme.text : app.theme.textMuted
                        padding: 4
                        TapHandler { onTapped: app.layout.togglePanel(dockItem.side, modelData) }
                    }
                }
                Label {
                    text: "—"; color: app.theme.textMuted; padding: 4
                    TapHandler { onTapped: app.layout.setDockMode(dockItem.side, "strip") }
                    ToolTip.visible: hh.hovered; ToolTip.text: "Hide"; HoverHandler { id: hh }
                }
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: app.theme.border }
        }
        Loader {
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
        y: 0
    }
}
