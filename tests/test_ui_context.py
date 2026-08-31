"""The context view: send, stop, errors — through the real controls."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from ui import start, wait_until


@pytest.fixture(scope="module")
def ui():
    h = start("ui-context")
    h.story_key = h.store.stories.create("ctx home", "")
    yield h
    h.shutdown()


def open_context(ui, prompt="hello"):
    cid = ui.store.contexts.spawn("claude-fast", prompt, story_key=ui.story_key)
    ui.store.layout.openContent("context", cid, prompt)
    QTest.qWait(150)
    return ui.store.contexts.get(cid)


def test_send_button_is_disabled_until_there_is_text(ui):
    c = open_context(ui)
    assert wait_until(lambda: c.status == "idle")
    assert not ui.find("sendButton").property("enabled")
    ui.focus_and_type(ui.find("promptInput"), "x")
    assert ui.find("sendButton").property("enabled")
    ui.find("promptInput").setProperty("text", "")


def test_send_button_sends_and_clears_the_input(ui):
    c = open_context(ui)
    assert wait_until(lambda: c.status == "idle")
    n = c.transcript.count()
    ui.focus_and_type(ui.find("promptInput"), "second message")
    ui.click(ui.find("sendButton"))
    assert c.transcript.rows()[n]["text"] == "second message"
    assert ui.find("promptInput").property("text") == ""
    assert wait_until(lambda: c.status == "idle")
    assert c.transcript.rows()[-1]["text"] == "echo: second message"
    assert wait_until(lambda: ui.find("transcript").property("count") == c.transcript.count())


def test_ctrl_enter_sends(ui):
    c = open_context(ui)
    assert wait_until(lambda: c.status == "idle")
    n = c.transcript.count()
    ui.focus_and_type(ui.find("promptInput"), "via keyboard")
    ui.key(Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert c.transcript.rows()[n]["text"] == "via keyboard"
    assert ui.find("promptInput").property("text") == ""
    assert wait_until(lambda: c.status == "idle")


def test_stop_button_stops_a_working_context(ui):
    c = open_context(ui, "slow reply please")
    assert wait_until(lambda: c.status == "working")
    stop = ui.find("stopButton")
    assert ui.visible(stop)
    ui.click(stop)
    assert wait_until(lambda: c.status == "stopped"), c.status
    assert ui.find("contextStatus").property("text") == "stopped"
    assert not ui.visible(stop)


def test_failed_context_shows_the_reason_in_the_view(ui, monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", "/nonexistent/claude-nope")
    c = open_context(ui, "will fail")
    assert wait_until(lambda: c.status == "failed"), c.status
    err = ui.find("contextError")
    assert ui.visible(err) and "claude-nope" in err.property("text")


def test_unknown_context_tab_explains_itself(ui):
    ui.store.layout.openContent("context", "ctx_nope", "gone")
    QTest.qWait(100)
    assert "not found" in ui.find("contextMissing").property("text").lower()
    assert not ui.has("sendButton") or not ui.visible(ui.find("sendButton"))


def test_story_link_in_header_opens_the_story(ui):
    open_context(ui, "link me")
    ui.click(ui.find("contextStoryLink"))
    assert ui.has(f"tab_story_{ui.story_key}")
