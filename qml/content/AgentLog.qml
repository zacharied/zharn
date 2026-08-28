import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// Every thread, live status. Click to open.
ContentBase {
    readonly property var statusColor: ({ starting: "#f0a732", working: "#3574f0", idle: "#5fb865", failed: "#e5534b", stopped: "#868a91" })
    ListView {
        anchors.fill: parent; anchors.margins: 8; clip: true; spacing: 2
        model: app.threads.model
        delegate: Rectangle {
            required property string id
            required property string title
            required property string taskKey
            required property string status
            required property string presetName
            required property string parentId
            required property double costUsd
            objectName: "agentLogRow_" + id
            width: ListView.view.width; height: 30; radius: 4
            color: hh.hovered ? app.theme.panel : "transparent"
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8; spacing: 8
                Rectangle { width: 8; height: 8; radius: 4; color: statusColor[status] || "gray" }
                Label { text: taskKey; color: app.theme.accent; font.pixelSize: 11; font.family: app.theme.monoFamily }
                Label { text: (parentId ? "↳ " : "") + title; color: app.theme.text; Layout.fillWidth: true; elide: Text.ElideRight }
                Label { text: presetName; color: app.theme.textMuted; font.pixelSize: 11 }
                Label { text: status; color: app.theme.textMuted; font.pixelSize: 11 }
            }
            HoverHandler { id: hh }
            TapHandler { onTapped: app.layout.openContent("thread", id, title) }
        }
        Label { anchors.centerIn: parent; visible: parent.count === 0; text: "No threads yet"; color: app.theme.textMuted }
    }
}
