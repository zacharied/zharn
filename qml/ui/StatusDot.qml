import QtQuick
import "Theme.js" as T

// Liveness dot: pulses while a context is working.
Rectangle {
    id: d
    property string status: "none"
    property int size: 8
    width: size; height: size; radius: size / 2
    color: T.statusColor(app.theme, status)
    readonly property bool live: status === "working" || status === "starting"
    SequentialAnimation on opacity {
        running: d.live; loops: Animation.Infinite
        NumberAnimation { to: 0.25; duration: 700; easing.type: Easing.InOutSine }
        NumberAnimation { to: 1; duration: 700; easing.type: Easing.InOutSine }
    }
    onLiveChanged: if (!live) opacity = 1
}
