# my-harness — design notes (2026-08-27)

A native, self-modifying coding-agent harness. Keeps bb's model, drops the web stack,
and treats *your fork as your config* (suckless/st style). Hot reload is a hard requirement
because the thing that edits the harness is the agent running inside it.

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
│ │ Projects · Threads · Environments · Providers · Terminals       │   │
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

Verbatim conceptual model (`bb guide`): **Project** ↔ repo · **Thread** = one agent conversation,
optional parent (parent gets child lifecycle events) · **Environment** = checkout or managed
worktree, shareable across threads, `.bb-env-setup.sh` hook · **Provider** = agent backend +
model · **Terminal** = persistent PTY scoped to thread/env · forks (clone session at a turn) ·
sections · hidden threads for background workers · permission modes as a ceiling from parent to child.

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

* **Dock (left/right/bottom)** hosts only **dockable panels**: task board, task details (the old
  bb sidebar becomes just another panel), git status, filesystem, terminal, agent log, presets.
  States: docked-visible, collapsed-to-strip, slide-over (overlay `Item`, not a window), floating
  (`Window`).
* **MCC** is a tab group that can show *any* content: a panel, a document, a thread, a task, a
  diff. Split any MCC horizontally/vertically; drag tabs between MCCs, to an edge for a new split,
  or out to float. Empty MCCs collapse.
* Content types register in `harness/content.py` (`kind` → QML component + Python controller),
  so adding a new panel/document type is one Python dict entry + one QML file — fork-as-config.

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

## 3b. Task-centric thread model

**Superseded by [`docs/superpowers/specs/2026-08-28-task-lifecycle-design.md`](superpowers/specs/2026-08-28-task-lifecycle-design.md)** — that spec is declarative and wins over both this section and the code. Summary:

* A **Task** is the smallest unit of work its *owner* describes and validates. State is
  `(phase, ball)`: `phase ∈ backlog|todo|planning|implementing|done|canceled`,
  `ball ∈ worker|owner`. Owner = human for board tasks, the creating thread for agent-created
  subtasks — same matrix at every level.
* **Nobody sets status.** Start / Reply / Proceed / Approve / Back-to-planning / Cancel (owner) and
  `yield --question|--handoff` / `proceed` (worker) are the only actions; each writes a comment and
  the comment stream is the audit log. A thread that exits without yielding is auto-handed-off.
* **Comments are the only channel.** No chat input; transcripts are read-only. `AskUserQuestion`
  is intercepted into a `question` comment with option buttons. `/call <preset>` in a comment
  attaches another thread. Replies route to the authoring thread; top-level → primary thread.
* **Skills** (`harness/skills/`, vendored from superpowers) are injected by phase into the system
  prompt; the harness enforces mechanically what it can (no status verb, handoff blocked while
  subtasks are open, check command attached to handoffs) and uses skills only for judgment.
* Board columns = phase; cards where the human holds the ball are highlighted and sorted first.

Kept from bb: projects with prefixes, presets, attachments, mentions (`@ABC-12`), threads without
a task landing in an auto-created "Inbox" task.

## 4. Fork-as-config

* `harness/config_def.py` is upstream's defaults; `harness/config.py` is yours (gitignored,
  created on first run by copying the def). Same for (same idea for any file you like).
  `git pull` never conflicts with config; deeper customizations are just edits to any file.
* Upstream updates: xmonad's model, not dwm's — on reload failure after a pull, the previous
  generation keeps running and the error is shown in-app. No patch files.
* Because the agent runs *inside* the harness, "customize" = "ask the thread to change it."
  The harness should expose its own source tree as a first-class Project.

## 5. Terminal & editor (open decisions)

* **Terminal**: `pyside6-qtermwidget` is GPL-3, Linux/macOS wheels only — no Windows. Options:
  (a) QML terminal on top of `pyte` (pure-Python VT100 emulator) — fully reloadable, cross-platform,
  ~1 week; (b) xterm.js in `QWebEngineView` — works everywhere but is exactly the web stack we're
  leaving. Lean (a); it is also the most "suckless" choice.
* **Editor**: v1 is a read-mostly diff/file viewer (`TextArea` + `QSyntaxHighlighter`); real
  editing stays in your $EDITOR. KTextEditor has no Python bindings; QScintilla is PyQt-only.

## 6. Licensing

Qt & PySide6 are LGPLv3 → app can be anything. Every embeddable terminal in Qt-land is GPL-2+,
and QScintilla/PyQt are GPL. **Recommend GPLv3-or-later** for the harness and stop thinking about
it. Avoid GPL-only Qt add-ons only if you ever want to relicense (Charts/Graphs, Quick 3D,
Virtual Keyboard, Timeline).

## 7. Environment caveats on this machine

* WSL (openSUSE Tumbleweed): no sudo, no `tar`; inotify is exhausted by bb's node daemon
  (524,273 / 524,288 watches) → poll. `guiApplications=false` in `.wslconfig` → no display in WSL.
* Working envs: WSL `~/.venvs/mh-conda` (conda-forge PySide6 6.11.2), Windows
  `C:\Users\zachd\.venvs\my-harness-win` (Python 3.10 + PySide6 6.11.2).
* Long-term the GUI likely runs on Windows and drives agents in WSL (bb's "machine" concept),
  or WSLg gets re-enabled. Either works with the architecture above.

## 8. Next steps

Status 2026-08-28: the UI is driven by tests (`tests/ui.py`, ~265 tests); every QML-facing slot is an `@intent` that reports failures to the status bar; the kanban wraps its columns when docked narrow.
Status 2026-08-27: steps 1–2 and 4 done (agent driver over claude-code stream-json, presets,
task dispatch with report-back contract, IPC + `harness.cli` for agent-spawns-agent on the same task,
thread/task/board/agent-log tabs). Step 3 (full task store: labels, comments, attachments) is next.
Earlier status: steps 1–2 done (skeleton, generation reloader, layout tree + QML renderer with
strips/docks/splittable tab groups/tab drag-drop, 15 tests green, rendered on WSL-offscreen and Windows).
Known churn: every intent re-parses the whole tree and rebuilds all groups (fine now; diff by node id later).

1. ~~Skeleton, generation reloader~~ (done).
2. ~~Layout tree + recursive QML renderer~~ (done).
3. **Task lifecycle** per the 2026-08-28 spec: `harness/lifecycle.py` pure state machine, comment
   store, CLI verbs (`yield`/`proceed`/`comment`/`create`/`wait`/owner verbs), auto-handoff,
   `AskUserQuestion` interception, phase-aware system prompts. Migrate `status` → `(phase, ball)`.
4. **Skills**: vendor superpowers' discipline skills into `harness/skills/`, write
   `using-harness` + the phase skills, `tests/skills/` runner with mechanical verb assertions.
5. **Task tab + board rework**: comment stream with per-cell action bars, option buttons, `/call`,
   "needs you" highlighting and count, read-only transcript tabs.
6. Projects/Environments (worktree create via `git worktree`), `.env-setup` hook; what Approve
   does to the worktree (merge/PR) gets its own spec; git status + filesystem panels.
7. `pyte`-backed terminal panel.
8. Self-hosting: open my-harness as a Project inside my-harness and have a thread edit the UI.

## Sources (selected)

Qt `QQmlEngine::clearComponentCache` docs · `QPluginLoader` / `PreventUnloadHint` docs · QTBUG-141188,
QTBUG-146122, QTBUG-97639 · Quickshell `generation.cpp` / `Reloadable` · Felgo Hot Reload docs & pricing ·
PySide6 6.11 release notes · jurigged, qtreload, pyedifice READMEs · Qt licensing page (6.11) ·
qtermwidget / QMLTermWidget / KTextEditor repos · qutebrowser `config.py`, xmonad reload docs.
