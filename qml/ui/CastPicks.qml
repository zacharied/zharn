import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// The three picks a character is cast with (lifecycle spec §1): a model — editable, so a model the
// config has not heard of can still be typed — an effort, and a preset naming which skills it wakes
// up with. The position is never here: the cast site is what implies it, and nobody picks it.
//
// Every pick this row makes is explicit — there is no blank standing for "whatever the position says".
// So the row seeds itself from the position's own picks, and reads as what the button will actually do.
// The entries that happen to be empty underneath are choices in their own right: the empty model id is
// the CLI's own default and the empty effort is the provider's own, and both say so.
RowLayout {
    id: picks
    property string prefix: "cast"      // objectNames: <prefix>Model, <prefix>Effort, <prefix>Preset
    property string position: app.casting.defaultPosition
    spacing: 6

    readonly property var models: app.casting.models
    readonly property var modelLabels: models.map(function (m) { return m.label })
    readonly property var efforts: app.casting.efforts
    readonly property var presets: app.casting.presetNames()
    // "" is a level like any other — the one the provider picks for itself — and needs a name to be picked by
    function anEffort(v) { return v || "provider default" }
    function labelOf(id) {
        for (var i = 0; i < models.length; i++) if (models[i].id === id) return models[i].label
        return id || ""
    }
    function idOf(label) {
        var t = String(label).trim()
        for (var i = 0; i < models.length; i++) if (models[i].label === t) return models[i].id
        return t                        // anything unlisted is taken as a model id, typed verbatim
    }

    // What Start / Recast / New context send.
    readonly property string modelId: idOf(modelBox.editText)
    readonly property string effort: effortBox.currentIndex >= 0 ? efforts[effortBox.currentIndex] : ""
    readonly property string preset: presetBox.currentIndex >= 0 ? presets[presetBox.currentIndex] : ""

    // Seed the row from a character being recast, so a recast that changes nothing changes nothing.
    function seed(model, effort, preset) {
        modelBox.editText = labelOf(model || "")
        effortBox.currentIndex = Math.max(0, efforts.indexOf(effort || ""))
        presetBox.currentIndex = Math.max(0, presets.indexOf(preset || ""))
    }
    // ...or from the position, where there is no character yet: Start and New context.
    function seedFromPosition() {
        var d = app.casting.defaultsFor(position)
        seed(d.model || "", d.effort || "", d.preset || "")
    }
    Component.onCompleted: seedFromPosition()
    onPositionChanged: seedFromPosition()

    Combo {
        id: modelBox
        objectName: picks.prefix + "Model"
        editable: true
        model: picks.modelLabels
        Layout.fillWidth: true; Layout.minimumWidth: 128
        onActivated: (i) => editText = picks.modelLabels[i]
        ToolTip.visible: hovered && !popup.visible; ToolTip.delay: 700
        ToolTip.text: "Model — pick one, or type any id the provider knows"
    }
    Combo {
        id: effortBox
        objectName: picks.prefix + "Effort"
        model: picks.efforts.map(picks.anEffort)
        ToolTip.visible: hovered && !popup.visible; ToolTip.delay: 700
        ToolTip.text: "Reasoning effort"
    }
    Combo {
        id: presetBox
        objectName: picks.prefix + "Preset"
        model: picks.presets
        ToolTip.visible: hovered && !popup.visible; ToolTip.delay: 700
        ToolTip.text: "Preset — which skills it wakes up with"
    }
}
