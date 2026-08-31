import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

ContentBase {
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 14; spacing: 8
        Label { text: "Welcome to zharn" + (tabKey && tabKey !== "welcome" ? " · " + tabKey : ""); color: app.theme.text; font.pixelSize: 16; font.bold: true }
        Label { text: "Native Qt. Your fork is your config. Edit qml/ or harness/ and watch it reload."; color: app.theme.textMuted; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Label { text: "Work is a story. Open the board, write one, press Start, and answer the protagonist when the ball is yours."; color: app.theme.textMuted; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Row { spacing: 8
            Button { objectName: "welcomeOpenBoard"; text: "Board"; onClicked: app.layout.showPanel("board") }
            Button { objectName: "welcomeNewStory"; text: "New story"
                     onClicked: { var k = app.stories.create("New story", ""); if (k) app.layout.openContent("story", k, k) } }
            Button { objectName: "welcomeContexts"; text: "Contexts"; onClicked: app.layout.showPanel("contexts") }
            Button { objectName: "welcomeNewContext"; text: "New context"
                     onClicked: { var id = app.contexts.newBare(""); if (id) app.layout.openContent("context", id, "New context") } }
            Button { objectName: "welcomeReset"; text: "Reset layout"; onClicked: app.layout.resetLayout() }
        }
        Label { text: "Agents can drive this app too: $HARNESS_CLI context new --role claude-fast --prompt \"...\" --wait"; color: app.theme.textMuted; font.family: app.theme.monoFamily; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Item { Layout.fillHeight: true }
    }
}
