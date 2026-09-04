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
