"""The Documents panel's backend (proposal docs/superpowers/proposals/2026-09-03-documents-panel.md):
a heading parser, the markdown corpus of the workspace's registered repos, the flat row view the panel
renders, heading search, and DocumentsStore — the QObject QML sees as `app.documents`."""
from __future__ import annotations

import os
import re
from pathlib import Path

_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_SETEXT_1 = re.compile(r"^ {0,3}=+[ \t]*$")
_SETEXT_2 = re.compile(r"^ {0,3}-+[ \t]*$")
_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\.?[ \t]+(\S.*)$")


def split_number(text: str) -> tuple[str, str]:
    """'4.6 Checks' -> ('4.6', 'Checks'); '2. Workspace' -> ('2', 'Workspace'); anything else -> ('', text)."""
    m = _NUMBER.match(text.strip())
    return (m.group(1), m.group(2).strip()) if m else ("", text.strip())


def parse_headings(text: str) -> list[dict]:
    """Every ATX or setext heading outside fenced code, in source order, as
    {index, level, number, title, line}. `index` is the ordinal among all headings — the same ordinal Qt's
    markdown engine gives the heading block, which is how the document tab finds it (spec §3, §4)."""
    out: list[dict] = []
    fence: tuple[str, int] | None = None   # (char, length) of the open fence
    lines = text.split("\n")
    prev_blank = True
    prev_is_para = False                   # previous line could be the text of a setext heading

    def add(level: int, raw: str, line: int):
        number, title = split_number(raw)
        out.append({"index": len(out), "level": level, "number": number, "title": title, "line": line})

    for i, line in enumerate(lines):
        stripped = line.strip()
        if fence:
            m = _FENCE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] and line.strip() == m.group(1):
                fence = None
            prev_is_para = False
            prev_blank = True
            continue
        m = _FENCE.match(line)
        if m:
            fence = (m.group(1)[0], len(m.group(1)))
            prev_is_para = False
            prev_blank = True
            continue
        m = _ATX.match(line)
        if m and stripped:
            add(len(m.group(1)), m.group(2) or "", i)
            prev_is_para = False
            prev_blank = False
            continue
        if prev_is_para and not prev_blank:
            if _SETEXT_1.match(line):
                add(1, lines[i - 1], i - 1)
                prev_is_para = False
                prev_blank = False
                continue
            if _SETEXT_2.match(line):
                add(2, lines[i - 1], i - 1)
                prev_is_para = False
                prev_blank = False
                continue
        prev_blank = not stripped
        prev_is_para = bool(stripped) and not line.startswith("    ") and not stripped.startswith(("|", ">", "-", "*", "+"))
    return out


def title_and_sections(headings: list[dict]) -> tuple[str, list[dict]]:
    """Spec §1: the first heading, when it is the document's only H1, is the title and not a section."""
    if headings and headings[0]["level"] == 1 and sum(1 for h in headings if h["level"] == 1) == 1:
        return headings[0]["title"], headings[1:]
    return "", list(headings)


EXCLUDED_DIRS = frozenset({".git", ".zharn", "node_modules", ".venv", "venv", "__pycache__"})


def _skip_dir(name: str) -> bool:
    return name in EXCLUDED_DIRS or name.startswith(".")


def read_document(name: str, path: Path, rel: str) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    title, sections = title_and_sections(parse_headings(text))
    return {
        "key": f"{name}/{rel}", "repo": name, "rel": rel, "name": Path(rel).name[:-3] if rel.lower().endswith(".md") else Path(rel).name,
        "path": str(path), "mtime": path.stat().st_mtime_ns, "title": title, "sections": sections,
        "numbered": any(s["number"] for s in sections),
    }


def scan_repo(name: str, path: Path) -> list[dict]:
    """Every *.md under `path`, minus EXCLUDED_DIRS and dot-directories, sorted by relative path."""
    path = Path(path)
    docs = []
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if not _skip_dir(d))
        for f in files:
            if f.lower().endswith(".md"):
                p = Path(root) / f
                rel = p.relative_to(path).as_posix()
                docs.append(read_document(name, p, rel))
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


def _row(id, kind, level, title, *, number="", has_children=False, expanded=False, key="", ordinal=-1, count=0, column=False):
    return {"id": id, "kind": kind, "level": level, "title": title, "number": number, "hasChildren": has_children,
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
    """Spec §2: every word must occur in the document name or in a heading's number+title, case-insensitively.
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
from PySide6.QtGui import QTextDocument

from harness.notify import intent
from harness.qmodels import DictListModel

ROW_ROLES = ["id", "kind", "level", "title", "number", "hasChildren", "expanded", "key", "ordinal", "count", "column"]


def heading_positions(text: str) -> list[int]:
    """Character positions of the heading blocks Qt's markdown engine makes of `text` — the same engine
    TextArea uses in MarkdownText mode, so ordinal n here is ordinal n in the tab."""
    doc = QTextDocument()
    doc.setMarkdown(text)
    return _heading_positions_of(doc)


def _heading_positions_of(doc: QTextDocument) -> list[int]:
    out, block = [], doc.begin()
    while block.isValid():
        if block.blockFormat().headingLevel():
            out.append(block.position())
        block = block.next()
    return out


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
        self._model = DictListModel(ROW_ROLES, self)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.rescan)

    def start(self, interval_ms: int):
        self.rescan()
        self._timer.start(interval_ms)

    # ---------------------------------------------------------------- corpus
    def rescan(self) -> bool:
        """Re-list every registered repo; re-read the files whose mtime changed. True when anything changed."""
        old = {d["key"]: d for d in self._docs}
        new: list[dict] = []
        changed = False
        for rec in self._ws.repos:
            if self._ws.repo_status(rec["name"]) != "ok":
                continue
            path = Path(self._ws.repo_path(rec))
            for root, dirs, files in os.walk(path):
                dirs[:] = sorted(d for d in dirs if not _skip_dir(d))
                for f in files:
                    if not f.lower().endswith(".md"):
                        continue
                    p = Path(root) / f
                    rel = p.relative_to(path).as_posix()
                    key = f"{rec['name']}/{rel}"
                    prev = old.get(key)
                    try:
                        mtime = p.stat().st_mtime_ns
                    except OSError:
                        continue
                    if prev and prev["mtime"] == mtime:
                        new.append(prev)
                    else:
                        try:
                            doc = read_document(rec["name"], p, rel)
                        except OSError:
                            # vanished or was mid-write between the stat above and this read; skip it for
                            # this scan and let the next one pick it up (or drop it, if it's really gone)
                            changed = True
                            continue
                        new.append(doc)
                        changed = True
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
        self._model.reset(build_rows(self._docs, self._expanded))

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
