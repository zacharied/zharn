import QtQuick

// JetBrains-style tool-window strip: one button per panel on this side.
Rectangle {
    id: strip
    property string side
    property var dock
    readonly property bool vertical: side !== "bottom"
    implicitWidth: 30; implicitHeight: 30
    width: vertical ? 30 : undefined
    height: vertical ? undefined : 30
    color: app.theme.strip
    objectName: "strip_" + side

    Rectangle {  // separator line toward the content
        color: app.theme.border
        width: vertical ? 1 : parent.width; height: vertical ? parent.height : 1
        x: side === "left" ? parent.width - 1 : 0
        y: side === "bottom" ? 0 : 0
    }

    Grid {
        columns: vertical ? 1 : 100
        rows: vertical ? 100 : 1
        anchors { top: parent.top; left: parent.left; topMargin: vertical ? 6 : 0; leftMargin: vertical ? 0 : 8 }
        spacing: 2
        Repeater {
            model: strip.dock ? strip.dock.panels : []
            delegate: Rectangle {
                objectName: "stripButton_" + modelData
                readonly property bool isActive: strip.dock.active === modelData && strip.dock.mode === "docked"
                width: strip.vertical ? 30 : label.implicitWidth + 18
                height: strip.vertical ? label.implicitWidth + 18 : 30
                color: isActive ? app.theme.accentSoft : (hover.hovered ? app.theme.border : "transparent")
                radius: 3
                Text {
                    id: label
                    text: app.content.iconFor(modelData) + " " + app.content.titleFor(modelData)
                    color: isActive ? app.theme.text : app.theme.textMuted
                    font.pixelSize: 12
                    anchors.centerIn: parent
                    rotation: strip.vertical ? (strip.side === "left" ? -90 : 90) : 0
                }
                HoverHandler { id: hover }
                TapHandler { onTapped: app.layout.togglePanel(strip.side, modelData) }
            }
        }
    }
}
