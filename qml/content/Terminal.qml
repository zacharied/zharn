import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

ContentBase {
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 14; spacing: 8
        Label { text: "Terminal" + (tabKey && tabKey !== "terminal" ? " · " + tabKey : ""); color: app.theme.text; font.pixelSize: 16; font.bold: true }
        Label { text: "$ (pyte-backed terminal panel, TODO)"; color: app.theme.text; font.family: app.theme.monoFamily }
        Item { Layout.fillHeight: true }
    }
}
