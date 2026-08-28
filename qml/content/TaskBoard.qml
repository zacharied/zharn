import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// Kanban over app.tasks. Cards show live agent activity.
ContentBase {
    readonly property var columns: [
        { status: "backlog", title: "Backlog" }, { status: "todo", title: "To do" },
        { status: "in_progress", title: "In progress" }, { status: "in_review", title: "In review" }, { status: "done", title: "Done" }
    ]
    Flickable {
        anchors.fill: parent; anchors.margins: 10; contentWidth: row.width; clip: true
        Row {
            id: row; spacing: 10
            Repeater {
                model: columns
                delegate: Rectangle {
                    required property var modelData
                    width: 220; height: col.implicitHeight + 20; radius: 6; color: app.theme.panel; border.color: app.theme.border
                    ColumnLayout {
                        id: col; spacing: 6
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                        Label { text: modelData.title; color: app.theme.textMuted; font.bold: true }
                        Repeater {
                            model: app.tasks.model
                            delegate: Rectangle {
                                required property string key
                                required property string title
                                required property string status
                                required property string priority
                                required property int threadCount
                                required property int workingCount
                                visible: status === modelData.status
                                Layout.fillWidth: true; height: visible ? card.implicitHeight + 16 : 0
                                radius: 4; color: app.theme.bg; border.color: app.theme.border
                                ColumnLayout {
                                    id: card; spacing: 4
                                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                                    RowLayout {
                                        Label { text: key; color: app.theme.accent; font.pixelSize: 11; font.bold: true }
                                        Item { Layout.fillWidth: true }
                                        Label { text: priority; color: priority === "urgent" || priority === "high" ? "#f0a732" : app.theme.textMuted; font.pixelSize: 10 }
                                    }
                                    Label { text: title; color: app.theme.text; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 12 }
                                    RowLayout {
                                        visible: threadCount > 0
                                        Rectangle { width: 7; height: 7; radius: 4; color: workingCount > 0 ? "#3574f0" : "#5fb865" }
                                        Label { text: threadCount + (threadCount === 1 ? " thread" : " threads") + (workingCount > 0 ? " · " + workingCount + " working" : ""); color: app.theme.textMuted; font.pixelSize: 10 }
                                    }
                                }
                                TapHandler { onTapped: app.layout.openContent("task", key, key + " " + title) }
                            }
                        }
                        Label {
                            visible: modelData.status === "todo"
                            text: "+ new task"; color: app.theme.textMuted; font.pixelSize: 11
                            TapHandler { onTapped: { var k = app.tasks.create("New task", ""); app.layout.openContent("task", k, k) } }
                        }
                    }
                }
            }
        }
    }
}
