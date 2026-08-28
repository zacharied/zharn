"""The thread view: send, stop, errors — through the real controls."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from ui import start, wait_until


@pytest.fixture(scope="module")
def ui():
    h = start("ui-thread")
    yield h
    h.shutdown()


def open_thread(ui, prompt="hello"):
    tid = ui.store.threads.spawn("ABC-1", "claude-fast", prompt)
    ui.store.layout.openContent("thread", tid, prompt)
    QTest.qWait(150)
    return ui.store.threads.get(tid)


def test_send_button_is_disabled_until_there_is_text(ui):
    t = open_thread(ui)
    assert wait_until(lambda: t.status == "idle")
    assert not ui.find("sendButton").property("enabled")
    ui.focus_and_type(ui.find("promptInput"), "x")
    assert ui.find("sendButton").property("enabled")
    ui.find("promptInput").setProperty("text", "")


def test_send_button_sends_and_clears_the_input(ui):
    t = open_thread(ui)
    assert wait_until(lambda: t.status == "idle")
    n = t.transcript.count()
    ui.focus_and_type(ui.find("promptInput"), "second message")
    ui.click(ui.find("sendButton"))
    assert t.transcript.rows()[n]["text"] == "second message"
    assert ui.find("promptInput").property("text") == ""
    assert wait_until(lambda: t.status == "idle")
    assert t.transcript.rows()[-1]["text"] == "echo: second message"
    assert wait_until(lambda: ui.find("transcript").property("count") == t.transcript.count())


def test_ctrl_enter_sends(ui):
    t = open_thread(ui)
    assert wait_until(lambda: t.status == "idle")
    n = t.transcript.count()
    ui.focus_and_type(ui.find("promptInput"), "via keyboard")
    ui.key(Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert t.transcript.rows()[n]["text"] == "via keyboard"
    assert ui.find("promptInput").property("text") == ""
    assert wait_until(lambda: t.status == "idle")


def test_stop_button_stops_a_working_thread(ui):
    t = open_thread(ui, "slow reply please")
    assert wait_until(lambda: t.status == "working")
    stop = ui.find("stopButton")
    assert ui.visible(stop)
    ui.click(stop)
    assert wait_until(lambda: t.status == "stopped"), t.status
    assert ui.find("threadStatus").property("text") == "stopped"
    assert not ui.visible(stop)


def test_failed_thread_shows_the_reason_in_the_view(ui, monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", "/nonexistent/claude-nope")
    t = open_thread(ui, "will fail")
    assert wait_until(lambda: t.status == "failed"), t.status
    err = ui.find("threadError")
    assert ui.visible(err) and "claude-nope" in err.property("text")


def test_unknown_thread_tab_explains_itself(ui):
    ui.store.layout.openContent("thread", "thr_nope", "gone")
    QTest.qWait(100)
    assert "not found" in ui.find("threadMissing").property("text").lower()
    assert not ui.has("sendButton") or not ui.visible(ui.find("sendButton"))


def test_task_link_in_header_opens_the_task(ui):
    t = open_thread(ui, "link me")
    ui.click(ui.find("threadTaskLink"))
    assert ui.has("tab_task_ABC-1")
