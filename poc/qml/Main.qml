import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: win
    width: 480; height: 360; visible: true
    title: "harness poc"

    ColumnLayout {
        anchors.fill: parent; anchors.margins: 16; spacing: 8
        Label { text: "counter: " + store.counter; font.pixelSize: 28 }
        Label { text: "hot reloads so far: " + store.reloads; color: "gray" }
        Button { text: "bump"; onClicked: store.bump() }
        Panel { Layout.fillWidth: true; Layout.fillHeight: true }
    }
}
