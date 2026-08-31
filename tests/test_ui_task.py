"""Task board + task view, driven through the real controls."""
import pytest
from PySide6.QtTest import QTest

from ui import start, wait_until


@pytest.fixture(scope="module")
def ui():
    h = start("ui-task")
    yield h
    h.shutdown()


def test_board_card_click_opens_task_tab(ui):
    ui.click(ui.find("card_ABC-3"))
    assert ui.has("tab_task_ABC-3")
    assert ui.find("taskTitle").property("text").startswith("Terminal panel")


def test_dispatch_button_spawns_context_and_opens_its_tab(ui):
    ui.store.layout.openContent("task", "ABC-3", "ABC-3")
    QTest.qWait(100)
    n = ui.store.contexts.model.count()
    ui.focus_and_type(ui.find("dispatchPrompt"), "do the thing via ui")
    ui.click(ui.find("dispatchButton"))
    assert ui.store.contexts.model.count() == n + 1
    c = ui.store.contexts.get(ui.store.contexts.model.rows()[-1]["id"])
    assert c.storyKey == "ABC-3" and c.title == "do the thing via ui"
    assert ui.has(f"tab_context_{c.id}")
    assert all(i.property("text") == "" for i in ui.find_all("dispatchPrompt"))  # cleared (tab may now be hidden)
    assert wait_until(lambda: c.status == "idle"), (c.status, c.lastError)


def test_dispatch_with_unimplemented_provider_shows_error_banner(ui):
    ui.store.layout.openContent("task", "ABC-4", "ABC-4")
    QTest.qWait(100)
    ui.choose(ui.find("roleBox"), "codex-review")
    n = ui.store.contexts.model.count()
    ui.focus_and_type(ui.find("dispatchPrompt"), "review it")
    ui.click(ui.find("dispatchButton"))
    assert ui.store.contexts.model.count() == n, "no context must be created"
    assert "codex" in ui.store.notify.lastError
    banner = ui.find("errorBanner")
    assert ui.visible(banner) and "codex" in banner.property("text")
    ui.click(ui.find("errorDismiss"))
    assert ui.store.notify.lastError == ""
    assert not ui.visible(banner)


def test_new_task_button_creates_and_opens_a_task(ui):
    n = ui.store.tasks.model.count()
    ui.click(ui.find("newTaskButton"))
    assert ui.store.tasks.model.count() == n + 1
    key = ui.store.tasks.list()[-1]["key"]
    assert ui.has(f"tab_task_{key}")
    assert ui.has(f"card_{key}")


def test_status_combo_changes_task_status(ui):
    ui.store.layout.openContent("task", "ABC-4", "ABC-4")
    QTest.qWait(100)
    ui.choose(ui.find("statusBox"), "done")
    assert ui.store.tasks.get("ABC-4")["status"] == "done"


def test_unknown_task_tab_explains_itself_and_hides_the_form(ui):
    ui.store.layout.openContent("task", "ABC-999", "ABC-999")
    QTest.qWait(100)
    assert "not found" in ui.find("taskMissing").property("text").lower()
    assert not ui.has("dispatchButton") or not ui.visible(ui.find("dispatchButton"))
