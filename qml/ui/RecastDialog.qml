import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Recast: same character, fresh memory (spec §3.4). Role defaults to the character's current
// one; an empty model means the role's default. Applies now, or at the turn boundary when the
// character is mid-turn (the store decides; either way a system comment records it).
Popup {
    id: dlg
    property string storyKey
    property string characterId
    property string characterName
    property string currentRole
    signal recasted(string contextId)    // the new context id, or "" when deferred to the boundary
    modal: true
    anchors.centerIn: Overlay.overlay
    width: 360; padding: 16
    background: Rectangle { color: app.theme.panel; radius: app.theme.radiusLarge; border.color: app.theme.border }
    onOpened: { roleBox.currentIndex = Math.max(0, app.roles.names().indexOf(dlg.currentRole)); modelField.text = "" }
    contentItem: ColumnLayout {
        spacing: 10
        Text { text: "Recast " + dlg.characterName; color: app.theme.text; font.weight: Font.DemiBold; font.pixelSize: 14 }
        Text {
            Layout.fillWidth: true; wrapMode: Text.Wrap; color: app.theme.textMuted; font.pixelSize: app.theme.fontSizeSmall; lineHeight: 1.3
            text: "Fresh memory, built from the story record and the latest recap. The character, its threads and its obligations survive. Mid-turn, it applies when the turn ends."
        }
        RowLayout {
            spacing: 8
            Combo { id: roleBox; objectName: "recastRole"; model: app.roles.names(); Layout.preferredWidth: 150 }
            Field { id: modelField; objectName: "recastModel"; Layout.fillWidth: true; placeholderText: "model (role default)" }
        }
        RowLayout {
            Item { Layout.fillWidth: true }
            Btn { objectName: "recastCancel"; quiet: true; text: "Cancel"; onClicked: dlg.close() }
            Btn {
                objectName: "recastConfirm"; primary: true; text: "Recast"
                onClicked: {
                    var cid = app.stories.recast(dlg.storyKey, dlg.characterId, roleBox.currentText, modelField.text.trim())
                    dlg.close()
                    dlg.recasted(cid || "")
                }
            }
        }
    }
}
