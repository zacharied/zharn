"""Cast tool window: derived statuses, Recast dialog, fork provenance, sub-stories — through the real controls."""
import pytest
from PySide6.QtTest import QTest

from ui import start, wait_until


@pytest.fixture(scope="module")
def ui():
    h = start("ui-cast")
    yield h
    h.shutdown()


def settled(ui, chr_id):
    ctx = ui.store.contexts.get(ui.store.stories.character(chr_id)["live_context"])
    assert wait_until(lambda: ctx.status == "idle"), ctx.status
    return ctx


def open_story(ui, key):
    ui.store.layout.openContent("story", key, key)
    QTest.qWait(120)


def test_cast_row_shows_the_derived_status(ui):
    key = ui.store.stories.create("Statuses", "")
    chr_id = ui.store.stories.start(key, "", "protagonist")
    settled(ui, chr_id)   # the quiet check has yielded the owed main thread for it
    open_story(ui, key)
    assert ui.find(f"castStatus_{chr_id}").property("text") == "waits on you · outline ready"
    ui.store.stories.comment(key, "slow reply please")   # the reply resumes it; fake claude dawdles
    assert wait_until(lambda: ui.find(f"castStatus_{chr_id}").property("text").startswith("working on #1"))
    settled(ui, chr_id)                                  # …quiet check yields for it again
    assert wait_until(lambda: ui.find(f"castStatus_{chr_id}").property("text").startswith("waits on you"))


def test_recast_dialog_recasts_onto_the_chosen_role(ui):
    key = ui.store.stories.create("Recastable", "")
    chr_id = ui.store.stories.start(key, "", "protagonist")
    settled(ui, chr_id)
    old_ctx = ui.store.stories.character(chr_id)["live_context"]
    open_story(ui, key)
    ui.click(ui.find(f"recastButton_{chr_id}"))
    assert ui.visible(ui.find("recastConfirm"))
    ui.choose(ui.find("recastRole"), "claude-fast")
    ui.click(ui.find("recastConfirm"))
    ch = ui.store.stories.character(chr_id)
    assert ch["role"] == "claude-fast" and ch["live_context"] != old_ctx
    assert not ui.has("recastConfirm") or not ui.visible(ui.find_all("recastConfirm")[0])


def test_retired_cast_shows_retired_and_loses_the_recast_button(ui):
    key = ui.store.stories.create("Retire me", "")
    chr_id = ui.store.stories.start(key, "", "protagonist")
    settled(ui, chr_id)                # quiet check: outline handoff waits on you
    ui.store.stories.proceed(key)
    settled(ui, chr_id)                # quiet check again: ready for review
    ui.store.stories.approve(key)
    open_story(ui, key)
    assert wait_until(lambda: ui.find(f"castStatus_{chr_id}").property("text") == "retired")
    btns = ui.find_all(f"recastButton_{chr_id}")
    assert not btns or not btns[0].isVisible()


def test_substories_list_under_the_cast_and_open_on_click(ui):
    key = ui.store.stories.create("Parent", "")
    chr_id = ui.store.stories.start(key, "", "protagonist")
    settled(ui, chr_id)
    sub = ui.store.stories.cast_create(chr_id, "the small part", start=True, role="claude-fast")
    open_story(ui, key)
    ui.click(ui.find(f"substoryRow_{sub}"))
    assert ui.has(f"tab_story_{sub}")
    assert ui.visible(ui.find(f"card_{sub}"))  # board shows it too, as a sub-story
