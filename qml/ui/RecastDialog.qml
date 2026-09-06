import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Recast: same character, fresh memory (spec §3.4). The three picks are seeded from the character
// being recast, so a recast that changes nothing keeps the model, effort and preset it had. Its
// position is not offered — a recast never moves a character to a different seat. Applies now, or at
// the turn boundary when the character is mid-turn (the store decides; either way a system comment
// records it).
Popup {
    id: dlg
    property string storyKey
    property string characterId
    property string characterName
    property string currentModel
    property string currentEffort
    property string currentPreset
    property bool viaReopen: false       // terminal story: reopen + recast + deliver in one intent
    signal recasted(string contextId)    // the new context id, or "" when deferred to the boundary
    modal: true
    anchors.centerIn: Overlay.overlay
    width: 440; padding: 16
    background: Rectangle { color: app.theme.panel; radius: app.theme.radiusLarge; border.color: app.theme.border }
    onOpened: picks.seed(dlg.currentModel, dlg.currentEffort, dlg.currentPreset)
    contentItem: ColumnLayout {
        spacing: 10
        Text { text: "Recast " + dlg.characterName; color: app.theme.text; font.weight: Font.DemiBold; font.pixelSize: 14 }
        Text {
            Layout.fillWidth: true; wrapMode: Text.Wrap; color: app.theme.textMuted; font.pixelSize: app.theme.fontSizeSmall; lineHeight: 1.3
            text: "Fresh memory, built from the story record and the latest recap. The character, its threads and its obligations survive. Mid-turn, it applies when the turn ends."
        }
        CastPicks { id: picks; prefix: "recast"; Layout.fillWidth: true }
        RowLayout {
            Item { Layout.fillWidth: true }
            Btn { objectName: "recastCancel"; quiet: true; text: "Cancel"; onClicked: dlg.close() }
            Btn {
                objectName: "recastConfirm"; primary: true; text: "Recast"
                onClicked: {
                    var cid = dlg.viaReopen
                        ? (app.stories.reopen(dlg.storyKey, "reopened with a fresh memory", picks.modelId, picks.effort, picks.preset), "")
                        : app.stories.recast(dlg.storyKey, dlg.characterId, picks.modelId, picks.effort, picks.preset)
                    dlg.close()
                    dlg.recasted(cid || "")
                }
            }
        }
    }
}
