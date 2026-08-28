import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Main Content Container: a tab group. Tabs can be dragged to other groups (reorder/move)
// or onto the edges of a group's content area (split). All of that is sent as intents.
Rectangle {
    id: group
    property var node
    readonly property string groupId: node ? node.id : ""
    readonly property bool isActive: app.layout.activeGroup === groupId
    readonly property int tabCount: node ? node.tabs.length : 0
    objectName: "group_" + groupId
    color: app.theme.bg

    Component {
        id: ghostComp
        Rectangle {
            property string fromGroup
            property int tabIndex
            property string title
            width: ghostLabel.implicitWidth + 24; height: 26; radius: 4; z: 10000
            color: app.theme.accentSoft; border.color: app.theme.accent; opacity: 0.92
            Text { id: ghostLabel; anchors.centerIn: parent; text: title; color: app.theme.text }
            Drag.keys: ["tab"]
            Drag.hotSpot.x: 12; Drag.hotSpot.y: 13
        }
    }

    ColumnLayout {
        anchors.fill: parent; spacing: 0

        // ---- tab bar
        Rectangle {
            id: bar
            Layout.fillWidth: true; height: 34; color: app.theme.panel
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: app.theme.border }

            Row {
                id: tabRow
                anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                Repeater {
                    model: group.node ? group.node.tabs : []
                    delegate: Rectangle {
                        id: tabItem
                        required property int index
                        required property var modelData
                        readonly property bool current: index === group.node.active
                        objectName: "tab_" + modelData.kind + "_" + modelData.key
                        width: tLabel.implicitWidth + 44; height: bar.height
                        color: current ? app.theme.tabActive : (tabHover.hovered ? app.theme.border : "transparent")
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2
                                    color: current && group.isActive ? app.theme.accent : "transparent" }
                        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: app.theme.border }
                        Text {
                            id: tLabel; x: 12; anchors.verticalCenter: parent.verticalCenter
                            text: app.content.iconFor(modelData.kind) + "  " + modelData.title
                            color: current ? app.theme.text : app.theme.textMuted
                        }
                        Text {
                            text: "×"; anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                            color: closeHover.hovered ? app.theme.text : app.theme.textMuted; font.pixelSize: 15
                            HoverHandler { id: closeHover }
                            TapHandler { onTapped: app.layout.closeTab(group.groupId, tabItem.index) }
                        }
                        HoverHandler { id: tabHover }
                        MouseArea {
                            anchors.fill: parent; anchors.rightMargin: 26
                            acceptedButtons: Qt.LeftButton | Qt.MiddleButton
                            property point pressPos
                            property Item ghost: null
                            onPressed: (mouse) => { pressPos = Qt.point(mouse.x, mouse.y); ghost = null }
                            onPositionChanged: (mouse) => {
                                if (!pressed) return
                                if (!ghost && Math.hypot(mouse.x - pressPos.x, mouse.y - pressPos.y) > 6) {
                                    ghost = ghostComp.createObject(Overlay.overlay, {
                                        fromGroup: group.groupId, tabIndex: tabItem.index, title: tabItem.modelData.title })
                                    ghost.Drag.active = true
                                }
                                if (ghost) {
                                    var p = tabItem.mapToItem(Overlay.overlay, mouse.x, mouse.y)
                                    ghost.x = p.x - 12; ghost.y = p.y - 13
                                }
                            }
                            onReleased: (mouse) => {
                                if (ghost) { ghost.Drag.drop(); ghost.destroy(); ghost = null }
                                else if (mouse.button === Qt.MiddleButton) app.layout.closeTab(group.groupId, tabItem.index)
                                else app.layout.activateTab(group.groupId, tabItem.index)
                            }
                            onCanceled: if (ghost) { ghost.destroy(); ghost = null }
                        }
                    }
                }
            }
            // drop onto the bar → move/reorder into this group at the pointer position
            DropArea {
                id: barDrop
                anchors.fill: parent; keys: ["tab"]
                onDropped: (drop) => {
                    var insertAt = group.tabCount
                    for (var i = 0; i < tabRow.children.length; i++) {
                        var c = tabRow.children[i]
                        if (c.width === undefined) continue
                        if (drop.x < c.x + c.width / 2) { insertAt = i; break }
                    }
                    app.layout.moveTab(drop.source.fromGroup, drop.source.tabIndex, group.groupId, insertAt)
                    drop.accept()
                }
                Rectangle { anchors.fill: parent; color: app.theme.dropHint; visible: barDrop.containsDrag }
            }
            // split buttons
            Row {
                anchors { right: parent.right; verticalCenter: parent.verticalCenter; rightMargin: 6 }
                spacing: 2
                Repeater {
                    model: [{ t: "◧", o: "horizontal", tip: "Split right" }, { t: "⬒", o: "vertical", tip: "Split down" }]
                    delegate: Label {
                        text: modelData.t; padding: 4; color: sh.hovered ? app.theme.text : app.theme.textMuted
                        HoverHandler { id: sh }
                        TapHandler { onTapped: app.layout.splitGroup(group.groupId, modelData.o) }
                        ToolTip.visible: sh.hovered; ToolTip.text: modelData.tip
                    }
                }
            }
        }

        // ---- content
        Item {
            id: contentArea
            Layout.fillWidth: true; Layout.fillHeight: true
            Repeater {
                model: group.node ? group.node.tabs : []
                delegate: Loader {
                    required property int index
                    required property var modelData
                    anchors.fill: parent
                    active: index === group.node.active
                    visible: active
                    Component.onCompleted: setSource(app.content.qmlFor(modelData.kind), { tabKey: modelData.key, tabTitle: modelData.title })
                }
            }
            Text {
                visible: group.tabCount === 0
                anchors.centerIn: parent; color: app.theme.textMuted
                text: "Empty container — drop a tab here"
            }
            MouseArea { anchors.fill: parent; z: -1; onPressed: (m) => { app.layout.activateTab(group.groupId, group.node.active); m.accepted = false } }

            // edge / center drop zones → split or move
            Repeater {
                model: [
                    { edge: "left",   x: 0,    y: 0,    w: 0.25, h: 1 },
                    { edge: "right",  x: 0.75, y: 0,    w: 0.25, h: 1 },
                    { edge: "top",    x: 0.25, y: 0,    w: 0.5,  h: 0.3 },
                    { edge: "bottom", x: 0.25, y: 0.7,  w: 0.5,  h: 0.3 },
                    { edge: "center", x: 0.25, y: 0.3,  w: 0.5,  h: 0.4 }
                ]
                delegate: DropArea {
                    required property var modelData
                    x: contentArea.width * modelData.x; y: contentArea.height * modelData.y
                    width: contentArea.width * modelData.w; height: contentArea.height * modelData.h
                    keys: ["tab"]
                    onDropped: (drop) => {
                        if (modelData.edge === "center") app.layout.moveTab(drop.source.fromGroup, drop.source.tabIndex, group.groupId, -1)
                        else app.layout.moveTabToEdge(drop.source.fromGroup, drop.source.tabIndex, group.groupId, modelData.edge)
                        drop.accept()
                    }
                    Rectangle { anchors.fill: parent; color: app.theme.dropHint; border.color: app.theme.accent; visible: parent.containsDrag }
                }
            }
        }
    }
    Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: app.theme.border }
}
