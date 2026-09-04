"""The Documents panel's backend (spec docs/specs/documents-panel.md): the headings Qt's markdown
engine makes of a document, the markdown corpus of the workspace's registered repos, the flat row view
the panel renders, heading search, and DocumentsStore — the QObject QML sees as `app.documents`."""
from __future__ import annotations

import os
import re
from pathlib import Path

from PySide6.QtGui import QTextDocument

_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\.?[ \t]+(\S.*)$")


def split_number(text: str) -> tuple[str, str]:
    """'4.6 Checks' -> ('4.6', 'Checks'); '2. Workspace' -> ('2', 'Workspace'); anything else -> ('', text.strip())."""
    m = _NUMBER.match(text.strip())
    return (m.group(1), m.group(2).strip()) if m else ("", text.strip())


def _heading_blocks(doc: QTextDocument):
    """(level, text, position) of every heading block of a rendered document, in order — the one walk
    both `headings_of` and `_heading_positions_of` go through, so the two can never disagree."""
    block = doc.begin()
    while block.isValid():
        level = block.blockFormat().headingLevel()
        if level:
            yield level, block.text(), block.position()
        block = block.next()


def _rendered(text: str) -> QTextDocument:
    doc = QTextDocument()
    doc.setMarkdown(text)
    return doc


def headings_of(text: str) -> list[dict]:
    """Every heading of `text` as {index, level, number, title}, in order. A heading is whatever Qt's
    markdown engine renders as a heading block — the same engine the document tab renders with, so
    `index` here is the tab's ordinal (spec: sections)."""
    out = []
    for level, raw, _ in _heading_blocks(_rendered(text)):
        number, title = split_number(raw)
        out.append({"index": len(out), "level": level, "number": number, "title": title})
    return out


def heading_positions(text: str) -> list[int]:
    """Character positions of the heading blocks Qt's markdown engine makes of `text` — the same engine
    TextArea uses in MarkdownText mode, so ordinal n here is ordinal n in the tab."""
    return _heading_positions_of(_rendered(text))


def _heading_positions_of(doc: QTextDocument) -> list[int]:
    return [pos for _, _, pos in _heading_blocks(doc)]


def title_and_sections(headings: list[dict]) -> tuple[str, list[dict]]:
    """The first heading, when it is the document's only H1, is the title and not a section."""
    if headings and headings[0]["level"] == 1 and sum(1 for h in headings if h["level"] == 1) == 1:
        return headings[0]["title"], headings[1:]
    return "", list(headings)


EXCLUDED_DIRS = frozenset({".git", ".zharn", "node_modules", ".venv", "venv", "__pycache__"})


def _skip_dir(name: str) -> bool:
    return name in EXCLUDED_DIRS or name.startswith(".")


def read_document(name: str, path: Path, rel: str) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    title, sections = title_and_sections(headings_of(text))
    return {
        "key": f"{name}/{rel}", "repo": name, "rel": rel, "name": Path(rel).name[:-3] if rel.lower().endswith(".md") else Path(rel).name,
        "path": str(path), "mtime": path.stat().st_mtime_ns, "title": title, "sections": sections,
        "numbered": any(s["number"] for s in sections),
    }


def walk_repo(path: Path):
    """(path, relative path) of every *.md under `path`, minus EXCLUDED_DIRS and dot-directories."""
    path = Path(path)
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if not _skip_dir(d))
        for f in files:
            if f.lower().endswith(".md"):
                p = Path(root) / f
                yield p, p.relative_to(path).as_posix()


def scan_repo(name: str, path: Path) -> list[dict]:
    """Every *.md under `path`, read, sorted by relative path."""
    docs = [read_document(name, p, rel) for p, rel in walk_repo(path)]
    docs.sort(key=lambda d: d["rel"].lower())
    return docs


# ---------------------------------------------------------------- the tree, flattened
def _dir_tree(docs: list[dict]) -> dict:
    """{'dirs': {name: subtree}, 'docs': [doc]} nested by the documents' relative paths."""
    root = {"dirs": {}, "docs": []}
    for d in docs:
        node = root
        for part in d["rel"].split("/")[:-1]:
            node = node["dirs"].setdefault(part, {"dirs": {}, "docs": []})
        node["docs"].append(d)
    return root


def _compact(node: dict, name: str) -> tuple[str, dict]:
    """VS Code's compact folders: a directory whose only child is a directory joins it (`superpowers/plans`)."""
    while not node["docs"] and len(node["dirs"]) == 1:
        (child_name, child), = node["dirs"].items()
        name, node = f"{name}/{child_name}", child
    return name, node


def _section_tree(sections: list[dict]) -> list[dict]:
    """Nest by level: each section under the nearest preceding one of a smaller level."""
    roots, stack = [], []   # stack: [(level, node)]
    for s in sections:
        node = {**s, "children": []}
        while stack and stack[-1][0] >= s["level"]:
            stack.pop()
        (stack[-1][1]["children"] if stack else roots).append(node)
        stack.append((s["level"], node))
    return roots


def _row(row_id, kind, level, title, *, number="", has_children=False, expanded=False, key="", ordinal=-1, count=0, column=False):
    return {"id": row_id, "kind": kind, "level": level, "title": title, "number": number, "hasChildren": has_children,
            "expanded": expanded, "key": key, "ordinal": ordinal, "count": count, "column": column}


def _walk(docs: list[dict], expanded: set[str] | None, out: list[dict]):
    """Depth-first over repos > directories > documents > sections. expanded=None visits everything (for ids);
    a set visits only what is open."""
    by_repo: dict[str, list[dict]] = {}
    for d in docs:
        by_repo.setdefault(d["repo"], []).append(d)

    def visible(id_):
        return expanded is None or id_ in expanded

    def sections(doc, nodes, level):
        for n in nodes:
            id_ = f"{doc['key']}#{n['index']}"
            out.append(_row(id_, "sec", level, n["title"], number=n["number"], has_children=bool(n["children"]),
                            expanded=id_ in (expanded or ()), key=doc["key"], ordinal=n["index"], column=doc["numbered"]))
            if n["children"] and visible(id_):
                sections(doc, n["children"], level + 1)

    def directory(repo, node, prefix, level):
        for name in sorted(node["dirs"], key=str.lower):
            cname, cnode = _compact(node["dirs"][name], name)
            id_ = f"{repo}/{prefix}{cname}"
            out.append(_row(id_, "dir", level, cname, has_children=True, expanded=id_ in (expanded or ())))
            if visible(id_):
                directory(repo, cnode, f"{prefix}{cname}/", level + 1)
        for d in sorted(node["docs"], key=lambda d: d["name"].lower()):
            tree = _section_tree(d["sections"])
            out.append(_row(d["key"], "doc", level, d["name"], has_children=bool(tree), expanded=d["key"] in (expanded or ()), key=d["key"]))
            if tree and visible(d["key"]):
                sections(d, tree, level + 1)

    for repo in sorted(by_repo, key=str.lower):
        out.append(_row(repo, "repo", 0, repo, has_children=True, expanded=repo in (expanded or ()), count=len(by_repo[repo])))
        if visible(repo):
            directory(repo, _dir_tree(by_repo[repo]), "", 1)


def build_rows(docs: list[dict], expanded: set[str]) -> list[dict]:
    out: list[dict] = []
    _walk(docs, expanded, out)
    return out


def all_row_ids(docs: list[dict]) -> list[str]:
    out: list[dict] = []
    _walk(docs, None, out)
    return [r["id"] for r in out]


def default_expanded(docs: list[dict]) -> set[str]:
    out: list[dict] = []
    _walk(docs, None, out)
    return {r["id"] for r in out if r["kind"] in ("repo", "dir")}


def ancestor_ids(doc: dict, index: int) -> list[str]:
    """The document's id, then the ids of the sections enclosing section `index`, outermost first."""
    ids = [doc["key"]]
    if index < 0:
        return ids
    stack: list[dict] = []
    for s in doc["sections"]:
        while stack and stack[-1]["level"] >= s["level"]:
            stack.pop()
        if s["index"] == index:
            return ids + [f"{doc['key']}#{a['index']}" for a in stack]
        stack.append(s)
    return ids


# ---------------------------------------------------------------- search
def search(docs: list[dict], query: str) -> list[dict]:
    """Every word must occur in the document name or in a heading's number+title, case-insensitively.
    Groups in corpus order; a document whose name matches is a group with no sections."""
    words = [w for w in query.lower().split() if w]
    if not words:
        return []

    def hit(text):
        t = text.lower()
        return all(w in t for w in words)

    out = []
    for d in docs:
        secs = [{"index": s["index"], "number": s["number"], "title": s["title"]}
                for s in d["sections"] if hit(f"{s['number']} {s['title']}")]
        if secs or hit(d["name"]):
            out.append({"key": d["key"], "name": d["name"], "repo": d["repo"], "sections": secs})
    return out


from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from harness.notify import intent
from harness.qmodels import DictListModel

ROW_ROLES = ["id", "kind", "level", "title", "number", "hasChildren", "expanded", "key", "ordinal", "count", "column"]


class DocumentsStore(QObject):
    """The markdown corpus of the workspace's registered repos, the panel's expansion state, and each
    document's reading position. State that must survive a QML reload lives here (DESIGN §1)."""
    documentsChanged = Signal()
    positionChanged = Signal(str)
    scrollRequested = Signal(str, int)
    notifier = None

    def __init__(self, workspace, layout_store, parent=None):
        super().__init__(parent)
        self._ws = workspace
        self.layout = layout_store
        self._docs: list[dict] = []
        self._by_key: dict[str, dict] = {}
        self._expanded: set[str] = set()
        self._seen: set[str] = set()          # repo/dir ids that have had their default expansion applied
        self._positions: dict[str, int] = {}
        self._pending_scroll: dict[str, int] = {}
        self._unreadable: dict[str, int] = {}   # key -> mtime of a file whose read failed, so a permanent
                                                # failure is reported once instead of every tick
        self._model = DictListModel(ROW_ROLES, self)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self, interval_ms: int):
        self.rescan()
        self._timer.start(interval_ms)

    def _tick(self):
        if self._in_use():
            self.rescan()

    def _in_use(self) -> bool:
        """Is anything showing the map? The panel is a dock's visible active panel, or a document tab is
        open somewhere in the centre. Walking every repo costs tens of milliseconds on the GUI thread, so
        a hidden panel does not pay it; the panel rescans when it is shown."""
        data = getattr(getattr(self.layout, "_layout", None), "data", None)
        if not isinstance(data, dict):
            return True
        for dock in (data.get("docks") or {}).values():
            if dock.get("active") == "documents" and dock.get("mode") == "docked":
                return True
        stack = [data.get("center")]
        while stack:
            node = stack.pop()
            if not isinstance(node, dict):
                continue
            if node.get("type") == "tabs":
                if any(t.get("kind") == "document" for t in node.get("tabs") or ()):
                    return True
            else:
                stack.extend(node.get("children") or ())
        return False

    # ---------------------------------------------------------------- corpus
    def rescan(self) -> bool:
        """Re-list every registered repo; re-read the files whose mtime changed. True when anything changed.
        Called directly it always walks; the periodic tick walks only while the map is in use (`_in_use`)."""
        old = {d["key"]: d for d in self._docs}
        new: list[dict] = []
        unreadable: dict[str, int] = {}
        changed = False
        for rec in self._ws.repos:
            if self._ws.repo_status(rec["name"]) != "ok":
                continue
            for p, rel in walk_repo(self._ws.repo_path(rec)):
                key = f"{rec['name']}/{rel}"
                prev = old.get(key)
                try:
                    mtime = p.stat().st_mtime_ns
                except OSError:
                    continue
                if prev and prev["mtime"] == mtime:
                    new.append(prev)
                    continue
                try:
                    doc = read_document(rec["name"], p, rel)
                except OSError:
                    # vanished or was mid-write between the stat above and this read; skip it for this
                    # scan and let the next one pick it up (or drop it, if it's really gone). A file that
                    # never becomes readable must not report a change every tick, so a failure counts as
                    # one only the first time, when its mtime moves, or when it costs us a document.
                    if key in old or self._unreadable.get(key) != mtime:
                        changed = True
                    unreadable[key] = mtime
                    continue
                new.append(doc)
                changed = True
        self._unreadable = unreadable          # a file that reads again, or vanishes, drops out
        new.sort(key=lambda d: (d["repo"].lower(), d["rel"].lower()))
        if len(new) != len(old) or changed:
            self._docs = new
            self._by_key = {d["key"]: d for d in new}
            for id_ in default_expanded(new):
                if id_ not in self._seen:
                    self._seen.add(id_)
                    self._expanded.add(id_)
            self._refresh()
            self.documentsChanged.emit()
            return True
        return False

    def documents(self) -> list[dict]:
        return list(self._docs)

    def document(self, key: str) -> dict | None:
        return self._by_key.get(key)

    @Slot(str, result=str)
    def text(self, key: str) -> str:
        d = self._by_key.get(key)
        if not d:
            return ""
        try:
            return Path(d["path"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    # ---------------------------------------------------------------- rows
    @Property(QObject, constant=True)
    def model(self):
        return self._model

    def _refresh(self):
        """Reset the model only when the visible rows actually differ: a reset sends the tree's scroll
        position back to the top, and most rescans (a body-only edit) change no row at all."""
        rows = build_rows(self._docs, self._expanded)
        if rows != self._model.rows():
            self._model.reset(rows)

    @Slot(result="QVariantList")
    def rows(self) -> list[dict]:
        return build_rows(self._docs, self._expanded)

    @Slot(str)
    @intent
    def toggle(self, id_: str):
        if id_ in self._expanded:
            self._expanded.discard(id_)
        else:
            self._expanded.add(id_)
        self._refresh()

    @Slot()
    @intent
    def collapseAll(self):
        self._expanded.clear()
        self._refresh()

    @Slot(str, int)
    @intent
    def expandTo(self, key: str, index: int):
        d = self._by_key.get(key)
        if not d:
            return
        self._expanded.update(ancestor_ids(d, index))
        # the repo and every directory above the document
        self._expanded.add(d["repo"])
        for r in build_rows(self._docs, set(all_row_ids(self._docs))):
            if r["kind"] == "dir" and r["id"].startswith(d["repo"] + "/") and d["rel"].startswith(r["id"][len(d["repo"]) + 1:] + "/"):
                self._expanded.add(r["id"])
        self._refresh()

    # ---------------------------------------------------------------- position and opening
    @Slot(str, result=int)
    def position(self, key: str) -> int:
        return self._positions.get(key, -1)

    @Slot(str, int)
    @intent
    def setPosition(self, key: str, index: int):
        """Called by the document tab as it scrolls with the ordinal of the topmost heading (-1 above the first).
        The title heading is not a section, so it reads as the document row."""
        d = self._by_key.get(key)
        if not d:
            return
        if index >= 0 and not any(s["index"] == index for s in d["sections"]):
            index = -1
        before = set(self._expanded)
        self._expanded.update(ancestor_ids(d, index))
        if self._positions.get(key, -1) != index or before != self._expanded:
            self._positions[key] = index
            if before != self._expanded:
                self._refresh()
            self.positionChanged.emit(key)

    @Slot(str)
    @Slot(str, int)
    @intent
    def open(self, key: str, index: int = -1):
        d = self._by_key.get(key)
        if not d:
            return
        self.layout.openContent("document", key, Path(d["rel"]).name)
        self.expandTo(key, index)
        self._pending_scroll[key] = index
        self.scrollRequested.emit(key, index)

    @Slot(str, result=int)
    def takeScroll(self, key: str) -> int:
        return self._pending_scroll.pop(key, -2)

    # ---------------------------------------------------------------- search, rendering
    @Slot(str, result="QVariantList")
    def search(self, query: str) -> list[dict]:
        return search(self._docs, query)

    @Slot(QObject, result="QVariantList")
    def headingPositionsIn(self, qdoc) -> list[int]:
        """`qdoc` is a TextEdit's `textDocument` (QQuickTextDocument); its QTextDocument is the rendered one."""
        return _heading_positions_of(qdoc.textDocument())
