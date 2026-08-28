import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

ContentBase {
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 14; spacing: 8
        Label { text: "Agent Log" + (tabKey && tabKey !== "agent_log" ? " · " + tabKey : ""); color: app.theme.text; font.pixelSize: 16; font.bold: true }
        Label { text: "thr_demo1  working  12s"; color: app.theme.textMuted; font.family: app.theme.monoFamily }
        Item { Layout.fillHeight: true }
    }
}
