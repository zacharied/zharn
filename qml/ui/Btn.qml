import QtQuick
import QtQuick.Controls.Basic

// New UI button: outlined by default, `primary` fills with the accent, `quiet` drops the border.
Button {
    id: b
    property bool primary: false
    property bool quiet: false
    property bool small: false
    property string icon_: ""
    implicitHeight: small ? 24 : app.theme.controlHeight
    leftPadding: small ? 9 : 12; rightPadding: small ? 9 : 12
    font.pixelSize: small ? app.theme.fontSizeSmall + 1 : app.theme.fontSize
    font.weight: Font.Medium
    contentItem: Row {
        spacing: 6
        Icon { visible: !!b.icon_; name: b.icon_; size: 14; anchors.verticalCenter: parent.verticalCenter
               color: b.primary ? "white" : (b.enabled ? app.theme.text : app.theme.textDim) }
        Text { text: b.text; font: b.font; anchors.verticalCenter: parent.verticalCenter
               color: b.primary ? "white" : (b.quiet ? (b.hovered ? app.theme.text : app.theme.textMuted) : app.theme.text)
               opacity: b.enabled ? 1 : 0.45 }
    }
    background: Rectangle {
        radius: app.theme.radius
        color: b.primary ? (b.hovered ? app.theme.accentHover : app.theme.accent) : (b.quiet && b.hovered ? app.theme.hover : "transparent")
        border.width: b.primary || b.quiet ? 0 : 1
        border.color: b.hovered ? "#7a7d84" : app.theme.buttonBorder
        opacity: b.enabled ? 1 : 0.45
    }
}
