import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../ui"

// The workspace page (Settings › Project, as an editor tab): name, key prefix, and the repos table —
// path, base, checks, setup; each repo's worktrees as story keys; Relocate for a missing repo,
// Unregister on hover, and a form to register one more (workspace spec §3, §7).
ContentBase {
    id: page
    property var repos: []
    property var stories: []
    property string relocating: ""          // the repo whose Relocate form is open
    function refresh() { repos = app.workspace.repos(); stories = app.stories.list() }
    function worktrees(name) {              // story keys with an environment in this repo, derived from the rows
        var out = []
        for (var i = 0; i < stories.length; i++) {
            var envs = stories[i].environments || []
            for (var j = 0; j < envs.length; j++) if (envs[j].repo === name) out.push(stories[i].key)
        }
        return out
    }
    function relative(path) {
        var d = app.workspace.dir
        return d && path.indexOf(d) === 0 ? (path.slice(d.length).replace(/^[\\/]/, "") || ".") : path
    }
    // Runs in the page's scope on purpose: the intent refreshes the repos, which rebuilds the delegates — the
    // clicked button is gone by the time the call returns, and its context can no longer resolve ids.
    function moveRepo(name, path) { if (app.workspace.relocate(name, path)) relocating = "" }
    Component.onCompleted: refresh()
    Connections { target: app.workspace; function onWorkspaceChanged() { page.refresh() } }
    Connections { target: app.stories; function onStoriesChanged() { page.refresh() } }   // a character registered a repo, or opened an environment

    // column widths, shared by the header row and every repo row
    readonly property int wName: 110
    readonly property int wBase: 72
    readonly property int wChecks: 120
    readonly property int wSetup: 96
    readonly property int wEnd: 96
    component Hd: Text { color: app.theme.textMuted; font.pixelSize: app.theme.fontSizeSmall }
    component Cell: Text { color: app.theme.textMuted; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize; elide: Text.ElideRight }

    Flickable {
        anchors.fill: parent; contentHeight: body.implicitHeight + 48; clip: true
        ScrollBar.vertical: ScrollBar {}
        ColumnLayout {
            id: body
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 20; leftMargin: 28; rightMargin: 28 }
            spacing: 0
            width: Math.min(parent.width - 56, 880)

            // ---- header: icon + name
            RowLayout {
                spacing: 12; Layout.fillWidth: true
                Rectangle { width: 28; height: 28; radius: 7
                            gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: "#7c5cff" } GradientStop { position: 1; color: app.theme.accent } }
                            Text { anchors.centerIn: parent; text: app.workspace.name.charAt(0).toUpperCase(); color: "white"; font.pixelSize: 14; font.weight: Font.DemiBold } }
                Text { objectName: "workspaceName"; text: app.workspace.name; color: app.theme.text; font.pixelSize: 20; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
            }
            // ---- state line
            RowLayout {
                spacing: 10; Layout.topMargin: 8
                Text { objectName: "workspaceDir"; text: app.workspace.dir; color: app.theme.textMuted; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize; elide: Text.ElideLeft; Layout.maximumWidth: 360 }
                Text { text: "·"; color: app.theme.textMuted }
                Row { spacing: 4
                      Text { text: "keys"; color: app.theme.textMuted }
                      Text { objectName: "workspacePrefix"; text: app.workspace.prefix + "-"; color: app.theme.text; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize; font.weight: Font.Medium } }
                Text { text: "·"; color: app.theme.textMuted }
                Text { text: page.stories.length + (page.stories.length === 1 ? " story" : " stories"); color: app.theme.textMuted }
                Text { text: "·"; color: app.theme.textMuted }
                Text { objectName: "workspaceRepoCount"; text: page.repos.length + (page.repos.length === 1 ? " repo" : " repos"); color: app.theme.textMuted }
            }

            // ---- repos
            Text { text: "Repos"; color: app.theme.text; font.pixelSize: 14; font.weight: Font.DemiBold; Layout.topMargin: 26 }
            Rectangle {
                Layout.fillWidth: true; Layout.topMargin: 10
                implicitHeight: table.implicitHeight + 2; radius: app.theme.radiusLarge; color: app.theme.bg; border.color: app.theme.border
                ColumnLayout {
                    id: table
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 1 }
                    spacing: 0
                    Rectangle {  // column headers
                        Layout.fillWidth: true; height: 26; color: app.theme.panel; radius: app.theme.radiusLarge
                        Rectangle { anchors { left: parent.left; right: parent.right; bottom: parent.bottom } height: parent.radius; color: parent.color }
                        RowLayout {
                            anchors { fill: parent; leftMargin: 12; rightMargin: 12 }
                            spacing: 10
                            Item { Layout.preferredWidth: 18 }
                            Hd { text: "Name"; Layout.preferredWidth: page.wName }
                            Hd { text: "Path"; Layout.fillWidth: true; Layout.minimumWidth: 90 }
                            Hd { text: "Base"; Layout.preferredWidth: page.wBase }
                            Hd { text: "Checks"; Layout.preferredWidth: page.wChecks }
                            Hd { text: "Setup"; Layout.preferredWidth: page.wSetup }
                            Item { Layout.preferredWidth: page.wEnd }
                        }
                    }
                    Repeater {
                        model: page.repos
                        delegate: ColumnLayout {
                            id: rp
                            required property var modelData
                            readonly property bool missing: modelData.status === "missing"
                            readonly property var keys: page.worktrees(modelData.name)
                            readonly property bool relocating: page.relocating === modelData.name
                            Layout.fillWidth: true; spacing: 0
                            Divider { Layout.fillWidth: true }
                            Rectangle {  // the record
                                objectName: "repoRow_" + rp.modelData.name
                                Layout.fillWidth: true; height: 34
                                color: rowHover.hovered ? app.theme.panel : "transparent"
                                RowLayout {
                                    anchors { fill: parent; leftMargin: 12; rightMargin: 12 }
                                    spacing: 10
                                    Icon { name: "git"; size: 14; color: app.theme.textDim; Layout.preferredWidth: 18 }
                                    Cell { text: rp.modelData.name; color: app.theme.text; font.weight: Font.Medium; Layout.preferredWidth: page.wName }
                                    Cell { objectName: "repoPath_" + rp.modelData.name; text: rp.modelData.path; Layout.fillWidth: true; Layout.minimumWidth: 90; elide: Text.ElideLeft
                                           HoverHandler { id: pathHover }
                                           ToolTip.visible: pathHover.hovered; ToolTip.text: rp.modelData.path; ToolTip.delay: 600 }
                                    Cell { text: rp.modelData.base; Layout.preferredWidth: page.wBase }
                                    Cell { text: rp.modelData.checks || "—"; color: rp.modelData.checks ? app.theme.textMuted : app.theme.textDim; Layout.preferredWidth: page.wChecks }
                                    Cell { text: rp.modelData.setup || "—"; color: rp.modelData.setup ? app.theme.textMuted : app.theme.textDim; Layout.preferredWidth: page.wSetup }
                                    Item {
                                        Layout.preferredWidth: page.wEnd; Layout.fillHeight: true
                                        Row {  // missing: say so, offer Relocate
                                            objectName: "repoStatus_" + rp.modelData.name
                                            visible: rp.missing; anchors { right: parent.right; verticalCenter: parent.verticalCenter } spacing: 6
                                            Rectangle { width: 7; height: 7; radius: 3.5; color: app.theme.danger; anchors.verticalCenter: parent.verticalCenter }
                                            Text { text: "missing"; color: app.theme.danger; font.pixelSize: app.theme.fontSizeSmall; anchors.verticalCenter: parent.verticalCenter }
                                            Btn { objectName: "relocateButton_" + rp.modelData.name; visible: !rp.relocating; small: true; text: "Relocate"; anchors.verticalCenter: parent.verticalCenter
                                                  onClicked: { page.relocating = rp.modelData.name } }
                                        }
                                        Btn {  // present: Unregister on hover
                                            objectName: "unregisterButton_" + rp.modelData.name
                                            visible: !rp.missing && rowHover.hovered; small: true; quiet: true; text: "Unregister"
                                            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                                            onClicked: app.workspace.unregister(rp.modelData.name)
                                        }
                                    }
                                }
                                HoverHandler { id: rowHover }
                            }
                            Rectangle {  // worktrees: the stories standing in this repo
                                objectName: "repoWorktrees_" + rp.modelData.name
                                visible: rp.keys.length > 0; Layout.fillWidth: true; height: 26; color: app.theme.bg
                                RowLayout {
                                    anchors { fill: parent; leftMargin: 40; rightMargin: 12 }
                                    spacing: 8
                                    Text { text: rp.keys.length + (rp.keys.length === 1 ? " worktree ·" : " worktrees ·"); color: app.theme.textDim; font.pixelSize: app.theme.fontSizeSmall }
                                    Repeater {
                                        model: rp.keys
                                        delegate: Text {
                                            required property var modelData
                                            objectName: "worktreeKey_" + rp.modelData.name + "_" + modelData
                                            text: modelData; color: kh.hovered ? app.theme.text : app.theme.textMuted
                                            font.family: app.theme.monoFamily; font.pixelSize: app.theme.fontSizeSmall
                                            HoverHandler { id: kh }
                                            TapHandler { onTapped: { var s = app.stories.get(modelData); app.layout.openContent("story", modelData, modelData + "  " + (s.title || "")) } }
                                        }
                                    }
                                    Item { Layout.fillWidth: true }
                                }
                            }
                            Rectangle {  // Relocate: a new path for a missing repo (spec §3.3)
                                visible: rp.relocating; Layout.fillWidth: true; height: 44; color: app.theme.bg
                                RowLayout {
                                    anchors { fill: parent; leftMargin: 40; rightMargin: 12 }
                                    spacing: 8
                                    Text { text: "Not found at that path."; color: app.theme.danger }
                                    Field { id: newPath; objectName: "relocatePath_" + rp.modelData.name; Layout.fillWidth: true; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize
                                            placeholderText: "Where it is now"; Component.onCompleted: forceActiveFocus()
                                            onAccepted: moveBtn.clicked() }
                                    Btn { id: moveBtn; objectName: "relocateConfirm_" + rp.modelData.name; small: true; primary: true; text: "Move here"; enabled: newPath.text.trim().length > 0
                                          onClicked: page.moveRepo(rp.modelData.name, newPath.text.trim()) }
                                    Btn { objectName: "relocateCancel_" + rp.modelData.name; small: true; quiet: true; text: "Cancel"; onClicked: page.relocating = "" }
                                    Btn { objectName: "unregisterMissing_" + rp.modelData.name; small: true; quiet: true; text: "Unregister"
                                          onClicked: { page.relocating = ""; app.workspace.unregister(rp.modelData.name) } }
                                }
                            }
                        }
                    }
                    Divider { Layout.fillWidth: true }
                    ColumnLayout {  // register one more (spec §3.2: the author registers from the workspace page)
                        Layout.fillWidth: true; Layout.margins: 10; spacing: 8
                        RowLayout {
                            Layout.fillWidth: true; spacing: 8
                            Field { id: addPath; objectName: "addRepoPath"; Layout.fillWidth: true; placeholderText: "Path to a git repository"; onAccepted: registerBtn.clicked() }
                            Btn { id: registerBtn; objectName: "addRepoButton"; text: "Register"; enabled: addPath.text.trim().length > 0
                                  onClicked: {
                                      var rec = app.workspace.register(addPath.text.trim(), addName.text.trim(), addChecks.text.trim(), addSetup.text.trim(), addBase.text.trim())
                                      if (rec && rec.name) { addPath.text = ""; addName.text = ""; addChecks.text = ""; addSetup.text = ""; addBase.text = "" }
                                  } }
                        }
                        RowLayout {
                            spacing: 8
                            Field { id: addName; objectName: "addRepoName"; Layout.preferredWidth: 160; placeholderText: "name" }
                            Field { id: addChecks; objectName: "addRepoChecks"; Layout.preferredWidth: 160; placeholderText: "checks"; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize }
                            Field { id: addSetup; objectName: "addRepoSetup"; Layout.preferredWidth: 160; placeholderText: "setup"; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize }
                            Field { id: addBase; objectName: "addRepoBase"; Layout.preferredWidth: 160; placeholderText: "base"; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize }
                        }
                    }
                }
            }
            Text {
                visible: page.repos.length === 0; Layout.topMargin: 14; Layout.fillWidth: true; wrapMode: Text.Wrap
                text: "No repos yet. Register one to give stories a place to work."; color: app.theme.textMuted
            }
        }
    }
}
