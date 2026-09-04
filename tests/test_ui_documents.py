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
