import QtQuick
import QtQuick.Layouts

// 36px tool-window header: bold title, optional muted subtitle, actions on the right.
Rectangle {
    id: h
    property string title
    property string subtitle: ""
    default property alias actions: actionRow.data
    height: app.theme.headerHeight; color: app.theme.panel
    RowLayout {
        anchors { fill: parent; leftMargin: 12; rightMargin: 6 }
        spacing: 8
        Text { text: h.title; color: app.theme.text; font.weight: Font.DemiBold; font.pixelSize: app.theme.fontSize }
        Text { visible: !!h.subtitle; text: h.subtitle; color: app.theme.textMuted; font.pixelSize: app.theme.fontSize; elide: Text.ElideRight; Layout.maximumWidth: 160 }
        Item { Layout.fillWidth: true }
        Row { id: actionRow; spacing: 2 }
    }
}
