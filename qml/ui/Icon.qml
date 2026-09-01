import QtQuick
import "Theme.js" as T

// A monochrome icon from qml/icons/<name>.svg, colored on the fly (harness/icons.py).
Image {
    id: icon
    property string name
    property color color: app.theme.textMuted
    property int size: 16
    width: size; height: size
    sourceSize: Qt.size(size * Screen.devicePixelRatio, size * Screen.devicePixelRatio)
    source: name ? "image://icon/" + name + "/" + T.hex(color) : ""
    smooth: true
}
