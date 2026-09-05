import QtQuick

// Context meter: a context's reading laid on the harness's runway — the bar ends at the recast
// line (`max`), a tick marks the recap line (`tick`); `hot` colors the fill amber while a recap
// is outstanding. The window is not the frame: a 1M character is replaced at 500K.
Item {
    id: meter
    property int value: 0
    property int max: 1
    property int tick: 0
    property bool hot: false
    readonly property real fraction: max > 0 ? Math.max(0, Math.min(1, value / max)) : 0
    implicitWidth: 72; implicitHeight: 4
    Rectangle { anchors.fill: parent; radius: height / 2; color: app.theme.border }
    Rectangle { objectName: "meterFill"; height: parent.height; radius: height / 2; width: Math.round(parent.width * meter.fraction)
                color: meter.hot ? app.theme.needsYou : app.theme.textMuted
                Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } } }
    Rectangle { visible: meter.tick > 0 && meter.max > 0 && meter.tick < meter.max
                x: Math.round(parent.width * meter.tick / meter.max) - 1; y: -2; width: 1; height: parent.height + 4
                color: app.theme.text; opacity: 0.55 }
}
