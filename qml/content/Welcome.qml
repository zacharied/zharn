import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

ContentBase {
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 14; spacing: 8
        Label { text: "Welcome to my-harness" + (tabKey && tabKey !== "welcome" ? " · " + tabKey : ""); color: app.theme.text; font.pixelSize: 16; font.bold: true }
        Label { text: "Native Qt. Your fork is your config. Edit qml/ or harness/ and watch it reload."; color: app.theme.textMuted; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Row { spacing: 8
            Button { text: "Open a thread"; onClicked: app.layout.openContent("thread", "thr_demo1", "claude: fix tests") }
            Button { text: "Open task ABC-12"; onClicked: app.layout.openContent("task", "ABC-12", "ABC-12 Hot reload") }
            Button { text: "Open a document"; onClicked: app.layout.openContent("document", "harness/layout.py", "layout.py") }
            Button { text: "Reset layout"; onClicked: app.layout.resetLayout() }
        }
        Item { Layout.fillHeight: true }
    }
}
