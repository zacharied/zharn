import QtQuick
import QtQuick.Controls.Basic

// Multi-line input with an optional small label inside (the composer's "Reply to Protagonist").
// Ctrl+Enter → submitted().
TextArea {
    id: t
    property string label: ""
    signal submitted()
    wrapMode: TextEdit.Wrap
    color: app.theme.text
    placeholderTextColor: app.theme.textDim
    font.pixelSize: app.theme.fontSize
    topPadding: label ? 24 : 8; bottomPadding: 8; leftPadding: 10; rightPadding: 10
    background: Rectangle {
        color: app.theme.bg; radius: app.theme.radiusLarge
        border.color: t.activeFocus ? app.theme.accent : app.theme.border
        border.width: t.activeFocus ? 2 : 1
        Text { visible: !!t.label; x: 10; y: 7; text: t.label; color: app.theme.textMuted
               font.family: app.theme.monoFamily; font.pixelSize: app.theme.fontSizeSmall; font.weight: Font.Medium
               font.letterSpacing: 1; font.capitalization: Font.AllUppercase }
    }
    Keys.onPressed: (e) => {
        if ((e.key === Qt.Key_Return || e.key === Qt.Key_Enter) && (e.modifiers & Qt.ControlModifier)) { t.submitted(); e.accepted = true }
    }
}
