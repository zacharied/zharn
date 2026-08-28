import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

ContentBase {
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 14; spacing: 8
        Label { text: "Task" + (tabKey && tabKey !== "task" ? " · " + tabKey : ""); color: app.theme.text; font.pixelSize: 16; font.bold: true }
        Label { text: "Description · comments · subtasks · attached threads"; color: app.theme.textMuted }
        Item { Layout.fillHeight: true }
    }
}
