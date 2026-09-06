"""Cast tool window: derived statuses, Recast dialog, fork provenance, sub-stories — through the real controls."""
import re

import pytest
from PySide6.QtTest import QTest

from ui import OUT, start, wait_until


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
    chr_id = ui.store.stories.start(key, "")
    settled(ui, chr_id)   # the quiet check has yielded the owed main thread for it
    open_story(ui, key)
    assert ui.find(f"castStatus_{chr_id}").property("text") == "waits on you · outline ready"
    ui.store.stories.comment(key, "slow reply please")   # the reply resumes it; fake claude dawdles
    assert wait_until(lambda: ui.find(f"castStatus_{chr_id}").property("text").startswith("working on #1"))
    settled(ui, chr_id)                                  # …quiet check yields for it again
    assert wait_until(lambda: ui.find(f"castStatus_{chr_id}").property("text").startswith("waits on you"))


def test_recast_dialog_recasts_onto_the_chosen_picks(ui):
    key = ui.store.stories.create("Recastable", "")
    chr_id = ui.store.stories.start(key, "")
    settled(ui, chr_id)
    old_ctx = ui.store.stories.character(chr_id)["live_context"]
    open_story(ui, key)
    ui.click(ui.find(f"recastButton_{chr_id}"))
    assert ui.visible(ui.find("recastConfirm"))
    # seeded from the character it is recasting: the position is never offered, the picks are
    assert ui.find("recastEffort").property("currentText") == "high"
    ui.choose(ui.find("recastModel"), "Sonnet 5")
    ui.choose(ui.find("recastEffort"), "low")
    ui.choose(ui.find("recastPreset"), "builder")
    ui.click(ui.find("recastConfirm"))
    ch = ui.store.stories.character(chr_id)
    assert (ch["model"], ch["effort"], ch["preset"]) == ("claude-sonnet-5", "low", "builder")
    assert ch["position"] == "protagonist" and ch["live_context"] != old_ctx
    # and the picks reached the context it was recast onto
    cast = ui.store.contexts.get(ch["live_context"]).meta["cast"]
    assert (cast["model"], cast["effort"], cast["preset"]) == ("claude-sonnet-5", "low", "builder")
    assert not ui.has("recastConfirm") or not ui.visible(ui.find_all("recastConfirm")[0])


def test_recast_dialog_takes_a_model_the_config_has_not_heard_of(ui):
    key = ui.store.stories.create("Typed model", "")
    chr_id = ui.store.stories.start(key, "")
    settled(ui, chr_id)
    open_story(ui, key)
    ui.click(ui.find(f"recastButton_{chr_id}"))
    ui.find("recastModel").setProperty("editText", "claude-opus-9")
    ui.click(ui.find("recastConfirm"))
    assert ui.store.stories.character(chr_id)["model"] == "claude-opus-9"


def test_retired_cast_shows_retired_and_loses_the_recast_button(ui):
    key = ui.store.stories.create("Retire me", "")
    chr_id = ui.store.stories.start(key, "")
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
    chr_id = ui.store.stories.start(key, "")
    settled(ui, chr_id)
    sub = ui.store.stories.cast_create(chr_id, "the small part", start=True)
    open_story(ui, key)
    ui.click(ui.find(f"substoryRow_{sub}"))
    assert ui.has(f"tab_story_{sub}")
    assert ui.visible(ui.find(f"card_{sub}"))  # board shows it too, as a sub-story


def test_cast_row_names_the_characters_environment(ui):
    import shutil
    from gitfix import make_repo
    from harness.environments import register_repo
    d = OUT / "ui-cast-repo"
    shutil.rmtree(d, ignore_errors=True)
    register_repo(ui.store.stories.workspace, str(make_repo(d)), name="api")
    key = ui.store.stories.create("Where", "")
    chr_id = ui.store.stories.start(key, "")
    settled(ui, chr_id)
    open_story(ui, key)
    assert "in api" not in ui.find(f"castMeta_{chr_id}").property("text")
    ui.store.stories.cast_env_open(chr_id, "api")
    QTest.qWait(80)
    assert ui.find(f"castMeta_{chr_id}").property("text").endswith(" · in api")


def test_cast_row_context_carries_its_reading(ui):
    key = ui.store.stories.create("Reading", "")
    chr_id = ui.store.stories.start(key, "tokens=2500")   # the note rides the brief; the fake reads it
    ctx = settled(ui, chr_id)
    assert ctx.contextTokens == 2510 and ctx.contextWindow == 1000000
    row = next(r for r in ui.store.contexts.summaries() if r["id"] == ctx.id)
    assert row["contextTokens"] == 2510 and row["contextWindow"] == 1000000
    assert ui.store.stories.cast(key)[0]["recapDue"] is False
    open_story(ui, key)
    vitals = ui.find(f"castContext_{chr_id}").property("text")
    assert vitals.startswith("3K · 1 turn · $") and "recap due" not in vitals
    meter = ui.find(f"castMeter_{chr_id}")
    assert abs(meter.property("fraction") - 2510 / 500_000) < 1e-6 and meter.property("hot") is False
    assert meter.property("tick") == 300_000 and meter.property("max") == 500_000     # framed on the recast line, not the window


def test_cast_row_goes_amber_while_a_recap_is_due(ui):
    key = ui.store.stories.create("Recap due", "")
    chr_id = ui.store.stories.start(key, "tokens=350000")   # the brief's first reading is past the warn line
    ctx = settled(ui, chr_id)
    open_story(ui, key)
    assert ui.store.stories.cast(key)[0]["recapDue"] is True
    assert wait_until(lambda: ui.find(f"castContext_{chr_id}").property("text").startswith("350K · recap due · "))
    assert ui.find(f"castMeter_{chr_id}").property("hot") is True
    # the Contexts pane says the same of the selected context
    ui.store.layout.showPanel("contexts")
    ui.store.contexts.reveal(ctx.id)                     # selects it in the pane (the row may be scrolled out of view)
    assert wait_until(lambda: ui.find("paneContextReading").property("text") == "350K · recap due")
    assert re.fullmatch(r"350K · \dt · \$\d+\.\d\d", ui.find(f"contextVitals_{ctx.id}").property("text"))   # the nudge's reply is a turn too
    ui.store.stories.cast_recap(chr_id, "so far: the outline")
    assert wait_until(lambda: "recap due" not in ui.find(f"castContext_{chr_id}").property("text"))
    assert re.match(r"350K · \d turns? · \$", ui.find(f"castContext_{chr_id}").property("text"))   # the number stays; only the state went
    assert ui.find(f"castMeter_{chr_id}").property("hot") is False
    assert wait_until(lambda: ui.find("paneContextReading").property("text") == "350K")
    ui.store.layout.setDockMode("bottom", "strip")


def test_a_recast_predecessor_row_names_the_reading_it_was_recast_at(ui):
    key = ui.store.stories.create("Lineage", "")
    chr_id = ui.store.stories.start(key, "tokens=120000")
    old = settled(ui, chr_id).id
    ui.store.stories.recast(key, chr_id)
    settled(ui, chr_id)
    ui.store.layout.showPanel("contexts")
    QTest.qWait(150)
    assert wait_until(lambda: ui.has(f"contextLineage_{old}"))
    assert ui.find(f"contextName_{old}").property("text") == "recast at 120K"
    ui.store.layout.setDockMode("bottom", "strip")
