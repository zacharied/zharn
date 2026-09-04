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
