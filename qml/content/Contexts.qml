import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../ui"
import "../ui/Theme.js" as T

// Contexts (the Services tool window): every conversation, grouped by story — characters with
// their recast lineage, bare contexts at the end — and a view of the selected one. New context
// lives in the header. Click selects; the pane's open-in-tab button (or the Cast panel) opens
// an editor tab.
ContentBase {
    id: panel
    property var rows: []
    property string selected: ""
    readonly property var selectedContext: selected ? app.contexts.get(selected) : null
    // the character behind the selected context, if any; re-read with `rows` so `recap due` follows the store
    readonly property var selectedCharacter: (rows, selectedContext && String(selectedContext.owner).indexOf("chr_") === 0) ? app.stories.character(selectedContext.owner) : null
    readonly property string headerSubtitle: {
        var n = 0; for (var i = 0; i < rows.length; i++) if (rows[i].status === "working" || rows[i].status === "starting") n++
        return n ? "· " + n + " live" : ""
    }
    property Component headerActions: Component {
        // one click opens a bare context on the position's own picks; the caret opens the dialog that offers them
        SplitBtn {
            mainName: "newContextButton"; menuName: "newContextMenu"
            small: true; primary: false; icon_: "plus"; text: "New context"
            items: [{ label: "New context with…", hint: "pick a model, an effort, a preset" }]
            onTriggered: panel.openBare(app.contexts.newBare(""))
            onItemTriggered: newContextDialog.open()
        }
    }
    function openBare(id) {
        if (!id) return
        selected = id
        app.layout.openContent("context", id, "New context")
    }
    NewContextDialog { id: newContextDialog; onCreated: (id) => panel.openBare(id) }

    // tree: [{story, title, contexts:[{ctx, lineage:[...]}]}, ...] + bare
    readonly property var groups: {
        var byId = {}, preds = {}
        for (var i = 0; i < rows.length; i++) { byId[rows[i].id] = rows[i]; if (rows[i].predecessor) preds[rows[i].predecessor] = rows[i].id }
        var gs = {}, order = [], bare = []
        for (i = 0; i < rows.length; i++) {
            var r = rows[i]
            if (preds[r.id]) continue                       // shown under its successor
            var lineage = [], p = r.predecessor
            while (p && byId[p]) { lineage.push(byId[p]); p = byId[p].predecessor }
            var entry = { ctx: r, lineage: lineage, aside: !!(r.about && r.about.story_key) }
            var k = entry.aside ? r.about.story_key : r.storyKey
            if (!k && r.owner === "human") { bare.push(entry); continue }
            k = k || "—"
            if (!gs[k]) { var s = k !== "—" ? app.stories.get(k) : null; gs[k] = { story: k, title: s && s.title ? s.title : "", contexts: [], asides: [] }; order.push(k) }
            (entry.aside ? gs[k].asides : gs[k].contexts).push(entry)
        }
        var out = order.map(function (k) { gs[k].contexts = gs[k].contexts.concat(gs[k].asides); return gs[k] })   // asides sit after the cast
        if (bare.length) out.push({ story: "", title: "Bare", contexts: bare })
        return out
    }
    function consumeReveal() {
        var t = app.contexts.revealTarget
        if (!t) return
        selected = t
        app.contexts.reveal("")
        paneView.focusInput()
    }
    function refresh() { rows = app.contexts.summaries() }
    Component.onCompleted: { refresh(); consumeReveal() }
    Connections { target: app.contexts; function onContextsChanged() { panel.refresh() }
                  function onRevealChanged() { panel.consumeReveal() } }
    Connections { target: app.stories; function onStoriesChanged() { panel.refresh() } }

    SplitView {
        anchors.fill: parent; orientation: Qt.Horizontal
        handle: SplitGrip {}
        Flickable {
            SplitView.preferredWidth: 320; SplitView.minimumWidth: 160; clip: true
            contentWidth: width; contentHeight: tree.implicitHeight + 8
            ScrollBar.vertical: ScrollBar {}
            Column {
                id: tree; width: parent.width; topPadding: 4
                Repeater {
                    model: panel.groups
                    delegate: Column {
                        id: grp
                        required property var modelData
                        width: tree.width
                        RowLayout {  // group header
                            width: parent.width; height: app.theme.rowHeight; spacing: 6
                            Item { width: 4 }
                            Icon { name: "down"; size: 14; color: app.theme.textMuted }
                            Text { visible: !!grp.modelData.story; text: grp.modelData.story; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize; color: app.theme.textMuted }
                            Text { text: grp.modelData.title; color: app.theme.text; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                        Repeater {
                            model: grp.modelData.contexts
                            delegate: Column {
                                id: entry
                                required property var modelData
                                width: grp.width
                                component CtxRow: Rectangle {
                                    id: cr
                                    property var ctx
                                    property bool lineageRow: false
                                    property bool asideRow: false
                                    readonly property bool sel: panel.selected === ctx.id
                                    readonly property bool isCharacter: String(ctx.owner).indexOf("chr_") === 0
                                    readonly property string display: {
                                        if (lineageRow) return ctx.contextTokens > 0 ? "recast at " + T.tokens(ctx.contextTokens) : "recast"
                                        var t = ctx.title || ""
                                        var i = t.indexOf(" · "); return isCharacter && i >= 0 ? t.slice(i + 3) : (t || ctx.id)
                                    }
                                    objectName: lineageRow ? "contextLineage_" + ctx.id : "contextRow_" + ctx.id
                                    width: entry.width; height: app.theme.rowHeight
                                    color: sel ? app.theme.selection : (rh.hovered ? app.theme.hover : "transparent")
                                    RowLayout {
                                        anchors { fill: parent; leftMargin: lineageRow ? 46 : 28; rightMargin: 10 }
                                        spacing: 8
                                        StatusDot { visible: !cr.lineageRow && !cr.asideRow; status: cr.ctx.status; size: 8 }
                                        Icon { visible: cr.asideRow; name: "aside"; size: 13; color: app.theme.textMuted }
                                        Text { objectName: "contextName_" + cr.ctx.id; text: cr.display; color: cr.lineageRow ? app.theme.textMuted : app.theme.text; font.italic: cr.lineageRow; elide: Text.ElideRight; Layout.fillWidth: true }
                                        Text { visible: !cr.lineageRow && !!cr.ctx.position && cr.ctx.position.toLowerCase() !== cr.display.toLowerCase(); text: cr.ctx.position; color: app.theme.textMuted; font.pixelSize: app.theme.fontSizeSmall }
                                        Text { objectName: "contextVitals_" + cr.ctx.id
                                               text: cr.lineageRow ? "read-only" : cr.asideRow ? "yours"
                                                   : [T.tokens(cr.ctx.contextTokens), cr.ctx.turns + "t", "$" + Number(cr.ctx.costUsd).toFixed(2)].filter(function (x) { return x }).join(" · ")
                                               color: app.theme.textDim; font.pixelSize: app.theme.fontSizeSmall }
                                    }
                                    HoverHandler { id: rh }
                                    TapHandler { onTapped: panel.selected = cr.ctx.id }
                                }
                                CtxRow { ctx: entry.modelData.ctx; asideRow: !!entry.modelData.aside }
                                Repeater { model: entry.modelData.lineage; delegate: CtxRow { required property var modelData; ctx: modelData; lineageRow: true } }
                            }
                        }
                    }
                }
            }
            // safe over the tree only because groups come from the data: with no rows there are no
            // headers to land on. A fixed group list would put it back on top of them (see StoryBoard).
            Text { visible: panel.rows.length === 0; anchors { top: parent.top; topMargin: 36; horizontalCenter: parent.horizontalCenter }
                   width: parent.width - 30; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                   text: "No contexts yet. Start a story, or open a bare one with New context."; color: app.theme.textMuted }
        }
        ColumnLayout {
            SplitView.fillWidth: true; spacing: 0
            Rectangle {
                Layout.fillWidth: true; height: 32; color: app.theme.panel
                RowLayout {
                    anchors { fill: parent; leftMargin: 12; rightMargin: 6 }
                    spacing: 8
                    StatusDot { visible: !!panel.selectedContext; status: panel.selectedContext ? panel.selectedContext.status : "none"; size: 9 }
                    Text { objectName: "paneContextTitle"; text: panel.selectedContext ? panel.selectedContext.title : "Select a context"; color: panel.selectedContext ? app.theme.text : app.theme.textDim; font.weight: Font.DemiBold; elide: Text.ElideRight }
                    Text { visible: !!panel.selectedContext; text: panel.selectedContext ? [panel.selectedContext.position, panel.selectedContext.model, panel.selectedContext.status].filter(function (x) { return x }).join(" · ") : ""; color: app.theme.textMuted; font.pixelSize: app.theme.fontSizeSmall; elide: Text.ElideRight; Layout.fillWidth: true }
                    Item { Layout.fillWidth: !panel.selectedContext }
                    Meter { visible: !!panel.selectedContext && panel.selectedContext.contextTokens > 0; Layout.preferredWidth: 72; Layout.preferredHeight: 4
                            value: panel.selectedContext ? panel.selectedContext.contextTokens : 0; max: panel.selectedContext ? panel.selectedContext.contextMax : 1
                            tick: panel.selectedCharacter ? panel.selectedContext.contextWarn : 0; hot: !!(panel.selectedCharacter && panel.selectedCharacter.recapDue) }
                    Text { objectName: "paneContextReading"; visible: !!panel.selectedContext && panel.selectedContext.contextTokens > 0
                           text: panel.selectedContext ? T.tokens(panel.selectedContext.contextTokens) + (panel.selectedCharacter && panel.selectedCharacter.recapDue ? " · recap due" : "") : ""
                           color: panel.selectedCharacter && panel.selectedCharacter.recapDue ? app.theme.needsYou : app.theme.textMuted; font.pixelSize: app.theme.fontSizeSmall }
                    Text { visible: !!panel.selectedContext; text: panel.selectedContext ? "$" + panel.selectedContext.costUsd.toFixed(3) : ""; color: app.theme.textMuted; font.pixelSize: app.theme.fontSizeSmall }
                    IconButton { objectName: "contextStop"; visible: !!panel.selectedContext && (panel.selectedContext.status === "working" || panel.selectedContext.status === "starting"); icon: "stop"; tip: "Stop"; onClicked: panel.selectedContext.stop() }
                    IconButton { objectName: "contextOpenInTab"; visible: !!panel.selectedContext; icon: "open-in-tab"; tip: "Open in a tab"
                                 onClicked: app.layout.openContent("context", panel.selected, panel.selectedContext.title) }
                }
                Divider { anchors.bottom: parent.bottom; width: parent.width }
            }
            ContextView { id: paneView; Layout.fillWidth: true; Layout.fillHeight: true; context: panel.selectedContext; showInput: !!panel.selectedContext }
        }
    }
}
