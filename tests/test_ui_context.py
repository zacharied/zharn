"""The context view: send, stop, errors — through the real controls."""
import pytest
from PySide6.QtCore import QPoint, Qt
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
    assert not any(r.isVisible() for r in ui.find_all("sendButton"))  # the panel's pane has one too, hidden


def test_story_link_in_header_opens_the_story(ui):
    open_context(ui, "link me")
    ui.click(ui.find("contextStoryLink"))
    assert ui.has(f"tab_story_{ui.story_key}")


# ---------------------------------------------------------------- selectable text
# Same as the story page (ZHAR-3): the transcript selects on drag and scrolls on the wheel.

def test_dragging_across_a_transcript_row_selects_text(ui):
    c = open_context(ui, "a message long enough that a drag across it selects a run of words")
    assert wait_until(lambda: c.status == "idle")
    assert wait_until(lambda: ui.find("transcript").property("count") == c.transcript.count())
    body = ui.find("transcriptBody_0")
    ui.drag_across(body)
    sel = body.property("selectedText")
    assert sel, "dragging across a transcript row selected nothing"
    assert sel in body.property("text")


def test_dragging_the_transcript_does_not_scroll_it(ui):
    c = open_context(ui)
    assert wait_until(lambda: c.status == "idle")
    for i in range(25):
        ui.store.contexts.send(c.id, f"filler {i} " + "words " * 12)
        assert wait_until(lambda: c.status == "idle")
    QTest.qWait(150)
    lst = ui.find("transcript")
    assert lst.property("contentHeight") > lst.property("height"), "transcript is not scrollable; test proves nothing"
    before = lst.property("contentY")
    ui.drag(QPoint(int(lst.property("width")) - 40, int(lst.property("height")) - 60),
            QPoint(int(lst.property("width")) - 40, 60))
    assert lst.property("contentY") == before, "the transcript panned on a mouse drag"
    ui.wheel(lst, notches=1)
    assert lst.property("contentY") < before, "the wheel no longer scrolls the transcript"


def fill_transcript(ui, c, n=25):
    for i in range(n):
        ui.store.contexts.send(c.id, f"filler {i} " + "words " * 12)
        assert wait_until(lambda: c.status == "idle")
    QTest.qWait(200)


def test_transcript_follows_the_tail_again_after_the_reader_scrolls_back(ui):
    """The wheel has to be able to reach the true bottom. If its clamp stops even a pixel short,
    atYEnd never goes true, stickToEnd latches false, and the view stops following new output
    for the rest of the session."""
    c = open_context(ui)
    assert wait_until(lambda: c.status == "idle")
    fill_transcript(ui, c)
    lst = ui.find("transcript")
    assert lst.property("contentHeight") > lst.property("height"), "transcript is not scrollable"

    ui.wheel(lst, notches=1)                       # read back through some history
    assert not lst.property("atYEnd")
    for _ in range(60):                            # ... then wheel back down to the bottom
        if lst.property("atYEnd"):
            break
        ui.wheel(lst, notches=-1)
    assert lst.property("atYEnd"), "the wheel cannot reach the bottom of the transcript"

    ui.store.contexts.send(c.id, "arrived after the reader came back")
    assert wait_until(lambda: c.status == "idle")
    assert wait_until(lambda: ui.find("transcript").property("count") == c.transcript.count())
    QTest.qWait(200)
    # not atYEnd: positionViewAtEnd() ignores bottomMargin, so following the tail lands ten
    # pixels short of it. What matters is that the end of the content is on screen.
    origin, content, view = (lst.property(x) for x in ("originY", "contentHeight", "height"))
    assert lst.property("contentY") + view >= origin + content - 1,         "a new message did not scroll into view"


def test_tool_rows_fold_and_keep_no_hidden_copy_of_their_output(ui):
    """Tool blocks stay a Text so they can elide; the Prose beside them must not quietly hold a
    second, un-elided copy of what can be very large output."""
    c = open_context(ui, "please run a tool")
    assert wait_until(lambda: c.status == "idle")
    assert wait_until(lambda: ui.find("transcript").property("count") == c.transcript.count())
    i = next(i for i, r in enumerate(c.transcript.rows()) if r["kind"] == "tool_result")
    assert c.transcript.rows()[i]["text"], "the fake produced no tool output to fold"

    tool = ui.find(f"transcriptTool_{i}")
    assert tool.property("maximumLineCount") == 4, "tool output no longer folds"
    assert ui.find(f"transcriptBody_{i}").property("text") == "", \
        "the hidden Prose still carries the whole tool output"

    ui.click(ui.find(f"transcriptRow_{i}"))
    assert tool.property("maximumLineCount") > 4, "tapping a tool row no longer expands it"
