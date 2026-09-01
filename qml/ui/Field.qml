import QtQuick
import QtQuick.Controls.Basic

// Single-line input, New UI styling.
TextField {
    id: f
    color: app.theme.text
    placeholderTextColor: app.theme.textDim
    font.pixelSize: app.theme.fontSize
    implicitHeight: app.theme.controlHeight
    leftPadding: 8; rightPadding: 8
    background: Rectangle {
        color: app.theme.bg; radius: app.theme.radius
        border.color: f.activeFocus ? app.theme.accent : app.theme.buttonBorder
        border.width: f.activeFocus ? 2 : 1
    }
}
