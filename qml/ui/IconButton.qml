import QtQuick
import QtQuick.Controls.Basic

// Square icon button (tool-window header actions, tab-bar actions, toolbar buttons).
Rectangle {
    id: b
    property string icon
    property int iconSize: 16
    property int size: 24
    property bool active: false
    property string tip: ""
    property color iconColor: active || hover.hovered ? app.theme.text : app.theme.textMuted
    signal clicked()
    width: size; height: size; radius: app.theme.radius
    color: active ? app.theme.hover : (hover.hovered ? app.theme.hover : "transparent")
    Icon { anchors.centerIn: parent; name: b.icon; size: b.iconSize; color: b.iconColor }
    HoverHandler { id: hover }
    TapHandler { onTapped: b.clicked() }
    ToolTip.visible: tip && hover.hovered; ToolTip.text: tip; ToolTip.delay: 600
}
