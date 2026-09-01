import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../ui"

// Cast: the characters of the story in the active editor tab (the Structure tool window follows
// the editor the same way). Sticky: stays on the last story when a non-story tab is focused.
ContentBase {
    id: cast
    property string storyKey: ""
    property var story: ({})
    property var members: []
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
    }
    function threadNumber(tid) {
        var ts = story.threads || []
        for (var i = 0; i < ts.length; i++) if (ts[i].id === tid) return ts[i].n
        return 0
    }
    Component.onCompleted: follow()
    Connections { target: app.layout; function onLayoutChanged() { cast.follow() } }
    Connections { target: app.stories; function onStoriesChanged() { cast.refresh() } }
    Connections { target: app.contexts; function onContextsChanged() { cast.refresh() } }

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
                    readonly property bool asksYou: isProtagonist && cast.story.ball === "author"
                    readonly property var ctx: modelData.live_context ? app.contexts.get(modelData.live_context) : null
                    readonly property string status: modelData.contextStatus
                    readonly property int attending: cast.threadNumber(modelData.attention)
                    objectName: "castRow_" + modelData.id
                    width: col.width; height: body.implicitHeight + 16
                    color: mh.hovered ? app.theme.hover : "transparent"
                    GridLayout {
                        id: body
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8; leftMargin: 12 }
                        columns: 2; columnSpacing: 8; rowSpacing: 3
                        Item { width: 16; height: 16
                               Ball { visible: m.asksYou; anchors.centerIn: parent; mine: true }
                               StatusDot { visible: !m.asksYou; anchors.centerIn: parent; status: m.status; size: 10 } }
                        Row { spacing: 6
                              Text { text: m.modelData.name; color: app.theme.text; font.weight: Font.Medium }
                              Text { readonly property string role: m.modelData.role !== m.modelData.name ? m.modelData.role : ""
                                     text: [role, m.ctx ? m.ctx.model : ""].filter(function (x) { return x }).join(" · "); color: app.theme.textMuted } }
                        Item { width: 16; height: 1 }
                        Text {
                            Layout.fillWidth: true; elide: Text.ElideRight; font.pixelSize: app.theme.fontSizeSmall
                            color: m.asksYou ? app.theme.needsYou : app.theme.textMuted
                            text: m.asksYou ? "waits on you · " + cast.story.flavor
                                : (m.status === "working" || m.status === "starting") ? (m.attending ? "busy on #" + m.attending : "busy")
                                : m.status === "failed" ? "failed" : m.status === "stopped" ? "stopped"
                                : m.attending ? "idle · attending #" + m.attending : "idle"
                        }
                        Item { width: 16; height: 1 }
                        Text {
                            Layout.fillWidth: true; elide: Text.ElideRight; font.pixelSize: app.theme.fontSizeSmall; color: app.theme.textDim
                            text: "inbox " + (m.modelData.inbox ? m.modelData.inbox.length : 0)
                                  + (m.ctx ? " · " + m.ctx.turns + (m.ctx.turns === 1 ? " turn" : " turns") + " · $" + m.ctx.costUsd.toFixed(2) : "")
                        }
                    }
                    HoverHandler { id: mh }
                    TapHandler { onTapped: if (m.modelData.live_context) app.layout.openContent("context", m.modelData.live_context, cast.storyKey + " · " + m.modelData.name) }
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
