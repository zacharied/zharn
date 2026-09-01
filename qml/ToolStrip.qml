import QtQuick
import QtQuick.Controls.Basic
import "ui"

// JetBrains-style tool-window strip: an icon per panel. The left strip carries two groups —
// the left dock's panels at the top and the bottom dock's at the bottom (New UI puts bottom
// tool windows there); the right strip carries the right dock's.
Rectangle {
    id: strip
    property string side               // "left" | "right"
    property var dock                  // this side's dock
    property var bottomDock: null      // left strip only: the bottom dock's panels
    width: app.theme.stripWidth
    color: app.theme.strip
    objectName: "strip_" + side

    property int needsYou: 0
    function refreshBadges() {
        var n = 0, rows = app.stories.list()
        for (var i = 0; i < rows.length; i++) if (rows[i].needsYou) n++
        needsYou = n
    }
    property int liveContexts: 0
    function refreshLive() {
        var n = 0, rows = app.contexts.summaries()
        for (var i = 0; i < rows.length; i++) if (rows[i].status === "working" || rows[i].status === "starting") n++
        liveContexts = n
    }
    Component.onCompleted: { refreshBadges(); refreshLive() }
    Connections { target: app.stories; function onStoriesChanged() { strip.refreshBadges() } }
    Connections { target: app.contexts; function onContextsChanged() { strip.refreshLive() } }

    Rectangle {  // separator toward the content
        color: app.theme.border; width: 1; height: parent.height
        x: side === "left" ? parent.width - 1 : 0
    }

    component StripButton: Rectangle {
        id: sb
        required property var modelData          // the panel kind (Repeater delegates with required
        required property string dockSide        // properties no longer get modelData implicitly)
        required property var dockData
        readonly property string panel: modelData
        readonly property bool isActive: dockData.active === panel && dockData.mode === "docked"
        readonly property int badge: panel === "board" ? strip.needsYou : 0
        readonly property bool dot: panel === "contexts" && strip.liveContexts > 0
        objectName: "stripButton_" + panel
        width: 28; height: 28; radius: app.theme.radiusLarge
        color: isActive || hover.hovered ? app.theme.hover : "transparent"
        Icon { anchors.centerIn: parent; name: app.content.iconFor(sb.panel); size: 20
               color: sb.isActive || hover.hovered ? app.theme.text : app.theme.textMuted }
        Rectangle {  // needs-you count
            visible: sb.badge > 0
            objectName: "stripBadge_" + sb.panel
            x: parent.width - width + 4; y: -3
            height: 15; width: Math.max(15, badgeText.implicitWidth + 8); radius: 8; color: app.theme.needsYou
            Text { id: badgeText; anchors.centerIn: parent; text: sb.badge; color: app.theme.bg; font.pixelSize: 10; font.weight: Font.DemiBold }
        }
        Rectangle {  // live dot
            visible: sb.dot; x: parent.width - 9; y: 2; width: 7; height: 7; radius: 4
            color: app.theme.live; border.color: app.theme.strip; border.width: 2
        }
        HoverHandler { id: hover }
        TapHandler { onTapped: app.layout.togglePanel(sb.dockSide, sb.panel) }
        ToolTip.visible: hover.hovered; ToolTip.text: app.content.titleFor(sb.panel); ToolTip.delay: 600
    }

    Column {
        anchors { top: parent.top; topMargin: 6; horizontalCenter: parent.horizontalCenter }
        spacing: 4
        Repeater {
            model: strip.dock ? strip.dock.panels : []
            delegate: StripButton { dockSide: strip.side; dockData: strip.dock }
        }
    }
    Column {
        visible: !!strip.bottomDock
        anchors { bottom: parent.bottom; bottomMargin: 6; horizontalCenter: parent.horizontalCenter }
        spacing: 4
        Repeater {
            model: strip.bottomDock ? strip.bottomDock.panels : []
            delegate: StripButton { dockSide: "bottom"; dockData: strip.bottomDock }
        }
    }
}
