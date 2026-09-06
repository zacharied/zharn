"""Board + story page through the real controls: create, edit, Start, yields as option buttons, the author's action bar."""
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from ui import OUT, start, wait_until


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
    ui.focus_and_type(ui.find("startNote"), "go build it")
    n = ui.store.contexts.model.count()
    ui.click(ui.find("startButton"))
    row = ui.store.stories.get(key)
    assert row["phase"] == "planning" and row["ball"] == "cast" and row["castCount"] == 1
    assert ui.store.contexts.model.count() == n + 1
    assert ui.find("storyPhase").property("text") == "planning" and ui.find("storyBall").property("text").startswith("cast")
    assert not ui.has("startButton") or not ui.visible(ui.find("startButton"))
    assert ui.visible(ui.find("cancelButton")) and not ui.visible(ui.find("proceedButton"))
    chr_id = row["protagonist"]
    assert ui.has(f"castRow_{chr_id}")
    comments = ui.store.stories.comments(key)
    assert ui.has(f"comment_{comments[0]['id']}")
    ctx = ui.store.contexts.get(ui.store.stories.character(chr_id)["live_context"])
    assert wait_until(lambda: ctx.status == "idle"), (ctx.status, ctx.lastError)


def test_question_yield_renders_rows_and_reply_posts_the_picks(ui):
    key = ui.store.stories.create("Q", "")
    ui.store.stories.start(key, "yield-question")     # the fake protagonist asks one question (a, b)
    open_story(ui, key)
    assert wait_until(lambda: any(r["kind"] == "question" for r in ui.store.stories.comments(key)))
    c = next(r for r in ui.store.stories.comments(key) if r["kind"] == "question")
    QTest.qWait(80)
    assert ui.visible(ui.find("needsYouBanner")) and "question" in ui.find("needsYouBanner").property("text")
    expected = sum(1 for r in ui.store.stories.list() if r["needsYou"])   # other stories may need you too
    assert expected >= 1 and ui.find("needsYouCount").property("text").startswith(f"{expected} need")
    assert ui.visible(ui.find(f"cardBadge_{key}"))
    assert ui.find(f"questionRow_{c['id']}_0").property("text") == "1. which one?"
    assert not ui.find("replyButton").property("enabled")
    ui.click(ui.find(f"optionButton_{c['id']}_0_1"))
    assert ui.store.stories.get(key)["ball"] == "author"              # a pick alone posts nothing
    assert ui.find("replyButton").property("enabled") and ui.find(f"optionButton_{c['id']}_0_1").property("icon_") == "check"
    ui.focus_and_type(ui.find("replyInput"), "and slowly")           # the reply resumes the fake, which dawdles on "slow":
    ui.click(ui.find("replyButton"))                                 # the ball stays with the cast while we read the view
    assert ui.store.stories.get(key)["ball"] == "cast"
    last = ui.store.stories.comments(key)[-1]
    assert last["body"] == "1. b\nand slowly" and last["reply_to"] == c["id"] and last["structured"]["answers"] == ["b"]
    assert not ui.visible(ui.find("needsYouBanner"))
    assert ui.find(f"optionButton_{c['id']}_0_1").property("icon_") == "check"     # the pick stays marked
    assert ui.find(f"optionButton_{c['id']}_0_0").property("icon_") == "" and ui.find("replyInput").property("text") == ""


def test_reply_composer_posts_a_human_comment(ui):
    key = ui.store.stories.create("R", "")
    ui.store.stories.start(key, "")
    open_story(ui, key)
    n = len(ui.store.stories.comments(key))
    ui.focus_and_type(ui.find("replyInput"), "btw use sqlite")
    ui.click(ui.find("replyButton"))
    comments = ui.store.stories.comments(key)
    assert len(comments) == n + 1 and comments[-1]["body"] == "btw use sqlite" and comments[-1]["authorName"] == "you"
    assert ui.find("replyInput").property("text") == ""


def test_action_bar_follows_the_cell(ui):
    key = ui.store.stories.create("Bar", "")
    chr_id = ui.store.stories.start(key, "")
    ui.store.stories.cast_yield(chr_id, "handoff", "the outline")   # before the character's own turn can finish and auto-yield
    open_story(ui, key)
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
    chr_id = ui.store.stories.start(key, "")
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
    ui.store.stories.start(key, "")
    QTest.qWait(80)
    assert ui.find("treeGroup_planning").property("count") == before + 1
    assert ui.visible(ui.find(f"card_{key}"))


def test_cast_panel_follows_the_active_story_tab(ui):
    a = ui.store.stories.create("A", "")
    b = ui.store.stories.create("B", "")
    ca = ui.store.stories.start(a, "")
    cb = ui.store.stories.start(b, "")
    open_story(ui, a)
    assert ui.visible(ui.find(f"castRow_{ca}")) and not ui.has(f"castRow_{cb}")
    open_story(ui, b)
    assert ui.visible(ui.find(f"castRow_{cb}")) and not ui.has(f"castRow_{ca}")
    ui.store.layout.openContent("welcome", "welcome", "Welcome")  # non-story tab: the cast stays on B
    QTest.qWait(80)
    assert ui.has(f"castRow_{cb}")


def test_aside_button_opens_a_private_context_and_reopens_it(ui):
    key = ui.store.stories.create("Aside me", "")
    chr_id = ui.store.stories.start(key, "yield-question")   # the fake protagonist asks, then idles
    ctx = ui.store.contexts.get(ui.store.stories.character(chr_id)["live_context"])
    assert wait_until(lambda: any(r["kind"] == "question" for r in ui.store.stories.comments(key))), \
        [(r["role"], r["kind"], (r.get("text") or "")[:200]) for r in ctx.transcript.rows()]
    assert wait_until(lambda: ctx.status == "idle")
    c = next(r for r in ui.store.stories.comments(key) if r["kind"] == "question")
    open_story(ui, key)
    name = f"asideButton_{c['id']}"
    ui.hover(ui.find("storyTitle"))                      # park the pointer away from the comment
    assert not ui.find_all(name)[0].isVisible()          # ghost: nothing until hover
    ui.hover(ui.find(f"comment_{c['id']}"))
    ui.click(ui.find(name))
    aside_id = next(r for r in ui.store.stories.comments(key) if r["id"] == c["id"])["asideId"]
    assert aside_id
    a = ui.store.contexts.get(aside_id)
    assert a.owner == "human" and a.storyKey == "" and a.title == "aside on #1 · Protagonist"
    import json
    docks = json.loads(ui.store.layout.layoutJson)["docks"]
    assert docks["bottom"] == {**docks["bottom"], "active": "contexts", "mode": "docked"}
    assert ui.find("paneContextTitle").property("text") == a.title
    assert ui.has(f"contextRow_{aside_id}")              # listed under its story, not under Bare
    ui.hover(ui.find("storyTitle"))                      # pointer away: the pill persists once an aside exists
    btn = ui.find(name)
    assert ui.visible(btn)
    n = ui.store.contexts.model.count()
    ui.click(btn)                                        # idempotent: reopens, creates nothing
    assert ui.store.contexts.model.count() == n
    assert next(r for r in ui.store.stories.comments(key) if r["id"] == c["id"])["asideId"] == aside_id
    ui.store.layout.setDockMode("bottom", "strip")


def test_new_thread_composer_routes_by_prefix(ui):
    key = ui.store.stories.create("Composer", "")
    chr_id = ui.store.stories.start(key, "")
    ctx = ui.store.contexts.get(ui.store.stories.character(chr_id)["live_context"])
    assert wait_until(lambda: ctx.status == "idle")
    open_story(ui, key)
    ui.focus_and_type(ui.find("newThreadInput"), "why this way?")
    ui.click(ui.find("newThreadButton"))
    threads = ui.store.stories.get(key)["threads"]
    assert threads[-1]["lead"] == chr_id and ui.find("newThreadInput").property("text") == ""
    assert ui.has(f"thread_{threads[-1]['id']}")
    ui.focus_and_type(ui.find("newThreadInput"), "/call Reviewer review the outline")
    ui.click(ui.find("newThreadButton"))
    cast = ui.store.stories.cast(key)
    assert len(cast) == 2 and cast[-1]["name"] == "Reviewer" and cast[-1]["position"] == "friend"
    assert ui.store.stories.get(key)["threads"][-1]["lead"] == cast[-1]["id"]
    assert ui.has(f"castRow_{cast[-1]['id']}")


def test_typing_in_a_character_context_is_the_comment_channel(ui):
    key = ui.store.stories.create("Speak", "")
    chr_id = ui.store.stories.start(key, "")
    ctx = ui.store.contexts.get(ui.store.stories.character(chr_id)["live_context"])
    assert wait_until(lambda: ctx.status == "idle")
    ui.store.layout.openContent("context", ctx.id, "ctx")
    QTest.qWait(120)
    n = len(ui.store.stories.comments(key))
    ui.focus_and_type(ui.find("promptInput"), "steering note")
    ui.click(ui.find("sendButton"))
    comments = ui.store.stories.comments(key)
    assert len(comments) == n + 1 and comments[-1]["body"] == "steering note" and comments[-1]["author"] == "human"
    assert ui.find("promptInput").property("text") == ""


def test_start_row_picks_reach_the_new_protagonist(ui):
    key = ui.store.stories.create("Picky", "d")
    open_story(ui, key)
    ui.choose(ui.find("startModel"), "Sonnet 5")      # the label is shown; the id is what is sent
    ui.choose(ui.find("startEffort"), "low")
    ui.choose(ui.find("startPreset"), "builder")
    ui.click(ui.find("startButton"))
    ch = ui.store.stories.character(ui.store.stories.get(key)["protagonist"])
    assert (ch["model"], ch["effort"], ch["preset"]) == ("claude-sonnet-5", "low", "builder")
    assert ch["position"] == "protagonist"            # nobody picked it: the Start row implies it
    cast = ui.store.contexts.get(ch["live_context"]).meta["cast"]
    assert (cast["model"], cast["effort"], cast["preset"]) == ("claude-sonnet-5", "low", "builder")


def test_start_row_is_seeded_with_the_positions_own_picks(ui):
    """The row reads as what pressing Start will do. A blank that quietly means something else is a lie:
    the protagonist position is cli default / high / full, so that is what the three combos show."""
    key = ui.store.stories.create("Default me", "d")
    open_story(ui, key)
    assert ui.find("startModel").property("editText") == "cli default"
    assert ui.find("startEffort").property("currentText") == "high"
    assert ui.find("startPreset").property("currentText") == "full"
    ui.click(ui.find("startButton"))
    ch = ui.store.stories.character(ui.store.stories.get(key)["protagonist"])
    assert (ch["model"], ch["effort"], ch["preset"]) == ("", "high", "full")


def test_the_start_row_can_pick_the_providers_own_effort(ui):
    """The empty entry in config.EFFORTS is a choice, and choosing it has to reach the character."""
    key = ui.store.stories.create("Bare effort", "d")
    open_story(ui, key)
    ui.choose(ui.find("startEffort"), "provider default")
    ui.click(ui.find("startButton"))
    ch = ui.store.stories.character(ui.store.stories.get(key)["protagonist"])
    assert ch["effort"] == ""                              # not the position's "high"
    assert ui.store.contexts.get(ch["live_context"]).meta["cast"]["effort"] == ""


def test_reopen_menu_offers_recast_and_reopens_on_a_fresh_context(ui):
    key = ui.store.stories.create("Reopenable", "")
    chr_id = ui.store.stories.start(key, "")
    ctx = ui.store.contexts.get(ui.store.stories.character(chr_id)["live_context"])
    assert wait_until(lambda: ctx.status == "idle")       # quiet check: outline handoff
    ui.store.stories.proceed(key)
    assert wait_until(lambda: ui.store.contexts.get(ui.store.stories.character(chr_id)["live_context"]).status == "idle")
    ui.store.stories.approve(key)
    open_story(ui, key)
    old_ctx = ui.store.stories.character(chr_id)["live_context"]
    assert ui.visible(ui.find("reopenButton")) and ui.find("reopenButton").property("text") == "Reopen"
    ui.click(ui.find("reopenMenuButton"))
    ui.click(ui.find("reopenMenuItem_1"))                 # Recast and reopen…
    ui.choose(ui.find("recastModel"), "Sonnet 5")
    ui.click(ui.find("recastConfirm"))
    ch = ui.store.stories.character(chr_id)
    assert ch["model"] == "claude-sonnet-5" and ch["live_context"] != old_ctx
    assert ui.store.contexts.get(ch["live_context"]).meta["cast"]["model"] == "claude-sonnet-5"
    assert ui.store.stories.get(key)["phase"] == "implementing"


def fresh_repo(name, **kw):
    """A real git repo under tests/_out, recreated per run so branches from the last run cannot collide."""
    import shutil
    from gitfix import make_repo
    d = OUT / name
    shutil.rmtree(d, ignore_errors=True)
    return make_repo(d)


def test_story_page_shows_environments_and_folds_passing_checks(ui):
    from harness.environments import register_repo
    register_repo(ui.store.stories.workspace, str(fresh_repo("ui-story-repo")), name="api", checks="echo ok")
    key = ui.store.stories.create("Envs", "")
    chr_id = ui.store.stories.start(key, "")
    ctx = ui.store.contexts.get(ui.store.stories.character(chr_id)["live_context"])
    assert wait_until(lambda: ctx.status == "idle")          # quiet check: outline handoff waits on you
    open_story(ui, key)
    assert not ui.has("storyEnv_api")                        # a story starts with no environments (spec §4.4)
    ui.store.stories.cast_env_open(chr_id, "api")
    QTest.qWait(80)
    assert ui.visible(ui.find("storyEnv_api"))
    assert ui.find("storyEnvBranch_api").property("text") == f"zharn/{key}"
    assert ui.find("storyEnvInto_api").property("text") == "into main"
    ui.store.stories.proceed(key)                            # implementing; the character resumes
    ui.store.stories.cast_yield(chr_id, "handoff", "built it", checks=[
        {"repo": "api", "cmd": "echo ok", "exit": 0, "output": "ok"},
        {"repo": "web", "cmd": "npm test", "exit": 1, "output": "1 failed"}])
    # the resumed process still has its own (irrelevant) turn in flight; let it settle now rather
    # than racing its trailing refresh against the fold-toggle click below.
    assert wait_until(lambda: ctx.status not in ("starting", "working"))
    QTest.qWait(80)
    c = ui.store.stories.comments(key)[-1]
    assert ui.find("checksFailingChip").property("text") == "1 check failing"
    assert not ui.visible(ui.find(f"checkOutput_{c['id']}_0"))   # passed: folded
    assert ui.visible(ui.find(f"checkOutput_{c['id']}_1"))       # failed: open
    ui.click(ui.find(f"checkRow_{c['id']}_0"))
    assert ui.visible(ui.find(f"checkOutput_{c['id']}_0"))
    ui.store.stories.approve(key)
    QTest.qWait(80)
    assert not ui.visible(ui.find("checksFailingChip"))          # the chip belongs to the handoff that waits on you
    last = ui.store.stories.comments(key)[-1]
    assert last["body"].splitlines()[1] == f"merged zharn/{key} → main in api (no changes)"
    assert ui.find(f"comment_{last['id']}")                      # the stage direction renders with its merged line
    assert wait_until(lambda: not ui.has("storyEnv_api"))         # swept once the protagonist's turn ended (§4.8)


# ---- ZHAR-4: an edit in progress is not thrown away by a refresh
#
# Every status transition of every live context emits contextsChanged (contexts.py: _context_changed),
# StoryStore._refresh turns that into storiesChanged, and the story page refreshes. None of that is
# about the story you are typing into, so a reset that follows it looks random.

def churn(ui):
    """What a working agent emits many times a turn — a context changed status, nothing else."""
    ui.store.contexts.contextsChanged.emit()
    QTest.qWait(60)


def test_a_half_typed_title_survives_an_unrelated_context_change(ui):
    key = ui.store.stories.create("", "")      # empty, so typing is the only writer — setProperty would drop the binding
    open_story(ui, key)
    ui.focus_and_type(ui.find("storyTitleEdit"), "Half typ")
    churn(ui)
    assert ui.find("storyTitleEdit").property("text") == "Half typ"


def test_a_half_typed_description_survives_an_unrelated_context_change(ui):
    key = ui.store.stories.create("Desc", "")
    open_story(ui, key)
    ui.focus_and_type(ui.find("storyDescriptionEdit"), "why it matters")
    churn(ui)
    assert ui.find("storyDescriptionEdit").property("text") == "why it matters"


def settled_story(ui, title):
    """A started story whose protagonist has finished its turn — so the only thing that moves next is the test."""
    key = ui.store.stories.create(title, "")
    chr_id = ui.store.stories.start(key, "")
    ctx = ui.store.contexts.get(ui.store.stories.character(chr_id)["live_context"])
    assert wait_until(lambda: ctx.status == "idle"), ctx.status
    open_story(ui, key)
    return key, chr_id


# The two below cover the reported symptom but do not discriminate: neither trigger changed the thread
# rows, so the old array-model Repeater left the delegate alone and they passed against the bug too.
# The regression guards are the four that name a focus, a call, a turn or a fold.
def test_a_half_typed_reply_survives_an_unrelated_context_change(ui):
    key, chr_id = settled_story(ui, "Reply churn")
    ui.focus_and_type(ui.find("replyInput"), "btw use sqlite")
    churn(ui)
    assert ui.find("replyInput").property("text") == "btw use sqlite"


def test_a_half_typed_reply_survives_a_comment_arriving_from_the_cast(ui):
    key, chr_id = settled_story(ui, "Reply comment")
    ui.focus_and_type(ui.find("replyInput"), "half a thought")
    ui.store.stories.cast_comment(chr_id, "meanwhile, from the agent")
    QTest.qWait(80)
    assert ui.find("replyInput").property("text") == "half a thought"


def test_a_half_typed_reply_keeps_its_focus_when_the_turn_changes(ui):
    """No thread appears — only the rows change — so the delegate holding the composer must not be rebuilt."""
    key, chr_id = settled_story(ui, "Reply turn")
    ui.focus_and_type(ui.find("replyInput"), "still typing")
    ui.store.stories.comment(key, "a note from elsewhere")     # main thread's turn flips back to the cast
    QTest.qWait(120)
    assert ui.store.stories.get(key)["ball"] == "cast"          # the change really landed
    assert ui.find("replyInput").property("text") == "still typing"
    assert ui.find("replyInput").property("activeFocus")        # the caret is still where you left it


def test_a_half_typed_reply_survives_the_protagonist_calling_a_friend(ui):
    """A thread appears, so the rows the Repeater is given really change and it rebuilds its delegates."""
    key, chr_id = settled_story(ui, "Reply call")
    n = len(ui.store.stories.get(key)["threads"])
    ui.focus_and_type(ui.find("replyInput"), "one more thing")
    ui.store.stories.cast_call(chr_id, "review the outline")
    QTest.qWait(120)
    assert len(ui.store.stories.get(key)["threads"]) == n + 1      # the change really landed
    assert ui.find("replyInput").property("text") == "one more thing"


def test_an_unfolded_check_stays_unfolded_when_a_comment_arrives(ui):
    """The same bug one Repeater deeper: comment rows change on every comment, so the delegate
    holding a check's fold must not be rebuilt either."""
    from harness.environments import register_repo
    register_repo(ui.store.stories.workspace, str(fresh_repo("ui-story-fold")), name="fold", checks="echo ok")
    key = ui.store.stories.create("Fold", "")
    chr_id = ui.store.stories.start(key, "")
    ctx = ui.store.contexts.get(ui.store.stories.character(chr_id)["live_context"])
    assert wait_until(lambda: ctx.status == "idle")
    open_story(ui, key)
    ui.store.stories.proceed(key)
    ui.store.stories.cast_yield(chr_id, "handoff", "built it",
                                checks=[{"repo": "fold", "cmd": "echo ok", "exit": 0, "output": "ok"}])
    assert wait_until(lambda: ctx.status not in ("starting", "working"))
    QTest.qWait(80)
    c = ui.store.stories.comments(key)[-1]
    ui.click(ui.find(f"checkRow_{c['id']}_0"))                    # you unfold a passing check to read it
    assert ui.visible(ui.find(f"checkOutput_{c['id']}_0"))
    ui.store.stories.comment(key, "a note from elsewhere")        # and a comment lands on the story
    QTest.qWait(120)
    assert ui.visible(ui.find(f"checkOutput_{c['id']}_0"))


# ---------------------------------------------------------------- selectable text
# The page is a Flickable full of prose. A mouse drag used to pan it like a touch screen;
# it now selects text, and only the wheel and the scrollbar scroll (ZHAR-3).

LOREM = ("The quick brown fox jumps over the lazy dog while the harness watches, "
         "and the sentence runs on long enough to select a piece of it.")


def selectable_story(ui, comments=14):
    key = ui.store.stories.create("Selectable", LOREM)
    ui.store.stories.start(key, "")
    for i in range(comments):
        ui.store.stories.comment(key, f"{i}. {LOREM}")
    open_story(ui, key)
    QTest.qWait(120)
    return key


def test_dragging_across_the_description_selects_text(ui):
    selectable_story(ui, comments=0)
    desc = ui.find("storyDescription")
    ui.drag_across(desc)
    sel = desc.property("selectedText")
    assert sel, "dragging across the description selected nothing"
    assert sel in desc.property("text")


def test_dragging_across_a_comment_body_selects_text(ui):
    key = selectable_story(ui, comments=1)
    cid = ui.store.stories.comments(key)[-1]["id"]
    body = ui.find(f"commentBody_{cid}")
    ui.drag_across(body)
    sel = body.property("selectedText")
    assert sel, "dragging across a comment body selected nothing"
    assert sel in body.property("text")


def test_dragging_the_page_does_not_scroll_it(ui):
    selectable_story(ui)
    flick = ui.find("storyScroll")
    assert flick.property("contentHeight") > flick.property("height"), "story page is not scrollable; test proves nothing"
    before = flick.property("contentY")
    h = flick.property("height")
    ui.drag(QPoint(int(flick.property("width")) - 40, int(h) - 60), QPoint(int(flick.property("width")) - 40, 60))
    assert flick.property("contentY") == before, "the page panned on a mouse drag"


def test_wheel_still_scrolls_the_page(ui):
    selectable_story(ui)
    flick = ui.find("storyScroll")
    before = flick.property("contentY")
    ui.wheel(flick, notches=-1)
    assert flick.property("contentY") > before, "the wheel no longer scrolls the page"
    ui.wheel(flick, notches=1)
    assert flick.property("contentY") == before, "the wheel does not scroll back up"
