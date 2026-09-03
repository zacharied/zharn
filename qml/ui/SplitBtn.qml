import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// JetBrains split button (the PR view's "Merge ▾"): one primary action, a caret menu of
// variants. `items`: [{label, hint, enabled}]. The main button keeps the caller's objectName
// via mainName; menu rows are <menuName>Item_<i>.
Item {
    id: sb
    property string text
    property bool primary: true
    property string mainName: ""
    property string menuName: "splitMenu"
    property var items: []
    signal triggered()
    signal itemTriggered(int index)
    implicitWidth: row.implicitWidth
    implicitHeight: 28

    Row {
        id: row
        spacing: 0
        Btn {
            id: main
            objectName: sb.mainName
            text: sb.text; primary: sb.primary
            onClicked: sb.triggered()
        }
        Rectangle { width: 1; height: main.height; color: sb.primary ? Qt.darker(app.theme.accent, 1.35) : app.theme.buttonBorder }
        Btn {
            id: caret
            objectName: sb.menuName + "Button"
            primary: sb.primary; leftPadding: 5; rightPadding: 5
            contentItem: Icon { name: "down"; size: 14; color: sb.primary ? "white" : app.theme.text }
            onClicked: menu.open()
        }
    }

    Popup {
        id: menu
        y: row.height + 4; x: 0
        padding: 4
        background: Rectangle { color: app.theme.panel; radius: app.theme.radiusLarge; border.color: app.theme.border }
        contentItem: ColumnLayout {
            spacing: 1
            Repeater {
                model: sb.items
                delegate: Rectangle {
                    id: mi
                    required property var modelData
                    required property int index
                    readonly property bool on: modelData.enabled === undefined || modelData.enabled
                    objectName: sb.menuName + "Item_" + index
                    Layout.fillWidth: true
                    implicitWidth: miRow.implicitWidth + 20; implicitHeight: 28
                    radius: app.theme.radius
                    color: on && miHover.hovered ? app.theme.selection : "transparent"
                    opacity: on ? 1 : 0.45
                    RowLayout {
                        id: miRow
                        anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                        spacing: 10
                        Text { text: mi.modelData.label; color: app.theme.text; font.pixelSize: app.theme.fontSize }
                        Item { Layout.fillWidth: true }
                        Text { visible: !!mi.modelData.hint; text: mi.modelData.hint; color: app.theme.textMuted; font.pixelSize: app.theme.fontSizeSmall }
                    }
                    HoverHandler { id: miHover }
                    TapHandler { enabled: mi.on; onTapped: { menu.close(); sb.itemTriggered(mi.index) } }
                }
            }
        }
    }
}
