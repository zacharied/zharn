import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// A task: description, its contexts, and a dispatch form. tabKey = task key.
ContentBase {
    id: view
    property var task: app.tasks.get(tabKey)
    readonly property bool found: !!(view.task && view.task.key)
    Connections { target: app.tasks; function onTasksChanged() { view.task = app.tasks.get(tabKey) } }

    Label {
        objectName: "taskMissing"; visible: !view.found
        anchors.centerIn: parent; width: parent.width - 40; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
        text: "Task " + tabKey + " not found — it may have been removed, or the tab is stale."; color: app.theme.textMuted
    }
    readonly property var statusColor: ({ starting: "#f0a732", working: "#3574f0", idle: "#5fb865", failed: "#e5534b", stopped: "#868a91" })

    Flickable {
        visible: view.found
        anchors.fill: parent; contentHeight: body.implicitHeight + 32; clip: true
        ColumnLayout {
            id: body
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 16 }
            spacing: 12
            RowLayout {
                Label { text: tabKey; color: app.theme.accent; font.bold: true }
                Label { objectName: "taskTitle"; text: view.task.title || ""; color: app.theme.text; font.pixelSize: 18; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                ComboBox {
                    id: statusBox; objectName: "statusBox"
                    model: app.tasks.statuses
                    currentIndex: Math.max(0, app.tasks.statuses.indexOf(view.task.status || "todo"))
                    onActivated: app.tasks.setStatus(tabKey, currentText)
                }
            }
            Label { text: view.task.description || "No description."; color: app.theme.textMuted; wrapMode: Text.Wrap; Layout.fillWidth: true }

            Label { text: "Contexts"; color: app.theme.text; font.bold: true; Layout.topMargin: 8 }
            Repeater {
                model: app.contexts.model
                delegate: Rectangle {
                    required property string id
                    required property string title
                    required property string storyKey
                    required property string status
                    required property string roleName
                    required property double costUsd
                    visible: storyKey === tabKey
                    Layout.fillWidth: true; height: visible ? 36 : 0
                    radius: 4; color: app.theme.panel; border.color: app.theme.border
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 8
                        Rectangle { width: 8; height: 8; radius: 4; color: view.statusColor[status] || "gray" }
                        Label { text: title; color: app.theme.text; Layout.fillWidth: true; elide: Text.ElideRight }
                        Label { text: roleName; color: app.theme.textMuted; font.pixelSize: 11 }
                        Label { text: status; color: app.theme.textMuted; font.pixelSize: 11 }
                        Label { text: "$" + costUsd.toFixed(3); color: app.theme.textMuted; font.pixelSize: 11 }
                    }
                    TapHandler { onTapped: app.layout.openContent("context", id, title) }
                }
            }
            Label { visible: (view.task.contextCount || 0) === 0; text: "No contexts yet — dispatch one below."; color: app.theme.textMuted }

            Label { text: "Dispatch"; color: app.theme.text; font.bold: true; Layout.topMargin: 8 }
            RowLayout {
                spacing: 8
                ComboBox { id: roleBox; objectName: "roleBox"; model: app.roles.names(); Layout.preferredWidth: 180 }
                Label { text: roleBox.currentText ? (app.roles.get(roleBox.currentText).model || "provider default") : ""; color: app.theme.textMuted; font.pixelSize: 11 }
            }
            TextArea {
                id: promptArea
                objectName: "dispatchPrompt"
                Layout.fillWidth: true; Layout.preferredHeight: 90
                placeholderText: "What should the agent do on this task?"
                wrapMode: TextEdit.Wrap; color: app.theme.text
                background: Rectangle { color: app.theme.bg; radius: 4; border.color: promptArea.activeFocus ? app.theme.accent : app.theme.border }
            }
            Button {
                objectName: "dispatchButton"
                text: "Dispatch " + roleBox.currentText
                enabled: promptArea.text.trim().length > 0
                onClicked: {
                    var id = app.tasks.dispatch(tabKey, roleBox.currentText, promptArea.text)
                    if (!id) return  // failed: the reason is in the status bar (app.notify)
                    promptArea.text = ""
                    app.layout.openContent("context", id, app.contexts.get(id).title)
                }
            }
        }
    }
}
