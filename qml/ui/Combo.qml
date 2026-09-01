import QtQuick
import QtQuick.Controls.Basic

// Drop-down, New UI styling.
ComboBox {
    id: c
    implicitHeight: app.theme.controlHeight
    font.pixelSize: app.theme.fontSize
    contentItem: Text { leftPadding: 8; rightPadding: 24; text: c.displayText; color: app.theme.text; font: c.font; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
    indicator: Icon { name: "down"; size: 14; x: c.width - width - 6; y: (c.height - height) / 2; color: app.theme.textMuted }
    background: Rectangle { radius: app.theme.radius; color: c.pressed ? app.theme.hover : "transparent"; border.color: c.activeFocus ? app.theme.accent : app.theme.buttonBorder }
    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: c.width; height: 26; highlighted: c.highlightedIndex === index
        contentItem: Text { text: modelData; color: app.theme.text; font: c.font; verticalAlignment: Text.AlignVCenter; leftPadding: 4 }
        background: Rectangle { color: highlighted ? app.theme.selection : "transparent"; radius: 3 }
    }
    popup: Popup {
        y: c.height + 2; width: c.width; padding: 4
        contentItem: ListView { implicitHeight: contentHeight; model: c.popup.visible ? c.delegateModel : null; currentIndex: c.highlightedIndex; clip: true }
        background: Rectangle { color: app.theme.panel; radius: app.theme.radiusLarge; border.color: app.theme.border }
    }
}
