import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../ui"

ContentBase {
    ColumnLayout {
        anchors { left: parent.left; top: parent.top; margins: 28 }
        width: Math.min(parent.width - 56, 640); spacing: 10
        Text { text: "zharn"; color: app.theme.text; font.pixelSize: 22; font.weight: Font.DemiBold }
        Text { text: "Work is a story. Write one, press Start, and answer the protagonist when the ball is yours."; color: app.theme.textMuted; wrapMode: Text.Wrap; Layout.fillWidth: true; lineHeight: 1.3 }
        Text { text: "Your fork is your config: edit qml/ or harness/ while it runs and watch it reload."; color: app.theme.textMuted; wrapMode: Text.Wrap; Layout.fillWidth: true; lineHeight: 1.3 }
        Flow { spacing: 8; Layout.fillWidth: true; Layout.topMargin: 6
            Btn { objectName: "welcomeNewStory"; primary: true; icon_: "play"; text: "New story"
                  onClicked: { var k = app.stories.create("New story", ""); if (k) app.layout.openContent("story", k, k) } }
            Btn { objectName: "welcomeOpenBoard"; icon_: "stories"; text: "Stories"; onClicked: app.layout.showPanel("board") }
            Btn { objectName: "welcomeContexts"; icon_: "contexts"; text: "Contexts"; onClicked: app.layout.showPanel("contexts") }
            Btn { objectName: "welcomeWorkspace"; icon_: "folder-open"; text: "Workspace"; onClicked: app.layout.openContent("workspace", "workspace", "Workspace") }
            Btn { objectName: "welcomeNewContext"; icon_: "context"; text: "New context"
                  onClicked: { var id = app.contexts.newBare(""); if (id) app.layout.openContent("context", id, "New context") } }
            Btn { objectName: "welcomeReset"; quiet: true; text: "Reset layout"; onClicked: app.layout.resetLayout() }
        }
        Text { Layout.topMargin: 10; Layout.fillWidth: true; wrapMode: Text.Wrap
               text: "Agents drive this app too:  $HARNESS_CLI context new --role claude-fast --prompt \"...\" --wait"
               color: app.theme.textDim; font.family: app.theme.monoFamily; font.pixelSize: app.theme.fontSizeSmall }
    }
}
