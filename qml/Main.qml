import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// The window. Everything below is a projection of app.layout (Python-owned tree).
ApplicationWindow {
    id: win
    objectName: "mainWindow"
    visible: true
    title: "my-harness"
    color: app.theme.bg
    font.family: app.theme.fontFamily
    font.pixelSize: app.theme.fontSize
    palette {  // Basic-style controls follow the palette, so buttons etc. match the theme
        window: app.theme.bg; windowText: app.theme.text
        base: app.theme.panel; text: app.theme.text; placeholderText: app.theme.textMuted
        button: app.theme.panel; buttonText: app.theme.text
        highlight: app.theme.accent; highlightedText: "white"
        mid: app.theme.border; dark: app.theme.border; light: app.theme.border
    }
    width: app.savedGeometry.w
    height: app.savedGeometry.h
    Component.onCompleted: if (app.savedGeometry.x >= 0) { x = app.savedGeometry.x; y = app.savedGeometry.y }
    onXChanged: geometrySave.restart()
    onYChanged: geometrySave.restart()
    onWidthChanged: geometrySave.restart()
    onHeightChanged: geometrySave.restart()
    Timer { id: geometrySave; interval: 500; onTriggered: app.saveGeometry(win.x, win.y, win.width, win.height) }

    readonly property var layoutTree: JSON.parse(app.layout.layoutJson)
    readonly property var docks: layoutTree.docks

    ToolStrip {
        id: leftStrip; side: "left"; dock: win.docks.left
        anchors { left: parent.left; top: parent.top; bottom: bottomStrip.top }
    }
    ToolStrip {
        id: rightStrip; side: "right"; dock: win.docks.right
        anchors { right: parent.right; top: parent.top; bottom: bottomStrip.top }
    }
    ToolStrip {
        id: bottomStrip; side: "bottom"; dock: win.docks.bottom
        anchors { left: parent.left; right: parent.right; bottom: statusBar.top }
    }

    SplitView {
        id: hsplit
        objectName: "hsplit"
        orientation: Qt.Horizontal
        anchors { left: leftStrip.right; right: rightStrip.left; top: parent.top; bottom: bottomStrip.top }
        handle: SplitGrip {}

        Dock {
            id: leftDock; side: "left"; dock: win.docks.left
            visible: dock.mode === "docked" && !!dock.active
            SplitView.preferredWidth: dock.size; SplitView.minimumWidth: 120
        }
        SplitView {
            id: vsplit
            orientation: Qt.Vertical
            SplitView.fillWidth: true; SplitView.minimumWidth: 200
            handle: SplitGrip {}
            LayoutNode { objectName: "centerRoot"; node: win.layoutTree.center; SplitView.fillHeight: true; SplitView.minimumHeight: 120 }
            Dock {
                id: bottomDock; side: "bottom"; dock: win.docks.bottom
                visible: dock.mode === "docked" && !!dock.active
                SplitView.preferredHeight: dock.size; SplitView.minimumHeight: 100
            }
            onResizingChanged: if (!resizing && bottomDock.visible) app.layout.setDockSize("bottom", bottomDock.height)
        }
        Dock {
            id: rightDock; side: "right"; dock: win.docks.right
            visible: dock.mode === "docked" && !!dock.active
            SplitView.preferredWidth: dock.size; SplitView.minimumWidth: 120
        }
        onResizingChanged: if (!resizing) {
            if (leftDock.visible) app.layout.setDockSize("left", leftDock.width)
            if (rightDock.visible) app.layout.setDockSize("right", rightDock.width)
        }
    }

    // status bar: hot-reload telemetry lives here so self-modification is always visible
    Rectangle {
        id: statusBar
        height: 24
        color: app.theme.panel
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        Rectangle { width: parent.width; height: 1; color: app.theme.border }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 16
            Label { objectName: "statusText"; text: app.notify.status; color: app.theme.textMuted }
            Label {
                objectName: "errorBanner"
                text: app.notify.lastError ? "✗ " + app.notify.lastError.split("\n")[0] : ""
                color: "#e5534b"; elide: Text.ElideRight; Layout.fillWidth: true
                visible: !!app.notify.lastError
            }
            Label {
                objectName: "errorDismiss"; visible: !!app.notify.lastError
                text: "✕"; color: app.theme.textMuted; padding: 2
                TapHandler { onTapped: app.notify.dismiss() }
            }
            Label {
                objectName: "reloadError"
                text: app.reloadError ? "⚠ " + app.reloadError.split("\n")[0] : ""
                color: "#f0a732"; elide: Text.ElideRight; Layout.fillWidth: true
                visible: !!app.reloadError
            }
            Item { Layout.fillWidth: !app.reloadError && !app.notify.lastError }
            Rectangle {
                objectName: "restartBadge"
                visible: app.restartRequired
                color: app.theme.accent; radius: 3; height: 18; width: restartLabel.implicitWidth + 16
                Label { id: restartLabel; anchors.centerIn: parent; text: "shape changed — restart"; color: "white"; font.pixelSize: 11 }
                MouseArea { anchors.fill: parent; onClicked: app.restart() }
            }
            Label { text: "gen " + app.generation + " · watch:" + app.watchMode; color: app.theme.textMuted; font.pixelSize: 11 }
        }
    }
}
