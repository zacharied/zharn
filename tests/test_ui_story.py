"""Board + story page through the real controls: create, edit, Start, yields as option buttons, the author's action bar."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from ui import start, wait_until


@pytest.fixture(scope="module")
def ui():
    h = start("ui-story")
    yield h
    h.shutdown()


def open_story(ui, key):
    ui.store.layout.openContent("story", key, key)
    QTest.qWait(120)


def test_new_story_button_creates_and_opens_a_story(ui):
    n = ui.store.stories.model.count()
    ui.click(ui.find("newStoryButton"))
    assert ui.store.stories.model.count() == n + 1
    key = ui.store.stories.list()[-1]["key"]
    assert ui.has(f"tab_story_{key}") and ui.has(f"card_{key}")
    assert ui.find("storyTitleEdit").property("text") == "New story"


def test_board_card_click_opens_story_tab(ui):
    key = ui.store.stories.create("Card me", "")
    QTest.qWait(80)
    ui.click(ui.find(f"card_{key}"))
    assert ui.has(f"tab_story_{key}")
    assert ui.find("storyTitleEdit").property("text") == "Card me"


def test_editing_title_and_description_updates_the_store(ui):
    key = ui.store.stories.create("Old", "")
    open_story(ui, key)
    ui.find("storyTitleEdit").setProperty("text", "")
    ui.focus_and_type(ui.find("storyTitleEdit"), "Renamed")
    ui.key(Qt.Key.Key_Return)
    assert ui.store.stories.get(key)["title"] == "Renamed"
    ui.focus_and_type(ui.find("storyDescriptionEdit"), "some words")
    ui.click(ui.find("storyTitle"))  # blur → editingFinished
    assert wait_until(lambda: ui.store.stories.get(key)["description"] == "some words")


def test_start_casts_protagonist_and_shows_phase_and_ball(ui):
    key = ui.store.stories.create("Startable", "d")
    open_story(ui, key)
    assert ui.has("startButton") and not ui.has("proceedButton")
    ui.choose(ui.find("roleBox"), "protagonist")
    ui.focus_and_type(ui.find("startNote"), "go build it")
    n = ui.store.contexts.model.count()
    ui.click(ui.find("startButton"))
    row = ui.store.stories.get(key)
    assert row["phase"] == "planning" and row["ball"] == "cast" and row["castCount"] == 1
    assert ui.store.contexts.model.count() == n + 1
    assert ui.find("storyPhase").property("text") == "planning" and ui.find("storyBall").property("text") == "cast"
    assert not ui.has("startButton") or not ui.visible(ui.find("startButton"))
    assert ui.visible(ui.find("cancelButton")) and not ui.visible(ui.find("proceedButton"))
    chr_id = row["protagonist"]
    assert ui.has(f"castRow_{chr_id}")
    comments = ui.store.stories.comments(key)
    assert ui.has(f"comment_{comments[0]['id']}")
    ctx = ui.store.contexts.get(ui.store.stories.character(chr_id)["live_context"])
    assert wait_until(lambda: ctx.status == "idle"), (ctx.status, ctx.lastError)


def test_question_yield_renders_options_and_clicking_one_replies(ui):
    key = ui.store.stories.create("Q", "")
    chr_id = ui.store.stories.start(key, "", "protagonist")
    open_story(ui, key)
    c = ui.store.stories.cast_yield(chr_id, "question", "pg or sqlite?", options=["pg", "sqlite"])
    QTest.qWait(80)
    assert ui.visible(ui.find("needsYouBanner")) and "question" in ui.find("needsYouBanner").property("text")
    assert ui.find("needsYouCount").property("text").startswith("1 need")
    assert ui.visible(ui.find(f"cardBadge_{key}"))
    ui.click(ui.find(f"optionButton_{c['id']}_1"))
    assert ui.store.stories.get(key)["ball"] == "cast"
    last = ui.store.stories.comments(key)[-1]
    assert last["body"] == "sqlite" and last["reply_to"] == c["id"]
    assert not ui.visible(ui.find("needsYouBanner"))


def test_reply_composer_posts_a_human_comment(ui):
    key = ui.store.stories.create("R", "")
    ui.store.stories.start(key, "", "protagonist")
    open_story(ui, key)
    n = len(ui.store.stories.comments(key))
    ui.focus_and_type(ui.find("replyInput"), "btw use sqlite")
    ui.click(ui.find("replyButton"))
    comments = ui.store.stories.comments(key)
    assert len(comments) == n + 1 and comments[-1]["body"] == "btw use sqlite" and comments[-1]["authorName"] == "you"
    assert ui.find("replyInput").property("text") == ""


def test_action_bar_follows_the_cell(ui):
    key = ui.store.stories.create("Bar", "")
    chr_id = ui.store.stories.start(key, "", "protagonist")
    open_story(ui, key)
    ui.store.stories.cast_yield(chr_id, "handoff", "the outline")
    QTest.qWait(80)
    assert ui.visible(ui.find("proceedButton")) and not ui.visible(ui.find("approveButton"))
    ui.click(ui.find("proceedButton"))
    assert ui.store.stories.get(key)["phase"] == "implementing"
    assert ui.find("storyPhase").property("text") == "implementing"
    ui.store.stories.cast_yield(chr_id, "handoff", "built it")
    QTest.qWait(80)
    assert ui.visible(ui.find("approveButton")) and ui.visible(ui.find("backButton"))
    ui.click(ui.find("backButton"))
    assert ui.store.stories.get(key)["phase"] == "planning"
    ui.store.stories.cast_yield(chr_id, "handoff", "outline v2")
    ui.store.stories.proceed(key)
    ui.store.stories.cast_yield(chr_id, "handoff", "built v2")
    QTest.qWait(80)
    ui.click(ui.find("approveButton"))
    assert ui.store.stories.get(key)["phase"] == "done"
    assert ui.visible(ui.find("reopenButton")) and not ui.visible(ui.find("cancelButton"))
    ui.click(ui.find("reopenButton"))
    assert ui.store.stories.get(key)["phase"] == "implementing"
    ui.click(ui.find("cancelButton"))
    assert ui.store.stories.get(key)["phase"] == "canceled"


def test_cast_row_opens_the_protagonist_context(ui):
    key = ui.store.stories.create("Cast", "")
    chr_id = ui.store.stories.start(key, "", "protagonist")
    open_story(ui, key)
    ui.click(ui.find(f"castRow_{chr_id}"))
    cid = ui.store.stories.character(chr_id)["live_context"]
    assert ui.has(f"tab_context_{cid}")
    ui.click(ui.find("contextStoryLink"))
    assert ui.has(f"tab_story_{key}")


def test_unknown_story_tab_explains_itself(ui):
    open_story(ui, "ZZZ-999")
    assert "not found" in ui.find("storyMissing").property("text").lower()
    assert not ui.has("startButton") or not ui.visible(ui.find("startButton"))


def test_tree_groups_count_stories_by_phase(ui):
    before = ui.find("treeGroup_planning").property("count")
    key = ui.store.stories.create("Grouped", "")
    ui.store.stories.start(key, "", "protagonist")
    QTest.qWait(80)
    assert ui.find("treeGroup_planning").property("count") == before + 1
    assert ui.visible(ui.find(f"card_{key}"))


def test_cast_panel_follows_the_active_story_tab(ui):
    a = ui.store.stories.create("A", "")
    b = ui.store.stories.create("B", "")
    ca = ui.store.stories.start(a, "", "protagonist")
    cb = ui.store.stories.start(b, "", "protagonist")
    open_story(ui, a)
    assert ui.visible(ui.find(f"castRow_{ca}")) and not ui.has(f"castRow_{cb}")
    open_story(ui, b)
    assert ui.visible(ui.find(f"castRow_{cb}")) and not ui.has(f"castRow_{ca}")
    ui.store.layout.openContent("welcome", "welcome", "Welcome")  # non-story tab: the cast stays on B
    QTest.qWait(80)
    assert ui.has(f"castRow_{cb}")
