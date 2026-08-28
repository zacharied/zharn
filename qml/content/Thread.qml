import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

ContentBase {
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 14; spacing: 8
        Label { text: "Thread" + (tabKey && tabKey !== "thread" ? " · " + tabKey : ""); color: app.theme.text; font.pixelSize: 16; font.bold: true }
        Label { text: "Conversation stream goes here (claude -p --output-format stream-json)."; color: app.theme.textMuted }
        Rectangle { Layout.fillWidth: true; height: 80; radius: 6; color: app.theme.panel; border.color: app.theme.border
            Label { anchors.centerIn: parent; text: "▶ agent working…"; color: app.theme.textMuted } }
        Item { Layout.fillHeight: true }
    }
}
