import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

ContentBase {
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 14; spacing: 8
        Label { text: "Files" + (tabKey && tabKey !== "files" ? " · " + tabKey : ""); color: app.theme.text; font.pixelSize: 16; font.bold: true }
        Repeater { model: ["harness/", "qml/", "docs/", "tests/", "pyproject.toml"]; delegate: Label { text: modelData; color: app.theme.text; font.family: app.theme.monoFamily } }
        Item { Layout.fillHeight: true }
    }
}
