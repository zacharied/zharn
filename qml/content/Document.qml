import QtQuick
import QtQuick.Controls.Basic
import ".."

// A markdown document, read-only (proposal 2026-09-03-documents-panel §4; DESIGN §5's read-mostly viewer).
// Scrolls to a section on app.documents.scrollRequested and reports the topmost heading back as the
// reader scrolls, which is what the Documents panel selects.
ContentBase {
    id: page
    readonly property string key: tabKey
    property var positions: []      // character position of heading n in the rendered document
    property string loaded: ""
    property int pending: -2        // a requested section (-1 = top), -2 = none
    property real keepY: -1         // a reload's scroll position to restore once laid out, -1 = none kept

    function load() {
        var t = app.documents.text(key)
        if (t === loaded) return
        var wasLoaded = loaded !== ""
        var y = flick.contentY
        loaded = t
        view.text = t
        positions = app.documents.headingPositionsIn(view.textDocument)
        // view.implicitHeight (and so flick.contentHeight) doesn't necessarily reflect the new text yet —
        // clamping here would clamp against the *old* height, so defer to settle, same as a requested
        // scroll does, and let it run after the new text has laid out. A scroll request already pending
        // beats a kept position outright (settle applies at most one of the two), so don't record it.
        if (wasLoaded && page.pending === -2) page.keepY = y
        settle.restart()
    }
    function yOf(i) { return view.y + view.positionToRectangle(positions[i]).y }
    function scrollTo(i) {
        var y = i < 0 || i >= positions.length ? 0 : yOf(i)
        // Clamp to the bottom of the document only when it has one to clamp to — a document shorter
        // than the viewport has no valid upper bound, and clamping to 0 there would strand every
        // request at the top, making report()'s scan below find nothing but the title.
        var max = flick.contentHeight - flick.height
        flick.contentY = max > 0 ? Math.max(0, Math.min(y, max)) : Math.max(0, y)
    }
    function report() {
        var cur = -1
        for (var i = 0; i < positions.length; i++) if (yOf(i) <= flick.contentY + 1) cur = i
        app.documents.setPosition(key, cur)
    }
    Component.onCompleted: { load(); settle.start() }
    // Every scroll request and every reload's kept position land here after the text is laid out, whether
    // the request arrived as a signal (tab already open) or was left pending in the store (tab created by
    // the open). A pending request always wins over a kept position — see load() and onScrollRequested,
    // which arbitrate that before this fires — so at most one of the two branches below runs, and either
    // way report() runs exactly once at the end.
    Timer {
        id: settle; interval: 0
        onTriggered: {
            var i = page.pending !== -2 ? page.pending : app.documents.takeScroll(page.key)
            page.pending = -2
            if (i !== -2) {
                page.scrollTo(i)
            } else if (page.keepY !== -1) {
                var max = Math.max(0, flick.contentHeight - flick.height)
                flick.contentY = Math.max(0, Math.min(page.keepY, max))
            }
            page.keepY = -1
            page.report()
        }
    }
    Timer { id: reportTimer; interval: 16; onTriggered: page.report() }
    Connections {
        target: app.documents
        // A fresh request beats whatever load() may have just queued as a kept position.
        function onScrollRequested(k, i) { if (k === page.key) { app.documents.takeScroll(k); page.pending = i; page.keepY = -1; settle.restart() } }
        function onDocumentsChanged() { page.load() }
    }

    Flickable {
        id: flick
        objectName: "documentFlick"
        anchors.fill: parent; clip: true
        contentWidth: width; contentHeight: view.y + view.implicitHeight + 40
        onContentYChanged: reportTimer.restart()
        ScrollBar.vertical: ScrollBar {}
        TextArea {
            id: view
            objectName: "documentView"
            x: 28; y: 20
            width: Math.min(flick.width - 56, 820)
            readOnly: true; selectByMouse: true
            textFormat: TextEdit.MarkdownText; wrapMode: TextEdit.Wrap
            color: app.theme.text; selectionColor: app.theme.selection
            font.family: app.theme.fontFamily; font.pixelSize: app.theme.fontSize
            background: null; padding: 0
        }
    }
}
