# Documents Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A left-dock **Documents** panel that maps every markdown document in the workspace's registered repos as a tree of sections, follows the reader's position in a new read-only markdown tab, and filters by heading as you type.

**Architecture:** `harness/documents.py` holds a pure parser (`parse_headings`), a pure corpus/tree layer (`scan_repo`, `build_rows`, `search`) and `DocumentsStore`, a hot-reloadable QObject exposed as `app.documents` that owns the corpus, a rescan timer, the expansion set and per-document reading positions, and feeds a flat `DictListModel` of *visible* rows. `qml/content/Documents.qml` is a `ListView` over that model (tree mode) or over `search()` results (filter mode). `qml/content/Document.qml` becomes a read-only `TextArea` in markdown mode that scrolls to a section on request and reports the current section back as the reader scrolls. The layout gains an invariant that every registered panel kind sits in some dock.

**Tech Stack:** Python 3.10+, PySide6 6.11 (QtCore, QtGui `QTextDocument`, QtQuick `QQuickTextDocument`), Qt Quick Controls Basic, pytest offscreen via `tests/ui.py`. Test runner: `~/.venvs/mh-conda/bin/python -m pytest` with `QT_QPA_PLATFORM=offscreen`.

**Spec:** `docs/superpowers/proposals/2026-09-03-documents-panel.md` (mockups `docs/design/mockups/07-documents.html`, `08-documents-1to1.html`).

## Global Constraints

- No backward compatibility (DESIGN §0): no migrations, no aliases; a saved session gains the panel through the layout invariant (spec §2), nothing else.
- Every interactive QML control gets a stable `objectName` (README "Test"); names in this plan: `stripButton_documents`, `docRow_<id>`, `docChevron_<id>`, `docFilter`, `docCollapseAll`, `docResult_<key>#<index>`, `docEmpty`, `documentView`, `tab_document_<key>`.
- Every QML-facing mutation is an `@intent` (`harness/notify.py`).
- No static explanatory copy in the UI: labels, placeholders, and one empty-state line only (spec §1: "No markdown documents in the registered repos.").
- Row ids (spec §3): `<repo>` repo, `<repo>/<dir>` directory, `<key>` document, `<key>#<index>` section; `key = <repo>/<rel path with forward slashes>`.
- Section `index` is the heading's ordinal among **all** headings of the document, title heading included, because the tab locates a heading by its ordinal among Qt's heading blocks (spec §3 "Parsing", §4).
- Excluded directories when scanning: `.git`, `.zharn`, any name starting with `.`, `node_modules`, `.venv`, `venv`, `__pycache__`.
- Config knob: `DOCS_RESCAN_MS = 2000` in `harness/config_def.py`.
- Theme metrics from `app.theme`: rows are `rowHeight` (24) tall; indent 18 px per level from a 10 px left margin; number column 24 px wide, mono, right-aligned.
- Commit after every task; messages in the repo's style (a sentence, present tense, what changed and why).

---

## File map

| file | responsibility |
|---|---|
| `harness/documents.py` (new) | `parse_headings`, `split_number`, `title_and_sections`, `scan_repo`, `build_rows`, `search`, `DocumentsStore` |
| `harness/config_def.py` | `DOCS_RESCAN_MS` |
| `harness/content.py` | `documents` panel kind; `document` icon |
| `harness/layout.py` | `Layout.ensure_panels`; default left dock gains `documents` |
| `harness/store.py` | `LayoutStore(session, panel_kinds)`; `AppStore.documents` |
| `harness/__main__.py` | build order (content before layout), construct `DocumentsStore`, start its timer |
| `harness/shell.py` | `harness.documents` in `RELOADABLE` |
| `qml/icons/documents.svg` (new) | strip/tab icon |
| `qml/content/Documents.qml` (new) | the panel |
| `qml/content/Document.qml` | the markdown tab |
| `tests/test_documents.py` (new) | parser, corpus, rows, search, store, Qt heading invariant |
| `tests/test_layout.py` | `ensure_panels` |
| `tests/test_ui_documents.py` (new) | panel and tab through the real QML |
| `docs/DESIGN.md`, `README.md` | present-tense revision when it lands |

---

### Task 1: The heading parser

**Files:**
- Create: `harness/documents.py`
- Test: `tests/test_documents.py`

**Interfaces:**
- Produces: `parse_headings(text: str) -> list[dict]` — every heading in source order as `{"index": int, "level": int, "number": str, "title": str, "line": int}` (`line` is 0-based; `number` is `""` when the heading is not numbered; `title` has the number stripped).
- Produces: `split_number(text: str) -> tuple[str, str]`.
- Produces: `title_and_sections(headings: list[dict]) -> tuple[str, list[dict]]` — spec §1's rule: when the first heading is the document's only H1 it is the title and not a section.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_documents.py
"""The Documents panel's backend (proposal 2026-09-03-documents-panel): heading parser, corpus scan, the
flat row view over an expansion set, search, and the store. No QML here; the UI is tests/test_ui_documents.py."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.documents import parse_headings, split_number, title_and_sections  # noqa: E402


def heads(text):
    return [(h["level"], h["number"], h["title"]) for h in parse_headings(text)]


def test_atx_headings_in_order_with_lines():
    hs = parse_headings("# T\n\ntext\n\n## A\n### A.1\n## B\n")
    assert [(h["index"], h["level"], h["title"], h["line"]) for h in hs] == [
        (0, 1, "T", 0), (1, 2, "A", 4), (2, 3, "A.1", 5), (3, 2, "B", 6)]


def test_headings_inside_fenced_code_are_not_headings():
    text = "# T\n```python\n# a comment\n## not a heading\n```\n## Real\n~~~\n# nope\n~~~\n"
    assert heads(text) == [(1, "", "T"), (2, "", "Real")]


def test_closing_fence_must_be_at_least_as_long():
    text = "````\n```\n# still code\n````\n# Out\n"
    assert heads(text) == [(1, "", "Out")]


def test_setext_headings():
    assert heads("Title\n=====\n\nSub\n---\n") == [(1, "", "Title"), (2, "", "Sub")]


def test_a_rule_after_a_blank_line_is_not_a_setext_heading():
    assert heads("para\n\n---\n# H\n") == [(1, "", "H")]


def test_trailing_hashes_and_indent_up_to_three_spaces():
    assert heads("   ## A ##\n    ## code, not heading\n") == [(2, "", "A")]


def test_numbers_split_off_the_title():
    assert split_number("4.6 Checks") == ("4.6", "Checks")
    assert split_number("2. Workspace") == ("2", "Workspace")
    assert split_number("10 Out of scope") == ("10", "Out of scope")
    assert split_number("Task 1: Parser") == ("", "Task 1: Parser")
    assert split_number("2026-09-03 plan") == ("", "2026-09-03 plan")
    assert heads("## 4.6 Checks\n") == [(2, "4.6", "Checks")]


def test_first_and_only_h1_is_the_title():
    title, secs = title_and_sections(parse_headings("# Doc\n## A\n## B\n"))
    assert title == "Doc" and [s["title"] for s in secs] == ["A", "B"]
    assert [s["index"] for s in secs] == [1, 2]


def test_several_h1s_are_all_sections_and_there_is_no_title():
    title, secs = title_and_sections(parse_headings("# Plan\n## Constraints\n# Task 1\n# Task 2\n"))
    assert title == "" and [s["title"] for s in secs] == ["Plan", "Constraints", "Task 1", "Task 2"]


def test_no_headings_at_all():
    assert title_and_sections(parse_headings("just text\n")) == ("", [])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_documents.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'harness.documents'`.

- [ ] **Step 3: Write the parser**

```python
# harness/documents.py
"""The Documents panel's backend (proposal docs/superpowers/proposals/2026-09-03-documents-panel.md):
a heading parser, the markdown corpus of the workspace's registered repos, the flat row view the panel
renders, heading search, and DocumentsStore — the QObject QML sees as `app.documents`."""
from __future__ import annotations

import re

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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_documents.py -q`
Expected: 10 passed. If `test_a_rule_after_a_blank_line_is_not_a_setext_heading` fails, `prev_blank` handling is wrong: a setext underline needs a non-blank paragraph line directly above it.

- [ ] **Step 5: Commit**

```bash
git add harness/documents.py tests/test_documents.py
git commit -m "Documents: the heading parser — ATX and setext outside fences, numbers split off, first-only-H1 is the title"
```

---

### Task 2: The corpus, the row view, and search

**Files:**
- Modify: `harness/documents.py`
- Test: `tests/test_documents.py`

**Interfaces:**
- Consumes: `parse_headings`, `title_and_sections` from Task 1.
- Produces: `EXCLUDED_DIRS: frozenset[str]`; `scan_repo(name: str, path: Path) -> list[dict]` — documents sorted by `rel`, each `{"key", "repo", "rel", "name", "path", "mtime", "title", "sections", "numbered"}` where `numbered` is `True` when any section has a number.
- Produces: `build_rows(docs: list[dict], expanded: set[str]) -> list[dict]` — the flat list of **visible** rows, each `{"id", "kind", "level", "title", "number", "hasChildren", "expanded", "key", "ordinal", "count", "column"}` (`ordinal` is the section's heading index; the row field is not called `index` because a QML delegate's `model.index` is the row number); `kind` in `repo|dir|doc|sec`; `count` is the document count on repo rows and `0` elsewhere; `column` is the document's `numbered` on `sec` rows.
- Produces: `all_row_ids(docs) -> list[str]` (every id, expanded or not, for `collapseAll` and `ensure_defaults`) and `default_expanded(docs) -> set[str]` (repo and directory ids).
- Produces: `ancestor_ids(doc: dict, index: int) -> list[str]` — the document id, then the ids of the sections that enclose section `index` (outermost first), for `expandTo`.
- Produces: `search(docs, query: str) -> list[dict]` — `[{"key", "name", "repo", "sections": [{"index", "number", "title"}]}]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_documents.py`:

```python
from harness.documents import (EXCLUDED_DIRS, all_row_ids, ancestor_ids, build_rows, default_expanded,  # noqa: E402
                               scan_repo, search)


def write(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def corpus(tmp_path):
    """A repo shaped like zharn's docs tree, plus things that must be skipped."""
    r = tmp_path / "zharn"
    write(r, "README.md", "# zharn\n## Run\n## Test\n")
    write(r, "CLAUDE.md", "# Working on zharn\n")
    write(r, "docs/DESIGN.md", "# design\n## 1. Stack\n")
    write(r, "docs/specs/workspace-model.md", "# Workspaces\n## 1. Concepts\n## 4. Environments\n### 4.1 Kinds\n### 4.6 Checks\n## 5. Stories\n")
    write(r, "docs/superpowers/plans/2026-09-03-environments.md", "# Plan\n## File map\n### Task 6: checks at handoff\n")
    write(r, "docs/empty/notes.txt", "not markdown")
    write(r, "node_modules/pkg/README.md", "# skip\n")
    write(r, ".zharn/stories/x.md", "# skip\n")
    write(r, ".hidden/x.md", "# skip\n")
    return r


def test_scan_finds_markdown_sorted_by_path_and_skips_excluded_dirs(corpus):
    docs = scan_repo("zharn", corpus)
    assert [d["rel"] for d in docs] == ["CLAUDE.md", "docs/DESIGN.md", "docs/specs/workspace-model.md",
                                        "docs/superpowers/plans/2026-09-03-environments.md", "README.md"]
    assert {"node_modules", ".zharn", ".venv", "venv", "__pycache__", ".git"} <= set(EXCLUDED_DIRS)
    wm = docs[2]
    assert wm["key"] == "zharn/docs/specs/workspace-model.md" and wm["name"] == "workspace-model"
    assert wm["title"] == "Workspaces" and wm["numbered"] is True
    assert [(s["index"], s["number"], s["title"]) for s in wm["sections"]] == [
        (1, "1", "Concepts"), (2, "4", "Environments"), (3, "4.1", "Kinds"), (4, "4.6", "Checks"), (5, "5", "Stories")]
    assert docs[4]["numbered"] is False


def test_default_expansion_is_repos_and_directories(corpus):
    docs = scan_repo("zharn", corpus)
    assert default_expanded(docs) == {"zharn", "zharn/docs", "zharn/docs/specs", "zharn/docs/superpowers/plans"}


def test_rows_compact_directories_and_order_dirs_before_docs(corpus):
    docs = scan_repo("zharn", corpus)
    rows = build_rows(docs, default_expanded(docs))
    assert [(r["kind"], r["level"], r["title"]) for r in rows] == [
        ("repo", 0, "zharn"),
        ("dir", 1, "docs"),
        ("dir", 2, "specs"),
        ("doc", 3, "workspace-model"),
        ("dir", 2, "superpowers/plans"),
        ("doc", 3, "2026-09-03-environments"),
        ("doc", 2, "DESIGN"),
        ("doc", 1, "CLAUDE"),
        ("doc", 1, "README"),
    ]
    assert rows[0]["count"] == 5 and rows[0]["hasChildren"] and rows[0]["expanded"]
    assert rows[3]["id"] == "zharn/docs/specs/workspace-model.md" and rows[3]["hasChildren"] and not rows[3]["expanded"]
    assert rows[4]["id"] == "zharn/docs/superpowers/plans"


def test_expanding_a_document_shows_its_top_sections_only(corpus):
    docs = scan_repo("zharn", corpus)
    key = "zharn/docs/specs/workspace-model.md"
    rows = build_rows(docs, default_expanded(docs) | {key})
    secs = [r for r in rows if r["kind"] == "sec"]
    assert [(r["level"], r["number"], r["title"], r["hasChildren"], r["column"]) for r in secs] == [
        (4, "1", "Concepts", False, True), (4, "4", "Environments", True, True), (4, "5", "Stories", False, True)]
    assert secs[1]["id"] == key + "#2" and secs[1]["key"] == key and secs[1]["ordinal"] == 2
    rows = build_rows(docs, default_expanded(docs) | {key, key + "#2"})
    assert [r["title"] for r in rows if r["kind"] == "sec"] == ["Concepts", "Environments", "Kinds", "Checks", "Stories"]
    assert [r["level"] for r in rows if r["title"] == "Kinds"] == [5]


def test_collapsed_repo_hides_everything_below_it(corpus):
    docs = scan_repo("zharn", corpus)
    assert [r["kind"] for r in build_rows(docs, set())] == ["repo"]


def test_ancestors_of_a_section(corpus):
    docs = scan_repo("zharn", corpus)
    wm = docs[2]
    assert ancestor_ids(wm, 4) == [wm["key"], wm["key"] + "#2"]
    assert ancestor_ids(wm, 1) == [wm["key"]]
    assert ancestor_ids(wm, -1) == [wm["key"]]


def test_all_row_ids_cover_repos_dirs_docs_and_sections(corpus):
    docs = scan_repo("zharn", corpus)
    ids = all_row_ids(docs)
    assert "zharn" in ids and "zharn/docs/superpowers/plans" in ids
    assert "zharn/docs/specs/workspace-model.md#2" in ids and "zharn/README.md" in ids


def test_search_groups_matching_sections_by_document_every_word_must_match(corpus):
    docs = scan_repo("zharn", corpus)
    groups = search(docs, "check")
    assert [(g["name"], g["repo"], [(s["index"], s["number"], s["title"]) for s in g["sections"]]) for g in groups] == [
        ("workspace-model", "zharn", [(4, "4.6", "Checks")]),
        ("2026-09-03-environments", "zharn", [(3, "", "Task 6: checks at handoff")]),
    ]
    assert search(docs, "checks handoff")[0]["sections"][0]["title"] == "Task 6: checks at handoff"
    assert len(search(docs, "checks handoff")) == 1
    assert search(docs, "4.6")[0]["sections"][0]["title"] == "Checks"      # the number counts as text


def test_search_matches_document_names_as_groups_without_sections(corpus):
    docs = scan_repo("zharn", corpus)
    assert [(g["name"], g["sections"]) for g in search(docs, "readme")] == [("README", [])]
    assert search(docs, "") == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_documents.py -q`
Expected: FAIL with `ImportError: cannot import name 'EXCLUDED_DIRS'`.

- [ ] **Step 3: Write the corpus, rows and search**

Append to `harness/documents.py`:

```python
import os
from pathlib import Path

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
```

Move the `import os` / `from pathlib import Path` lines to the top of the module with the other imports.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_documents.py -q`
Expected: 20 passed.

- [ ] **Step 5: Commit**

```bash
git add harness/documents.py tests/test_documents.py
git commit -m "Documents: the corpus of a repo, the flat row view over an expansion set, heading search"
```

---

### Task 3: `DocumentsStore` and its wiring

**Files:**
- Modify: `harness/documents.py`
- Modify: `harness/config_def.py` (after `WATCH_POLL_MS`)
- Modify: `harness/store.py:138-190` (`AppStore`)
- Modify: `harness/__main__.py:67-77`
- Modify: `harness/shell.py:25` (`RELOADABLE`)
- Test: `tests/test_documents.py`

**Interfaces:**
- Consumes: Task 2's functions; `harness.workspace.Workspace` (`.repos`, `.repo_path(rec)`, `.repo_status(name)`); `LayoutStore.openContent(kind, key, title)`; `harness.qmodels.DictListModel`.
- Produces: `DocumentsStore(workspace, layout_store, parent=None)` with
  - signals `documentsChanged()`, `positionChanged(str)`, `scrollRequested(str, int)`;
  - `rescan() -> bool` (True when anything changed), `start(interval_ms)`;
  - `documents() -> list[dict]`, `document(key) -> dict | None`;
  - `model` (Property, `DictListModel` of visible rows, roles `ROW_ROLES`);
  - `@Slot(result="QVariantList") rows()`;
  - intents `toggle(id)`, `collapseAll()`, `expandTo(key, index)`, `setPosition(key, index)`, `open(key, index=-1)`;
  - `@Slot(str, result=int) position(key)`, `@Slot(str, result=int) takeScroll(key)` (returns the pending index or `-2`);
  - `@Slot(str, result=str) text(key)`, `@Slot(str, result="QVariantList") search(query)`;
  - `@Slot(QObject, result="QVariantList") headingPositionsIn(qdoc)` — character positions of the heading blocks of a `QQuickTextDocument`;
  - `heading_positions(text) -> list[int]` (module function; the same walk over a `QTextDocument` built with `setMarkdown`).
- Produces: `AppStore.documents` property; `config.DOCS_RESCAN_MS`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_documents.py`:

```python
from PySide6.QtCore import QObject, Signal  # noqa: E402

from harness.documents import ROW_ROLES, DocumentsStore, heading_positions  # noqa: E402
from harness.workspace import Workspace  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class FakeLayout(QObject):
    """Records openContent calls; the real LayoutStore is exercised by the UI tests."""
    layoutChanged = Signal()

    def __init__(self):
        super().__init__()
        self.opened = []

    def openContent(self, kind, key, title, group_id=""):
        self.opened.append((kind, key, title))


@pytest.fixture
def store(tmp_path, corpus):
    ws = Workspace.create(tmp_path / "ws", name="W", prefix="W")
    ws.add_repo(corpus)
    layout = FakeLayout()
    s = DocumentsStore(ws, layout)
    s.rescan()
    s.layout = layout
    return s


def test_store_scans_registered_repos_and_fills_the_model(store):
    assert [d["repo"] for d in store.documents()][:1] == ["zharn"]
    assert store.model.count() == 9                      # Task 2's default rows
    assert store.model.roleNames() and set(ROW_ROLES) == {"id", "kind", "level", "title", "number", "hasChildren",
                                                         "expanded", "key", "ordinal", "count", "column"}
    assert store.document("zharn/README.md")["name"] == "README"
    assert store.text("zharn/README.md").startswith("# zharn")


def test_toggle_and_collapse_all(store):
    key = "zharn/docs/specs/workspace-model.md"
    store.toggle(key)
    assert [r["title"] for r in store.rows() if r["kind"] == "sec"] == ["Concepts", "Environments", "Stories"]
    store.toggle(key)
    assert not [r for r in store.rows() if r["kind"] == "sec"]
    store.collapseAll()
    assert [r["kind"] for r in store.rows()] == ["repo"]


def test_expand_to_a_section_opens_its_ancestors(store):
    key = "zharn/docs/specs/workspace-model.md"
    store.collapseAll()
    store.expandTo(key, 4)
    assert [r["title"] for r in store.rows() if r["kind"] == "sec"] == ["Concepts", "Environments", "Kinds", "Checks", "Stories"]


def test_open_opens_the_tab_expands_the_document_and_requests_a_scroll(store):
    key = "zharn/docs/specs/workspace-model.md"
    got = []
    store.scrollRequested.connect(lambda k, i: got.append((k, i)))
    store.open(key, 4)
    assert store.layout.opened == [("document", key, "workspace-model.md")]
    assert got == [(key, 4)] and store.takeScroll(key) == 4 and store.takeScroll(key) == -2
    assert any(r["id"] == key + "#4" for r in store.rows())
    store.open(key)
    assert got[-1] == (key, -1)


def test_set_position_records_it_and_expands_the_enclosing_section(store):
    key = "zharn/docs/specs/workspace-model.md"
    changed = []
    store.positionChanged.connect(changed.append)
    store.setPosition(key, 4)
    assert store.position(key) == 4 and changed == [key]
    assert any(r["id"] == key + "#4" for r in store.rows())
    store.setPosition(key, 0)                              # the title heading is not a section: the document row
    assert store.position(key) == -1
    assert store.position("zharn/nothing.md") == -1


def test_rescan_picks_up_an_edited_file_and_a_new_one(store, corpus):
    n = []
    store.documentsChanged.connect(lambda: n.append(1))
    assert store.rescan() is False
    write(corpus, "README.md", "# zharn\n## Run\n## Test\n## More\n")
    import os, time
    os.utime(corpus / "README.md", ns=(time.time_ns(), time.time_ns()))
    assert store.rescan() is True and len(n) == 1
    assert [s["title"] for s in store.document("zharn/README.md")["sections"]] == ["Run", "Test", "More"]
    write(corpus, "docs/new.md", "# New\n")
    assert store.rescan() is True
    assert store.document("zharn/docs/new.md")["title"] == "New"
    (corpus / "docs/new.md").unlink()
    assert store.rescan() is True and store.document("zharn/docs/new.md") is None


def test_search_goes_through_the_store(store):
    assert [g["name"] for g in store.search("check")] == ["workspace-model", "2026-09-03-environments"]


def test_a_missing_repo_is_skipped(tmp_path, corpus):
    ws = Workspace.create(tmp_path / "ws2", name="W", prefix="W")
    ws.add_repo(corpus)
    ws.add_repo(tmp_path / "gone", name="gone")
    s = DocumentsStore(ws, FakeLayout())
    s.rescan()
    assert {d["repo"] for d in s.documents()} == {"zharn"}


@pytest.mark.parametrize("path", sorted(p for p in ROOT.rglob("*.md") if ".git" not in p.parts and "_out" not in p.parts))
def test_parser_agrees_with_qt_about_which_blocks_are_headings(path):
    """Spec §3: a section's index is its ordinal among Qt's heading blocks — the tab relies on it."""
    text = path.read_text(encoding="utf-8")
    ours = [(h["level"], h["index"]) for h in parse_headings(text)]
    theirs = heading_positions(text)
    assert len(ours) == len(theirs), f"{path}: parsed {len(ours)} headings, Qt renders {len(theirs)}"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_documents.py -q`
Expected: FAIL with `ImportError: cannot import name 'ROW_ROLES'`.

- [ ] **Step 3: Write the store**

Append to `harness/documents.py`:

```python
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
                        new.append(read_document(rec["name"], p, rel))
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
```

The `expandTo` directory loop is deliberately simple: it walks every row id once and adds the directories whose compacted path prefixes the document's path. `Path` and `os` are already imported at the top of the module from Task 2.

- [ ] **Step 4: Add the config knob and wire the store**

`harness/config_def.py`, after `WATCH_POLL_MS = 250`:

```python
# The Documents panel re-lists the registered repos' *.md files this often (proposal 2026-09-03-documents-panel §3)
DOCS_RESCAN_MS = 2000
```

`harness/shell.py` `RELOADABLE`: insert `"harness.documents"` after `"harness.workspace_store"` (it imports notify and qmodels, both earlier in the list).

`harness/store.py` `AppStore.__init__`: add a keyword `documents=None`, store it as `self._documents`, and add the property next to `workspace`:

```python
    @Property(QObject, constant=True)
    def documents(self):
        return self._documents
```

`harness/__main__.py` in `build()`, after `workspace_store = WorkspaceStore(workspace, stories)`:

```python
    from harness.documents import DocumentsStore
    documents = DocumentsStore(workspace, layout_store)
    workspace_store.workspaceChanged.connect(documents.rescan)   # a repo registered or unregistered: rescan now
```

add `documents` to the `for s in (...)` notifier loop and pass `documents=documents` to `AppStore(...)`. After the IPC lines, start the timer:

```python
    documents.start(cfg.DOCS_RESCAN_MS)
```

(`cfg` is `harness.config` as `build()` already imports it.)

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_documents.py -q`
Expected: all pass, including one parametrized case per `*.md` in the repo. If a parametrized case fails, the parser and Qt disagree on that file: open it at the reported counts, find the construct (a heading inside a blockquote, a setext underline under a list item, a `#` line inside an indented code block…), and adjust `parse_headings` to match Qt. Never change the rule that index = Qt's ordinal.

Then the whole suite: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q -x` — the app still builds (`tests/test_app.py`) with the new store wired.

- [ ] **Step 6: Commit**

```bash
git add harness/documents.py harness/config_def.py harness/store.py harness/__main__.py harness/shell.py tests/test_documents.py
git commit -m "Documents: DocumentsStore on app.documents — corpus with a rescan timer, expansion and reading positions, open/scroll, search; the parser agrees with Qt's heading blocks over every doc in the repo"
```

---

### Task 4: The panel kind, its icon, and the layout invariant

**Files:**
- Modify: `harness/content.py:11-23`
- Create: `qml/icons/documents.svg`
- Modify: `harness/layout.py:40-48` (`default_layout`) and the `Layout` class
- Modify: `harness/store.py:32-40` (`LayoutStore.__init__`)
- Modify: `harness/__main__.py:67-68`
- Test: `tests/test_layout.py`, `tests/test_icons.py` (only if it enumerates icons — read it first)

**Interfaces:**
- Produces: `Layout.ensure_panels(kinds: list[str]) -> bool` (True when it added any); `LayoutStore(session, panel_kinds=())`; content kind `documents`; icon name `documents`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_layout.py`:

```python
def test_default_left_dock_carries_documents_between_files_and_git():
    assert Layout().data["docks"]["left"]["panels"] == ["board", "files", "documents", "git"]


def test_ensure_panels_adds_a_kind_missing_from_every_dock_to_the_left_dock():
    l = Layout()
    l.data["docks"]["left"]["panels"] = ["board", "files", "git"]
    assert l.ensure_panels(["board", "files", "git", "documents", "cast", "contexts", "terminal"]) is True
    assert l.data["docks"]["left"]["panels"] == ["board", "files", "git", "documents"]
    assert l.ensure_panels(["board", "documents"]) is False          # already reachable: nothing to do


def test_ensure_panels_never_moves_a_panel_that_lives_elsewhere():
    l = Layout()
    l.ensure_panels(["cast"])
    assert "cast" not in l.data["docks"]["left"]["panels"] and "cast" in l.data["docks"]["right"]["panels"]


def test_ensure_panels_gives_an_empty_left_dock_an_active_panel():
    l = Layout()
    l.data["docks"]["left"] = {"panels": [], "active": None, "mode": "strip", "size": 290}
    l.ensure_panels(["documents"])
    assert l.data["docks"]["left"]["active"] == "documents"
```

And in `tests/test_documents.py` (it imports `KINDS` already through `harness.content` in Task 3? no — add):

```python
from harness.content import KINDS  # noqa: E402


def test_documents_is_a_panel_kind_and_the_document_tab_shares_its_icon():
    assert KINDS["documents"] == {"title": "Documents", "qml": "content/Documents.qml", "panel": True, "icon": "documents"}
    assert KINDS["document"]["icon"] == "documents"
    assert (ROOT / "qml/icons/documents.svg").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_layout.py tests/test_documents.py -q -k "documents or ensure_panels"`
Expected: FAIL (`AttributeError: 'Layout' object has no attribute 'ensure_panels'`, `KeyError: 'documents'`).

- [ ] **Step 3: Implement**

`harness/content.py`: in `KINDS`, after the `files` line:

```python
    "documents": {"title": "Documents", "qml": "content/Documents.qml", "panel": True,  "icon": "documents"},
```

and change the `document` line's icon to `"documents"`.

`qml/icons/documents.svg` (same stroke conventions as `qml/icons/story.svg`; `harness/icons.py` recolours `currentColor`):

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 2.5h5.5L13 6v7.5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1z"/><path d="M9.5 2.5V6H13M5.5 9h5M5.5 11.5h3.5"/></svg>
```

`harness/layout.py`: `default_layout()` left panels become `["board", "files", "documents", "git"]`. Add to `Layout`, after `find_tab`:

```python
    def ensure_panels(self, kinds) -> bool:
        """Every registered panel kind sits in some dock — a fork's new panel, or one added upstream, shows on
        the left strip of a saved layout without a reset. An invariant, not a migration."""
        placed = {p for d in self.data["docks"].values() for p in d["panels"]}
        missing = [k for k in kinds if k not in placed]
        if not missing:
            return False
        left = self.data["docks"]["left"]
        left["panels"].extend(missing)
        if left.get("active") is None:
            left["active"] = left["panels"][0]
        return True
```

`harness/store.py` `LayoutStore.__init__(self, session, panel_kinds=())`: after constructing `self._layout`, `if self._layout.ensure_panels(list(panel_kinds)): self._session.data["layout"] = self._layout.data` (no save yet; the next commit saves).

`harness/__main__.py`: construct `content = ContentRegistry(QML_DIR)` **before** `layout_store`, then `layout_store = LayoutStore(session, content.panelKinds())`.

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_layout.py tests/test_documents.py tests/test_icons.py tests/test_ui_chrome.py -q`
Expected: all pass. `test_ui_chrome` still finds `stripButton_files` and the docks; if a chrome test asserts the exact left panel list, update it to include `documents`.

- [ ] **Step 5: Commit**

```bash
git add harness/content.py qml/icons/documents.svg harness/layout.py harness/store.py harness/__main__.py tests/test_layout.py tests/test_documents.py
git commit -m "Documents is a panel kind on the left strip; a layout places every registered panel kind somewhere, so saved sessions see it"
```

---

### Task 5: The Documents panel

**Files:**
- Create: `qml/content/Documents.qml`
- Test: `tests/test_ui_documents.py`

**Interfaces:**
- Consumes: `app.documents.model` (roles `id, kind, level, title, number, hasChildren, expanded, key, ordinal, count, column`), `app.documents.toggle(id)`, `collapseAll()`, `open(key, index)`, `position(key)`, `search(query)`, signals `documentsChanged`, `positionChanged(key)`; `app.layout.layoutJson` / `activeGroup` (as `StoryBoard.qml` reads them); `qml/ui/Icon.qml`, `IconButton.qml`, `Field.qml`.
- Produces: the object names in Global Constraints. The panel's root exposes `headerActions` (collapse-all) for `Dock.qml`.

- [ ] **Step 1: Write the failing UI tests**

```python
# tests/test_ui_documents.py
"""The Documents panel and the document tab through the real QML (proposal 2026-09-03-documents-panel):
the strip button, the section tree, opening a document or a section, the selection that follows the
reader, type-to-filter, collapse-all."""
import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from gitfix import make_repo
from ui import OUT, start, wait_until

SPEC = """# Workspaces

Intro paragraph.

## 1. Concepts

Some words about concepts.

## 4. Environments

### 4.1 Kinds

""" + ("Kinds text line.\n" * 60) + """
### 4.6 Checks

""" + ("Checks text line.\n" * 60) + """
## 5. Stories

Tail.
"""

KEY = "d/docs/specs/workspace-model.md"


@pytest.fixture(scope="module")
def ui():
    h = start("ui-documents")
    repo = OUT / "ui-documents-repo"
    shutil.rmtree(repo, ignore_errors=True)
    make_repo(repo)
    (repo / "docs/specs").mkdir(parents=True)
    (repo / "docs/specs/workspace-model.md").write_text(SPEC)
    (repo / "docs/guide.md").write_text("# Guide\n## Run\n## Test\n")
    h.store.workspace.register(str(repo), "d", "", "", "")
    h.store.documents.rescan()
    QTest.qWait(100)
    yield h
    h.shutdown()


def show(ui):
    if not ui.has("docRow_d"):
        ui.click(ui.find("stripButton_documents"))
        QTest.qWait(120)


def test_strip_button_shows_the_panel_with_the_repo_and_its_documents(ui):
    show(ui)
    assert ui.visible(ui.find("docRow_d"))
    assert ui.visible(ui.find("docRow_d/docs"))
    assert ui.visible(ui.find("docRow_d/docs/specs"))
    assert ui.visible(ui.find(r"docRow_d/docs/specs/workspace-model\.md"))
    assert ui.visible(ui.find(r"docRow_d/README\.md"))
    assert not ui.has("docEmpty")


def test_chevron_expands_a_document_into_numbered_sections_without_opening_it(ui):
    show(ui)
    ui.click(ui.find(r"docChevron_d/docs/specs/workspace-model\.md"))
    QTest.qWait(80)
    assert ui.visible(ui.find(r"docRow_d/docs/specs/workspace-model\.md#1"))    # 1 Concepts
    assert ui.visible(ui.find(r"docRow_d/docs/specs/workspace-model\.md#2"))    # 4 Environments
    assert not ui.has(r"docRow_d/docs/specs/workspace-model\.md#3")            # 4.1 Kinds is folded under 4
    assert not ui.has(f"tab_document_{KEY}")


def test_clicking_a_section_opens_the_tab_at_that_section_and_selects_its_row(ui):
    show(ui)
    ui.click(ui.find(r"docChevron_d/docs/specs/workspace-model\.md#2"))
    QTest.qWait(80)
    ui.click(ui.find(r"docRow_d/docs/specs/workspace-model\.md#4"))             # 4.6 Checks
    assert wait_until(lambda: ui.has(f"tab_document_{KEY}"))
    assert wait_until(lambda: ui.store.documents.position(KEY) == 4)
    assert ui.find(r"docRow_d/docs/specs/workspace-model\.md#4").property("selected") is True
    assert ui.find("documentView").property("text").startswith("# Workspaces")


def test_scrolling_the_tab_moves_the_selection(ui):
    show(ui)
    flick = ui.find("documentFlick")
    flick.setProperty("contentY", 0)
    assert wait_until(lambda: ui.store.documents.position(KEY) == -1)
    assert ui.find(r"docRow_d/docs/specs/workspace-model\.md").property("selected") is True


def test_clicking_a_document_opens_it_at_the_top(ui):
    show(ui)
    ui.click(ui.find(r"docRow_d/docs/guide\.md"))
    assert wait_until(lambda: ui.has("tab_document_d/docs/guide\\.md"))
    assert wait_until(lambda: ui.store.documents.position("d/docs/guide.md") == -1)
    assert ui.visible(ui.find(r"docRow_d/docs/guide\.md#1"))                    # Run, no number column


def test_typing_filters_to_matching_sections_grouped_by_document_and_escape_clears(ui):
    show(ui)
    ui.find("docTree").forceActiveFocus()
    ui.type("check")
    QTest.qWait(80)
    assert ui.find("docFilter").property("text") == "check"
    assert ui.visible(ui.find(f"docResult_{KEY}#4"))
    assert not ui.has(r"docRow_d/docs/guide\.md")
    ui.click(ui.find(f"docResult_{KEY}#4"))
    assert wait_until(lambda: ui.store.documents.position(KEY) == 4)
    ui.find("docFilter").forceActiveFocus()
    ui.key(Qt.Key.Key_Escape)
    QTest.qWait(80)
    assert not ui.find("docFilter").isVisible()
    assert ui.visible(ui.find(r"docRow_d/docs/guide\.md"))


def test_collapse_all_leaves_the_repo_rows(ui):
    show(ui)
    ui.click(ui.find("docCollapseAll"))
    QTest.qWait(80)
    assert ui.visible(ui.find("docRow_d")) and not ui.has("docRow_d/docs")
    ui.click(ui.find("docChevron_d"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_ui_documents.py -q -x`
Expected: the first test fails (`expected exactly one visible 'docRow_d'`) — the strip button exists (Task 4) but the panel is `Missing.qml`.

- [ ] **Step 3: Write the panel**

```qml
// qml/content/Documents.qml
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../ui"

// Documents: the workspace's markdown as a tree of sections (proposal 2026-09-03-documents-panel).
// Rows come flat from app.documents.model (expansion lives in Python); the selected row is the current
// section of the active document tab; typing filters by heading into a results list.
ContentBase {
    id: panel
    property string filter: ""
    property var results: []
    property string activeKey: ""
    property int position: -1
    readonly property bool filtering: filter.length > 0

    property Component headerActions: Component {
        IconButton { objectName: "docCollapseAll"; icon: "collapse"; tip: "Collapse all"; onClicked: app.documents.collapseAll() }
    }

    // the document of the active editor tab, if it is one
    function readActive() {
        var tree = JSON.parse(app.layout.layoutJson), gid = app.layout.activeGroup
        function find(node) {
            if (!node) return null
            if (node.type === "tabs") return node.id === gid ? node : null
            for (var i = 0; i < node.children.length; i++) { var f = find(node.children[i]); if (f) return f }
            return null
        }
        var g = find(tree.center)
        var t = g && g.tabs.length ? g.tabs[g.active] : null
        activeKey = t && t.kind === "document" ? t.key : ""
        position = activeKey ? app.documents.position(activeKey) : -1
        reveal()
    }
    function reveal() {   // keep the selected row in view
        for (var i = 0; i < tree.count; i++) {
            var r = app.documents.model.get(i)
            if (r.key === activeKey && (r.kind === "sec" ? r.ordinal === position : r.kind === "doc" && position < 0)) { tree.positionViewAtIndex(i, ListView.Contain); return }
        }
    }
    function refreshResults() { results = filtering ? app.documents.search(filter) : [] }
    function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") }
    function highlight(text) {   // every filter word, bold in the accent
        var out = esc(text), words = filter.toLowerCase().split(/\s+/).filter(function (w) { return w })
        for (var i = 0; i < words.length; i++) {
            var re = new RegExp("(" + words[i].replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig")
            out = out.replace(re, '<b><font color="' + app.theme.accentHover + '">$1</font></b>')
        }
        return out
    }
    Component.onCompleted: readActive()
    onFilterChanged: refreshResults()
    Connections { target: app.layout; function onLayoutChanged() { panel.readActive() } }
    Connections {
        target: app.documents
        function onDocumentsChanged() { panel.refreshResults(); panel.reveal() }
        function onPositionChanged(key) { if (key === panel.activeKey) { panel.position = app.documents.position(key); panel.reveal() } }
    }

    ColumnLayout {
        anchors.fill: parent; spacing: 0
        Field {
            id: filterField
            objectName: "docFilter"
            Layout.fillWidth: true; Layout.margins: 8; Layout.topMargin: 4; Layout.bottomMargin: 4
            implicitHeight: 26
            visible: panel.filtering || activeFocus
            onTextEdited: panel.filter = text
            Keys.onEscapePressed: { text = ""; panel.filter = ""; tree.forceActiveFocus() }
            Keys.onDownPressed: { if (panel.filtering) resultsView.forceActiveFocus() }
        }

        // ---- the tree
        ListView {
            id: tree
            objectName: "docTree"
            Layout.fillWidth: true; Layout.fillHeight: true
            visible: !panel.filtering
            clip: true; model: app.documents.model
            topMargin: 4; bottomMargin: 4
            keyNavigationEnabled: true
            ScrollBar.vertical: ScrollBar {}
            Keys.onPressed: function (event) {
                var r = currentIndex >= 0 ? app.documents.model.get(currentIndex) : null
                if (event.text.length === 1 && event.text >= " " && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier))) {
                    filterField.text = event.text; panel.filter = event.text; filterField.forceActiveFocus(); filterField.cursorPosition = 1; event.accepted = true
                } else if (r && event.key === Qt.Key_Right && r.hasChildren && !r.expanded) { app.documents.toggle(r.id); event.accepted = true }
                else if (r && event.key === Qt.Key_Left && r.expanded) { app.documents.toggle(r.id); event.accepted = true }
                else if (r && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) {
                    if (r.kind === "doc" || r.kind === "sec") app.documents.open(r.key, r.ordinal); else app.documents.toggle(r.id)
                    event.accepted = true
                }
            }
            delegate: Rectangle {
                id: row
                required property int index
                required property var model
                readonly property bool selected: model.key === panel.activeKey && model.kind !== "repo" && model.kind !== "dir"
                                                 && (model.kind === "sec" ? model.ordinal === panel.position : panel.position < 0)
                objectName: "docRow_" + model.id
                width: tree.width; height: app.theme.rowHeight
                color: selected ? app.theme.selection : (rh.hovered ? app.theme.hover : "transparent")
                RowLayout {
                    anchors { fill: parent; leftMargin: 10 + 18 * row.model.level; rightMargin: 10 }
                    spacing: 6
                    Item {   // the chevron column: kept for leaves so siblings align
                        objectName: "docChevron_" + row.model.id
                        width: 14; height: 14
                        Icon { anchors.fill: parent; visible: row.model.hasChildren; name: row.model.expanded ? "down" : "right"; size: 14; color: app.theme.textDim }
                        TapHandler { enabled: row.model.hasChildren; onTapped: app.documents.toggle(row.model.id) }
                    }
                    Text {
                        visible: row.model.kind === "sec" && row.model.column
                        text: row.model.number; width: 24; horizontalAlignment: Text.AlignRight
                        font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize
                        color: row.selected ? "#b7c9f2" : app.theme.textMuted
                        Layout.preferredWidth: 24
                    }
                    Text {
                        text: row.model.title; elide: Text.ElideRight; Layout.fillWidth: true
                        color: row.model.kind === "dir" ? app.theme.textMuted : app.theme.text
                        font.pixelSize: app.theme.fontSize
                        font.weight: row.model.kind === "repo" ? Font.DemiBold
                                   : (row.model.kind === "doc" && app.layout.layoutJson.indexOf('"key": "' + row.model.key + '"') >= 0 ? Font.Medium : Font.Normal)
                    }
                    Text { visible: row.model.kind === "repo"; text: row.model.count; color: app.theme.textMuted; font.pixelSize: app.theme.fontSize }
                }
                HoverHandler { id: rh }
                TapHandler {
                    onTapped: {
                        tree.currentIndex = row.index
                        if (row.model.kind === "doc" || row.model.kind === "sec") app.documents.open(row.model.key, row.model.ordinal)
                        else app.documents.toggle(row.model.id)
                    }
                }
            }
            Text {
                objectName: "docEmpty"
                visible: tree.count === 0
                anchors { top: parent.top; topMargin: 40; horizontalCenter: parent.horizontalCenter }
                width: parent.width - 40; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                text: "No markdown documents in the registered repos."; color: app.theme.textMuted
            }
        }

        // ---- filter results: sections grouped by document, titles wrap
        ListView {
            id: resultsView
            objectName: "docResults"
            Layout.fillWidth: true; Layout.fillHeight: true
            visible: panel.filtering
            clip: true; topMargin: 4
            ScrollBar.vertical: ScrollBar {}
            model: panel.results
            delegate: Column {
                id: group
                required property var modelData
                width: resultsView.width
                Rectangle {
                    objectName: "docResult_" + group.modelData.key
                    width: parent.width; height: app.theme.rowHeight
                    color: gh.hovered ? app.theme.hover : "transparent"
                    RowLayout {
                        anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                        Text { textFormat: Text.RichText; text: panel.highlight(group.modelData.name); color: app.theme.text; font.weight: Font.Medium; elide: Text.ElideRight; Layout.fillWidth: true }
                        Text { text: group.modelData.repo; color: app.theme.textDim; font.pixelSize: app.theme.fontSizeSmall }
                    }
                    HoverHandler { id: gh }
                    TapHandler { onTapped: app.documents.open(group.modelData.key, -1) }
                }
                Repeater {
                    model: group.modelData.sections
                    delegate: Rectangle {
                        id: hit
                        required property var modelData
                        objectName: "docResult_" + group.modelData.key + "#" + modelData.index
                        width: group.width; height: Math.max(app.theme.rowHeight, hitText.implicitHeight + 8)
                        color: hh.hovered ? app.theme.hover : "transparent"
                        RowLayout {
                            anchors { fill: parent; leftMargin: 28; rightMargin: 10; topMargin: 4; bottomMargin: 4 }
                            spacing: 6
                            Text { visible: hit.modelData.number.length > 0; text: hit.modelData.number; Layout.preferredWidth: 24; horizontalAlignment: Text.AlignRight
                                   font.family: app.theme.monoFamily; font.pixelSize: app.theme.monoSize; color: app.theme.textMuted; Layout.alignment: Qt.AlignTop }
                            Text { id: hitText; textFormat: Text.RichText; text: panel.highlight(hit.modelData.title); wrapMode: Text.Wrap
                                   color: app.theme.text; Layout.fillWidth: true }
                        }
                        HoverHandler { id: hh }
                        TapHandler { onTapped: app.documents.open(group.modelData.key, hit.modelData.index) }
                    }
                }
            }
        }
    }
}
```

Notes for the implementer:
- `app.documents.model.get(i)` is `DictListModel.get` (`harness/qmodels.py`), a slot returning the row map.
- The document-open weight test (`layoutJson.indexOf`) is a cheap string probe over the layout JSON; it is fine for a tab list this size.
- The chevron `Item` carries `docChevron_<id>` so tests can click its centre; the handler inside it does the toggle.
- The filter field is not bound to `panel.filter`: the tree seeds it with the first typed character, edits flow back through `onTextEdited`, and Esc clears both.
- Field's `implicitHeight` override makes the filter 26 px as in the mockup.

- [ ] **Step 4: Run the panel tests**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_ui_documents.py -q -x -k "strip or chevron or collapse or typing"`
Expected: `strip`, `chevron`, `collapse` pass. `typing` passes for the results and Esc part; if its `open` assertion (`position(KEY) == 4`) fails, that is Task 6's tab — skip it for now with `-k "not typing"` and return after Task 6.

- [ ] **Step 5: Commit**

```bash
git add qml/content/Documents.qml tests/test_ui_documents.py
git commit -m "Documents panel: the section tree over app.documents, the selection that follows the active document, type-to-filter into grouped results, collapse-all"
```

---

### Task 6: The document tab

**Files:**
- Modify: `qml/content/Document.qml` (replace the stub)
- Test: `tests/test_ui_documents.py` (written in Task 5)

**Interfaces:**
- Consumes: `app.documents.text(key)`, `headingPositionsIn(textDocument)`, `takeScroll(key)`, `setPosition(key, index)`, signals `scrollRequested(key, index)`, `documentsChanged()`.
- Produces: object names `documentView` (the `TextArea`), `documentFlick` (the `Flickable`).

- [ ] **Step 1: Run the tab tests to see them fail**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_ui_documents.py -q -k "section or scrolling or document_opens or typing"`
Expected: FAIL — `documentView` not found; `position(KEY)` stays -1.

- [ ] **Step 2: Write the tab**

```qml
// qml/content/Document.qml
import QtQuick
import QtQuick.Controls.Basic
import ".."

// A markdown document, read-only (proposal 2026-09-03-documents-panel §4; DESIGN §5's read-mostly viewer).
// Scrolls to a section on app.documents.scrollRequested and reports the topmost heading back as the
// reader scrolls, which is what the Documents panel selects.
ContentBase {
    id: page
    readonly property string key: tabKey
    property var positions: []      // character position of heading n in the rendered document
    property string loaded: ""
    property int pending: -2        // a requested section (-1 = top), -2 = none

    function load() {
        var t = app.documents.text(key)
        if (t === loaded) return
        var y = flick.contentY
        loaded = t
        view.text = t
        positions = app.documents.headingPositionsIn(view.textDocument)
        flick.contentY = Math.min(y, Math.max(0, flick.contentHeight - flick.height))
    }
    function yOf(i) { return view.y + view.positionToRectangle(positions[i]).y }
    function scrollTo(i) {
        var y = i < 0 || i >= positions.length ? 0 : yOf(i)
        flick.contentY = Math.max(0, Math.min(y, flick.contentHeight - flick.height))
        report()
    }
    function report() {
        var cur = -1
        for (var i = 0; i < positions.length; i++) if (yOf(i) <= flick.contentY + 1) cur = i
        app.documents.setPosition(key, cur)
    }
    Component.onCompleted: { load(); settle.start() }
    // Every scroll request lands here after the text is laid out, whether it arrived as a signal (tab already
    // open) or was left pending in the store (tab created by the open).
    Timer {
        id: settle; interval: 0
        onTriggered: {
            var i = page.pending !== -2 ? page.pending : app.documents.takeScroll(page.key)
            page.pending = -2
            if (i !== -2) page.scrollTo(i); else page.report()
        }
    }
    Timer { id: reportTimer; interval: 16; onTriggered: page.report() }
    Connections {
        target: app.documents
        function onScrollRequested(k, i) { if (k === page.key) { app.documents.takeScroll(k); page.pending = i; settle.restart() } }
        function onDocumentsChanged() { page.load() }
    }

    Flickable {
        id: flick
        objectName: "documentFlick"
        anchors.fill: parent; clip: true
        contentWidth: width; contentHeight: view.y + view.implicitHeight + 40
        onContentYChanged: reportTimer.restart()
        ScrollBar.vertical: ScrollBar {}
        TextArea {
            id: view
            objectName: "documentView"
            x: 28; y: 20
            width: Math.min(flick.width - 56, 820)
            readOnly: true; selectByMouse: true
            textFormat: TextEdit.MarkdownText; wrapMode: TextEdit.Wrap
            color: app.theme.text; selectionColor: app.theme.selection
            font.family: app.theme.fontFamily; font.pixelSize: app.theme.fontSize
            background: null; padding: 0
        }
    }
}
```

Notes:
- `positionToRectangle` is valid once the `TextArea` has laid out its text; `settle` (a 0 ms timer) runs after that, which is why every scroll request is applied there and not in `onCompleted` or the signal handler.
- Heading sizes, code styling and rules are Qt's markdown defaults (spec §4 as amended); do not fight them here.
- Reloading on `documentsChanged` compares the text so unrelated rescans do not reset the view.

- [ ] **Step 3: Run the whole documents suite**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_ui_documents.py -q`
Expected: 7 passed. If `test_scrolling_the_tab_moves_the_selection` is flaky, the report timer fired before the flick settled: raise the `wait_until` timeout in the test rather than the timer interval.

Then everything: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q`
Expected: all green.

- [ ] **Step 4: Look at it**

Run: `HARNESS_EXIT_AFTER_MS=4000 HARNESS_SCREENSHOT=/tmp/docs.png QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m harness` from the repo root, then open `/tmp/docs.png`: the left strip has the Documents icon between Files and Git; clicking is not possible in a screenshot, so also open `Documents` through a seed: in a Python shell, `build()` + `reloader.load()`, `store.layout.showPanel("documents")`, `store.documents.open("<key>", 3)`, `win.grabWindow().save(...)`. The map must show the repo, `docs`, the document expanded, and the section row selected while the tab shows that heading at the top. Delete the PNG afterwards.

- [ ] **Step 5: Commit**

```bash
git add qml/content/Document.qml tests/test_ui_documents.py
git commit -m "Document tab: read-only markdown that scrolls to a section on request and reports the topmost heading to the Documents panel"
```

---

### Task 7: The docs say what the program is

**Files:**
- Modify: `docs/DESIGN.md:113-124` (§3a default layout and component list), `docs/DESIGN.md` §5 (editor line), `docs/DESIGN.md` §8 status line
- Modify: `README.md` (the UI paragraph naming the tool windows)

- [ ] **Step 1: Revise DESIGN §3a**

In the "Look: JetBrains New UI" bullet, the default layout sentence becomes: `Default layout: left Stories · Files · Documents · Git, right Cast (follows the active story tab), bottom Contexts · Terminal; …`. Add one sentence after the components list: `The Documents tool window maps every markdown document in the registered repos as a tree of sections — the row is the heading, the selection follows the active document tab's reading position, and typing filters by heading (proposal docs/superpowers/proposals/2026-09-03-documents-panel.md until it graduates to a spec).` Add `documents` to the §3a dock panel list ("board, contexts …, git status, filesystem, **documents**, terminal …").

- [ ] **Step 2: Revise DESIGN §5**

The Editor line becomes: `* **Editor**: v1 is a read-only markdown tab (`TextArea` in markdown mode, opened from the Documents tool window) and, later, a diff/file viewer with a `QSyntaxHighlighter`; real editing stays in your $EDITOR. …` (keep the KTextEditor/QScintilla sentence).

- [ ] **Step 3: Status line in §8**

Prepend to the status block: `Status 2026-09-03 (later): Documents tool window and the read-only document tab (plan docs/superpowers/plans/2026-09-03-documents-panel.md); the layout places every registered panel kind.`

- [ ] **Step 4: README**

In the paragraph "The UI follows JetBrains' New UI conventions…", after "a Stories tree on the left", add ", a Documents map of the repos' markdown next to it".

- [ ] **Step 5: Commit**

```bash
git add docs/DESIGN.md README.md
git commit -m "DESIGN/README: the Documents tool window and the read-only document tab, in the present tense"
```

---

## Self-review

**Spec coverage.** §1 rows/ordering/compaction/sections/numbering → Tasks 1–2, rendered in Task 5; typography and header → Task 5; empty state → Task 5 (`docEmpty`). §2 follow-the-reader → Tasks 3 (`setPosition`, `expandTo`, `open`) and 6; type-to-filter with wrapping grouped results → Task 5; every-panel-reachable → Task 4. §3 store surface → Task 3 (all listed names present); §3 freshness timer and `workspaceChanged` hook → Task 3 step 4; the Qt heading invariant → Task 3's parametrized test. §4 tab → Task 6. §5 registration, icon, default layout, object names, keyboard → Tasks 4–5. §6 tests → Tasks 1–6. §7 out of scope untouched. §8 docs → Task 7.

**Placeholders.** None: every step carries its code or exact edit. The one open-ended instruction is the invariant test's "adjust the parser to match Qt", which is the test's purpose.

**Type consistency.** `rows()` rows carry `id, kind, level, title, number, hasChildren, expanded, key, ordinal, count, column` in Task 2, `ROW_ROLES` in Task 3, and the delegate in Task 5. `open(key, index=-1)`, `takeScroll(key) -> int | -2`, `setPosition(key, index)`, `position(key)`, `headingPositionsIn(qdoc)`, `search(query)` are named the same in Tasks 3, 5 and 6. `ensure_panels` / `LayoutStore(session, panel_kinds)` match between Task 4's tests and code. The `d` repo name and `KEY` in the UI tests match `register(str(repo), "d", …)`.
