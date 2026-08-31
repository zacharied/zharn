import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// The board: stories by phase. Stories waiting on you are highlighted, say why, sort first, and are counted.
ContentBase {
    id: board
    readonly property var columns: [
        { phase: "backlog", title: "Backlog" }, { phase: "todo", title: "To do" },
        { phase: "planning", title: "Planning" }, { phase: "implementing", title: "Implementing" }, { phase: "done", title: "Done" }
    ]
    property var rows: app.stories.list()
    readonly property int needsYouCount: rows.filter(function (r) { return r.needsYou }).length
    Connections { target: app.stories; function onStoriesChanged() { board.rows = app.stories.list() } }
    function inPhase(phase) {
        return rows.filter(function (r) { return r.phase === phase })
                   .sort(function (a, b) { return (b.needsYou - a.needsYou) || (a.createdAt - b.createdAt) })
    }

    ColumnLayout {
        anchors.fill: parent; anchors.margins: 10; spacing: 8
        RowLayout {
            Label {
                objectName: "needsYouCount"
                text: board.needsYouCount > 0 ? board.needsYouCount + " need" + (board.needsYouCount === 1 ? "s" : "") + " you" : "nothing waits on you"
                color: board.needsYouCount > 0 ? "#f0a732" : app.theme.textMuted; font.bold: board.needsYouCount > 0
            }
            Item { Layout.fillWidth: true }
            Label {
                objectName: "newStoryButton"; text: "+ new story"; color: app.theme.accent
                TapHandler { onTapped: { var k = app.stories.create("New story", ""); if (k) app.layout.openContent("story", k, k) } }
            }
        }
        Flickable {
            id: flick
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentWidth: width; contentHeight: flow.height
            ScrollBar.vertical: ScrollBar {}
            Flow {
                id: flow; width: flick.width; spacing: 10
                Repeater {
                    model: board.columns
                    delegate: Rectangle {
                        id: column
                        required property var modelData
                        readonly property var cards: board.inPhase(modelData.phase)
                        width: 220; height: col.implicitHeight + 20; radius: 6; color: app.theme.panel; border.color: app.theme.border
                        ColumnLayout {
                            id: col; spacing: 6
                            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                            Label { text: column.modelData.title + "  " + column.cards.length; color: app.theme.textMuted; font.bold: true }
                            Repeater {
                                model: column.cards
                                delegate: Rectangle {
                                    id: card
                                    required property var modelData
                                    objectName: "card_" + modelData.key
                                    Layout.fillWidth: true; height: body.implicitHeight + 16
                                    radius: 4; color: app.theme.bg
                                    border.color: modelData.needsYou ? "#f0a732" : app.theme.border; border.width: modelData.needsYou ? 2 : 1
                                    ColumnLayout {
                                        id: body; spacing: 4
                                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                                        RowLayout {
                                            Label { text: card.modelData.key; color: app.theme.accent; font.pixelSize: 11; font.bold: true }
                                            Item { Layout.fillWidth: true }
                                            Label { text: card.modelData.priority; color: app.theme.textMuted; font.pixelSize: 10 }
                                        }
                                        Label { text: card.modelData.title; color: app.theme.text; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 12 }
                                        Label {
                                            objectName: "cardBadge_" + card.modelData.key
                                            visible: card.modelData.needsYou
                                            text: "needs you · " + card.modelData.flavor; color: "#f0a732"; font.pixelSize: 10; font.bold: true
                                        }
                                        RowLayout {
                                            visible: card.modelData.castCount > 0
                                            Rectangle { width: 7; height: 7; radius: 4; color: card.modelData.workingCount > 0 ? "#3574f0" : "#5fb865" }
                                            Label {
                                                text: card.modelData.castCount + " cast" + (card.modelData.workingCount > 0 ? " · working" : "")
                                                color: app.theme.textMuted; font.pixelSize: 10
                                            }
                                        }
                                    }
                                    TapHandler { onTapped: app.layout.openContent("story", card.modelData.key, card.modelData.key + " " + card.modelData.title) }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
