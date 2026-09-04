import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../ui"

// Documents: the workspace's markdown as a tree of sections (spec docs/specs/documents-panel.md).
// Rows come flat from app.documents.model (expansion lives in Python); the selected row is the current
// section of the active document tab; typing filters by heading into a results list.
ContentBase {
    id: panel
    property string filter: ""
    property var results: []
    property string activeKey: ""
    property int position: -1
    property var openKeys: ({})     // key -> true for every document tab open in the layout
    readonly property bool filtering: filter.length > 0

    property Component headerActions: Component {
        IconButton { objectName: "docCollapseAll"; icon: "collapse"; tip: "Collapse all"; onClicked: app.documents.collapseAll() }
    }

    // the document of the active editor tab, if it is one, and which documents have a tab at all
    function readActive() {
        var lay = JSON.parse(app.layout.layoutJson), gid = app.layout.activeGroup, open = {}, active = null
        function walk(node) {
            if (!node) return
            if (node.type === "tabs") {
                for (var i = 0; i < node.tabs.length; i++) if (node.tabs[i].kind === "document") open[node.tabs[i].key] = true
                if (node.id === gid) active = node
                return
            }
            for (var j = 0; j < node.children.length; j++) walk(node.children[j])
        }
        walk(lay.center)
        openKeys = open
        var g = active
        var t = g && g.tabs.length ? g.tabs[g.active] : null
        activeKey = t && t.kind === "document" ? t.key : ""
        position = activeKey ? app.documents.position(activeKey) : -1
        reveal()
    }
    function reveal() {   // keep the selected row in view
        for (var i = 0; i < tree.count; i++) {
            var r = app.documents.model.get(i)
            if (r.key === activeKey && (r.kind === "sec" ? r.ordinal === position : r.kind === "doc" && position < 0)) { tree.positionViewAtIndex(i, ListView.Contain); return }
        }
    }
    function refreshResults() { results = filtering ? app.documents.search(filter) : [] }
    function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") }
    function highlight(text) {   // every filter word, bold in the accent
        var out = esc(text), words = filter.toLowerCase().split(/\s+/).filter(function (w) { return w })
        for (var i = 0; i < words.length; i++) {
            var re = new RegExp("(" + words[i].replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig")
            out = out.replace(re, '<b><font color="' + app.theme.accentHover + '">$1</font></b>')
        }
        return out
    }
    // A hidden panel is not worth walking the repos for, so the periodic rescan skips one — which makes
    // showing the panel the moment to catch up. The dock keeps a hidden panel loaded, so this has to
    // hang off visibility, not just onCompleted.
    Component.onCompleted: { app.documents.rescan(); readActive(); tree.forceActiveFocus() }
    onVisibleChanged: if (visible) app.documents.rescan()
    onFilterChanged: refreshResults()
    Connections { target: app.layout; function onLayoutChanged() { panel.readActive() } }
    Connections {
        target: app.documents
        function onDocumentsChanged() { panel.refreshResults(); panel.reveal() }
        function onPositionChanged(key) { if (key === panel.activeKey) { panel.position = app.documents.position(key); panel.reveal() } }
    }

    ColumnLayout {
        anchors.fill: parent; spacing: 0
        Field {
            id: filterField
            objectName: "docFilter"
            Layout.fillWidth: true; Layout.margins: 8; Layout.topMargin: 4; Layout.bottomMargin: 4
            implicitHeight: 26
            visible: panel.filtering || activeFocus
            onTextEdited: panel.filter = text
            Keys.onEscapePressed: { text = ""; panel.filter = ""; tree.forceActiveFocus() }
            Keys.onDownPressed: { if (panel.filtering) resultsView.forceActiveFocus() }
        }

        // ---- the tree
        ListView {
            id: tree
            objectName: "docTree"
            Layout.fillWidth: true; Layout.fillHeight: true
            visible: !panel.filtering
            clip: true; model: panel.filtering ? null : app.documents.model
            topMargin: 4; bottomMargin: 4
            keyNavigationEnabled: true
            ScrollBar.vertical: ScrollBar {}
            Keys.onPressed: function (event) {
                var r = currentIndex >= 0 ? app.documents.model.get(currentIndex) : null
                if (event.text.length === 1 && event.text >= " " && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier))) {
                    filterField.text = event.text; panel.filter = event.text; filterField.forceActiveFocus(); filterField.cursorPosition = 1; event.accepted = true
                } else if (r && event.key === Qt.Key_Right && r.hasChildren && !r.expanded) { app.documents.toggle(r.id); event.accepted = true }
                else if (r && event.key === Qt.Key_Left && r.expanded) { app.documents.toggle(r.id); event.accepted = true }
                else if (r && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) {
                    if (r.kind === "doc" || r.kind === "sec") app.documents.open(r.key, r.ordinal); else app.documents.toggle(r.id)
                    event.accepted = true
                }
            }
            delegate: Rectangle {
                id: row
                required property int index
                required property var model
                readonly property bool selected: model.key === panel.activeKey && model.kind !== "repo" && model.kind !== "dir"
                                                 && (model.kind === "sec" ? model.ordinal === panel.position : panel.position < 0)
                objectName: "docRow_" + model.id
                width: tree.width; height: app.theme.rowHeight
                color: selected ? app.theme.selection : (rh.hovered ? app.theme.hover : "transparent")
                RowLayout {
                    anchors { fill: parent; leftMargin: 10 + 18 * row.model.level; rightMargin: 10 }
                    spacing: 6
                    Item {   // the chevron column: kept for leaves so siblings align
                        objectName: "docChevron_" + row.model.id
                        width: 14; height: 14
                        Icon { anchors.fill: parent; visible: row.model.hasChildren; name: row.model.expanded ? "down" : "right"; size: 14; color: app.theme.textDim }
                        TapHandler { enabled: row.model.hasChildren; onTapped: { tree.forceActiveFocus(); app.documents.toggle(row.model.id) } }
                    }
                    Text {
                        visible: row.model.kind === "sec" && row.model.column
                        text: row.model.number; width: 24; horizontalAlignment: Text.AlignRight
                        font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize
                        color: row.selected ? app.theme.selectedKey : app.theme.textMuted
                        Layout.preferredWidth: 24
                    }
                    Text {
                        text: row.model.title; elide: Text.ElideRight; Layout.fillWidth: true
                        color: row.model.kind === "dir" ? app.theme.textMuted : app.theme.text
                        font.pixelSize: app.theme.fontSize
                        font.weight: row.model.kind === "repo" ? Font.DemiBold
                                   : (row.model.kind === "doc" && panel.openKeys[row.model.key] ? Font.Medium : Font.Normal)
                    }
                    Text { visible: row.model.kind === "repo"; text: row.model.count; color: app.theme.textMuted; font.pixelSize: app.theme.fontSize }
                }
                HoverHandler { id: rh }
                TapHandler {
                    onTapped: {
                        tree.forceActiveFocus()      // so type-to-filter follows a click, not only the keyboard
                        tree.currentIndex = row.index
                        if (row.model.kind === "doc" || row.model.kind === "sec") app.documents.open(row.model.key, row.model.ordinal)
                        else app.documents.toggle(row.model.id)
                    }
                }
            }
            Loader {
                active: !panel.filtering && tree.count === 0
                anchors { top: parent.top; topMargin: 40; horizontalCenter: parent.horizontalCenter }
                width: parent.width - 40
                sourceComponent: Text {
                    objectName: "docEmpty"
                    width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                    text: "No markdown documents in the registered repos."; color: app.theme.textMuted
                }
            }
        }

        // ---- filter results: sections grouped by document, titles wrap
        ListView {
            id: resultsView
            objectName: "docResults"
            Layout.fillWidth: true; Layout.fillHeight: true
            visible: panel.filtering
            clip: true; topMargin: 4
            ScrollBar.vertical: ScrollBar {}
            model: panel.results
            delegate: Column {
                id: group
                required property var modelData
                width: resultsView.width
                Rectangle {
                    objectName: "docResult_" + group.modelData.key
                    width: parent.width; height: app.theme.rowHeight
                    color: gh.hovered ? app.theme.hover : "transparent"
                    RowLayout {
                        anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                        Text { textFormat: Text.RichText; text: panel.highlight(group.modelData.name); color: app.theme.text; font.weight: Font.Medium; elide: Text.ElideRight; Layout.fillWidth: true }
                        Text { text: group.modelData.repo; color: app.theme.textDim; font.pixelSize: app.theme.fontSizeSmall }
                    }
                    HoverHandler { id: gh }
                    TapHandler { onTapped: app.documents.open(group.modelData.key, -1) }
                }
                Repeater {
                    model: group.modelData.sections
                    delegate: Rectangle {
                        id: hit
                        required property var modelData
                        objectName: "docResult_" + group.modelData.key + "#" + modelData.index
                        width: group.width; height: Math.max(app.theme.rowHeight, hitText.implicitHeight + 8)
                        color: hh.hovered ? app.theme.hover : "transparent"
                        RowLayout {
                            anchors { fill: parent; leftMargin: 28; rightMargin: 10; topMargin: 4; bottomMargin: 4 }
                            spacing: 6
                            Text { visible: hit.modelData.number.length > 0; text: hit.modelData.number; Layout.preferredWidth: 24; horizontalAlignment: Text.AlignRight
                                   font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize; color: app.theme.textMuted; Layout.alignment: Qt.AlignTop }
                            Text { id: hitText; textFormat: Text.RichText; text: panel.highlight(hit.modelData.title); wrapMode: Text.Wrap
                                   color: app.theme.text; Layout.fillWidth: true }
                        }
                        HoverHandler { id: hh }
                        TapHandler { onTapped: app.documents.open(group.modelData.key, hit.modelData.index) }
                    }
                }
            }
        }
    }
}
