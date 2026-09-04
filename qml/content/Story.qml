import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../ui"
import "../ui/Theme.js" as T

// A story page (the pull-request view, typeset as a script). tabKey = story key.
// Unstarted: editable title/description, role picker, Start. Started: phase + whose turn,
// the actions you have right now, then the threads — speakers as small mono caps, system
// events as stage directions, yields as labeled rules, choices as buttons, checks as a console.
ContentBase {
    id: view
    property var story: app.stories.get(tabKey)
    property var comments: app.stories.comments(tabKey)
    property var cast: app.stories.cast(tabKey)
    readonly property bool found: !!(story && story.key)
    readonly property bool started: found && story.phase !== "backlog" && story.phase !== "todo"
    readonly property bool terminal: found && (story.phase === "done" || story.phase === "canceled")
    readonly property bool mine: found && story.ball === "author"
    readonly property var threads: found && story.threads ? story.threads : []
    readonly property var mainThread: threads.length ? threads[0] : null
    function refresh() { story = app.stories.get(tabKey); comments = app.stories.comments(tabKey); cast = app.stories.cast(tabKey) }
    Connections { target: app.stories; function onStoriesChanged() { view.refresh() } }
    Connections { target: app.contexts; function onContextsChanged() { view.refresh() } }   // asideEnabled follows source status

    // ---- lookups
    function character(id) { for (var i = 0; i < cast.length; i++) if (cast[i].id === id) return cast[i]; return null }
    function protagonistName() { var p = character(story.protagonist); return p ? p.name : "the protagonist" }
    function commentsIn(tid) { return comments.filter(function (c) { return c.thread_id === tid }) }
    function lastIn(tid) { var cs = commentsIn(tid); return cs.length ? cs[cs.length - 1] : null }
    function speaker(c) {
        if (c.author === "human") return "You"
        var ch = character(c.author)
        return ch ? ch.name : c.authorName
    }
    function speakerRole(c) {
        if (c.structured && c.structured.auto_for) {  // the harness yielded for a quiet character
            var q = character(c.structured.auto_for)
            return "for " + (q ? q.name : c.structured.auto_for)
        }
        var ch = character(c.author)
        return ch && ch.role !== ch.name ? ch.role : ""
    }
    function when(ts) {
        if (!ts) return ""
        var d = new Date(ts * 1000), now = new Date()
        var hm = Qt.formatTime(d, "HH:mm")
        if (d.toDateString() === now.toDateString()) return hm
        var y = new Date(now); y.setDate(now.getDate() - 1)
        if (d.toDateString() === y.toDateString()) return "yesterday " + hm
        return Qt.formatDate(d, "MMM d") + " " + hm
    }
    function yieldLabel(c) {
        if (c.kind === "question") return "Question"
        var to = c.structured && c.structured.transition ? c.structured.transition.to : null
        var phase = to ? to[0] : story.phase
        return phase === "planning" ? "Handoff · outline" : "Handoff · ready for review"
    }
    function isPending(c) { for (var i = 0; i < threads.length; i++) if (threads[i].pendingYield === c.id) return true; return false }
    function pickedOption(c) {  // the reply that answered this question, if any
        for (var i = 0; i < comments.length; i++) if (comments[i].reply_to === c.id) return comments[i].body
        return ""
    }
    function turnText(t) {
        if (!t) return ""
        if (t.turn === "resolved") return "resolved"
        if (t.turn === "author") return t.author === "human" ? "waits on you" : "waits on its author"
        var lead = character(t.lead); return (lead ? lead.name : "cast") + "'s turn"
    }
    // failing checks on the handoff that waits on you (workspace spec §4.6): the action bar says so in red
    readonly property int failingChecks: {
        if (!mine || !mainThread || !mainThread.pendingYield) return 0
        var n = 0
        for (var i = 0; i < comments.length; i++) {
            if (comments[i].id !== mainThread.pendingYield) continue
            var cs = comments[i].structured && comments[i].structured.checks ? comments[i].structured.checks : []
            for (var j = 0; j < cs.length; j++) if (cs[j].exit !== 0) n++
        }
        return n
    }
    function envPath(path) {  // inside the workspace dir → relative; the tooltip keeps the full path
        var d = app.workspaceDir
        return d && path.indexOf(d) === 0 ? path.slice(d.length).replace(/^[\\/]/, "") : path
    }
    readonly property string needsYouText: {
        if (!mine) return ""
        switch (story.flavor) {
        case "question": return protagonistName() + " asks a question — answer below, or pick an option."
        case "outline ready": return "The outline is ready — Proceed, or reply with changes."
        case "ready for review": return protagonistName() + " handed off — Approve, reply with changes, or send it back to planning."
        default: return "Waiting on you."
        }
    }

    // Reopen: resume by default; recast when chosen — or when resuming is impossible (spec §2.1:
    // "Reopen resumes; the UI may offer a recast instead").
    readonly property var protagonistCtx: {
        var p = character(story.protagonist)
        return p && p.live_context ? app.contexts.get(p.live_context) : null
    }
    readonly property bool canResume: !!protagonistCtx && protagonistCtx.sessionId !== ""
    RecastDialog { id: reopenRecast; storyKey: view.tabKey; viaReopen: true }
    function reopenViaRecast() {
        var p = character(story.protagonist)
        if (!p) return
        reopenRecast.characterId = p.id
        reopenRecast.characterName = p.name
        reopenRecast.currentRole = p.role
        reopenRecast.open()
    }

    function openAside(commentId) {
        var cid = app.stories.aside(tabKey, commentId)   // idempotent; rejections land in the status bar
        if (!cid) return
        app.layout.showPanel("contexts")
        app.contexts.reveal(cid)
    }

    Label {
        objectName: "storyMissing"; visible: !view.found
        anchors.centerIn: parent; width: parent.width - 40; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
        text: "Story " + tabKey + " not found — it may have been removed, or the tab is stale."; color: app.theme.textMuted
    }

    Flickable {
        visible: view.found
        anchors.fill: parent; contentHeight: page.implicitHeight + 48; clip: true
        ScrollBar.vertical: ScrollBar {}
        ColumnLayout {
            id: page
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 20; leftMargin: 28; rightMargin: 28 }
            spacing: 0
            width: Math.min(parent.width - 56, 820)

            // ---- header: key + title
            RowLayout {
                spacing: 12; Layout.fillWidth: true
                Text { text: tabKey; font.family: app.theme.monoFamily; font.pixelSize: 14; font.weight: Font.Medium; color: app.theme.textMuted; Layout.alignment: Qt.AlignBaseline }
                Text {
                    // Always present (a neutral click target that blurs an editor), blank until Start —
                    // storyTitleEdit is the title control until then.
                    objectName: "storyTitle"; text: view.started ? (view.story.title || "") : ""
                    color: app.theme.text; font.pixelSize: 20; font.weight: Font.DemiBold
                    Layout.fillWidth: true; Layout.preferredHeight: 28; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter
                    TapHandler { onTapped: view.forceActiveFocus() }
                }
                Field {
                    objectName: "storyTitleEdit"; visible: !view.started; Layout.fillWidth: true
                    text: view.story.title || ""; font.pixelSize: 20; font.weight: Font.DemiBold; implicitHeight: 34
                    placeholderText: "Title"
                    onEditingFinished: if (text !== view.story.title) app.stories.update(tabKey, text, descEdit.text)
                }
            }
            // ---- state line
            RowLayout {
                visible: view.started; spacing: 8; Layout.topMargin: 8
                Text { objectName: "storyPhase"; text: view.story.phase || ""; font.capitalization: Font.Capitalize; font.weight: Font.Medium
                       color: T.phaseColor(app.theme, view.story.phase) }
                Text { text: "·"; color: app.theme.textMuted; visible: !view.terminal }
                Ball { visible: !view.terminal; mine: view.mine }
                Text { objectName: "storyBall"; visible: !view.terminal
                       text: view.mine ? "your turn" + (view.story.flavor ? " — " + view.story.flavor : "") : (view.story.ball || "") + "'s turn"
                       color: view.mine ? app.theme.needsYou : app.theme.textMuted; font.weight: view.mine ? Font.Medium : Font.Normal }
                Text { text: "·"; color: app.theme.textMuted }
                Text { text: view.threads.length + (view.threads.length === 1 ? " thread" : " threads"); color: app.theme.textMuted }
                Text { text: "·"; color: app.theme.textMuted }
                Text { text: "cast of " + view.cast.length; color: app.theme.textMuted }
            }
            // ---- environments: where the work is — repo, this story's branch, the branch it merges into (spec §4)
            ColumnLayout {
                visible: view.started && view.story.environments && view.story.environments.length > 0
                Layout.fillWidth: true; Layout.topMargin: 10; spacing: 3
                Repeater {
                    model: view.found && view.story.environments ? view.story.environments : []
                    delegate: RowLayout {
                        id: env
                        required property var modelData
                        objectName: "storyEnv_" + modelData.repo
                        Layout.fillWidth: true; Layout.preferredHeight: 22; spacing: 8
                        Icon { name: "git"; size: 14; color: app.theme.textDim }
                        Text { text: env.modelData.repo; color: app.theme.text; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize; font.weight: Font.Medium }
                        Text { objectName: "storyEnvBranch_" + env.modelData.repo; text: env.modelData.branch; color: app.theme.text; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize }
                        Text { objectName: "storyEnvInto_" + env.modelData.repo; visible: !!env.modelData.into; text: "into " + env.modelData.into
                               color: app.theme.textMuted; font.pixelSize: app.theme.fontSizeSmall + 1 }
                        Item { Layout.fillWidth: true }
                        Text { text: view.envPath(env.modelData.path); color: app.theme.textDim; font.family: app.theme.monoFamily; font.pixelSize: app.theme.fontSizeSmall
                               elide: Text.ElideLeft; Layout.maximumWidth: 320
                               HoverHandler { id: envHover }
                               ToolTip.visible: envHover.hovered; ToolTip.text: env.modelData.path; ToolTip.delay: 600 }
                    }
                }
            }
            // ---- description
            Text { objectName: "storyDescription"; visible: view.started && !!view.story.description; Layout.topMargin: 10; Layout.fillWidth: true
                   text: view.story.description || ""; color: app.theme.textMuted; wrapMode: Text.Wrap; textFormat: Text.MarkdownText; lineHeight: 1.3 }
            TextBox {
                id: descEdit; objectName: "storyDescriptionEdit"; visible: !view.started
                Layout.fillWidth: true; Layout.preferredHeight: 96; Layout.topMargin: 12
                placeholderText: "Describe the work: what, why, how you will validate it."
                text: view.story.description || ""
                onActiveFocusChanged: if (!activeFocus && text !== view.story.description) app.stories.update(tabKey, view.story.title, text)
            }
            // ---- Start (unstarted only)
            RowLayout {
                visible: !view.started && view.story.phase !== "canceled"; spacing: 8; Layout.topMargin: 12
                Combo { id: roleBox; objectName: "roleBox"; model: app.roles.names(); Layout.preferredWidth: 180
                        Component.onCompleted: currentIndex = Math.max(0, app.roles.names().indexOf("protagonist")) }
                Field { id: startNote; objectName: "startNote"; Layout.fillWidth: true; placeholderText: "Opening note for the protagonist (optional)" }
                Btn { objectName: "startButton"; text: "Start"; primary: true; icon_: "play"
                      onClicked: { if (app.stories.start(tabKey, startNote.text, roleBox.currentText)) startNote.text = "" } }
            }

            // ---- action bar (started): what you can do right now
            Loader {  // only instantiated once started: no action controls exist on an unstarted story
                active: view.started; Layout.fillWidth: true; Layout.topMargin: 12
                sourceComponent: Rectangle {
                implicitHeight: Math.max(actions.implicitHeight, why.implicitHeight) + 20
                radius: app.theme.radiusLarge; color: app.theme.panel; border.color: app.theme.border
                Rectangle { visible: view.mine; width: 3; height: parent.height; color: app.theme.needsYou; radius: 2 }
                RowLayout {
                    anchors { fill: parent; leftMargin: 14; rightMargin: 10 }
                    spacing: 8
                    Text { objectName: "needsYouBanner"; visible: view.mine; text: view.needsYouText; color: app.theme.textMuted; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Text { id: why; objectName: "castTurnText"; visible: !view.mine
                           text: view.terminal ? "This story is " + view.story.phase + "." : "The cast has the ball — your comments arrive between turns."
                           color: app.theme.textDim; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Chip { objectName: "checksFailingChip"; visible: view.failingChecks > 0; fg: app.theme.danger
                           text: view.failingChecks + (view.failingChecks === 1 ? " check failing" : " checks failing") }
                    Row {
                        id: actions; spacing: 8
                        Btn { objectName: "proceedButton"; visible: view.story.phase === "planning" && view.mine; primary: true; text: "Proceed"; onClicked: app.stories.proceed(tabKey, "") }
                        Btn { objectName: "approveButton"; visible: view.story.phase === "implementing" && view.mine; primary: true; text: "Approve"; onClicked: app.stories.approve(tabKey, "") }
                        Btn { objectName: "backButton"; visible: view.story.phase === "implementing" && view.mine; text: "Back to planning"; onClicked: app.stories.backToPlanning(tabKey, "") }
                        SplitBtn {
                            visible: view.terminal
                            mainName: "reopenButton"; menuName: "reopenMenu"
                            text: view.canResume ? "Reopen" : "Reopen (recast)"
                            primary: false
                            items: [
                                { label: "Resume " + view.protagonistName(), hint: "continues with its memory", enabled: view.canResume },
                                { label: "Recast and reopen…", hint: "fresh memory from the story record" }
                            ]
                            onTriggered: view.canResume ? app.stories.reopen(tabKey, "reopened from the story page") : view.reopenViaRecast()
                            onItemTriggered: (i) => i === 0 ? app.stories.reopen(tabKey, "reopened from the story page") : view.reopenViaRecast()
                        }
                        Btn { objectName: "cancelButton"; visible: !view.terminal; quiet: true; text: "Cancel"; onClicked: app.stories.cancel(tabKey, "") }
                    }
                }
            }
            }

            // ---- new thread (after the threads; see the Repeater below)
            // ---- threads
            Repeater {
                model: view.threads
                delegate: ColumnLayout {
                    id: th
                    required property var modelData
                    required property int index
                    readonly property var rows: view.commentsIn(modelData.id)
                    readonly property string turn: view.turnText(modelData)
                    readonly property bool waitsOnYou: modelData.turn === "author" && modelData.author === "human"
                    property bool open: modelData.isMain
                    Layout.fillWidth: true; Layout.topMargin: modelData.isMain ? 22 : 6; spacing: 0
                    objectName: "thread_" + modelData.id

                    Divider { visible: th.modelData.isMain; Layout.fillWidth: true }
                    // thread header (folded rows for side threads)
                    Rectangle {
                        Layout.fillWidth: true; Layout.topMargin: th.modelData.isMain ? 10 : 0; height: 28; radius: app.theme.radius
                        color: !th.modelData.isMain && thHover.hovered ? app.theme.panel : "transparent"
                        RowLayout {
                            anchors { fill: parent; leftMargin: 4; rightMargin: 4 }
                            spacing: 8
                            Icon { name: th.open ? "down" : "right"; size: 14; color: app.theme.textDim }
                            Text { text: "#" + th.modelData.n; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize; color: app.theme.textMuted }
                            Text { text: th.modelData.isMain ? "Main thread" : (th.rows.length ? th.rows[0].body.split("\n")[0] : ""); color: app.theme.text; font.weight: Font.Medium; elide: Text.ElideRight; Layout.maximumWidth: 320 }
                            Text { text: (th.modelData.author === "human" ? "You" : view.speaker({ author: th.modelData.author })) + " → " + view.speaker({ author: th.modelData.lead })
                                         + (th.modelData.isMain ? "" : " · " + th.rows.length + (th.rows.length === 1 ? " comment" : " comments"))
                                   color: app.theme.textMuted; font.pixelSize: app.theme.fontSizeSmall + 1; elide: Text.ElideRight; Layout.fillWidth: true }
                            Text { text: th.turn; font.pixelSize: app.theme.fontSizeSmall
                                   color: th.waitsOnYou ? app.theme.needsYou : app.theme.textDim }
                            Btn { objectName: "resolveButton_" + th.modelData.id; visible: !th.modelData.isMain && th.waitsOnYou && !view.terminal; small: true; quiet: true; text: "Resolve"
                                  onClicked: app.stories.resolve(tabKey, th.modelData.id, "") }
                        }
                        HoverHandler { id: thHover }
                        TapHandler { enabled: !th.modelData.isMain; onTapped: th.open = !th.open }
                    }

                    // the script
                    ColumnLayout {
                        visible: th.open; Layout.fillWidth: true; Layout.leftMargin: 26; Layout.rightMargin: 40; spacing: 0
                        Repeater {
                            model: th.rows
                            delegate: ColumnLayout {
                                id: line
                                required property var modelData
                                required property int index
                                readonly property bool isSystem: modelData.kind === "system"
                                readonly property bool isYield: modelData.kind === "question" || modelData.kind === "handoff"
                                readonly property bool isReply: !!modelData.reply_to
                                readonly property bool pending: line.isYield && view.isPending(modelData)
                                readonly property var options: (modelData.structured && modelData.structured.options) ? modelData.structured.options : []
                                readonly property var checks: (modelData.structured && modelData.structured.checks) ? modelData.structured.checks : []
                                readonly property string picked: options.length ? view.pickedOption(modelData) : ""
                                readonly property bool answerable: options.length > 0 && pending && th.waitsOnYou
                                readonly property bool isCharacter: !!view.character(modelData.author)
                                objectName: "comment_" + modelData.id
                                HoverHandler { id: lineHover }
                                Layout.fillWidth: true; Layout.topMargin: isSystem ? 12 : 14; Layout.leftMargin: isReply ? 14 : 0
                                spacing: 0

                                // (stage direction)
                                Text { visible: line.isSystem; Layout.fillWidth: true; wrapMode: Text.Wrap
                                       text: "(" + line.modelData.body + (line.modelData.author === "human" ? " — you" : "") + (line.modelData.created_at ? ", " + view.when(line.modelData.created_at) : "") + ")"
                                       color: app.theme.textMuted; font.italic: true; font.pixelSize: app.theme.fontSize - 0.5 }

                                // SPEAKER · ROLE                                   time
                                RowLayout {
                                    visible: !line.isSystem; Layout.fillWidth: true; spacing: 10
                                    Text { text: view.speaker(line.modelData); color: line.modelData.author === "human" ? app.theme.text : "#b4b8c0"
                                           font.family: app.theme.monoFamily; font.pixelSize: app.theme.fontSizeSmall; font.weight: Font.Medium
                                           font.letterSpacing: 1; font.capitalization: Font.AllUppercase }
                                    Text { visible: !!view.speakerRole(line.modelData); text: "· " + view.speakerRole(line.modelData); color: app.theme.textMuted
                                           font.family: app.theme.monoFamily; font.pixelSize: app.theme.fontSizeSmall; font.letterSpacing: 1; font.capitalization: Font.AllUppercase }
                                    Item { Layout.fillWidth: true }
                                    Text { text: view.when(line.modelData.created_at); color: app.theme.textDim; font.pixelSize: app.theme.fontSizeSmall }
                                    Rectangle {
                                        // Aside: a private chat with a copy of whoever wrote this comment (spec §3.5).
                                        // Ghost (icon only) while hovering the comment; a labeled pill once one exists.
                                        id: asideBtn
                                        objectName: "asideButton_" + line.modelData.id
                                        readonly property bool hasAside: line.modelData.asideId !== ""
                                        readonly property bool canUse: line.modelData.asideEnabled
                                        visible: line.isCharacter && (hasAside || lineHover.hovered)
                                        width: asideRow.implicitWidth + 16; height: 22; radius: 11
                                        color: hasAside ? app.theme.panel : app.theme.bg
                                        border.color: abHover.hovered && canUse ? app.theme.buttonBorder : app.theme.border
                                        opacity: canUse ? 1 : 0.4
                                        Row {
                                            id: asideRow; anchors.centerIn: parent; spacing: 5
                                            Icon { name: "aside"; size: 13; anchors.verticalCenter: parent.verticalCenter
                                                   color: abHover.hovered && asideBtn.canUse ? app.theme.text : app.theme.textMuted }
                                            Text { visible: asideBtn.hasAside; text: "aside"; font.pixelSize: app.theme.fontSizeSmall
                                                   color: abHover.hovered ? app.theme.text : app.theme.textMuted; anchors.verticalCenter: parent.verticalCenter }
                                        }
                                        HoverHandler { id: abHover }
                                        TapHandler { enabled: asideBtn.canUse; onTapped: view.openAside(line.modelData.id) }
                                        ToolTip.visible: abHover.hovered; ToolTip.delay: 600
                                        ToolTip.text: !asideBtn.canUse ? view.speaker(line.modelData) + " is working or its memory is gone — try when it stops"
                                                    : asideBtn.hasAside ? "Reopen the aside on this comment"
                                                    : "Aside: ask a private copy of " + view.speaker(line.modelData) + " about this comment"
                                    }
                                }
                                // —— Question / Handoff ——
                                RowLayout {
                                    visible: line.isYield; Layout.fillWidth: true; Layout.topMargin: 8; spacing: 10
                                    readonly property color c: line.pending ? app.theme.needsYou : (line.modelData.kind === "handoff" ? app.theme.settled : app.theme.textMuted)
                                    Rectangle { Layout.preferredWidth: 60; height: 1; color: parent.c; opacity: 0.45 }
                                    Text { text: view.yieldLabel(line.modelData); color: parent.c; font.pixelSize: 12; font.weight: Font.Medium }
                                    Rectangle { Layout.fillWidth: true; height: 1; color: parent.c; opacity: 0.45 }
                                }
                                // the line itself
                                Text { visible: !line.isSystem && !!line.modelData.body; Layout.fillWidth: true; Layout.topMargin: 4
                                       text: line.modelData.body; textFormat: Text.MarkdownText; wrapMode: Text.Wrap; lineHeight: 1.35
                                       color: app.theme.text; font.pixelSize: app.theme.fontSize
                                       onLinkActivated: (link) => Qt.openUrlExternally(link) }
                                // choices
                                Flow {
                                    visible: line.options.length > 0; Layout.fillWidth: true; Layout.topMargin: 8; spacing: 6
                                    Repeater {
                                        model: line.options
                                        delegate: Btn {
                                            required property int index
                                            required property var modelData
                                            objectName: "optionButton_" + line.modelData.id + "_" + index
                                            small: true; text: modelData; enabled: line.answerable
                                            icon_: line.picked === modelData ? "check" : ""
                                            onClicked: app.stories.comment(tabKey, modelData)
                                        }
                                    }
                                }
                                // checks (implementing handoffs)
                                Rectangle {
                                    visible: line.checks.length > 0; Layout.fillWidth: true; Layout.topMargin: 10
                                    implicitHeight: checksCol.implicitHeight + 2; radius: app.theme.radiusLarge; color: app.theme.panel; border.color: app.theme.border
                                    ColumnLayout {
                                        id: checksCol; anchors { left: parent.left; right: parent.right; top: parent.top; margins: 1 }
                                        spacing: 0
                                        Repeater {
                                            model: line.checks
                                            delegate: ColumnLayout {
                                                id: chk
                                                required property var modelData
                                                required property int index
                                                readonly property bool ok: modelData.exit === 0
                                                property bool open: !ok   // failing output shows; a passing run folds until asked
                                                Layout.fillWidth: true; spacing: 0
                                                Divider { visible: chk.index > 0; Layout.fillWidth: true }
                                                RowLayout {
                                                    objectName: "checkRow_" + line.modelData.id + "_" + chk.index
                                                    Layout.fillWidth: true; Layout.preferredHeight: 26; Layout.leftMargin: 10; Layout.rightMargin: 10; spacing: 8
                                                    Icon { name: chk.open ? "down" : "right"; size: 14; color: app.theme.textDim; opacity: chk.modelData.output ? 1 : 0.35 }
                                                    Icon { name: chk.ok ? "check" : "x"; size: 14; color: chk.ok ? app.theme.settled : app.theme.danger }
                                                    Text { text: chk.modelData.repo; color: app.theme.text; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize }
                                                    Text { text: chk.modelData.cmd; color: app.theme.textMuted; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize; elide: Text.ElideRight; Layout.fillWidth: true }
                                                    Text { text: chk.ok ? "passed" : "exit " + chk.modelData.exit; color: chk.ok ? app.theme.textMuted : app.theme.danger; font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize }
                                                    TapHandler { onTapped: chk.open = !chk.open }
                                                }
                                                Rectangle {  // the output, open by default only when it failed
                                                    objectName: "checkOutput_" + line.modelData.id + "_" + chk.index
                                                    visible: chk.open && !!chk.modelData.output; Layout.fillWidth: true; color: app.theme.bg
                                                    implicitHeight: out.implicitHeight + 16
                                                    Divider { width: parent.width }
                                                    Text { id: out; anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8; leftMargin: 12 }
                                                           text: chk.modelData.output; color: app.theme.textMuted; wrapMode: Text.Wrap
                                                           font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize - 0.5; lineHeight: 1.4 }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // composer for this thread
                        RowLayout {
                            visible: !view.terminal && th.modelData.turn !== "resolved"; Layout.fillWidth: true; Layout.topMargin: 16; spacing: 8
                            TextBox {
                                id: reply; objectName: th.modelData.isMain ? "replyInput" : "replyInput_" + th.modelData.id
                                Layout.fillWidth: true; Layout.preferredHeight: 64
                                label: th.waitsOnYou ? "Reply to " + view.speaker({ author: th.modelData.lead }) : "Comment for " + view.speaker({ author: th.modelData.lead })
                                placeholderText: th.waitsOnYou ? "Your reply answers the pending yield  (Ctrl+Enter)" : "Arrives between turns  (Ctrl+Enter)"
                                onSubmitted: post()
                                function post() { if (text.trim().length) { app.stories.comment(tabKey, text, th.modelData.isMain ? "" : th.modelData.id); text = "" } }
                            }
                            Btn { objectName: th.modelData.isMain ? "replyButton" : "replyButton_" + th.modelData.id; Layout.alignment: Qt.AlignBottom
                                  primary: th.waitsOnYou; text: th.waitsOnYou ? "Reply" : "Comment"; enabled: reply.text.trim().length > 0; onClicked: reply.post() }
                        }
                    }
                }
            }

            // ---- a composer for opening threads: plain → protagonist; @Name; /call <role>; /fork @Name
            RowLayout {
                visible: view.started && !view.terminal; Layout.fillWidth: true; Layout.topMargin: 26; spacing: 8
                TextBox {
                    id: newThread; objectName: "newThreadInput"
                    Layout.fillWidth: true; Layout.preferredHeight: 64
                    label: "New thread"
                    placeholderText: "Write to " + view.protagonistName() + ", @Name, /call <role>, or /fork @Name for a copy of their memory  (Ctrl+Enter)"
                    onSubmitted: post()
                    function post() {
                        if (!text.trim().length) return
                        if (app.stories.openThread(tabKey, text)) text = ""
                    }
                }
                Btn { objectName: "newThreadButton"; Layout.alignment: Qt.AlignBottom; text: "Open"
                      enabled: newThread.text.trim().length > 0; onClicked: newThread.post() }
            }
        }
    }
}
