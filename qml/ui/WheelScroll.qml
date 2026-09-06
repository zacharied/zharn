import QtQuick

// Puts the wheel back on a Flickable that gave up `interactive` so its prose could select.
//
// `interactive: false` is what lets a drag reach the TextEdit under it instead of panning the
// page (see Prose.qml), but it makes the Flickable ignore the wheel too — so the wheel is
// handled here, against the same extents Flickable itself uses.
//
// The margins are the whole reason this is shared rather than copied. A ListView with a
// bottomMargin has its real bottom at originY + contentHeight + bottomMargin - height; clamping
// even a pixel short of it means atYEnd is never true, which silently breaks anything watching
// for the tail. originY is not 0 on a ListView that has scrolled, either.
WheelHandler {
    property Flickable flick      // the Flickable this sits in; a handler's `parent` is null here
    signal scrolled()

    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
    onWheel: (e) => {
        var dy = e.pixelDelta.y !== 0 ? e.pixelDelta.y : e.angleDelta.y / 120 * 60
        var top = flick.originY - flick.topMargin
        var bottom = Math.max(top, flick.originY + flick.contentHeight + flick.bottomMargin - flick.height)
        flick.contentY = Math.max(top, Math.min(bottom, flick.contentY - dy))
        scrolled()
    }
}
