import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "Theme.js" as T

// One context's transcript + input. Used by the Context editor tab and by the Contexts tool
// window's right pane (the same component in two mounts, like a run console).
// For a character's context the input posts a *comment* in the thread it attends — the same
// channel, a different skin (AGENT-MODEL §7); for a bare context it is plain conversation.
Item {
    id: cv
    property var context: null
    property bool showInput: true
    readonly property bool busy: context ? (context.status === "working" || context.status === "starting") : false
    readonly property bool isCharacter: !!context && String(context.owner).indexOf("chr_") === 0
    readonly property var character: isCharacter ? app.stories.character(context.owner) : null
    readonly property var story: context && context.storyKey ? app.stories.get(context.storyKey) : null
    readonly property int attendedThread: {
        if (!character || !story || !story.threads) return 0
        for (var i = 0; i < story.threads.length; i++) if (story.threads[i].id === character.attention) return story.threads[i].n
        return 0
    }
    readonly property bool isAside: !!context && !!context.about && !!context.about.story_key
    readonly property string inputLabel: isAside ? "Aside — private" : isCharacter ? (attendedThread ? "Comment in #" + attendedThread : "Comment") : "Message"
    function focusInput() { prompt.forceActiveFocus() }
    function post(text) {
        if (!context) return
        if (isCharacter) app.stories.speak(context.owner, text)   // its attended thread, or a new one to it (§2.3)
        else context.send(text)
    }

    ColumnLayout {
        anchors.fill: parent; spacing: 0

        // ---- transcript
        ListView {
            id: list
            objectName: "transcript"
            Layout.fillWidth: true; Layout.fillHeight: true
            model: cv.context ? cv.context.transcriptModel : null
            clip: true; spacing: 8
            topMargin: 10; bottomMargin: 10; leftMargin: 14; rightMargin: 14
            // Not interactive, so a drag selects the prose instead of panning the list (ZHAR-3).
            // The wheel goes with it, so it is put back here — and it, not onMovementEnded,
            // is now what tells us the reader has scrolled away from the tail.
            interactive: false
            ScrollBar.vertical: ScrollBar {}
            property bool stickToEnd: true
            onContentHeightChanged: if (stickToEnd) positionViewAtEnd()
            WheelHandler {
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                onWheel: (e) => {
                    var dy = e.pixelDelta.y !== 0 ? e.pixelDelta.y : e.angleDelta.y / 120 * 60
                    list.contentY = Math.max(list.originY, Math.min(list.originY + Math.max(0, list.contentHeight - list.height), list.contentY - dy))
                    list.stickToEnd = list.atYEnd
                }
            }
            delegate: Item {
                id: row
                required property int index
                required property string role
                required property string kind
                required property string text
                required property string name
                required property string input
                required property bool isError
                required property bool streaming
                width: list.width - list.leftMargin - list.rightMargin
                height: col.implicitHeight
                property bool expanded: false
                readonly property bool isUser: role === "user"
                readonly property bool isTool: kind === "tool_use" || kind === "tool_result"
                readonly property bool isThinking: kind === "thinking"
                readonly property string label: isUser ? (cv.isCharacter ? "comment" : "you")
                                              : kind === "tool_use" ? name : kind === "tool_result" ? (isError ? "error" : "result")
                                              : kind === "note" ? "harness" : kind
                ColumnLayout {
                    id: col; width: parent.width; spacing: 3
                    RowLayout {
                        visible: row.kind !== "text" || row.isUser   // plain assistant prose needs no label
                        spacing: 6
                        Icon { visible: row.kind === "tool_use"; name: "terminal"; size: 12; color: app.theme.textDim }
                        Text { text: row.label; color: row.isError ? app.theme.danger : (row.isUser ? app.theme.text : app.theme.textMuted)
                               font.family: app.theme.monoFamily; font.pixelSize: app.theme.fontSizeSmall; font.weight: Font.Medium
                               font.letterSpacing: 0.8; font.capitalization: Font.AllUppercase }
                        Item { Layout.fillWidth: true }
                        Icon { visible: row.isTool; name: row.expanded ? "down" : "right"; size: 12; color: app.theme.textDim }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        visible: row.text.length > 0 || row.input.length > 0
                        implicitHeight: (row.isTool ? toolBody.implicitHeight : body.implicitHeight) + (row.isTool || row.isUser ? 12 : 0)
                        radius: app.theme.radius
                        color: row.isUser ? app.theme.accentSoft : row.isError ? app.theme.dangerSoft : row.isTool ? (row.kind === "tool_use" ? app.theme.panel : app.theme.bg) : "transparent"
                        border.color: row.isTool ? app.theme.border : "transparent"
                        // Two bodies, one visible: prose is a selectable Prose, but a tool block
                        // folds to four elided lines and neither elide nor maximumLineCount exists
                        // on a TextEdit — so tool output stays a Text (ZHAR-3).
                        Prose {
                            id: body
                            visible: !row.isTool
                            anchors { left: parent.left; right: parent.right; top: parent.top; margins: row.isUser ? 6 : 0; leftMargin: row.isUser ? 8 : 0 }
                            objectName: "transcriptBody_" + row.index
                            text: row.text
                            textFormat: (row.kind === "text" && !row.isUser) ? TextEdit.MarkdownText : TextEdit.PlainText
                            color: row.isThinking || row.kind === "note" ? app.theme.textMuted : app.theme.text
                            font.pixelSize: app.theme.fontSize - 0.5
                            font.italic: row.isThinking
                        }
                        Text {
                            id: toolBody
                            visible: row.isTool
                            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 6; leftMargin: 8 }
                            text: row.kind === "tool_use" ? row.input : row.text  // `text` alone would be Text.text
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap; lineHeight: 1.3
                            color: app.theme.textMuted
                            font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize
                            maximumLineCount: row.expanded ? 100000 : 4
                            elide: row.expanded ? Text.ElideNone : Text.ElideRight
                        }
                    }
                    Rectangle { visible: row.streaming; width: 8; height: 13; color: app.theme.accent; opacity: 0.7 }
                }
                TapHandler { enabled: row.isTool; onTapped: row.expanded = !row.expanded }
            }
            Text { visible: list.count === 0 && !!cv.context; anchors.centerIn: parent; text: "Nothing yet."; color: app.theme.textDim }
        }

        // ---- input
        Rectangle {
            visible: cv.showInput
            Layout.fillWidth: true; implicitHeight: inputCol.implicitHeight + 16; color: app.theme.panel
            Divider { width: parent.width }
            ColumnLayout {
                id: inputCol
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                spacing: 4
                RowLayout {
                    spacing: 8
                    TextBox {
                        id: prompt
                        objectName: "promptInput"
                        Layout.fillWidth: true; Layout.preferredHeight: 60
                        label: cv.inputLabel
                        placeholderText: cv.isAside ? "Nobody on the story hears this; what should change the story goes in your reply  (Ctrl+Enter)"
                                       : cv.isCharacter ? "Posted in the thread " + (cv.character ? cv.character.name : "it") + " is attending  (Ctrl+Enter)"
                                       : cv.busy ? "Working — a follow-up is queued  (Ctrl+Enter)" : "Ctrl+Enter to send"
                        onSubmitted: send()
                        function send() { if (text.trim().length && cv.context) { cv.post(text); text = "" } }
                    }
                    Btn { objectName: "sendButton"; Layout.alignment: Qt.AlignBottom; primary: true; icon_: "send"
                          text: cv.isCharacter ? "Comment" : "Send"; enabled: !!cv.context && prompt.text.trim().length > 0; onClicked: prompt.send() }
                }
                RowLayout {
                    visible: !!(cv.context && cv.context.lastError); spacing: 6
                    Icon { name: "error"; size: 12; color: app.theme.danger }
                    Label { objectName: "contextError"; text: cv.context ? cv.context.lastError : ""; color: app.theme.danger; font.pixelSize: app.theme.fontSizeSmall; Layout.fillWidth: true; elide: Text.ElideRight }
                }
            }
        }
    }
}
