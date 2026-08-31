import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// Every context, live status. Click to open.
ContentBase {
    readonly property var statusColor: ({ starting: "#f0a732", working: "#3574f0", idle: "#5fb865", failed: "#e5534b", stopped: "#868a91" })
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 8; spacing: 6
        Button { objectName: "newContextButton"; text: "+ New context"
                 onClicked: { var id = app.contexts.newBare(""); if (id) app.layout.openContent("context", id, "New context") } }
        ListView {
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 2
            model: app.contexts.model
            delegate: Rectangle {
                required property string id
                required property string title
                required property string storyKey
                required property string owner
                required property string status
                required property string roleName
                required property double costUsd
                objectName: "contextRow_" + id
                width: ListView.view.width; height: 30; radius: 4
                color: hh.hovered ? app.theme.panel : "transparent"
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8; spacing: 8
                    Rectangle { width: 8; height: 8; radius: 4; color: statusColor[status] || "gray" }
                    Label { text: storyKey; color: app.theme.accent; font.pixelSize: 11; font.family: app.theme.monoFamily }
                    Label { text: title; color: app.theme.text; Layout.fillWidth: true; elide: Text.ElideRight }
                    Label { text: owner === "human" ? "you" : owner; color: app.theme.textMuted; font.pixelSize: 11 }
                    Label { text: roleName; color: app.theme.textMuted; font.pixelSize: 11 }
                    Label { text: status; color: app.theme.textMuted; font.pixelSize: 11 }
                }
                HoverHandler { id: hh }
                TapHandler { onTapped: app.layout.openContent("context", id, title) }
            }
            Label { anchors.centerIn: parent; visible: parent.count === 0; text: "No contexts yet"; color: app.theme.textMuted }
        }
    }
}
