# Documents panel

The workspace's markdown, mapped as a tree whose leaves are *sections*, not files. It is a code browser
for prose: the unit of navigation is the heading, the map follows what you are reading, and typing filters
by heading. It sits next to Files on the left strip; Files stays the file tree. Complements the
[workspace model](workspace-model.md), which says which repos are registered, and DESIGN §3a, which says
what a panel is. Where code disagrees with this document, the code is wrong.

*Written 2026-09-03. Mockups: `docs/design/mockups/07-documents.html`, `08-documents-1to1.html`.*

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

**Sections.** A heading is what Qt's markdown engine renders as a heading block — the same engine the
document tab renders with, which is the whole point: the panel and the tab count headings the same way, so
the *n*th heading here is the *n*th heading there. (Qt decides the awkward cases, and they are pinned by
test: a `#` line inside a fence is not a heading, one inside a blockquote or a list item is, YAML front
matter is not a setext heading, an unclosed fence swallows the rest of the file.) The first heading of a
document, when it is the only H1, is the document's title and is not a row; every other heading is a
section, nested by level under the nearest preceding heading of a smaller level. A heading that begins with
a number (`4.6 Checks`, `2. Workspace`) is split into number and title; the document has a number column
when any of its headings is numbered, and no column otherwise, so `README`'s `Run` / `Test` rows start
where a title would.

**Typography.** The number column is the Stories tree's key column: mono, muted, right-aligned; the
selected row's number takes `theme.selectedKey`. No file or heading-level icons; depth is the indent and
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
search); Esc clears and hides it, returning focus to the tree. The tree takes focus when the panel appears
and whenever a row or chevron is clicked, so the keyboard reaches it after a mouse click and not only after
a Tab. The filter matches document names and heading text, case-insensitively; every whitespace-separated
word must occur in the row's text. Body text is not searched. While a filter is active the tree is replaced
by a **results list**: matching sections grouped under their document, each group headed by the document
name with the repo name muted at the right; a document whose *name* matches appears as a group with no
sections. Result titles wrap rather than elide, so the matched word is never hidden. Matched text is bold
in the accent. Clicking a result opens as above.

**Every panel is reachable.** A panel kind registered in `content.KINDS` that is in no dock is added to
the left dock's list when the layout loads, so a saved session shows Documents on its strip without a
reset. (An invariant of the layout, not a migration: it holds for any panel a fork adds.)

## 3. Backend: `harness/documents.py`, `app.documents`

`DocumentsStore` (a QObject singleton like the others, hot-reloadable, exposed on `AppStore` as
`documents`) owns:

* **The corpus.** `walk_repo` lists `*.md` under each registered repo, skipping `.git`, `.zharn`, any
  dot-directory, `node_modules`, `.venv`/`venv`, and `__pycache__`. A document's key is `<repo>/<path
  relative to the repo>` with forward slashes; keys are unique because repo names are. A document record is

  ```
  {key, repo, rel, name, path, mtime, title, sections: [{index, level, number, title}], numbered}
  ```

  in source order, `index` being the heading's ordinal in the rendered document.
* **Headings.** `headings_of(text)` renders the text with `QTextDocument.setMarkdown` and returns its
  heading blocks; `heading_positions(text)` returns the character position of each of those same blocks.
  Both go through one block walk, because §1's ordinal agreement is what the tab navigates by.
* **Freshness.** A `QTimer` rescans every `config.DOCS_RESCAN_MS` (default 2000): re-list the files,
  re-read the ones whose mtime changed, emit `documentsChanged` when anything did. The walk costs tens of
  milliseconds on the GUI thread over a large repo, so the periodic tick takes it only while the map is in
  use — the panel is a dock's docked-visible active panel, or a document tab is open — which it reads from
  the layout; `rescan()` called directly always walks, and the panel rescans when it appears. A file that
  stats but fails to read is skipped for that scan and counts as a change only the first time, so a
  permanently unreadable file does not report one every tick. Registering or unregistering a repo
  (`workspaceChanged`) rescans at once. This deliberately does not extend the shell's `Watcher`, which
  watches the harness's own code and is never reloaded.
* **View state.** Expansion is a set of row ids in the store (state that survives a QML reload lives in
  Python, DESIGN §1); a repo or directory id enters the set the first time a scan sees it, which is how
  §2's defaults hold. The store feeds a `DictListModel` of the *visible* rows given the expansion state —

  ```
  {id, kind, level, title, number, hasChildren, expanded, key, ordinal, count, column}
  ```

  `ordinal` being a section's heading index — so the panel is a `ListView` over that model and never walks
  a tree in QML. The model is reset only when the rows it would hold differ from the rows it holds, so an
  edit to a document's body leaves the tree's scroll position alone. `toggle(id)`, `collapseAll()`,
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

The `document` content kind is a read-only markdown view, the first real filling of the "read-mostly file
viewer" slot (DESIGN §5). It is deliberately small:

* A `TextArea` with `textFormat: TextEdit.MarkdownText`, read-only, selectable, in a `Flickable`, at the story
  page's measure (max width 820, 20/28 px margins), the theme's UI face at the theme size for prose. Heading
  sizes, code styling and rules are Qt's markdown defaults for now; the mockup's typography is the viewer's
  later business.
* It reads its text from `app.documents.text(key)`. On `documentsChanged` it reloads and keeps its scroll
  position.
* **Section positions.** `app.documents.headingPositionsIn(textDocument)` returns, per heading ordinal, the
  character position of that heading in the rendered document; the tab maps a position to a y with
  `positionToRectangle`. Scrolling to a section sets `contentY` to that y, clamped to the bottom of the
  document only when there is one to clamp to: a document shorter than the viewport scrolls so the requested
  heading sits at the top, with blank space below, rather than being stranded at the top of the file.
  Reporting the position finds the last heading whose y is at or above `contentY` and calls `setPosition`,
  throttled to a frame so the selection follows a continuous flick.
* **One settle.** A reload's kept scroll position and a requested section both land in a single zero-interval
  timer that runs after the new text has laid out, because neither can be clamped against a height the text
  has not reached yet. A scroll request beats a kept position outright — a reload and an `open` in the same
  tick leave the reader at the requested section — and `report()` runs once at the end either way.

No editing, no diff, no syntax colouring inside code blocks. The tab's `objectName` is
`tab_document_<key>` as every tab; the view is `documentView`.

## 5. QML: `qml/content/Documents.qml`

* Registered in `content.KINDS` as `"documents": {"title": "Documents", "qml": "content/Documents.qml",
  "panel": True, "icon": "documents"}`; the `document` kind shares the `documents` icon. The icon
  `qml/icons/documents.svg` is a page with a folded corner and lines; `collapse.svg` is reused.
* Default layout: left dock `["board", "files", "documents", "git"]`.
* A `ListView` over the store's model, delegates per §1; `headerActions` contributes collapse-all.
  Keyboard: Up/Down move, Right/Left expand/collapse, Enter opens; printable keys open the filter field
  with the typed character. Which documents have a tab open is read once per layout change into a set of
  keys, not searched for in the layout JSON per row.
* Object names: `stripButton_documents`, `docRow_<id>`, `docChevron_<id>`, `docFilter`, `docCollapseAll`,
  `docResult_<key>#<index>`, `docEmpty`.

## 6. Tests

* `tests/test_documents.py`: `headings_of` (fenced code skipped, setext, first-H1-as-title, multiple H1s,
  numbering split) and a table of the shapes a hand-written parser gets wrong, pinning what Qt does with
  each; the corpus scan over a temp repo (exclusions, keys, sorting, directory compaction); `rows()` under
  expansion changes; `search` grouping and multi-word matching; rescan picking up an edited file, staying
  quiet about an unreadable one, and leaving the rows alone on a body-only edit; the rescan gate; the
  two heading walks agreeing over every `*.md` in this repo.
* `tests/test_layout.py`: a saved layout missing a panel kind gains it on the left.
* `tests/test_ui_documents.py`, through `tests/ui.py`: the empty state; the strip button shows the panel; a
  registered repo's documents appear; clicking a document opens `tab_document_<key>`; clicking a section
  opens the tab scrolled so that section is current and the row is selected; scrolling the tab moves the
  selection; a click on a row leaves the keyboard on the tree, so typing filters; Esc clears; collapse-all;
  a shrinking reload keeps the scroll in bounds; a scroll request beats a reload in the same tick.

## 7. What the panel does not do, yet

* Body-text search (a second filter mode later).
* "Cited by": which documents link to a section — the find-usages half of a code browser; its own round.
* A git-modified tint on document names (DESIGN §3a keeps saturated colour for turns and liveness).
* Documents outside registered repos (the workspace dir itself when it is not a repo).
* Editing, diffs, and the Files panel, which stays a stub for now.
* A filesystem watcher per registered repo, which would retire the rescan timer and its gate together.
