import QtQuick
import QtQuick.Controls.Basic

Rectangle {
    implicitWidth: 1; implicitHeight: 1
    color: SplitHandle.pressed ? app.theme.accent : (SplitHandle.hovered ? app.theme.accentSoft : app.theme.border)
    containmentMask: Item { x: -3; y: -3; width: 7; height: 7 }  // fat grab area, thin line
}
