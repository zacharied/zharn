import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../ui"

// One agent conversation as an editor tab: header + ContextView. tabKey = context id.
ContentBase {
    id: view
    readonly property var context: app.contexts.get(tabKey)
    readonly property bool busy: context ? (context.status === "working" || context.status === "starting") : false

    Label {
        objectName: "contextMissing"; visible: !view.context
        anchors.centerIn: parent; width: parent.width - 40; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
        text: "Context " + tabKey + " not found — it may have been removed, or the tab is stale."; color: app.theme.textMuted
    }

    ColumnLayout {
        visible: !!view.context
        anchors.fill: parent; spacing: 0
        Rectangle {
            Layout.fillWidth: true; height: app.theme.headerHeight; color: app.theme.panel
            RowLayout {
                anchors { fill: parent; leftMargin: 12; rightMargin: 8 }
                spacing: 10
                StatusDot { status: view.context ? view.context.status : "none"; size: 9 }
                Label { objectName: "contextTitle"; text: view.context ? view.context.title : ""; color: app.theme.text; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                Label { objectName: "contextStatus"; text: view.context ? view.context.status : ""; color: app.theme.textMuted; font.pixelSize: app.theme.fontSizeSmall }
                Chip { objectName: "contextStoryLink"; visible: !!(view.context && view.context.storyKey); text: view.context ? view.context.storyKey : ""; fg: "#7da7ff"; mono: true
                       TapHandler { onTapped: app.layout.openContent("story", view.context.storyKey, view.context.storyKey) } }
                Label { text: view.context ? [view.context.position, view.context.model].filter(function (x) { return x }).join(" · ") : ""; color: app.theme.textMuted; font.pixelSize: app.theme.fontSizeSmall }
                Label { text: view.context ? view.context.turns + (view.context.turns === 1 ? " turn" : " turns") + " · $" + view.context.costUsd.toFixed(3) : ""; color: app.theme.textMuted; font.pixelSize: app.theme.fontSizeSmall }
                Btn { objectName: "stopButton"; visible: view.busy; small: true; quiet: true; icon_: "stop"; text: "Stop"; onClicked: view.context.stop() }
            }
            Divider { anchors.bottom: parent.bottom; width: parent.width }
        }
        ContextView { Layout.fillWidth: true; Layout.fillHeight: true; context: view.context }
    }
}
