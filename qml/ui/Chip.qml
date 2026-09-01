import QtQuick

// Pill label: "2 need you", "ZH-12", phase chips.
Rectangle {
    id: c
    property string text
    property color fg: app.theme.textMuted
    property color bg: Qt.rgba(fg.r, fg.g, fg.b, 0.14)
    property bool mono: false
    height: 18; radius: 9; color: bg
    width: label.implicitWidth + 14
    Text { id: label; anchors.centerIn: parent; text: c.text; color: c.fg
           font.pixelSize: app.theme.fontSizeSmall; font.weight: Font.Medium
           font.family: c.mono ? app.theme.monoFamily : app.theme.fontFamily }
}
