"""Window chrome: strips, docks, tabs, splits, welcome page, contexts panel — through the real controls."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from ui import start, wait_until


@pytest.fixture(scope="module")
def ui():
    h = start("ui-chrome")
    yield h
    h.shutdown()


def docks(ui):
    import json
    return json.loads(ui.store.layout.layoutJson)["docks"]


def test_strip_button_toggles_its_dock(ui):
    assert ui.visible(ui.find("dock_left"))
    ui.click(ui.find("stripButton_board"))
    assert not ui.find("dock_left").isVisible()
    ui.click(ui.find("stripButton_board"))
    assert ui.visible(ui.find("dock_left"))


def test_dock_hide_button_collapses_it_to_the_strip(ui):
    ui.click(ui.find("dockHide_left"))
    assert docks(ui)["left"]["mode"] == "strip"
    ui.click(ui.find("stripButton_board"))


def test_strip_button_of_another_panel_switches_the_dock_to_it(ui):
    ui.click(ui.find("stripButton_files"))
    assert docks(ui)["left"]["active"] == "files" and docks(ui)["left"]["mode"] == "docked"
    assert ui.find("dockContent_left").property("source").endswith("Files.qml")
    ui.click(ui.find("stripButton_board"))
    assert docks(ui)["left"]["active"] == "board"


def test_bottom_panels_live_on_the_left_strip_and_open_the_bottom_dock(ui):
    assert not ui.find("dock_bottom").isVisible()
    ui.click(ui.find("stripButton_contexts"))
    assert docks(ui)["bottom"] == {**docks(ui)["bottom"], "active": "contexts", "mode": "docked"}
    assert ui.visible(ui.find("dock_bottom"))
    ui.click(ui.find("stripButton_contexts"))
    assert not ui.find("dock_bottom").isVisible()


def test_clicking_a_tab_activates_it(ui):
    ui.store.layout.openContent("document", "a.py", "a.py")
    QTest.qWait(50)
    ui.click(ui.find("tab_welcome_welcome"))
    g = ui.store.layout._layout.active_group()
    assert g["tabs"][g["active"]]["kind"] == "welcome"


def test_close_button_closes_the_tab(ui):
    ui.store.layout.openContent("document", "b.py", "b.py")
    QTest.qWait(50)
    ui.click(ui.find("tabClose_document_b.py"))
    assert not ui.has("tab_document_b.py")


def test_middle_click_closes_the_tab(ui):
    ui.store.layout.openContent("document", "c.py", "c.py")
    QTest.qWait(50)
    ui.click(ui.find("tab_document_c.py"), Qt.MouseButton.MiddleButton)
    assert not ui.has("tab_document_c.py")


def test_split_buttons_split_the_group(ui):
    gid = ui.store.layout.activeGroup
    ui.click(ui.find(f"splitRight_{gid}"))
    assert len(ui.find_all(r"group_g\d+")) == 2
    new = ui.store.layout.activeGroup
    ui.click(ui.find(f"splitDown_{new}"))
    assert len(ui.find_all(r"group_g\d+")) == 3
    ui.store.layout.resetLayout()
    QTest.qWait(50)


def test_welcome_new_story_creates_and_opens_one(ui):
    ui.store.layout.openContent("welcome", "welcome", "Welcome")
    QTest.qWait(50)
    n = ui.store.stories.model.count()
    ui.click(ui.find("welcomeNewStory"))
    assert ui.store.stories.model.count() == n + 1
    assert ui.has(f"tab_story_{ui.store.stories.list()[-1]['key']}")


def test_welcome_open_board_shows_the_story_board(ui):
    ui.store.layout.resetLayout()
    ui.store.layout.togglePanel("left", "board")  # collapse it first
    QTest.qWait(50)
    ui.click(ui.find("welcomeOpenBoard"))
    assert docks(ui)["left"] == {**docks(ui)["left"], "active": "board", "mode": "docked"}


def test_welcome_contexts_opens_the_bottom_panel(ui):
    ui.store.layout.openContent("welcome", "welcome", "Welcome")
    QTest.qWait(50)
    ui.click(ui.find("welcomeContexts"))
    assert docks(ui)["bottom"] == {**docks(ui)["bottom"], "active": "contexts", "mode": "docked"}
    assert ui.visible(ui.find("dock_bottom"))
    ui.store.layout.setDockMode("bottom", "strip")


def test_contexts_row_opens_the_context(ui):
    cid = ui.store.contexts.spawn("claude-fast", "from the log", story_key="ABC-2")
    ui.store.layout.showPanel("contexts")
    QTest.qWait(150)
    ui.click(ui.find(f"contextRow_{cid}"))
    assert ui.has(f"tab_context_{cid}")
    assert wait_until(lambda: ui.store.contexts.get(cid).status == "idle")


def test_new_context_button_opens_a_bare_context(ui):
    ui.store.layout.showPanel("contexts")
    QTest.qWait(150)
    n = ui.store.contexts.model.count()
    ui.click(ui.find("newContextButton"))
    assert ui.store.contexts.model.count() == n + 1
    cid = ui.store.contexts.model.rows()[-1]["id"]
    assert ui.store.contexts.get(cid).owner == "human"
    assert ui.store.contexts.get(cid).roleName == "claude-default"
    assert ui.has(f"tab_context_{cid}")


def test_welcome_reset_layout_restores_the_default(ui):
    ui.store.layout.openContent("document", "z.py", "z.py")
    ui.store.layout.openContent("welcome", "welcome", "Welcome")
    QTest.qWait(50)
    ui.click(ui.find("welcomeReset"))
    assert not ui.has("tab_document_z.py") and ui.has("tab_welcome_welcome")


def test_restart_badge_is_hidden_unless_a_shape_change_happened(ui):
    assert not ui.find("restartBadge").isVisible()
    ui.store.set_hot(restart_required=True)
    QTest.qWait(30)
    assert ui.visible(ui.find("restartBadge"))
    ui.store.set_hot(restart_required=False)
