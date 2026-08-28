import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

ContentBase {
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 14; spacing: 8
        Label { text: "Unknown content kind" + (tabKey && tabKey !== "missing" ? " · " + tabKey : ""); color: app.theme.text; font.pixelSize: 16; font.bold: true }
        Label { text: "Register it in harness/content.py"; color: app.theme.textMuted }
        Item { Layout.fillHeight: true }
    }
}
