import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// Kanban placeholder. Real data comes from the task store (docs/DESIGN.md §3b).
ContentBase {
    readonly property var columns: [
        { status: "todo", title: "To do", cards: ["ABC-14 Terminal panel (pyte)", "ABC-15 Git status panel"] },
        { status: "in_progress", title: "In progress", cards: ["ABC-12 Hot reload · claude-deep ● working"] },
        { status: "in_review", title: "In review", cards: ["ABC-9 Layout tree"] }
    ]
    Flickable {
        anchors.fill: parent; anchors.margins: 10; contentWidth: row.width; clip: true
        Row {
            id: row; spacing: 10
            Repeater {
                model: columns
                delegate: Rectangle {
                    width: 210; height: col.implicitHeight + 20; radius: 6; color: app.theme.panel; border.color: app.theme.border
                    ColumnLayout {
                        id: col; spacing: 6
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                        Label { text: modelData.title + "  " + modelData.cards.length; color: app.theme.textMuted; font.bold: true }
                        Repeater {
                            model: modelData.cards
                            delegate: Rectangle {
                                Layout.fillWidth: true; height: 44; radius: 4; color: app.theme.bg; border.color: app.theme.border
                                Label { anchors.fill: parent; anchors.margins: 8; text: modelData; color: app.theme.text; wrapMode: Text.Wrap; font.pixelSize: 12 }
                                TapHandler { onTapped: app.layout.openContent("task", modelData.split(" ")[0], modelData.split(" ·")[0]) }
                            }
                        }
                    }
                }
            }
        }
    }
}
