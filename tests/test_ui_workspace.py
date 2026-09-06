"""The workspace page through the real controls: opened from the toolbar, repos with status, worktrees as story
keys, Relocate for a missing repo, Unregister on hover, and registering from the form (workspace spec §3, §7)."""
import shutil

import pytest
from PySide6.QtTest import QTest

from gitfix import make_repo, rmtree
from ui import OUT, start, wait_until


@pytest.fixture(scope="module")
def ui():
    h = start("ui-workspace")
    yield h
    h.shutdown()


def fresh_repo(name):
    d = OUT / name
    shutil.rmtree(d, ignore_errors=True)
    return make_repo(d)


def open_page(ui):
    ui.click(ui.find("workspaceWidget"))
    QTest.qWait(120)
    assert ui.has("tab_workspace_workspace")


def test_toolbar_widget_opens_the_page_with_name_prefix_and_dir(ui):
    open_page(ui)
    ws = ui.store.stories.workspace
    assert ui.find("workspaceName").property("text") == ws.name
    assert ui.find("workspacePrefix").property("text") == ws.prefix + "-"
    assert ui.find("workspaceDir").property("text") == str(ws.dir)
    assert ui.find("workspaceRepoCount").property("text") == "0 repos"


def test_register_from_the_form_adds_a_row(ui):
    open_page(ui)
    repo = fresh_repo("ui-ws-repo-a")
    ui.focus_and_type(ui.find("addRepoPath"), str(repo))
    ui.focus_and_type(ui.find("addRepoChecks"), "echo ok")
    ui.click(ui.find("addRepoButton"))
    QTest.qWait(80)
    rec = ui.store.stories.workspace.repo(repo.name)
    assert rec and rec["checks"] == "echo ok" and rec["base"] == "main"
    assert ui.visible(ui.find(f"repoRow_{repo.name}"))
    assert ui.find("addRepoPath").property("text") == "" and ui.find("workspaceRepoCount").property("text") == "1 repo"


def test_worktrees_list_the_stories_in_the_repo_and_open_them(ui):
    open_page(ui)
    repo = fresh_repo("ui-ws-repo-b")
    ui.store.workspace.register(str(repo), "b", "", "", "")
    key = ui.store.stories.create("In b", "")
    chr_id = ui.store.stories.start(key, "")
    ctx = ui.store.contexts.get(ui.store.stories.character(chr_id)["live_context"])
    assert wait_until(lambda: ctx.status == "idle")
    assert not ui.visible(ui.find("repoWorktrees_b"))
    ui.store.stories.cast_env_open(chr_id, "b")
    QTest.qWait(80)
    assert ui.visible(ui.find("repoWorktrees_b"))
    ui.click(ui.find(f"worktreeKey_b_{key}"))
    assert ui.has(f"tab_story_{key}")


def test_missing_repo_offers_relocate_and_recovers(ui):
    open_page(ui)
    repo = fresh_repo("ui-ws-repo-c")
    ui.store.workspace.register(str(repo), "c", "", "", "")
    moved = OUT / "ui-ws-repo-c-moved"
    rmtree(moved)
    shutil.move(str(repo), str(moved))
    ui.store.workspace.workspaceChanged.emit()   # nothing watches the filesystem; the page re-reads status on the signal
    QTest.qWait(80)
    assert ui.visible(ui.find("repoStatus_c")) and ui.visible(ui.find("relocateButton_c"))
    ui.click(ui.find("relocateButton_c"))
    ui.focus_and_type(ui.find("relocatePath_c"), str(moved))
    ui.click(ui.find("relocateConfirm_c"))
    QTest.qWait(80)
    assert ui.store.stories.workspace.repo_status("c") == "ok"
    assert all(not r.isVisible() for r in ui.find_all("relocatePath_c"))   # the form folds; the row is whole again
    assert not ui.visible(ui.find("repoStatus_c"))


def test_unregister_on_hover_removes_the_row(ui):
    open_page(ui)
    repo = fresh_repo("ui-ws-repo-d")
    ui.store.workspace.register(str(repo), "d", "", "", "")
    QTest.qWait(80)
    ui.hover(ui.find("repoRow_d"))
    ui.click(ui.find("unregisterButton_d"))
    QTest.qWait(80)
    assert ui.store.stories.workspace.repo("d") is None and not ui.has("repoRow_d")
    assert (repo / ".git").exists()   # never deletes files (spec §3.2)
