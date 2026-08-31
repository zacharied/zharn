import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// A story page. tabKey = story key. Description and Start until it begins; then phase, ball, the
// actions you have right now, the comments (choices as buttons), a composer, and the cast.
ContentBase {
    id: view
    property var story: app.stories.get(tabKey)
    property var comments: app.stories.comments(tabKey)
    property var cast: app.stories.cast(tabKey)
    readonly property bool found: !!(story && story.key)
    readonly property bool started: found && story.phase !== "backlog" && story.phase !== "todo"
    readonly property bool terminal: found && (story.phase === "done" || story.phase === "canceled")
    readonly property bool mine: found && story.ball === "author"
    function refresh() { story = app.stories.get(tabKey); comments = app.stories.comments(tabKey); cast = app.stories.cast(tabKey) }
    Connections { target: app.stories; function onStoriesChanged() { view.refresh() } }
    readonly property var statusColor: ({ starting: "#f0a732", working: "#3574f0", idle: "#5fb865", failed: "#e5534b", stopped: "#868a91", none: "#868a91" })

    Label {
        objectName: "storyMissing"; visible: !view.found
        anchors.centerIn: parent; width: parent.width - 40; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
        text: "Story " + tabKey + " not found — it may have been removed, or the tab is stale."; color: app.theme.textMuted
    }

    Flickable {
        visible: view.found
        anchors.fill: parent; contentHeight: body.implicitHeight + 32; clip: true
        ScrollBar.vertical: ScrollBar {}
        ColumnLayout {
            id: body
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 16 }
            spacing: 12

            // ---- header
            RowLayout {
                spacing: 10
                Label { text: tabKey; color: app.theme.accent; font.bold: true }
                Label {
                    objectName: "storyTitle"; text: view.story.title || ""; color: app.theme.text; font.pixelSize: 18; font.bold: true
                    Layout.fillWidth: view.started; elide: Text.ElideRight
                    TapHandler { onTapped: view.forceActiveFocus() }  // a neutral place to click to blur an editor
                }
                TextField {
                    objectName: "storyTitleEdit"; visible: !view.started; Layout.fillWidth: true
                    text: view.story.title || ""; font.pixelSize: 18; font.bold: true; color: app.theme.text
                    onEditingFinished: if (text !== view.story.title) app.stories.update(tabKey, text, descEdit.text)
                }
                Rectangle { visible: view.started; radius: 3; color: app.theme.accentSoft; height: 20; width: phaseLabel.implicitWidth + 12
                            Label { id: phaseLabel; objectName: "storyPhase"; anchors.centerIn: parent; text: view.story.phase || ""; color: app.theme.text; font.pixelSize: 11 } }
                Rectangle { visible: view.started && !view.terminal; radius: 3; color: view.mine ? "#f0a732" : app.theme.panel; height: 20; width: ballLabel.implicitWidth + 12; border.color: app.theme.border
                            Label { id: ballLabel; objectName: "storyBall"; anchors.centerIn: parent; text: view.story.ball || ""; color: view.mine ? "black" : app.theme.textMuted; font.pixelSize: 11 } }
            }
            Label { objectName: "storyDescription"; visible: view.started; text: view.story.description || "No description."; color: app.theme.textMuted; wrapMode: Text.Wrap; Layout.fillWidth: true; textFormat: Text.MarkdownText }
            TextArea {
                id: descEdit; objectName: "storyDescriptionEdit"; visible: !view.started
                Layout.fillWidth: true; Layout.preferredHeight: 90; wrapMode: TextEdit.Wrap; color: app.theme.text
                placeholderText: "Describe the work: what, why, how you will validate it."
                text: view.story.description || ""
                background: Rectangle { color: app.theme.bg; radius: 4; border.color: descEdit.activeFocus ? app.theme.accent : app.theme.border }
                onActiveFocusChanged: if (!activeFocus && text !== view.story.description) app.stories.update(tabKey, view.story.title, text)
            }

            // ---- Start (unstarted only)
            RowLayout {
                visible: !view.started && view.story.phase !== "canceled"; spacing: 8
                ComboBox { id: roleBox; objectName: "roleBox"; model: app.roles.names(); Layout.preferredWidth: 180
                           Component.onCompleted: currentIndex = Math.max(0, app.roles.names().indexOf("protagonist")) }
                TextField { id: startNote; objectName: "startNote"; Layout.fillWidth: true; placeholderText: "Opening note for the protagonist (optional)"; color: app.theme.text }
                Button { objectName: "startButton"; text: "Start"; onClicked: { if (app.stories.start(tabKey, startNote.text, roleBox.currentText)) startNote.text = "" } }
            }

            // ---- needs-you banner + action bar (started only)
            Rectangle {
                visible: view.mine
                Layout.fillWidth: true; height: 30; radius: 4; color: "#3a2e14"; border.color: "#f0a732"
                Label { objectName: "needsYouBanner"; visible: view.mine; anchors.verticalCenter: parent.verticalCenter; x: 10; text: "Waiting on you: " + view.story.flavor; color: "#f0a732"; font.bold: true }
            }
            Loader {
                active: view.started; Layout.fillWidth: true
                sourceComponent: Component {
                    RowLayout {
                        spacing: 8
                        Button { objectName: "proceedButton"; visible: view.story.phase === "planning" && view.mine; text: "Proceed to implementing"; onClicked: app.stories.proceed(tabKey, "") }
                        Button { objectName: "approveButton"; visible: view.story.phase === "implementing" && view.mine; text: "Approve"; onClicked: app.stories.approve(tabKey, "") }
                        Button { objectName: "backButton"; visible: view.story.phase === "implementing" && view.mine; text: "Back to planning"; onClicked: app.stories.backToPlanning(tabKey, "") }
                        Item { Layout.fillWidth: true }
                        Button { objectName: "reopenButton"; visible: view.terminal; text: "Reopen"; onClicked: app.stories.reopen(tabKey, "reopened from the story page") }
                        Button { objectName: "cancelButton"; visible: !view.terminal; text: "Cancel"; onClicked: app.stories.cancel(tabKey, "") }
                    }
                }
            }

            // ---- comments
            Label { visible: view.started; text: "Main thread"; color: app.theme.text; font.bold: true; Layout.topMargin: 8 }
            Repeater {
                model: view.comments
                delegate: Rectangle {
                    id: row
                    required property int index
                    required property var modelData
                    readonly property var options: (modelData.structured && modelData.structured.options) ? modelData.structured.options : []
                    readonly property bool answerable: options.length > 0 && view.mine && index === view.comments.length - 1
                    objectName: "comment_" + modelData.id
                    Layout.fillWidth: true; height: ccol.implicitHeight + 16; radius: 4
                    color: modelData.author === "human" ? app.theme.accentSoft : (modelData.kind === "system" ? "transparent" : app.theme.panel)
                    border.color: modelData.kind === "system" ? "transparent" : app.theme.border
                    ColumnLayout {
                        id: ccol; spacing: 4
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                        RowLayout {
                            Label { text: row.modelData.authorName; color: app.theme.text; font.bold: true; font.pixelSize: 11 }
                            Label { text: row.modelData.kind; color: row.modelData.kind === "question" || row.modelData.kind === "handoff" ? "#f0a732" : app.theme.textMuted; font.pixelSize: 10 }
                            Item { Layout.fillWidth: true }
                            Label { visible: !!(row.modelData.structured && row.modelData.structured.transition); text: "→ " + (row.modelData.structured && row.modelData.structured.transition ? row.modelData.structured.transition.to.join("/") : ""); color: app.theme.textMuted; font.pixelSize: 10 }
                        }
                        Text { text: row.modelData.body; textFormat: Text.MarkdownText; wrapMode: Text.Wrap; Layout.fillWidth: true; color: row.modelData.kind === "system" ? app.theme.textMuted : app.theme.text; font.family: app.theme.fontFamily; font.pixelSize: app.theme.fontSize }
                        Flow {
                            visible: row.options.length > 0; Layout.fillWidth: true; spacing: 6
                            Repeater {
                                model: row.options
                                delegate: Button {
                                    required property int index
                                    required property var modelData
                                    objectName: "optionButton_" + row.modelData.id + "_" + index
                                    text: modelData; enabled: row.answerable
                                    onClicked: app.stories.comment(tabKey, modelData)
                                }
                            }
                        }
                    }
                }
            }

            // ---- composer
            RowLayout {
                visible: view.started && !view.terminal; spacing: 8
                TextArea {
                    id: reply; objectName: "replyInput"; Layout.fillWidth: true; Layout.preferredHeight: 70
                    placeholderText: view.mine ? "Reply to the protagonist  (Ctrl+Enter)" : "Comment for the protagonist — arrives between turns  (Ctrl+Enter)"
                    wrapMode: TextEdit.Wrap; color: app.theme.text
                    background: Rectangle { color: app.theme.bg; radius: 4; border.color: reply.activeFocus ? app.theme.accent : app.theme.border }
                    Keys.onPressed: (e) => { if ((e.key === Qt.Key_Return || e.key === Qt.Key_Enter) && (e.modifiers & Qt.ControlModifier)) { post(); e.accepted = true } }
                    function post() { if (text.trim().length) { app.stories.comment(tabKey, text); text = "" } }
                }
                Button { objectName: "replyButton"; text: view.mine ? "Reply" : "Comment"; enabled: reply.text.trim().length > 0; onClicked: reply.post() }
            }

            // ---- cast
            Label { visible: view.cast.length > 0; text: "Cast"; color: app.theme.text; font.bold: true; Layout.topMargin: 8 }
            Repeater {
                model: view.cast
                delegate: Rectangle {
                    required property var modelData
                    objectName: "castRow_" + modelData.id
                    Layout.fillWidth: true; height: 34; radius: 4; color: app.theme.panel; border.color: app.theme.border
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 8
                        Rectangle { width: 8; height: 8; radius: 4; color: view.statusColor[modelData.contextStatus] || "gray" }
                        Label { text: modelData.name + (modelData.id === view.story.protagonist ? "  · protagonist" : ""); color: app.theme.text; Layout.fillWidth: true }
                        Label { text: modelData.role; color: app.theme.textMuted; font.pixelSize: 11 }
                        Label { text: modelData.contextStatus; color: app.theme.textMuted; font.pixelSize: 11 }
                    }
                    TapHandler { onTapped: if (modelData.live_context) app.layout.openContent("context", modelData.live_context, tabKey + " · " + modelData.name) }
                }
            }
        }
    }
}
