import QtQuick

// The ball: a half-filled circle. Amber when it is with you.
Item {
    id: b
    property bool mine: true
    property int size: 10
    readonly property color c: mine ? app.theme.needsYou : app.theme.textDim
    width: size; height: size
    Rectangle { anchors.fill: parent; radius: width / 2; color: "transparent"; border.color: b.c; border.width: 1.5 }
    Item {  // left half filled
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
        width: parent.width / 2; clip: true
        Rectangle { width: b.size; height: b.size; radius: b.size / 2; color: b.c }
    }
}
