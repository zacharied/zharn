import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../ui"

// Cast: the characters of the story in the active editor tab (the Structure tool window follows
// the editor the same way), with the derived state of lifecycle §6 — working on #n / waiting /
// idle / retired, owes/awaits, fork provenance, inbox depth — a Recast button each, and the
// story's open sub-stories. Sticky: stays on the last story when a non-story tab is focused.
ContentBase {
    id: cast
    property string storyKey: ""
    property var story: ({})
    property var members: []
    property var substories: []
    readonly property string headerSubtitle: storyKey ? "· " + storyKey : ""

    function activeStoryKey() {
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
        if (t.kind === "story") return t.key
        if (t.kind === "context") { var c = app.contexts.get(t.key); return c ? c.storyKey : "" }
        return ""
    }
    function follow() { var k = activeStoryKey(); if (k) storyKey = k; refresh() }
    function refresh() {
        story = storyKey ? app.stories.get(storyKey) : {}
        members = storyKey ? app.stories.cast(storyKey) : []
        substories = storyKey ? app.stories.list().filter(function (r) { return r.parentStory === storyKey }) : []
    }
    function threadNumber(tid) {
        var ts = story.threads || []
        for (var i = 0; i < ts.length; i++) if (ts[i].id === tid) return ts[i].n
        return 0
    }
    function place(id) {  // an awaited thread id → "#n"; an awaited sub-story key stays a key
        var n = threadNumber(id)
        return n ? "#" + n : id
    }
    function memberName(id) {
        for (var i = 0; i < members.length; i++) if (members[i].id === id) return members[i].name
        return id
    }
    Component.onCompleted: follow()
    Connections { target: app.layout; function onLayoutChanged() { cast.follow() } }
    Connections { target: app.stories; function onStoriesChanged() { cast.refresh() } }
    Connections { target: app.contexts; function onContextsChanged() { cast.refresh() } }

    RecastDialog { id: recastDialog; storyKey: cast.storyKey }
    function openRecast(m) {
        recastDialog.characterId = m.id
        recastDialog.characterName = m.name
        recastDialog.currentRole = m.role
        recastDialog.open()
    }

    Flickable {
        anchors.fill: parent; clip: true
        contentWidth: width; contentHeight: col.implicitHeight + 8
        ScrollBar.vertical: ScrollBar {}
        Column {
            id: col
            width: parent.width; topPadding: 4
            Repeater {
                model: cast.members
                delegate: Rectangle {
                    id: m
                    required property var modelData
                    readonly property bool isProtagonist: modelData.id === cast.story.protagonist
                    readonly property bool asksYou: isProtagonist && cast.story.ball === "author" && modelData.status !== "retired"
                    readonly property bool retired: modelData.status === "retired"
                    readonly property var ctx: modelData.live_context ? app.contexts.get(modelData.live_context) : null
                    readonly property int attending: cast.threadNumber(modelData.attention)
                    objectName: "castRow_" + modelData.id
                    width: col.width; height: body.implicitHeight + 16
                    color: mh.hovered ? app.theme.hover : "transparent"
                    opacity: retired ? 0.55 : 1
                    RowLayout {
                        id: body
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8; leftMargin: 12 }
                        spacing: 8
                        Item { Layout.preferredWidth: 16; Layout.preferredHeight: 16; Layout.alignment: Qt.AlignTop
                               Ball { visible: m.asksYou; anchors.centerIn: parent; mine: true }
                               StatusDot { visible: !m.asksYou; anchors.centerIn: parent; size: 10
                                           status: m.retired ? "none" : m.modelData.contextStatus } }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 3
                            Row { spacing: 6
                                  Text { text: m.modelData.name; color: app.theme.text; font.weight: Font.Medium }
                                  Text { readonly property string role: m.modelData.role !== m.modelData.name ? m.modelData.role : ""
                                         readonly property string fork: m.modelData.forkedFrom ? "forked from " + cast.memberName(m.modelData.forkedFrom) : ""
                                         text: [role, m.ctx && m.ctx.model ? m.ctx.model : "", fork].filter(function (x) { return x }).join(" · ")
                                         color: app.theme.textMuted; elide: Text.ElideRight } }
                            Text {
                                objectName: "castStatus_" + m.modelData.id
                                Layout.fillWidth: true; elide: Text.ElideRight; font.pixelSize: app.theme.fontSizeSmall
                                color: m.asksYou ? app.theme.needsYou : app.theme.textMuted
                                text: m.asksYou ? "waits on you · " + cast.story.flavor
                                    : m.modelData.status === "working" ? (m.attending ? "working on #" + m.attending : "working")
                                    : m.modelData.status === "waiting" ? "waiting · awaits " + m.modelData.awaits.map(cast.place).join(", ")
                                    : m.modelData.status === "retired" ? "retired"
                                    : m.modelData.contextStatus === "failed" ? "failed"
                                    : m.attending ? "idle · attending #" + m.attending : "idle"
                            }
                            Text {
                                Layout.fillWidth: true; elide: Text.ElideRight; font.pixelSize: app.theme.fontSizeSmall; color: app.theme.textDim
                                text: "inbox " + (m.modelData.inboxDepth || 0)
                                      + (m.modelData.owes.length ? " · owes " + m.modelData.owes.map(cast.place).join(", ") : "")
                                      + (m.ctx ? " · " + m.ctx.turns + (m.ctx.turns === 1 ? " turn" : " turns") + " · $" + m.ctx.costUsd.toFixed(2) : "")
                            }
                        }
                        Btn { objectName: "recastButton_" + m.modelData.id; visible: !m.retired; Layout.alignment: Qt.AlignTop
                              small: true; quiet: true; text: "Recast"; onClicked: cast.openRecast(m.modelData) }
                    }
                    HoverHandler { id: mh }
                    TapHandler { onTapped: if (m.modelData.live_context) app.layout.openContent("context", m.modelData.live_context, cast.storyKey + " · " + m.modelData.name) }
                }
            }
            Item { visible: cast.substories.length > 0; width: 1; height: 8 }
            RowLayout {
                visible: cast.substories.length > 0
                width: parent.width; height: app.theme.rowHeight; spacing: 6
                Item { width: 6 }
                Icon { name: "story"; size: 14; color: app.theme.textDim }
                Text { text: "Sub-stories"; color: app.theme.textMuted; font.weight: Font.DemiBold; font.pixelSize: 12 }
            }
            Repeater {
                model: cast.substories
                delegate: Rectangle {
                    id: sub
                    required property var modelData
                    objectName: "substoryRow_" + modelData.key
                    width: col.width; height: app.theme.rowHeight
                    color: sh.hovered ? app.theme.hover : "transparent"
                    RowLayout {
                        anchors { fill: parent; leftMargin: 30; rightMargin: 10 }
                        spacing: 8
                        Text { text: sub.modelData.key; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize; color: app.theme.textMuted }
                        Text { text: sub.modelData.title; color: app.theme.text; elide: Text.ElideRight; Layout.fillWidth: true }
                        Text { text: sub.modelData.phase + (sub.modelData.ball ? " · " + sub.modelData.ball : ""); font.pixelSize: app.theme.fontSizeSmall
                               color: sub.modelData.needsYou ? app.theme.needsYou : app.theme.textDim }
                    }
                    HoverHandler { id: sh }
                    TapHandler { onTapped: app.layout.openContent("story", sub.modelData.key, sub.modelData.key + "  " + sub.modelData.title) }
                }
            }
        }
        Text {
            visible: cast.members.length === 0
            anchors { top: parent.top; topMargin: 40; horizontalCenter: parent.horizontalCenter }
            width: parent.width - 40; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
            text: cast.storyKey ? "No cast yet — Start the story to cast its protagonist." : "Open a story to see its cast."
            color: app.theme.textMuted
        }
    }
}
