import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../ui"
import "../ui/Theme.js" as T

// Stories: a tree by phase (the Project tool window, not a kanban — it survives a narrow dock).
// Stories waiting on you sort first in their phase, carry their flavor in amber, and are counted
// in the header; a working cast shows as a live dot.
ContentBase {
    id: board
    readonly property var phases: [
        { phase: "planning", title: "Planning" }, { phase: "implementing", title: "Implementing" },
        { phase: "todo", title: "Todo" }, { phase: "backlog", title: "Backlog" },
        { phase: "done", title: "Done" }, { phase: "canceled", title: "Canceled" }
    ]
    property var rows: app.stories.list()
    readonly property int needsYouCount: rows.filter(function (r) { return r.needsYou }).length
    property var collapsed: ({ done: true, canceled: true })
    Connections { target: app.stories; function onStoriesChanged() { board.rows = app.stories.list() } }
    function inPhase(phase) {
        return rows.filter(function (r) { return r.phase === phase })
                   .sort(function (a, b) { return (b.needsYou - a.needsYou) || (a.createdAt - b.createdAt) })
    }
    function toggle(phase) { var c = Object.assign({}, collapsed); c[phase] = !c[phase]; collapsed = c }

    // the story of the active editor tab is the selected row
    readonly property string selectedKey: {
        var tree = JSON.parse(app.layout.layoutJson), gid = app.layout.activeGroup
        function find(node) {
            if (!node) return null
            if (node.type === "tabs") return node.id === gid ? node : null
            for (var i = 0; i < node.children.length; i++) { var f = find(node.children[i]); if (f) return f }
            return null
        }
        var g = find(tree.center)
        if (!g || !g.tabs.length) return ""
        var t = g.tabs[g.active]
        return t.kind === "story" ? t.key : ""
    }

    // header contributions (see Dock.qml)
    property Component headerBadge: Component {
        Chip { objectName: "needsYouCount"; visible: board.needsYouCount > 0; fg: app.theme.needsYou
               text: board.needsYouCount + (board.needsYouCount === 1 ? " needs you" : " need you") }
    }

    Flickable {
        anchors.fill: parent; clip: true
        contentWidth: width; contentHeight: tree.implicitHeight + 8
        ScrollBar.vertical: ScrollBar {}
        Column {
            id: tree
            width: parent.width; topPadding: 4
            Repeater {
                model: board.phases
                delegate: Column {
                    id: grp
                    required property var modelData
                    readonly property var cards: board.inPhase(modelData.phase)
                    readonly property bool open: !board.collapsed[modelData.phase]
                    readonly property color phaseColor: T.phaseColor(app.theme, modelData.phase)
                    width: tree.width
                    visible: board.rows.length > 0 && (modelData.phase !== "canceled" || cards.length > 0)
                    Rectangle {  // group header
                        objectName: "treeGroup_" + grp.modelData.phase
                        property int count: grp.cards.length
                        width: parent.width; height: app.theme.rowHeight
                        color: gh.hovered ? app.theme.hover : "transparent"
                        RowLayout {
                            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                            spacing: 6
                            Icon { name: grp.open ? "down" : "right"; size: 14; color: app.theme.textMuted }
                            Text { text: grp.modelData.title; color: grp.phaseColor; font.weight: Font.DemiBold }
                            Item { Layout.fillWidth: true }
                            Text { text: grp.cards.length; color: grp.phaseColor; opacity: 0.75; font.pixelSize: app.theme.fontSize }
                        }
                        HoverHandler { id: gh }
                        TapHandler { onTapped: board.toggle(grp.modelData.phase) }
                    }
                    Repeater {
                        model: grp.open ? grp.cards : []
                        delegate: Rectangle {
                            id: card
                            required property var modelData
                            readonly property bool selected: modelData.key === board.selectedKey
                            objectName: "card_" + modelData.key
                            width: tree.width; height: app.theme.rowHeight
                            color: selected ? app.theme.selection : (ch.hovered ? app.theme.hover : "transparent")
                            RowLayout {
                                anchors { fill: parent; leftMargin: 30; rightMargin: 10 }
                                spacing: 8
                                Text { text: card.modelData.key; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize
                                       color: card.selected ? app.theme.selectedKey : app.theme.textMuted; Layout.preferredWidth: 46 }
                                Text { text: card.modelData.title; color: app.theme.text; elide: Text.ElideRight; Layout.fillWidth: true
                                       font.weight: card.modelData.needsYou ? Font.Medium : Font.Normal }
                                StatusDot { visible: card.modelData.workingCount > 0; status: "working"; size: 7 }
                                Text { objectName: "cardBadge_" + card.modelData.key; visible: card.modelData.needsYou
                                       text: card.modelData.flavor; color: app.theme.needsYou; font.pixelSize: app.theme.fontSizeSmall }
                                Text {  // a character's sub-story is its business, not yours (AGENT-MODEL §9)
                                    readonly property var author: card.modelData.parentStory ? app.stories.character(card.modelData.author) : null
                                    visible: !!card.modelData.parentStory && !card.modelData.needsYou
                                    text: "sub-story · " + (author ? author.name : "")
                                    color: app.theme.textDim; font.pixelSize: app.theme.fontSizeSmall
                                }
                            }
                            HoverHandler { id: ch }
                            TapHandler { onTapped: app.layout.openContent("story", card.modelData.key, card.modelData.key + "  " + card.modelData.title) }
                        }
                    }
                }
            }
            Text {  // last in the flow, so a section that draws pushes it down instead of under it
                objectName: "emptyStories"
                visible: board.rows.length === 0
                width: tree.width; topPadding: 36; leftPadding: 20; rightPadding: 20
                horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                text: "No stories yet. Press New story in the toolbar to write the first one."; color: app.theme.textMuted
            }
        }
    }
}
