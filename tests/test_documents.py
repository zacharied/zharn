"""The Documents panel's backend (spec docs/specs/documents-panel.md): the headings Qt makes of a
document, corpus scan, the flat row view over an expansion set, search, and the store. No QML here; the
UI is tests/test_ui_documents.py."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.documents import headings_of, heading_positions, split_number, title_and_sections  # noqa: E402


def heads(text):
    return [(h["level"], h["number"], h["title"]) for h in headings_of(text)]


def test_headings_in_order_with_their_ordinal():
    hs = headings_of("# T\n\ntext\n\n## A\n### A.1\n## B\n")
    assert [(h["index"], h["level"], h["title"]) for h in hs] == [
        (0, 1, "T"), (1, 2, "A"), (2, 3, "A.1"), (3, 2, "B")]


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
    title, secs = title_and_sections(headings_of("# Doc\n## A\n## B\n"))
    assert title == "Doc" and [s["title"] for s in secs] == ["A", "B"]
    assert [s["index"] for s in secs] == [1, 2]


def test_several_h1s_are_all_sections_and_there_is_no_title():
    title, secs = title_and_sections(headings_of("# Plan\n## Constraints\n# Task 1\n# Task 2\n"))
    assert title == "" and [s["title"] for s in secs] == ["Plan", "Constraints", "Task 1", "Task 2"]


def test_no_headings_at_all():
    assert title_and_sections(headings_of("just text\n")) == ("", [])


# What Qt's markdown engine does with the shapes a hand-written parser gets wrong. These are not our
# rules — they are the renderer's, pinned so a Qt upgrade that moves a heading (and so every ordinal
# the document tab scrolls by) fails here rather than in the panel.
HARD_SHAPES = [
    ("yaml front matter is not a setext heading",
     "---\ntitle: x\n---\n\n# Doc\n\n## A\n", [(1, "", "Doc"), (2, "", "A")]),
    ("a heading inside an HTML comment is no heading, and its text joins the block above",
     "# T\n\n<!--\n## hidden\n-->\n\n## Real\n", [(1, "", "T## hidden-->"), (2, "", "Real")]),
    ("a heading inside a blockquote is a heading",
     "# T\n\n> ## quoted\n\ntext\n", [(1, "", "T"), (2, "", "quoted")]),
    ("a heading inside a list item is a heading",
     "# T\n\n- ## in a list\n\ntext\n", [(1, "", "T"), (2, "", "in a list")]),
    ("a heading indented under a list item is a heading",
     "# T\n\n- item\n\n  ## indented\n\ntext\n", [(1, "", "T"), (2, "", "indented")]),
    ("a table delimiter row is not a setext heading",
     "# T\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", [(1, "", "T")]),
    ("an unclosed fence swallows the rest of the document",
     "# T\n\n```\n## code\n\n## after\n", [(1, "", "T")]),
    ("a multi-line paragraph over a setext rule is one heading",
     "# T\n\nline one\nline two\n---\n", [(1, "", "T"), (2, "", "line one line two")]),
]


@pytest.mark.parametrize("name,text,expected", HARD_SHAPES, ids=[c[0] for c in HARD_SHAPES])
def test_qt_decides_what_a_heading_is(name, text, expected):
    assert heads(text) == expected


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
        ("2026-09-03-environments", "zharn", [(2, "", "Task 6: checks at handoff")]),
    ]
    assert search(docs, "checks handoff")[0]["sections"][0]["title"] == "Task 6: checks at handoff"
    assert len(search(docs, "checks handoff")) == 1
    assert search(docs, "4.6")[0]["sections"][0]["title"] == "Checks"      # the number counts as text


def test_search_matches_document_names_as_groups_without_sections(corpus):
    docs = scan_repo("zharn", corpus)
    assert [(g["name"], g["sections"]) for g in search(docs, "readme")] == [("README", [])]
    assert search(docs, "") == []


from types import SimpleNamespace  # noqa: E402

from PySide6.QtCore import QObject, Signal  # noqa: E402

from harness.content import KINDS  # noqa: E402
from harness.documents import ROW_ROLES, DocumentsStore, heading_positions  # noqa: E402
from harness.workspace import Workspace  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_documents_is_a_panel_kind_and_the_document_tab_shares_its_icon():
    assert KINDS["documents"] == {"title": "Documents", "qml": "content/Documents.qml", "panel": True, "icon": "documents"}
    assert KINDS["document"]["icon"] == "documents"
    assert (ROOT / "qml/icons/documents.svg").exists()


class FakeLayout(QObject):
    """Records openContent calls, and carries a `_layout.data` shaped like the real LayoutStore's, which
    is what the rescan gate reads; the real LayoutStore is exercised by the UI tests."""
    layoutChanged = Signal()

    def __init__(self):
        super().__init__()
        self.opened = []
        self._layout = SimpleNamespace(data={
            "docks": {"left": {"panels": ["board", "documents"], "active": "board", "mode": "docked", "size": 290},
                      "right": {"panels": ["cast"], "active": "cast", "mode": "docked", "size": 300}},
            "center": {"type": "tabs", "id": "g1", "tabs": [{"kind": "welcome", "key": "welcome", "title": "Welcome"}],
                       "active": 0},
        })

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


def test_rescan_survives_a_file_that_vanishes_between_the_stat_and_the_read(store, corpus, monkeypatch):
    """A file can be deleted or mid-write between rescan's freshness stat and read_document's read: that
    must not blow up the scan or lose the other documents (review finding, fix round 1)."""
    import harness.documents as docmod
    real_read_document = docmod.read_document
    victim = str(corpus / "README.md")

    def flaky(name, path, rel):
        if str(path) == victim:
            raise OSError("vanished mid-scan")
        return real_read_document(name, path, rel)

    monkeypatch.setattr(docmod, "read_document", flaky)
    write(corpus, "README.md", "# zharn\n## Changed\n")
    import os, time
    os.utime(corpus / "README.md", ns=(time.time_ns(), time.time_ns()))
    assert store.rescan() is True                          # does not raise
    assert store.document("zharn/README.md") is None        # skipped for this scan
    assert store.document("zharn/CLAUDE.md") is not None    # the rest of the corpus survives

    assert store.rescan() is False                          # the same failure is not news every 2 seconds

    monkeypatch.setattr(docmod, "read_document", real_read_document)
    assert store.rescan() is True
    assert store.document("zharn/README.md")["title"] == "zharn"   # picked up again once it stops erroring


def test_a_body_only_edit_leaves_the_rows_alone_so_the_tree_keeps_its_scroll(store, corpus):
    store.toggle("zharn/README.md")                # its sections are rows now, so a new one would show
    resets = []
    store.model.modelReset.connect(lambda: resets.append(1))
    import os, time
    write(corpus, "README.md", "# zharn\n## Run\n## Test\n\nA paragraph nobody sees in the tree.\n")
    os.utime(corpus / "README.md", ns=(time.time_ns(), time.time_ns()))
    assert store.rescan() is True                  # the corpus changed: an open tab reloads its text
    assert resets == []                            # but no row moved
    write(corpus, "README.md", "# zharn\n## Run\n## Test\n## More\n")
    os.utime(corpus / "README.md", ns=(time.time_ns(), time.time_ns()))
    assert store.rescan() is True and resets == [1]   # a new heading is a new row


def test_the_periodic_tick_walks_only_while_the_map_is_in_use(store, monkeypatch):
    """The walk costs tens of milliseconds on the GUI thread over a large repo (finding: every 2 s).
    A direct rescan() always walks; the tick asks the layout whether anything is showing the map."""
    docks = store.layout._layout.data["docks"]
    assert store._in_use() is False
    docks["left"]["active"] = "documents"
    assert store._in_use() is True
    docks["left"]["mode"] = "strip"                # the panel is hidden behind its strip button
    assert store._in_use() is False
    store.layout._layout.data["center"] = {"type": "split", "id": "s1", "children": [
        {"type": "tabs", "id": "g1", "tabs": [{"kind": "welcome", "key": "welcome", "title": "W"}], "active": 0},
        {"type": "tabs", "id": "g2", "tabs": [{"kind": "document", "key": "zharn/README.md", "title": "README.md"}], "active": 0}]}
    assert store._in_use() is True                 # an open document tab reloads from documentsChanged

    walked = []
    monkeypatch.setattr(store, "rescan", lambda: walked.append(1))
    store._tick()
    assert walked == [1]
    store.layout._layout.data["center"] = {"type": "tabs", "id": "g1", "tabs": [], "active": 0}
    store._tick()
    assert walked == [1]


def test_search_goes_through_the_store(store):
    assert [g["name"] for g in store.search("check")] == ["workspace-model", "2026-09-03-environments"]


def test_a_missing_repo_is_skipped(tmp_path, corpus):
    ws = Workspace.create(tmp_path / "ws2", name="W", prefix="W")
    ws.add_repo(corpus)
    ws.add_repo(tmp_path / "gone", name="gone")
    s = DocumentsStore(ws, FakeLayout())
    s.rescan()
    assert {d["repo"] for d in s.documents()} == {"zharn"}


def _qt_headings(text):
    """An independent walk of Qt's heading blocks, so the guard below doesn't test documents.py with itself."""
    from PySide6.QtGui import QTextDocument
    doc = QTextDocument()
    doc.setMarkdown(text)
    out, block = [], doc.begin()
    while block.isValid():
        level = block.blockFormat().headingLevel()
        if level:
            out.append((level, block.position()))
        block = block.next()
    return out


@pytest.mark.parametrize("path", sorted(p for p in ROOT.rglob("*.md") if ".git" not in p.parts and "_out" not in p.parts))
def test_the_headings_and_their_positions_are_one_walk_over_every_document_in_the_repo(path):
    """A section's index is its ordinal among Qt's heading blocks and the tab scrolls to the position of
    that same block: headings_of and heading_positions must never drift apart."""
    text = path.read_text(encoding="utf-8")
    qt = _qt_headings(text)
    assert [h["level"] for h in headings_of(text)] == [level for level, _ in qt], path
    assert heading_positions(text) == [pos for _, pos in qt], path
