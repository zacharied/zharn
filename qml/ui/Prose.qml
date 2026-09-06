import QtQuick

// Read-only prose you can select with the mouse (Ctrl+C copies).
//
// A QML `Text` cannot be selected at all — `TextEdit` is the only item that can, so every
// passage a reader might want to quote is one of these. Read-only, no cursor, no background:
// it renders exactly like the `Text` it replaces. Its container must not be `interactive`,
// or the Flickable steals the drag and pans the page instead of selecting (see Story.qml).
//
// Selection lives inside one item: a drag cannot sweep from one comment into the next.
// That is Qt Quick's limit, not a setting.
TextEdit {
    readOnly: true
    selectByMouse: true
    cursorDelegate: Item {}                     // read-only still blinks a cursor otherwise
    wrapMode: TextEdit.Wrap
    textFormat: TextEdit.MarkdownText
    color: app.theme.text
    selectionColor: app.theme.selection
    selectedTextColor: app.theme.text
    font.family: app.theme.fontFamily
    font.pixelSize: app.theme.fontSize
    onLinkActivated: (link) => Qt.openUrlExternally(link)
}
