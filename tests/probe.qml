import QtQuick

// Test probe, instantiated by tests/ui.py inside the app's engine. Everything about items
// (lookup, geometry, properties, focus) happens here in JS and comes back as plain values in
// `result`, so Python never holds wrappers for QML-created items — those go stale when a
// generation is torn down and shiboken then hands back the wrong object for a reused address.
QtObject {
    property var win        // the QQuickWindow (set by Python)
    property var result

    function _walk(item, rx, out) {
        if (rx.test(item.objectName || "")) out.push(item)
        var cs = item.children
        for (var i = 0; i < cs.length; i++) _walk(cs[i], rx, out)
        return out
    }
    function _all(pattern) { return _walk(win.contentItem, new RegExp("^(?:" + pattern + ")$"), []) }
    function _nth(pattern, nth) {
        var items = _all(pattern)
        if (nth >= items.length) throw new Error("no item #" + nth + " for " + pattern)
        return items[nth]
    }
    function _info(item) {
        var p = item.mapToItem(null, 0, 0)
        return { name: item.objectName, visible: item.visible && item.width > 0 && item.height > 0,
                 x: p.x, y: p.y, w: item.width, h: item.height }
    }

    function match(pattern) { result = _all(pattern).map(_info) }
    function prop(pattern, nth, key) { var v = _nth(pattern, nth)[key]; result = (v !== null && typeof v === "object" && !Array.isArray(v)) ? String(v) : v }
    function set(pattern, nth, key, value) { _nth(pattern, nth)[key] = value; result = true }
    function focus(pattern, nth) { _nth(pattern, nth).forceActiveFocus(); result = true }
    function choose(pattern, nth, text) {   // ComboBox: what a user ends up with after picking an entry
        var c = _nth(pattern, nth), i = c.find(text)
        if (i < 0) throw new Error("no entry " + text + " in " + pattern)
        c.currentIndex = i
        c.activated(i)
        result = i
    }
}
