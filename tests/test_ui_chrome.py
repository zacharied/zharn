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


def test_welcome_workspace_opens_the_workspace_page(ui):
    ui.click(ui.find("welcomeWorkspace"))
    assert ui.has("tab_workspace_workspace") and ui.has("workspaceName")


def test_welcome_contexts_opens_the_bottom_panel(ui):
    ui.store.layout.openContent("welcome", "welcome", "Welcome")
    QTest.qWait(50)
    ui.click(ui.find("welcomeContexts"))
    assert docks(ui)["bottom"] == {**docks(ui)["bottom"], "active": "contexts", "mode": "docked"}
    assert ui.visible(ui.find("dock_bottom"))
    ui.store.layout.setDockMode("bottom", "strip")


def test_contexts_row_opens_the_context(ui):
    cid = ui.store.contexts.spawn("friend", "from the log", story_key="ABC-2")
    ui.store.layout.showPanel("contexts")
    QTest.qWait(150)
    ui.click(ui.find(f"contextRow_{cid}"))            # selects: the pane shows it
    assert ui.find("paneContextTitle").property("text") == "from the log"
    ui.click(ui.find("contextOpenInTab"))               # and this opens the editor tab
    assert ui.has(f"tab_context_{cid}")
    assert wait_until(lambda: ui.store.contexts.get(cid).status == "idle")
    ui.store.layout.setDockMode("bottom", "strip")


def test_new_context_button_opens_a_bare_context(ui):
    ui.store.layout.showPanel("contexts")
    QTest.qWait(150)
    n = ui.store.contexts.model.count()
    ui.click(ui.find("newContextButton"))
    assert ui.store.contexts.model.count() == n + 1
    cid = ui.store.contexts.model.rows()[-1]["id"]
    assert ui.store.contexts.get(cid).owner == "human"
    assert ui.store.contexts.get(cid).position == "bare"
    assert ui.has(f"tab_context_{cid}")


def test_toolbar_new_context_button_opens_a_bare_context(ui):
    n = ui.store.contexts.model.count()
    ui.click(ui.find("toolbarNewContextButton"))
    assert ui.store.contexts.model.count() == n + 1
    cid = ui.store.contexts.model.rows()[-1]["id"]
    assert ui.store.contexts.get(cid).owner == "human"
    assert ui.store.contexts.get(cid).position == "bare"
    assert ui.has(f"tab_context_{cid}")


def edges(ui, name):
    """(left, right, top) of a toolbar item, in window coordinates. Asserts it is on screen —
    geometry alone reports position for an invisible item too."""
    ref = ui.find(name)
    assert ui.visible(ref), f"{name} is not visible"
    return ref.x(), ref.x() + ref.width(), ref.y()


def test_toolbar_actions_cluster_at_the_left_beside_the_workspace_widget(ui):
    ws_l, ws_r, ws_y = edges(ui, "workspaceWidget")
    st_l, st_r, st_y = edges(ui, "newStoryButton")
    cx_l, cx_r, cx_y = edges(ui, "toolbarNewContextButton")
    assert ws_r <= st_l < st_r <= cx_l                     # workspace, then New story, then New context
    assert st_y == ws_y and cx_y == ws_y                   # one row
    assert st_l - ws_r < 40 and cx_l - st_r < 40           # a cluster, not split by the stretcher
    assert cx_r < ui.win.width() / 2                       # at the top left, not the right end


def chip(ui, name):
    """The rendered fill of a toolbar chip, as a QColor."""
    from PySide6.QtGui import QColor
    return QColor(ui.find(name).property("color"))


def test_the_run_widget_stays_the_brighter_chip_of_the_pair(ui):
    """New story is the cluster's focal point and New context its quiet twin, so the run widget
    has to read brighter in both states. Both hovering to app.theme.hover would flatten them."""
    ui.hover(ui.find("workspaceWidget"))                                  # pointer off both
    # against the toolbar, not the twin: the twin at rest is literally "transparent", so QColor
    # reads it as value 0 and the comparison would hold for a chip flattened into the panel.
    assert chip(ui, "newStoryButton").value() > chip(ui, "toolbar").value()
    ui.hover(ui.find("toolbarNewContextButton"))
    ctx_hovered = chip(ui, "toolbarNewContextButton")
    ui.hover(ui.find("newStoryButton"))
    assert chip(ui, "newStoryButton").value() > ctx_hovered.value()
    ui.hover(ui.find("workspaceWidget"))


def test_new_context_menu_opens_a_bare_context_on_the_chosen_picks(ui):
    ui.store.layout.showPanel("contexts")
    QTest.qWait(150)
    n = ui.store.contexts.model.count()
    ui.click(ui.find("newContextMenuButton"))
    ui.click(ui.find("newContextMenuItem_0"))       # New context with…
    ui.choose(ui.find("bareModel"), "Sonnet 5")
    ui.choose(ui.find("bareEffort"), "low")
    ui.click(ui.find("newContextConfirm"))
    assert ui.store.contexts.model.count() == n + 1
    ctx = ui.store.contexts.get(ui.store.contexts.model.rows()[-1]["id"])
    assert ctx.position == "bare"                  # the cast site implies it; the dialog never offers it
    assert (ctx.meta["cast"]["model"], ctx.meta["cast"]["effort"]) == ("claude-sonnet-5", "low")


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
