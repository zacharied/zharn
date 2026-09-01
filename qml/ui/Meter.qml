import QtQuick

// Context meter: 0..1, turns amber past `hot`.
Rectangle {
    property real value: 0
    property real hot: 0.8
    width: 56; height: 5; radius: 3; color: app.theme.border
    Rectangle { height: parent.height; radius: 3; width: parent.width * Math.max(0, Math.min(1, parent.value))
               color: parent.value >= parent.hot ? app.theme.needsYou : app.theme.textMuted }
}
