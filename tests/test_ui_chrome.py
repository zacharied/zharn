"""Window chrome: strips, docks, tabs, splits, welcome page, agent log — through the real controls."""
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
    ui.click(ui.find("stripButton_tasks"))
    assert not ui.find("dock_left").isVisible()
    ui.click(ui.find("stripButton_tasks"))
    assert ui.visible(ui.find("dock_left"))


def test_dock_hide_button_collapses_it_to_the_strip(ui):
    ui.click(ui.find("dockHide_left"))
    assert docks(ui)["left"]["mode"] == "strip"
    ui.click(ui.find("stripButton_tasks"))


def test_dock_panel_switcher_changes_active_panel(ui):
    ui.click(ui.find("dockPanel_files"))
    assert docks(ui)["left"]["active"] == "files"
    assert ui.find("dockContent_left").property("source").toString().endswith("Files.qml")
    ui.click(ui.find("dockPanel_tasks"))
    assert docks(ui)["left"]["active"] == "tasks"


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


def test_welcome_new_task_creates_and_opens_one(ui):
    ui.store.layout.openContent("welcome", "welcome", "Welcome")
    QTest.qWait(50)
    n = ui.store.tasks.model.count()
    ui.click(ui.find("welcomeNewTask"))
    assert ui.store.tasks.model.count() == n + 1
    assert ui.has(f"tab_task_{ui.store.tasks.list()[-1]['key']}")


def test_welcome_open_board_shows_the_task_board(ui):
    ui.store.layout.resetLayout()
    ui.store.layout.togglePanel("left", "tasks")  # collapse it first
    QTest.qWait(50)
    ui.click(ui.find("welcomeOpenBoard"))
    assert docks(ui)["left"] == {**docks(ui)["left"], "active": "tasks", "mode": "docked"}


def test_welcome_agent_log_opens_the_bottom_panel(ui):
    ui.store.layout.openContent("welcome", "welcome", "Welcome")
    QTest.qWait(50)
    ui.click(ui.find("welcomeAgentLog"))
    assert docks(ui)["bottom"] == {**docks(ui)["bottom"], "active": "agent_log", "mode": "docked"}
    assert ui.visible(ui.find("dock_bottom"))


def test_agent_log_row_opens_the_thread(ui):
    tid = ui.store.threads.spawn("ABC-2", "claude-fast", "from the log")
    ui.store.layout.showPanel("agent_log")
    QTest.qWait(150)
    ui.click(ui.find(f"agentLogRow_{tid}"))
    assert ui.has(f"tab_thread_{tid}")
    assert wait_until(lambda: ui.store.threads.get(tid).status == "idle")


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
