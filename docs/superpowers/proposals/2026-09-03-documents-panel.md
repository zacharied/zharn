# Documents panel: a map of the workspace's markdown

*Proposal, 2026-09-03. Mockups: `docs/design/mockups/07-documents.html`, `08-documents-1to1.html`.*

A new left-dock panel, **Documents**, that shows every markdown document in the workspace's registered
repos as a tree whose leaves are *sections*, not files. It is a code browser for prose: the unit of
navigation is the heading, the map follows what you are reading, and typing filters by heading. It sits
next to Files on the strip; Files stays the file tree.

Naming follows the existing pairs: Stories opens a Story, Contexts a Context, Documents a Document.

## 1. What the panel shows

One tree, four kinds of row:

| row | text | notes |
|---|---|---|
| repo | repo name, bold; count of documents at the right | one per registered repo with at least one document; missing repos (§3.3 of the workspace spec) are skipped |
| directory | path segment, muted | compacted like VS Code's folders: a directory whose only child is a directory joins it (`superpowers/plans`); directories that contain no document, directly or below, do not appear |
| document | filename without `.md`; weight 500 while its tab is open | sorted after directories, by name |
| section | heading text; a numbered heading splits into a mono number column and a title | nested strictly by heading level |

Ordering inside a group: directories, then documents, both by name, case-insensitive.

**Sections.** A heading is an ATX (`## …`) or setext (underlined) heading outside fenced code; a `#` line
inside a fence is not a heading. The first heading of a document, when it is the only H1, is the
document's title and is not a row; every other heading is a section, nested by level under the nearest
preceding heading of a smaller level. A heading that begins with a number (`4.6 Checks`, `2. Workspace`)
is split into number and title; the document has a number column when any of its headings is numbered,
and no column otherwise, so `README`'s `Run` / `Test` rows start where a title would.

**Typography.** The number column is the Stories tree's key column: mono, muted, right-aligned; the
selected row's number takes the selected-key tint. No file or heading-level icons; depth is the indent and
the number. Indent is 18 px per level from a 10 px left margin. Rows are `rowHeight` tall and elide.

**Header.** Title "Documents", a collapse-all action, Hide. No badge, no subtitle.

**Empty state.** "No markdown documents in the registered repos." when the tree is empty.

## 2. Rules

**The map follows the reader.**

* Clicking a document row opens its tab (kind `document`) at the top and expands the row. Clicking a
  section row opens the tab scrolled to that heading. The chevron toggles a row without opening anything.
* The **selected row** is the current section of the active editor tab when that tab is a document: the
  section that contains the first visible line of the tab's viewport. It moves as the reader scrolls, and
  the map scrolls to keep it visible.
* Inside an expanded document, sections that have children are collapsed except the one that contains the
  current section, which is expanded as the position moves. Nothing auto-collapses; collapse-all does, and
  it collapses every row so only the repo rows remain.
* Repos and directories start expanded; documents start collapsed.

**Type to filter.** Typing while the tree has focus shows a filter field above the tree (JetBrains speed
search); Esc clears and hides it. The filter matches document names and heading text, case-insensitively;
every whitespace-separated word must occur in the row's text. Body text is not searched. While a filter is
active the tree is replaced by a **results list**: matching sections grouped under their document, each
group headed by the document name with the repo name muted at the right; a document whose *name* matches
appears as a group with no sections. Result titles wrap rather than elide, so the matched word is never
hidden. Matched text is bold in the accent. Clicking a result opens as above.

**Every panel is reachable.** A panel kind registered in `content.KINDS` that is in no dock is added to
the left dock's list when the layout loads, so a saved session shows Documents on its strip without a
reset. (An invariant of the layout, not a migration: it holds for any panel a fork adds.)

## 3. Backend: `harness/documents.py`, `app.documents`

`DocumentsStore` (a QObject singleton like the others, hot-reloadable, exposed on `AppStore` as
`documents`) owns:

* **The corpus.** `scan()` walks each registered repo for `*.md`, skipping `.git`, `.zharn`, any dot-directory,
  `node_modules`, `.venv`/`venv`, and `__pycache__`. A document's key is `<repo>/<path relative to the repo>`
  with forward slashes; keys are unique because repo names are. Each document record carries `key`, `repo`,
  `rel`, `name`, `mtime`, `title`, and `sections`: `[{index, level, number, title, line}]` in source order.
* **Parsing.** `parse_headings(text)` implements §1's rules and is a pure function with its own tests. Its
  heading sequence must equal the heading blocks Qt's markdown engine produces for the same text, because
  the tab locates a section by its index in the rendered document (§4); a test asserts this over every
  document in the repo.
* **Freshness.** A `QTimer` rescans every `config.DOCS_RESCAN_MS` (default 2000): re-list the files, re-parse
  the ones whose mtime changed, emit `documentsChanged` when anything did. Registering or unregistering a
  repo (`workspaceChanged`) rescans at once. This deliberately does not extend the shell's `Watcher`, which
  watches the harness's own code and is never reloaded.
* **View state.** Expansion is a set of row ids in the store (state that survives a QML reload lives in
  Python, DESIGN §1); a repo or directory id enters the set the first time a scan sees it, which is how
  §2's defaults hold. The store exposes `rows()`: the flat list of *visible* rows given the expansion
  state — `[{id, kind, level, title, number, hasChildren, expanded, key, index}]` — so the panel is a
  `ListView` over a `DictListModel` and never walks a tree in QML. `toggle(id)`, `collapseAll()`,
  `expandTo(key, index)` (expand the document and the ancestors of a section) are intents.
* **Position.** `setPosition(key, index)` is called by the document tab as it scrolls; `position(key)` reads
  it; `positionChanged(key)` is emitted. The panel derives the selected row from the active tab's key
  (read from `app.layout`, as the Stories tree does) and `position(key)`.
* **Filter.** `search(query)` returns §2's groups: `[{key, name, repo, sections: [{index, number, title}]}]`.
* **Opening.** `open(key, index=-1)` opens or activates the document tab (`layout.openContent("document",
  key, name + ".md")`), expands the document in the map, and emits `scrollRequested(key, index)` for the tab
  to act on; `-1` means the top.

Row ids: `<key>` for a document, `<key>#<index>` for a section, `<repo>/<dir>` for a directory, `<repo>` for
a repo.

## 4. The document tab: `qml/content/Document.qml`

The `document` content kind becomes a read-only markdown view, the first real filling of the
"read-mostly file viewer" slot (DESIGN §5). v1 is deliberately small:

* A `TextArea` with `textFormat: TextEdit.MarkdownText`, read-only, selectable, in a `Flickable`, at the story
  page's measure (max width 820, 20/28 px margins), the theme's UI face for prose and mono for code. Headings
  in the UI face at 20/17/14 px, weight 600, an H2 carrying a top rule as in the mockup.
* It reads its text from `app.documents.text(key)`. On `documentsChanged` for its key it reloads and keeps
  its scroll position.
* **Section positions.** `app.documents.headingPositions(key)` returns, per section index, the character
  position of that heading in the rendered document (computed in Python with `QTextDocument.setMarkdown`, the
  same engine `TextArea` uses). The tab maps a position to a y with `positionToRectangle`. Scrolling to a
  section sets `contentY` to that y; reporting the position finds the last section whose y is at or above
  `contentY` and calls `setPosition` (debounced to a frame).
* Handles `scrollRequested` for its key; on open with a pending request it scrolls once laid out.

No editing, no diff, no syntax colouring inside code blocks. The tab's `objectName` is
`tab_document_<key>` as every tab; the view is `documentView`.

## 5. QML: `qml/content/Documents.qml`

* Registered in `content.KINDS` as `"documents": {"title": "Documents", "qml": "content/Documents.qml",
  "panel": True, "icon": "documents"}`; the `document` kind's icon becomes `documents` too. New icon
  `qml/icons/documents.svg` (a page with a folded corner and lines) and `collapse.svg` is reused.
* Default layout: left dock `["board", "files", "documents", "git"]`.
* A `ListView` over `app.documents.rows()` (a `DictListModel` refreshed on `documentsChanged` and after each
  intent), delegates per §1; `headerActions` contributes collapse-all. Keyboard: Up/Down move, Right/Left
  expand/collapse, Enter opens; printable keys open the filter field with the typed character.
* Object names: `stripButton_documents`, `docRow_<id>`, `docChevron_<id>`, `docFilter`, `docCollapseAll`,
  `docResult_<key>#<index>`, `docEmpty`.

## 6. Tests

* `tests/test_documents.py`: `parse_headings` (fenced code skipped, setext, first-H1-as-title, multiple H1s,
  numbering split, nesting by level); `scan` over a temp repo (exclusions, keys, sorting, directory
  compaction); `rows()` under expansion changes; `search` grouping and multi-word matching; the rescan picks
  up an edited file; the Qt-heading-count invariant over every `*.md` in this repo.
* `tests/test_layout.py`: a saved layout missing a panel kind gains it on the left.
* `tests/test_ui_documents.py`, through `tests/ui.py`: the strip button shows the panel; a registered repo's
  documents appear; clicking a document opens `tab_document_<key>`; clicking a section opens the tab scrolled
  so that section is current and the row is selected; scrolling the tab moves the selection; typing filters
  and Esc clears; collapse-all.

## 7. Out of scope, deliberately

* Body-text search (a second filter mode later).
* "Cited by": which documents link to a section — the find-usages half of a code browser; its own round.
* A git-modified tint on document names (DESIGN §3a keeps saturated colour for turns and liveness).
* Documents outside registered repos (the workspace dir itself when it is not a repo).
* Editing, diffs, and the Files panel, which stays a stub for now.

## 8. When this lands

DESIGN §3a's default layout line and the component list, README's panel list, and DESIGN §5's editor note
are revised to the present tense; this proposal expires.
