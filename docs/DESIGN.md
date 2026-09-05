# zharn — design notes (2026-08-27)

A native, self-modifying coding-agent harness. Keeps bb's model, drops the web stack,
and treats *your fork as your config* (suckless/st style). Hot reload is a hard requirement
because the thing that edits the harness is the agent running inside it.

## 0. Compatibility policy (2026-08-31)

**This is an experimental project. Historical compatibility does not matter until the author says
so.** No migrations of on-disk data (`.harness/`, `tasks.json`, thread transcripts, sessions), no
deprecation shims, no aliases for renamed modules, env vars, or CLI verbs. When a model changes,
delete the old code and the old data; rewrite tests against the new shape.

## 1. The stack decision

**PySide6 6.11 + Qt Quick/QML, no C++ in the loop.**

| Option | Hot reload reality | Verdict |
|---|---|---|
| C++ + QML | QML reloads (lossy, free via `clearComponentCache`/`qmlpreview`); C++ never does — Qt sets `QLibrary::PreventUnloadHint` on plugins since 5.7, maintainers closed the "let plugins unload" ticket as "too dangerous" (QTBUG-141188, Dec 2025), and every function-body patcher (Live++, VS Hot Reload) is Windows-only and can't touch moc'd metaobjects. | Rebuild+restart for anything non-QML. Fine for a normal app, wrong for a self-modifying one. |
| C++ + QPluginLoader reload | Second reload is a coin flip (QMetaType, `staticMetaObject`, `QStringLiteral` dangling). Qt Creator, 3D Slicer, ParaView all refused to support it. | No. |
| Qt Widgets (any language) | No reload story from Qt at all; `QUiLoader` for `.ui` only. | No. |
| **PySide6 + QML** | **Measured in `poc/`: Python logic swap 1–16 ms, QML re-render 9–40 ms, app state preserved, on WSL and Windows, zero third-party tools.** No compiler anywhere: agent edits `.py`/`.qml`, sees result next frame. | **Yes.** |

The only thing C++ buys here (binary distribution, ~200 ms faster cold start) is irrelevant
for a tool whose users are expected to have the source checked out. Qt's own state-preserving
hot reload (QTBUG-146122, targeting 6.12) and Felgo's (proprietary, free <€50k turnover) are
QML-only anyway; our QML story is the same as theirs, and Python covers the rest.

Known limits, and the rule that neutralizes each:

| Limit | Rule |
|---|---|
| `importlib.reload` gives existing instances the *old* class; adding a `Signal`/`Property`/`@Slot` doesn't reach them | Shape changes → fast restart (<1 s, session persisted). Body changes → in-place. The reloader detects which by diffing the class's `__dict__` keys. |
| `@QmlElement` registration is permanent; re-import double-registers and leaks | Never use `@QmlElement` in reloadable code. Expose backend objects as context properties / singleton *instances* that outlive every reload. |
| `clearComponentCache()` leaves old QML objects with old types | Generation model (below): new engine per reload, old one torn down after success. |
| UI state (scroll, focus, text in fields) dies with the QML tree | All state that matters lives in Python `Store` objects. QML is a projection. If a view needs to survive, give it a `reloadableId` and hand it its predecessor (Quickshell pattern). |
| `QtAsyncio` can't spawn subprocesses | Drive agent CLIs with `QProcess` (or `qasync` if we want asyncio). |
| `.py` edits with syntax errors | Reload is transactional: compile first, keep the running generation on failure, surface the traceback in the UI. |

## 2. Architecture

```
┌─ shell (never reloaded) ──────────────────────────────────────────────┐
│ QGuiApplication · watcher (poll or inotify) · Reloader · Session      │
│                                                                       │
│ ┌─ Store layer (reload-tolerant) ─────────────────────────────────┐   │
│ │ Workspace · Repos · Environments · Stories · Contexts · Roles   │   │
│ │ QObject singletons, long-lived, exposed to QML by *instance*    │   │
│ └─────────────────────────────────────────────────────────────────┘   │
│ ┌─ Logic layer (hot-swapped by importlib.reload) ─────────────────┐   │
│ │ harness/*.py: agent drivers (QProcess→claude-code/codex CLIs),  │   │
│ │ git/worktree ops, prompt templates, keymaps, commands           │   │
│ └─────────────────────────────────────────────────────────────────┘   │
│ ┌─ View layer (generation N: fresh QQmlEngine per reload) ────────┐   │
│ │ qml/**/*.qml — panels, thread view, diff view, terminal view    │   │
│ └─────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────┘
```

* **Generation model** (stolen from Quickshell v0.3): on change, scan the QML import graph,
  build a *new* engine, load `Main.qml`; on success swap windows and `deleteLater()` the old
  engine; on failure keep the old generation and show the error. Never partially-applied.
* **Watcher**: inotify where it works, mtime poll (250 ms) where it doesn't. On this machine it
  doesn't — see `poc/README.md`. Re-add watches after every reload (editors save via rename).
* **Shell is tiny** (~200 lines) and is the only thing that requires a restart to change.
  Restart = `QProcess.startDetached(sys.executable, sys.argv)` after persisting `Session`.
* **Agents are child processes** (`claude -p --output-format stream-json`, `codex exec --json`),
  exactly as bb does it. Streaming JSON → Store → QML list models.

## 3. What we keep from bb

Verbatim conceptual model (`bb guide`): **Project** ↔ repo (zharn: **repo**, inside a **workspace**, §3c) · **Thread** = one agent conversation,
optional parent (parent gets child lifecycle events) · **Environment** = checkout or managed
worktree, shareable across threads, `.bb-env-setup.sh` hook · **Provider** = agent backend +
model · **Terminal** = persistent PTY scoped to thread/env · forks (clone session at a turn) ·
sections · hidden threads for background workers · permission modes as a ceiling from parent to child.
(Naming: bb's *thread* is zharn's **context** — in zharn a "thread" is a chain of comments, §3b.)

Also keep: context env vars (`BB_THREAD_ID`-style) injected into agent processes, a CLI the
agent can call to spawn/message/wait on sibling threads, `--json` on everything.

Deliberately drop: the sidebar (it becomes a dockable "task details" panel, §3a), daemon/client
split (start single-process; split later only if remote machines matter), plugin marketplace
(plugins are just modules in your fork), web renderer.

## 3a. Window model: JetBrains-style docks + splittable content containers

No sidebar. The window is:

```
┌──┬────────────────────────────────────────────────┬──┐
│L │  Main Content Area                              │R │  L/R/B = tool-window strips
│  │  ┌─ MCC ─────────────┬─ MCC ─────────────────┐  │  │  (JetBrains style: click = open panel
│s │  │ [Task ABC-12][Thr]│ [diff.py][terminal]   │  │s │   docked, drag = reorder, pin/unpin,
│t │  │                   │                       │  │t │   collapse to icon strip)
│r │  ├───────────────────┴───────────────────────┤  │r │
│i │  │ MCC  [claude: fix tests]                  │  │i │  MCC = Main Content Container:
│p │  │                                           │  │p │   a tab group; split H/V any depth;
│  │  └───────────────────────────────────────────┘  │  │   drag tabs between MCCs / to edges
├──┴────────────────────────────────────────────────┴──┤
│ B strip: [Terminal] [Problems] [Git] [Agent log]     │
└──────────────────────────────────────────────────────┘
```

* **Dock (left/right/bottom)** hosts only **dockable panels**: board, contexts (the old
  bb sidebar becomes just another panel), git status, filesystem, terminal, agent log, roles.
  States: docked-visible, collapsed-to-strip, slide-over (overlay `Item`, not a window), floating
  (`Window`).
* **MCC** is a tab group that can show *any* content: a panel, a document, a thread, a task, a
  diff. Split any MCC horizontally/vertically; drag tabs between MCCs, to an edge for a new split,
  or out to float. Empty MCCs collapse.
* Content types register in `harness/content.py` (`kind` → QML component + Python controller),
  so adding a new panel/document type is one Python dict entry + one QML file — fork-as-config.
* **Look: JetBrains New UI (dark), by convention.** Main toolbar (workspace widget, New story);
  40px icon strips — the left strip carries the left dock's panels at the top and the bottom
  dock's at the bottom, the right strip the right dock's; 36px tool-window headers and editor
  tabs; a 26px status bar. Default layout: left Stories · Files · Git, right Cast (follows the
  active story tab), bottom Contexts · Terminal; the workspace page (repos, Relocate/Unregister) is an
  editor tab opened from the toolbar's workspace widget. Tokens live in `config_def.THEME` (chrome,
  semantic: needsYou/live/settled/danger, one soft color per phase, type, metrics); components in
  `qml/ui/` (Icon, IconButton, Btn, Chip, StatusDot, Ball, Meter, ToolWindowHeader, TextBox,
  Field, Combo, ContextView); icons are monochrome SVGs in `qml/icons/` recolored on request by
  `harness/icons.py` (`image://icon/<name>/<rrggbb>`); Inter + JetBrains Mono ship in `qml/fonts/`.
  The story page is typeset as a script (speakers in small mono caps, system comments as stage
  directions, yields as labeled rules). Design mockups: `docs/design/mockups/` (run `build.py`).
  Rule of thumb for color: phases get a soft key each; only *turns* (amber = needs you) and
  *liveness* (blue = a character mid-turn) get saturated color.

**Implementation decision: homegrown, over a Python-owned layout tree.** Research result:
KDDockWidgets 2.4 has a QtQuick frontend but *no auto-hide/strip support* (#634: "not supported for
QtQuick"), a process-global `DockRegistry` that breaks when the QML engine is recreated (#210, #685),
and Python bindings for Widgets only. Qt ADS 5.1 (+ `PySide6-QtAds`) has everything but is
Widgets-only. Nothing pure-QML is maintained (last one died in 2016).

So the layout is data:

```python
Layout = Split(orientation, ratios, children=[Split|Group|Dock…])
Group  = Tabs(id, tabs=[ContentRef(kind, key)], active)
Dock   = Edge(side, panels=[PanelRef], mode: docked|strip|overlay, size)
Float  = Window(geometry, root=Split|Group)
```

Lives in `Store.layout` (Python), persisted in the session, exposed to QML as a JSON tree.
QML renders it recursively (`Loader` → `SplitView` / `TabBar`+`StackLayout` / strip `Column`s) and
sends **intents** back (`moveTab`, `split`, `setRatios`, `togglePanel`, `float`). The QML tree
never owns layout state, so a hot reload of any dock/tab/strip component is free by construction
— the property the docking libraries can't give us. Primitives are all stock Qt Quick 6.11:
`SplitView` (nested), `DragHandler` + `DropArea` for tab drag and edge drop-zones, `Window` for
floats, `Popup.popupType: Popup.Window` so menus escape panes.

Effort estimate from research: 3–5 weeks for a solid v1 (drop-zone hit-testing and cross-window
drags are the expensive bits). **Fallback** if that stalls: `QMainWindow` + `PySide6-QtAds` 5.0
(auto-hide, perspectives, pip-installable, LGPL) hosting `QQuickWidget` panes — 1–2 weeks, but
Widgets chrome around QML content and no threaded render loop. Prior art for the strip model:
Kate's `KateMDI::Sidebar`, KDevelop's `Sublime::IdealController`.

## 3b. The Story model (agent-interaction model)

Defined in **[`docs/AGENT-MODEL.md`](AGENT-MODEL.md)** (design) and
**[`docs/specs/story-lifecycle.md`](specs/story-lifecycle.md)**
(implementation). Both win over this section and over the code. In brief:

* Work is a **Story** (the smallest unit its **author** describes and validates); agents are its
  **cast**. Three load-bearing concepts, one job each: a **thread** (a root comment + replies:
  one topic, with an author, a lead character, and a *turn*), a **character** (named participant
  with an inbox, an attention, and one live context at a time), and a **context** (one agent
  conversation — what bb calls a thread — owned by a character, a minion, or the human as a
  story-less *bare context*).
* The **protagonist** is cast at Start onto the story's **main thread** and is the only character
  that can yield there — the ball *is* the main thread's turn. It calls in **friends** (peers on
  their own threads), sends out **minions** (invisible helpers; forkable contexts), or creates
  **sub-stories** (which it then authors). Characters are cast from **roles**.
* State is `(phase ∈ backlog|todo|planning|implementing|done|canceled, ball = main thread's turn)`.
  **Nobody sets status** — Start/Reply/Proceed/Approve (author) and `yield`/`proceed` (cast) are
  the only actions; each writes a comment, and the threads are the audit log.
* **Comments are the only channel** — even typing in a character's context view posts a comment.
  Delivery is attention-based: replies in a character's attended thread arrive now (steering);
  new threads and `@Name` pings queue in its inbox until it comes up for air (a "btw").
* Context lifecycle: when a context runs low the harness demands a **recap** comment; **recast**
  (manual or automatic) rebuilds the character on a fresh context from the story record + recap —
  the story record *is* the compaction. Recast also swaps role/model mid-story.
* The harness enforces mechanically what it can (no status verb, main handoff blocked while
  sub-stories are open, checks attached to handoffs, per-thread auto-yield on silence, inbox
  bookkeeping, the recap/recast ladder) and injects phase skills (vendored from superpowers into
  `harness/skills/`) for the rest.

Kept from bb: roles, attachments, mentions (`@ABC-12`), a **New Context** button (bb's
"new thread": a bare chat for questions, promotable into a story). Not kept: per-project prefixes
and the auto-created "Inbox" project — stories are rooted at a workspace (§3c).

## 3c. Workspaces, repos, environments

Defined in **[`docs/specs/workspace-model.md`](specs/workspace-model.md)**,
which wins over this section and over the code. In brief:

* A **workspace** is a directory with a `.zharn/`: one board, one story-key prefix, a set of
  repos. It is what you open on the start screen. Identity is a UUID in `workspace.toml`, never a
  path (the same dir has three spellings on a Windows-GUI/WSL-agents machine).
* A **repo** is a registered git repository (path, name, `checks`, `setup`, `base`) — bb's
  "project", renamed because it is 1:1 with a repository and "project" is the word a board will
  want for a group of stories. Repos may live anywhere; inside the workspace dir they are stored
  relative. The author registers repos; **so may any character**, by path or by URL (cloned into
  `<workspace>/repos/`), recorded as a system comment in its thread. Unregistering is author-only.
* An **environment** is a checkout of one repo where a context stands: the main checkout, or a
  managed worktree zharn creates on branch `zharn/<key>`. A story acquires environments lazily —
  the first `zharn env open <repo>` makes the worktree for `(story, repo)`, shared by the cast —
  so a story's repos are *derived* from where its cast worked: zero for docs, two for API+client.
  Per-repo `checks` run in each environment at every implementing handoff.
* **Stories are workspace-rooted**, so cross-repo work needs no ceremony. **Move story to
  workspace** re-keys a story (old key kept as an alias) and re-homes its environments.
* **Scratch** is an ordinary workspace zharn creates in appdata on first run — pinned, undeletable,
  zharn's own checkout pre-registered — the home of bare contexts started from the start screen
  and of stories that do not yet have a home. No code may special-case it.
* Storage: the durable record (`workspace.toml`, `stories/<key>/story.json` + `threads.jsonl`)
  lives in `.zharn/`, portable and committable; machine-local state (contexts, worktrees, layout)
  in `.zharn/local/`, gitignored.

## 4. Fork-as-config

* `harness/config_def.py` is upstream's defaults; `harness/config.py` is yours (gitignored,
  created on first run by copying the def). Same for (same idea for any file you like).
  `git pull` never conflicts with config; deeper customizations are just edits to any file.
* Upstream updates: xmonad's model, not dwm's — on reload failure after a pull, the previous
  generation keeps running and the error is shown in-app. No patch files.
* Because the agent runs *inside* the harness, "customize" = "ask a character (or a bare
  context) to change it."
  The harness's own checkout is pre-registered as a repo in Scratch and can be registered in any
  workspace (§3c).

## 5. Terminal & editor (open decisions)

* **Terminal**: `pyside6-qtermwidget` is GPL-3, Linux/macOS wheels only — no Windows. Options:
  (a) QML terminal on top of `pyte` (pure-Python VT100 emulator) — fully reloadable, cross-platform,
  ~1 week; (b) xterm.js in `QWebEngineView` — works everywhere but is exactly the web stack we're
  leaving. Lean (a); it is also the most "suckless" choice.
* **Editor**: v1 is a read-mostly diff/file viewer (`TextArea` + `QSyntaxHighlighter`); real
  editing stays in your $EDITOR. KTextEditor has no Python bindings; QScintilla is PyQt-only.

## 6. Licensing

Qt & PySide6 are LGPLv3 → app can be anything. Bundled fonts (Inter, JetBrains Mono) are OFL 1.1
(licenses alongside them in `qml/fonts/`). Every embeddable terminal in Qt-land is GPL-2+,
and QScintilla/PyQt are GPL. **Recommend GPLv3-or-later** for the harness and stop thinking about
it. Avoid GPL-only Qt add-ons only if you ever want to relicense (Charts/Graphs, Quick 3D,
Virtual Keyboard, Timeline).

## 7. Environment caveats on this machine

* WSL (openSUSE Tumbleweed): no sudo, no `tar`; inotify is exhausted by bb's node daemon
  (524,273 / 524,288 watches) → poll. `guiApplications=false` in `.wslconfig` → no display in WSL.
* Working envs: WSL `~/.venvs/mh-conda` (conda-forge PySide6 6.11.2), Windows
  `C:\Users\zachd\.venvs\My-harness-win` (Python 3.10 + PySide6 6.11.2 + pytest; an editable install of the
  old `C:\Users\zachd\Code\my-harness` checkout — `python -m harness` from another checkout's directory still
  runs that checkout, since its cwd is first on `sys.path`; pin `PYTHONPATH` for pytest).
* Windows runs natively from WSL: `cd` to a `/mnt/c/...` checkout and
  `cmd.exe /c "set HARNESS_WORKSPACE=%CD%&& ...\python.exe -m harness"` — env vars go inside the cmd string,
  and cmd.exe refuses a WSL (UNC) working directory.
* Long-term the GUI may run on Windows and drive agents in WSL (bb's "machine" concept), but that needs
  the IPC pipe and `HARNESS_CLI` to cross the boundary; today a character runs on the harness's own OS.

## 8. Next steps

Status 2026-08-31 (later): UI on JetBrains New UI conventions — toolbar, icon strips, Stories tree,
Cast and Contexts tool windows, the story page as a script (§3a); 396 tests.
Status 2026-08-31: foundation shipped per docs/superpowers/plans/2026-08-31-story-foundation.md — workspace storage (.zharn/), lifecycle state machine, stories/characters/contexts/roles stores, zharn story verbs, board + story + context UI over the main thread; the old task/thread/preset model is gone (§0).
Status 2026-08-28: the UI is driven by tests (`tests/ui.py`, ~265 tests); every QML-facing slot is an `@intent` that reports failures to the status bar; the kanban wraps its columns when docked narrow.
Status 2026-08-27: steps 1–2 and 4 done (agent driver over claude-code stream-json, roles,
task dispatch with report-back contract, IPC + `harness.cli` for agent-spawns-agent on the same task,
thread/task/board/agent-log tabs). Step 3 (full task store: labels, comments, attachments) is next.
Earlier status: steps 1–2 done (skeleton, generation reloader, layout tree + QML renderer with
strips/docks/splittable tab groups/tab drag-drop, 15 tests green, rendered on WSL-offscreen and Windows).
Known churn: every intent re-parses the whole tree and rebuilds all groups (fine now; diff by node id later).

1. ~~Skeleton, generation reloader~~ (done).
2. ~~Layout tree + recursive QML renderer~~ (done).
3. **Story lifecycle** per [`specs/story-lifecycle.md`](specs/story-lifecycle.md): `harness/lifecycle.py`
   pure state machine with per-thread turns, thread/comment store, attention + inbox delivery,
   characters/friends (fresh or forked), `zharn story …` verbs, the quiet check, recap/recast
   ladder, character system prompts (since reworked in item 4). Minions are Claude's native `Agent` tool for now;
   `AskUserQuestion` does not exist under `-p`, so `yield --question` is the only way to ask.
   Migrate tasks → stories, code `Thread` → `Context`. **Done 2026-09-02** — characters and delivery
   (plan `docs/superpowers/plans/2026-09-02-characters-delivery.md`): friends fresh or forked, routing to
   addressees, delivery by attention (push mid-turn / inbox), the quiet check at every turn end, `call`/`wait`,
   retirement, sub-stories authored by characters, recast rungs 1 and 3; asides (`Comment.context`,
   `ContextStore.fork`, `stories.aside`). **Deferred:** recast rung 2 (a final restricted recap turn); repo `checks` at handoff
   (workspace plan); the QML for cast panel / `/fork` / sub-stories (UI thread).
   **Context usage shipped 2026-09-04** (proposal `docs/superpowers/proposals/2026-09-04-context-usage.md`, plan
   `docs/superpowers/plans/2026-09-04-context-usage.md`): the reading is the input side of the latest API call from the
   CLI's usage fields, the window from `modelUsage`; `CONTEXT_WARN`/`CONTEXT_MAX` are tokens (300K/500K, scaled to a
   smaller window); a `[harness]` line at each crossing, `recap due` on the situation line, recast at the boundary;
   Claude Code's auto-compaction is off in every context. **The meter shipped 2026-09-04** (spec §6 "Context vitals"):
   every cast row and the Contexts pane header lay the reading on the warn/max runway, amber only while a recap is due;
   tree rows carry the reading, predecessor rows the reading they were recast at (mockup `07-cast-1to1.html`).
4. **Skills** (proposal `docs/superpowers/proposals/2026-09-03-skills.md`). **Shipped 2026-09-04** (plan
   `docs/superpowers/plans/2026-09-03-skills.md`): `harness/skills/` is one Claude Code plugin (`zharn:<name>`,
   `--plugin-dir` at every spawn) holding `being-a-character`, `planning-a-story`, `implementing-a-story`, `delegating`
   and five discipline skills vendored from superpowers 6.3.0 (`VENDORED.md`, `LICENSES/superpowers`); the character
   prompt is split by volatility — a stable system prompt built at every spawn and never stored, the situation line and
   the phase skill in messages (`Character.phase_seen`; spec §5.3); `tests/skills/` runs three scenarios against real
   `claude -p` behind `HARNESS_PAID_TESTS=1`, blanking the skill under test for the baseline; the paid run landed
   2026-09-04 on Sonnet 5 (`HARNESS_PAID_MODEL`), its `baseline.json`/`skilled.json` beside each scenario. What that run
   taught (proposal `2026-09-04-paid-run-frictions.md`, shipped the same day): a question yield is a JSON document on
   stdin, one record per question, rendered as a button row each; `wait` rejects only the go-quiet case; the main thread
   is `#main` wherever the harness speaks; an implementing handoff on main refuses a dirty tree. **Deferred:**
   `writing-skills`, a separate `yielding` skill, shrinking the situation line.
5. **Story tab + board rework**: threads with per-cell action bars, option buttons, `@`/`/call`,
   cast panel (attention, inbox, context meter, Recast), needs-you highlighting and count,
   interactive context views, New Context + Promote to story.
6. **Workspaces, repos, environments** per [`specs/workspace-model.md`](specs/workspace-model.md): `workspace.toml` + `.zharn/`
   layout, start screen (Scratch, recents, open folder), repo registration (author + `zharn repo
   add`), lazy managed worktrees (`zharn env open`), per-repo checks at handoff, story move with
   aliases; migrate `.harness/` → `.zharn/`. Approve fast-forwards each environment into its
   target and sweeps worktrees (spec §4.8, **shipped 2026-09-05**, plan
   `docs/superpowers/plans/2026-09-05-approve-merge.md`); git status + filesystem panels. **Harness side shipped 2026-09-03** (plan `docs/superpowers/plans/2026-09-03-environments.md`, spec §4 revised 2026-09-03):
   repo registration (`zharn repo add`, paths or URL clones), environments — every story on its own branch
   and worktree, cut from its parent environment's branch; friends share a tree, stories get a branch — lazy
   managed worktrees, context placement at spawn, checks at implementing handoffs run by the CLI (`HANDOFF_CHECKS` gate/attach),
   Scratch under appdata as the default workspace. **UI shipped 2026-09-03:** the workspace page (an editor
   tab off the toolbar's workspace widget: name, prefix, the repos table with each repo's worktrees as story
   keys, Relocate for a missing repo, Unregister on hover, register by path) over `app.workspace`
   (`harness/workspace_store.py`); the story page lists each environment as repo · branch · the branch it
   merges into; the cast panel names a character's environment; check rows fold and a red chip on the action
   bar counts failing checks on the handoff that waits on you. **Next:** start screen, story move (§5.3);
   clone/setup still run in the harness process (bounded by GIT_TIMEOUT_S/SETUP_TIMEOUT_S); moving them into
   the character's turn like checks is the follow-up.
7. `pyte`-backed terminal panel.
8. Self-hosting: open Scratch, start a story against the pre-registered zharn repo, and have the
   cast edit the UI. The loop is closed: a story's branch lands in the running checkout through
   Approve (§3c, spec §4.8).

## Sources (selected)

Qt `QQmlEngine::clearComponentCache` docs · `QPluginLoader` / `PreventUnloadHint` docs · QTBUG-141188,
QTBUG-146122, QTBUG-97639 · Quickshell `generation.cpp` / `Reloadable` · Felgo Hot Reload docs & pricing ·
PySide6 6.11 release notes · jurigged, qtreload, pyedifice READMEs · Qt licensing page (6.11) ·
qtermwidget / QMLTermWidget / KTextEditor repos · qutebrowser `config.py`, xmonad reload docs.
