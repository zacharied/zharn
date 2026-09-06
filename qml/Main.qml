import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "ui"

// The window. Everything below is a projection of app.layout (Python-owned tree).
// Chrome follows JetBrains' New UI: main toolbar, icon strips (left strip = left + bottom
// tool windows, right strip = right ones), editor tabs, status bar.
ApplicationWindow {
    id: win
    objectName: "mainWindow"
    visible: true
    title: "zharn"
    color: app.theme.bg
    font.family: app.theme.fontFamily
    font.pixelSize: app.theme.fontSize
    palette {  // Basic-style controls follow the palette, so stock controls match the theme
        window: app.theme.bg; windowText: app.theme.text
        base: app.theme.panel; text: app.theme.text; placeholderText: app.theme.textDim
        button: app.theme.panel; buttonText: app.theme.text
        highlight: app.theme.accent; highlightedText: "white"
        mid: app.theme.border; dark: app.theme.border; light: app.theme.border
        toolTipBase: app.theme.panel; toolTipText: app.theme.text
    }
    width: app.savedGeometry.w
    height: app.savedGeometry.h
    Component.onCompleted: if (app.savedGeometry.x >= 0) { x = app.savedGeometry.x; y = app.savedGeometry.y }
    onXChanged: geometrySave.restart()
    onYChanged: geometrySave.restart()
    onWidthChanged: geometrySave.restart()
    onHeightChanged: geometrySave.restart()
    Timer { id: geometrySave; interval: 500; onTriggered: app.saveGeometry(win.x, win.y, win.width, win.height) }

    // bundled type (qml/fonts/, OFL): Inter for UI, JetBrains Mono for keys, verbs and output
    FontLoader { source: "fonts/Inter-Regular.ttf" }
    FontLoader { source: "fonts/Inter-Medium.ttf" }
    FontLoader { source: "fonts/Inter-SemiBold.ttf" }
    FontLoader { source: "fonts/Inter-Italic.ttf" }
    FontLoader { source: "fonts/JetBrainsMono-Regular.ttf" }
    FontLoader { source: "fonts/JetBrainsMono-Medium.ttf" }
    FontLoader { source: "fonts/JetBrainsMono-Italic.ttf" }

    readonly property var layoutTree: JSON.parse(app.layout.layoutJson)
    readonly property var docks: layoutTree.docks
    readonly property string workspaceName: {
        var parts = app.workspaceDir.split(/[\\/]/).filter(function (p) { return p.length })
        return parts.length ? parts[parts.length - 1] : "zharn"
    }

    // ---- main toolbar
    Rectangle {
        id: toolbar
        objectName: "toolbar"
        height: app.theme.toolbarHeight; color: app.theme.panel
        anchors { left: parent.left; right: parent.right; top: parent.top }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: app.theme.border }
        RowLayout {
            anchors { fill: parent; leftMargin: 10; rightMargin: 8 }
            spacing: 6
            Rectangle {  // workspace widget (the New UI project widget)
                objectName: "workspaceWidget"
                height: 28; radius: app.theme.radius; width: wsRow.implicitWidth + 14
                color: wsHover.hovered ? app.theme.hover : "transparent"
                Row {
                    id: wsRow; anchors.centerIn: parent; spacing: 7
                    Rectangle { width: 20; height: 20; radius: 5; anchors.verticalCenter: parent.verticalCenter
                                gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: "#7c5cff" } GradientStop { position: 1; color: app.theme.accent } }
                                Text { anchors.centerIn: parent; text: win.workspaceName.charAt(0).toUpperCase(); color: "white"; font.pixelSize: 11; font.weight: Font.DemiBold } }
                    Text { text: win.workspaceName; color: app.theme.text; font.weight: Font.DemiBold; anchors.verticalCenter: parent.verticalCenter }
                    Icon { name: "down"; size: 14; anchors.verticalCenter: parent.verticalCenter }
                }
                HoverHandler { id: wsHover }
                TapHandler { onTapped: app.layout.openContent("workspace", "workspace", win.workspaceName) }
                ToolTip.visible: wsHover.hovered; ToolTip.text: app.workspaceDir; ToolTip.delay: 600
            }
            Item { Layout.fillWidth: true }
            Rectangle {  // the run widget slot: New story
                objectName: "newStoryButton"
                height: 28; radius: app.theme.radius; width: nsRow.implicitWidth + 18
                color: nsHover.hovered ? app.theme.hover : "#2e3238"
                Row {
                    id: nsRow; anchors.centerIn: parent; spacing: 6
                    Icon { name: "play"; size: 14; color: app.theme.settled; anchors.verticalCenter: parent.verticalCenter }
                    Text { text: "New story"; color: app.theme.text; font.weight: Font.Medium; anchors.verticalCenter: parent.verticalCenter }
                }
                HoverHandler { id: nsHover }
                TapHandler { onTapped: { var k = app.stories.create("New story", ""); if (k) app.layout.openContent("story", k, k) } }
            }
        }
    }

    ToolStrip {
        id: leftStrip; side: "left"; dock: win.docks.left; bottomDock: win.docks.bottom
        anchors { left: parent.left; top: toolbar.bottom; bottom: statusBar.top }
    }
    ToolStrip {
        id: rightStrip; side: "right"; dock: win.docks.right
        anchors { right: parent.right; top: toolbar.bottom; bottom: statusBar.top }
    }

    SplitView {
        id: hsplit
        objectName: "hsplit"
        orientation: Qt.Horizontal
        anchors { left: leftStrip.right; right: rightStrip.left; top: toolbar.bottom; bottom: statusBar.top }
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

    // ---- status bar: hot-reload telemetry lives here so self-modification is always visible
    Rectangle {
        id: statusBar
        height: app.theme.statusHeight
        color: app.theme.panel
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        Rectangle { width: parent.width; height: 1; color: app.theme.border }
        property int working: 0
        property real cost: 0
        function refresh() {
            var n = 0, c = 0, rows = app.contexts.summaries()
            for (var i = 0; i < rows.length; i++) { if (rows[i].status === "working" || rows[i].status === "starting") n++; c += rows[i].costUsd }
            working = n; cost = c
        }
        Component.onCompleted: refresh()
        Connections { target: app.contexts; function onContextsChanged() { statusBar.refresh() } }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 16
            Label { objectName: "statusText"; text: app.notify.status; color: app.theme.textMuted; font.pixelSize: 12 }
            RowLayout {
                visible: !!app.notify.lastError; spacing: 6; Layout.fillWidth: true
                Icon { name: "error"; size: 14; color: app.theme.danger }
                Label { objectName: "errorBanner"; text: app.notify.lastError ? app.notify.lastError.split("\n")[0] : ""
                        color: app.theme.danger; elide: Text.ElideRight; font.pixelSize: 12; Layout.fillWidth: true }
                IconButton { objectName: "errorDismiss"; icon: "close"; iconSize: 12; size: 18; onClicked: app.notify.dismiss() }
            }
            RowLayout {
                visible: !!app.reloadError; spacing: 6; Layout.fillWidth: true
                Icon { name: "warning"; size: 14; color: app.theme.warning }
                Label { objectName: "reloadError"; text: app.reloadError ? app.reloadError.split("\n")[0] : ""
                        color: app.theme.warning; elide: Text.ElideRight; font.pixelSize: 12; Layout.fillWidth: true }
            }
            Item { Layout.fillWidth: !app.reloadError && !app.notify.lastError }
            Rectangle {
                objectName: "restartBadge"
                visible: app.restartRequired
                color: app.theme.accent; radius: 3; height: 18; width: restartRow.implicitWidth + 14
                Row { id: restartRow; anchors.centerIn: parent; spacing: 5
                      Icon { name: "restart"; size: 12; color: "white"; anchors.verticalCenter: parent.verticalCenter }
                      Label { text: "shape changed — restart"; color: "white"; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter } }
                MouseArea { anchors.fill: parent; onClicked: app.restart() }
            }
            Row {
                visible: statusBar.working > 0; spacing: 6
                Item { width: 12; height: 12; anchors.verticalCenter: parent.verticalCenter
                       Rectangle { anchors.fill: parent; radius: 6; color: "transparent"; border.color: app.theme.border; border.width: 2 }
                       Rectangle { anchors.fill: parent; radius: 6; color: "transparent"; border.color: app.theme.live; border.width: 2
                                   // a quarter arc: mask the ring with a rotating wedge
                                   layer.enabled: false
                                   RotationAnimation on rotation { from: 0; to: 360; duration: 1000; loops: Animation.Infinite; running: statusBar.working > 0 }
                                   opacity: 0.9 } }
                Label { objectName: "workingCount"; text: statusBar.working + (statusBar.working === 1 ? " character working" : " characters working")
                        color: app.theme.textMuted; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
            }
            Label { visible: statusBar.cost > 0; text: "$" + statusBar.cost.toFixed(2); color: app.theme.textMuted; font.pixelSize: 12 }
            Label { text: "gen " + app.generation + " · watch:" + app.watchMode; color: app.theme.textMuted; font.pixelSize: 11 }
        }
    }
}
