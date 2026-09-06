import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// New context, with the picks: a bare conversation of your own, on the model, effort and preset you
// choose. The position is not offered — New context opens a bare one, and that is what the button means.
Popup {
    id: dlg
    signal created(string contextId)
    modal: true
    anchors.centerIn: Overlay.overlay
    width: 440; padding: 16
    background: Rectangle { color: app.theme.panel; radius: app.theme.radiusLarge; border.color: app.theme.border }
    onOpened: picks.seed("", "", "")
    contentItem: ColumnLayout {
        spacing: 10
        Text { text: "New context"; color: app.theme.text; font.weight: Font.DemiBold; font.pixelSize: 14 }
        Text {
            Layout.fillWidth: true; wrapMode: Text.Wrap; color: app.theme.textMuted; font.pixelSize: app.theme.fontSizeSmall; lineHeight: 1.3
            text: "A bare context: no story, no obligations, and the skills its preset gives it. Leave a pick on default to take the bare position's own."
        }
        CastPicks { id: picks; prefix: "bare"; Layout.fillWidth: true }
        RowLayout {
            Item { Layout.fillWidth: true }
            Btn { objectName: "newContextCancel"; quiet: true; text: "Cancel"; onClicked: dlg.close() }
            Btn {
                objectName: "newContextConfirm"; primary: true; text: "Create"
                onClicked: {
                    var id = app.contexts.newBare("", picks.modelId, picks.effort, picks.preset)
                    dlg.close()
                    if (id) dlg.created(id)
                }
            }
        }
    }
}
