import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// One agent conversation: streaming transcript + input. tabKey = context id.
ContentBase {
    id: view
    readonly property var context: app.contexts.get(tabKey)
    readonly property bool busy: context ? (context.status === "working" || context.status === "starting") : false
    readonly property var statusColor: ({ starting: "#f0a732", working: "#3574f0", idle: "#5fb865", failed: "#e5534b", stopped: "#868a91" })

    Label {
        objectName: "contextMissing"; visible: !view.context
        anchors.centerIn: parent; width: parent.width - 40; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
        text: "Context " + tabKey + " not found — it may have been removed, or the tab is stale."; color: app.theme.textMuted
    }

    ColumnLayout {
        visible: !!view.context
        anchors.fill: parent; spacing: 0

        // ---- header
        Rectangle {
            Layout.fillWidth: true; height: 36; color: app.theme.panel
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 10
                Rectangle { width: 9; height: 9; radius: 5; color: view.context ? view.statusColor[view.context.status] || "gray" : "gray"
                            SequentialAnimation on opacity { running: view.busy; loops: Animation.Infinite; NumberAnimation { to: 0.2; duration: 600 } NumberAnimation { to: 1; duration: 600 } } }
                Label { objectName: "contextTitle"; text: view.context ? view.context.title : ""; color: app.theme.text; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                Label { objectName: "contextStatus"; text: view.context ? view.context.status : ""; color: app.theme.textMuted; font.pixelSize: 11 }
                Label { objectName: "contextStoryLink"; text: view.context && view.context.storyKey ? view.context.storyKey : ""; color: app.theme.accent; font.pixelSize: 11
                        TapHandler { onTapped: app.layout.openContent("task", view.context.storyKey, view.context.storyKey) } }
                Label { text: view.context ? view.context.model : ""; color: app.theme.textMuted; font.pixelSize: 11 }
                Label { text: view.context ? "$" + view.context.costUsd.toFixed(3) : ""; color: app.theme.textMuted; font.pixelSize: 11 }
                Label { objectName: "stopButton"; visible: view.busy; text: "■ stop"; color: app.theme.textMuted; TapHandler { onTapped: view.context.stop() } }
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: app.theme.border }
        }

        // ---- transcript
        ListView {
            id: list
            objectName: "transcript"
            Layout.fillWidth: true; Layout.fillHeight: true
            model: view.context ? view.context.transcriptModel : null
            clip: true; spacing: 6
            topMargin: 10; bottomMargin: 10; leftMargin: 12; rightMargin: 12
            ScrollBar.vertical: ScrollBar {}
            property bool stickToEnd: true
            onContentHeightChanged: if (stickToEnd) positionViewAtEnd()
            onMovementEnded: stickToEnd = atYEnd
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
                height: bubble.implicitHeight
                property bool expanded: false
                readonly property bool isUser: role === "user"
                readonly property bool isTool: kind === "tool_use" || kind === "tool_result"
                Rectangle {
                    id: bubble
                    width: parent.width
                    implicitHeight: col.implicitHeight + 16
                    radius: 6
                    color: isUser ? app.theme.accentSoft : (isError ? "#4a2a2a" : (isTool ? app.theme.panel : "transparent"))
                    border.color: isTool || isUser ? app.theme.border : "transparent"
                    ColumnLayout {
                        id: col
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                        spacing: 4
                        RowLayout {
                            visible: kind !== "text" || isUser
                            spacing: 6
                            Label {
                                text: isUser ? "you" : (kind === "tool_use" ? "⚙ " + name : (kind === "tool_result" ? (isError ? "✗ result" : "↳ result") : (kind === "thinking" ? "thinking" : (kind === "note" ? "harness" : kind))))
                                color: isError ? "#e5534b" : app.theme.textMuted; font.pixelSize: 11; font.bold: true
                            }
                            Item { Layout.fillWidth: true }
                            Label { visible: isTool; text: expanded ? "▾" : "▸"; color: app.theme.textMuted; font.pixelSize: 11 }
                        }
                        Text {
                            id: body
                            Layout.fillWidth: true
                            visible: row.text.length > 0 || row.input.length > 0
                            text: kind === "tool_use" ? row.input : row.text  // `text` alone would be Text.text
                            textFormat: (kind === "text" && !isUser) ? Text.MarkdownText : Text.PlainText
                            wrapMode: Text.Wrap
                            color: kind === "thinking" || kind === "note" ? app.theme.textMuted : app.theme.text
                            font.family: isTool ? app.theme.monoFamily : app.theme.fontFamily
                            font.pixelSize: isTool ? 12 : app.theme.fontSize
                            font.italic: kind === "thinking"
                            maximumLineCount: isTool && !expanded ? 4 : 100000
                            elide: isTool && !expanded ? Text.ElideRight : Text.ElideNone
                            onLinkActivated: (link) => Qt.openUrlExternally(link)
                        }
                        Rectangle { visible: streaming; width: 8; height: 14; color: app.theme.accent; opacity: 0.7 }
                    }
                    TapHandler { enabled: isTool; onTapped: expanded = !expanded }
                }
            }
        }

        // ---- input
        Rectangle {
            Layout.fillWidth: true; height: inputCol.implicitHeight + 16; color: app.theme.panel
            Rectangle { width: parent.width; height: 1; color: app.theme.border }
            ColumnLayout {
                id: inputCol
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                RowLayout {
                    spacing: 8
                    TextArea {
                        id: prompt
                        objectName: "promptInput"
                        Layout.fillWidth: true
                        placeholderText: view.busy ? "agent is working — queue a follow-up…" : "Message the agent  (Ctrl+Enter to send)"
                        wrapMode: TextEdit.Wrap
                        color: app.theme.text
                        background: Rectangle { color: app.theme.bg; radius: 4; border.color: prompt.activeFocus ? app.theme.accent : app.theme.border }
                        Keys.onPressed: (e) => { if ((e.key === Qt.Key_Return || e.key === Qt.Key_Enter) && (e.modifiers & Qt.ControlModifier)) { send(); e.accepted = true } }
                        function send() { if (text.trim().length && view.context) { view.context.send(text); text = "" } }
                    }
                    Button { objectName: "sendButton"; text: "Send"; enabled: !!view.context && prompt.text.trim().length > 0; onClicked: prompt.send() }
                }
                Label { objectName: "contextError"; visible: !!(view.context && view.context.lastError); text: view.context ? view.context.lastError : ""; color: "#e5534b"; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
            }
        }
    }
}
