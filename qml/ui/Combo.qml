import QtQuick
import QtQuick.Controls.Basic

// Drop-down, New UI styling. `editable: true` turns it into a combo you can also type into —
// the content item is a text input either way, disabled when the drop-down is a closed list, which
// is what lets a click on a non-editable one fall through and open the popup.
ComboBox {
    id: c
    implicitHeight: app.theme.controlHeight
    implicitContentWidthPolicy: ComboBox.WidestText   // wide enough for the longest entry, not just the current one
    font.pixelSize: app.theme.fontSize
    contentItem: TextField {
        leftPadding: 8; rightPadding: 24; topPadding: 0; bottomPadding: 0
        text: c.editable ? c.editText : c.displayText
        enabled: c.editable
        autoScroll: c.editable      // a closed list reads from the left; scrolling it to the tail hides the word
        readOnly: c.down
        color: app.theme.text; font: c.font
        placeholderTextColor: app.theme.textDim
        selectionColor: app.theme.selection; selectedTextColor: app.theme.text
        selectByMouse: true
        verticalAlignment: Text.AlignVCenter
        background: null
    }
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
