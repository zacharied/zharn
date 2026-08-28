import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// A task: description, its threads, and a dispatch form. tabKey = task key.
ContentBase {
    id: view
    property var task: app.tasks.get(tabKey)
    Connections { target: app.tasks; function onTasksChanged() { view.task = app.tasks.get(tabKey) } }
    readonly property var statusColor: ({ starting: "#f0a732", working: "#3574f0", idle: "#5fb865", failed: "#e5534b", stopped: "#868a91" })

    Flickable {
        anchors.fill: parent; contentHeight: body.implicitHeight + 32; clip: true
        ColumnLayout {
            id: body
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 16 }
            spacing: 12
            RowLayout {
                Label { text: tabKey; color: app.theme.accent; font.bold: true }
                Label { text: view.task.title || "(unknown task)"; color: app.theme.text; font.pixelSize: 18; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                ComboBox {
                    id: statusBox
                    model: app.tasks.statuses
                    currentIndex: Math.max(0, app.tasks.statuses.indexOf(view.task.status || "todo"))
                    onActivated: app.tasks.setStatus(tabKey, currentText)
                }
            }
            Label { text: view.task.description || "No description."; color: app.theme.textMuted; wrapMode: Text.Wrap; Layout.fillWidth: true }

            Label { text: "Threads"; color: app.theme.text; font.bold: true; Layout.topMargin: 8 }
            Repeater {
                model: app.threads.model
                delegate: Rectangle {
                    required property string id
                    required property string title
                    required property string taskKey
                    required property string status
                    required property string presetName
                    required property string parentId
                    required property double costUsd
                    visible: taskKey === tabKey
                    Layout.fillWidth: true; height: visible ? 36 : 0
                    radius: 4; color: app.theme.panel; border.color: app.theme.border
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 8
                        Rectangle { width: 8; height: 8; radius: 4; color: view.statusColor[status] || "gray" }
                        Label { text: (parentId ? "↳ " : "") + title; color: app.theme.text; Layout.fillWidth: true; elide: Text.ElideRight }
                        Label { text: presetName; color: app.theme.textMuted; font.pixelSize: 11 }
                        Label { text: status; color: app.theme.textMuted; font.pixelSize: 11 }
                        Label { text: "$" + costUsd.toFixed(3); color: app.theme.textMuted; font.pixelSize: 11 }
                    }
                    TapHandler { onTapped: app.layout.openContent("thread", id, title) }
                }
            }
            Label { visible: (view.task.threadCount || 0) === 0; text: "No threads yet — dispatch one below."; color: app.theme.textMuted }

            Label { text: "Dispatch"; color: app.theme.text; font.bold: true; Layout.topMargin: 8 }
            RowLayout {
                spacing: 8
                ComboBox { id: presetBox; objectName: "presetBox"; model: app.presets.names(); Layout.preferredWidth: 180 }
                Label { text: presetBox.currentText ? (app.presets.get(presetBox.currentText).model || "provider default") : ""; color: app.theme.textMuted; font.pixelSize: 11 }
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
                text: "Dispatch " + presetBox.currentText
                enabled: promptArea.text.trim().length > 0
                onClicked: {
                    var id = app.tasks.dispatch(tabKey, presetBox.currentText, promptArea.text)
                    promptArea.text = ""
                    app.layout.openContent("thread", id, app.threads.get(id).title)
                }
            }
        }
    }
}
