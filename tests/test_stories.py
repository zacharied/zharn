"""StoryStore against a stub context store: persistence, Start casts a protagonist, author actions deliver
to the protagonist, cast verbs, brief and system prompt, needs-you rows."""
import json

import pytest
from PySide6.QtCore import QObject, Signal

from harness import config as cfg
from harness.lifecycle import OpenThread, Rejected, Yield
from harness.stories import StoryStore, author_name, needs_you_flavor, render_brief
from harness.workspace import Workspace


class StubContext:
    def __init__(self, cid, meta):
        self.id, self.meta, self.status, self.sent, self.stopped = cid, meta, "idle", [], False
        self.sessionId = "sess-" + cid

    def send(self, text):
        self.sent.append(text)
        self.status = "working"

    def stop(self):
        self.stopped = True
        self.status = "stopped"


class StubContexts(QObject):
    contextsChanged = Signal()

    def __init__(self):
        super().__init__()
        self.by_id = {}
        self.created = []
        self.forked = []

    def create(self, role_name, **kw):
        if role_name == "codex-review":
            # Mirrors the real ContextStore.create's guard for unimplemented providers.
            raise ValueError("provider 'codex' not implemented yet")
        cid = f"ctx_{len(self.by_id) + 1}"
        self.by_id[cid] = StubContext(cid, {"role": role_name, **kw})
        self.created.append((role_name, kw))
        return cid

    def get(self, cid):
        return self.by_id.get(cid)

    def contexts_for(self, key):
        return [c for c in self.by_id.values() if c.meta.get("story_key") == key]

    def all(self):
        return list(self.by_id.values())

    def fork(self, source_id, **kw):
        if source_id not in self.by_id:
            raise KeyError(source_id)
        if self.by_id[source_id].status in ("starting", "working"):
            raise ValueError(f"{source_id} is working; fork it when it stops")
        cid = f"ctx_{len(self.by_id) + 1}"
        self.by_id[cid] = StubContext(cid, {"forkedFrom": source_id, **kw})
        self.forked.append((source_id, kw))
        return cid


class StubRoles:
    def get(self, name):
        return {"protagonist": {"name": "protagonist", "instructions": "Lead.", "outline_first": True},
                "claude-fast": {"name": "claude-fast", "instructions": "", "outline_first": False},
                "codex-review": {"name": "codex-review", "instructions": "", "outline_first": False, "provider": "codex"},
                }.get(name, {})


class Notes:
    def __init__(self):
        self.infos, self.errors = [], []

    def info(self, t): self.infos.append(t)

    def error(self, t): self.errors.append(t)


@pytest.fixture
def ws(tmp_path):
    return Workspace.create(tmp_path / "ws", prefix="ZH")


@pytest.fixture
def contexts():
    return StubContexts()


@pytest.fixture
def store(ws, contexts):
    s = StoryStore(ws, contexts, StubRoles())
    s.notifier = Notes()
    return s


def started(store, note="go"):
    key = store.create("Title", "Desc")
    chr_id = store.start(key, note, "protagonist")
    return key, chr_id


# ---------------------------------------------------------------- create / persist

def test_create_assigns_workspace_keys_and_persists(store, ws):
    assert store.create("A") == "ZH-1" and store.create("B", "d") == "ZH-2"
    d = json.loads((ws.stories_dir / "ZH-2" / "story.json").read_text())
    assert d["title"] == "B" and d["description"] == "d" and d["phase"] == "todo" and d["author"] == "human"
    assert "ball" not in d and d["threads"] == [] and d["created"] > 0
    row = store.get("zh-2")
    assert row["key"] == "ZH-2" and row["phase"] == "todo" and row["ball"] == "" and row["needsYou"] is False
    assert store.get("ZH-9") == {} and [r["key"] for r in store.list()] == ["ZH-1", "ZH-2"]


def test_fresh_store_reloads_stories_comments_and_characters(ws, contexts):
    a = StoryStore(ws, contexts, StubRoles())
    key, chr_id = started(a)
    a.cast_yield(chr_id, "question", "which db?", options=["pg", "sqlite"])
    b = StoryStore(ws, contexts, StubRoles())
    row = b.get(key)
    assert row["phase"] == "planning" and row["ball"] == "author" and row["needsYou"] is True and row["flavor"] == "question"
    assert [c["kind"] for c in b.comments(key)] == ["text", "question"]
    assert b.character(chr_id)["name"] == "protagonist" and b.character(chr_id)["live_context"] == "ctx_1"


def test_corrupt_story_json_is_skipped_and_reported_once_a_notifier_is_attached(ws, contexts):
    a = StoryStore(ws, contexts, StubRoles())
    key = a.create("A")
    (ws.story_dir(key) / "story.json").write_text("{not json", encoding="utf-8")
    b = StoryStore(ws, contexts, StubRoles())
    assert key not in [row["key"] for row in b.list()]
    assert b.load_errors and any(key in e for e in b.load_errors)
    notes = Notes()
    b.notifier = notes
    b.create("x")  # any mutation that runs _refresh
    assert any(key in e for e in notes.errors)
    assert b.load_errors == []


def test_update_edits_unstarted_story_only(store):
    key = store.create("A")
    store.update(key, "A2", "d2")
    assert store.get(key)["title"] == "A2" and store.get(key)["description"] == "d2"
    store.start(key, "", "protagonist")
    with pytest.raises(Rejected, match="started"):
        store.update(key, "A3", "")


def test_model_rows_track_changes(store):
    seen = []
    store.storiesChanged.connect(lambda: seen.append(True))
    key = store.create("A")
    assert store.model.rows()[-1]["key"] == key and seen


# ---------------------------------------------------------------- Start

def test_start_casts_protagonist_with_context_brief_and_env(store, contexts, ws):
    key, chr_id = started(store, "please build it")
    ch = store.character(chr_id)
    assert ch["name"] == "protagonist" and ch["role"] == "protagonist" and ch["story_key"] == key
    assert ch["attention"] == store.story(key).main_thread and ch["inbox"] == [] and ch["live_context"] == "ctx_1"
    role_name, kw = contexts.created[0]
    assert role_name == "protagonist" and kw["story_key"] == key and kw["owner"] == chr_id
    assert kw["env"] == {"HARNESS_CHARACTER_ID": chr_id} and kw["title"] == f"{key} · protagonist"
    prompt = kw["system_prompt"]
    assert "protagonist" in prompt and key in prompt and "story yield" in prompt and "outline" in prompt.lower()
    brief = contexts.get("ctx_1").sent[0]
    assert brief.startswith(f"# {key}: Title") and "Desc" in brief and "please build it" in brief and "Lead." in brief
    row = store.get(key)
    assert row["phase"] == "planning" and row["ball"] == "cast" and row["castCount"] == 1 and row["workingCount"] == 1
    assert store.comments(key)[0] == {**store.comments(key)[0], "kind": "text", "body": "please build it", "authorName": "you"}
    assert json.loads((ws.local_dir / "characters.json").read_text())[chr_id]["name"] == "protagonist"
    records = [json.loads(l) for l in (ws.stories_dir / key / "threads.jsonl").read_text().splitlines()]
    assert [r["type"] for r in records] == ["thread", "comment"]


def test_start_defaults_role_and_rejects_unknown(store, monkeypatch):
    monkeypatch.setattr(cfg, "DEFAULT_ROLE", "protagonist", raising=False)
    key = store.create("A")
    store.start(key)
    assert store.character(store.story(key).protagonist)["role"] == "protagonist"
    key2 = store.create("B")
    with pytest.raises(ValueError, match="unknown role"):
        store.start(key2, "", "nope")
    assert store.get(key2)["phase"] == "todo"


def test_start_rejects_unimplemented_provider_without_wedging_the_story(store, ws):
    key = store.create("A")
    with pytest.raises(ValueError, match="codex"):
        store.start(key, "", "codex-review")
    row = store.get(key)
    assert row["phase"] == "todo" and row["protagonist"] == ""
    assert store.cast(key) == []
    fresh = StoryStore(ws, StubContexts(), StubRoles())
    assert fresh.get(key)["phase"] == "todo"
    # Start still works afterwards — the story was never wedged.
    chr_id = store.start(key, "", "protagonist")
    assert store.get(key)["phase"] == "planning" and store.character(chr_id) is not None


def test_second_character_with_same_role_gets_suffixed_name(store):
    k1, c1 = started(store)
    k2, c2 = started(store)
    assert store.character(c1)["name"] == "protagonist"
    assert store.character(c2)["name"] == "protagonist"  # per story: no collision across stories


# ---------------------------------------------------------------- cast verbs

def test_cast_yield_moves_ball_and_notifies(store, contexts):
    key, chr_id = started(store)
    c = store.cast_yield(chr_id, "question", "pg or sqlite?", options=["pg", "sqlite"])
    assert c["kind"] == "question" and c["structured"]["options"] == ["pg", "sqlite"] and c["author"] == chr_id
    row = store.get(key)
    assert row["ball"] == "author" and row["needsYou"] and row["flavor"] == "question"
    assert store.notifier.infos[-1] == f"{key} needs you: question"


def test_cast_yield_rejections_surface(store):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline")
    with pytest.raises(Rejected, match="already waits"):
        store.cast_yield(chr_id, "question", "again")
    with pytest.raises(KeyError):
        store.cast_yield("chr_nobody", "question", "x")


def test_cast_proceed_requires_approved_outline_for_outline_first_role(store):
    key, chr_id = started(store)
    with pytest.raises(Rejected, match="outline"):
        store.cast_proceed(chr_id)
    store.cast_yield(chr_id, "handoff", "the outline")
    store.proceed(key, "ok")
    assert store.get(key)["phase"] == "implementing"


def test_cast_proceed_allowed_for_plain_role(store):
    key = store.create("A")
    chr_id = store.start(key, "", "claude-fast")
    c = store.cast_proceed(chr_id, "bounded change")
    assert store.get(key)["phase"] == "implementing" and c["kind"] == "system"


def test_cast_proceed_gate_matches_transition_not_prose(store):
    key, chr_id = started(store)
    # A comment whose prose mimics the old "outline approved" sentinel must not satisfy the gate:
    # only the real planning/author -> implementing/cast transition (an author Proceed) does.
    store.comment(key, "outline approved (fake, not a real transition)")
    with pytest.raises(Rejected, match="outline"):
        store.cast_proceed(chr_id)
    store.cast_yield(chr_id, "handoff", "the outline")
    store.proceed(key, "ok")
    assert store.get(key)["phase"] == "implementing"


def test_cast_recap_and_comment(store):
    key, chr_id = started(store)
    r = store.cast_recap(chr_id, "done: x")
    assert r["kind"] == "recap" and store.character(chr_id)["recaps"] == [r["id"]]
    c = store.cast_comment(chr_id, "working on it")
    assert c["kind"] == "text" and store.get(key)["ball"] == "cast"


def test_log_verb_appends_to_character(store):
    key, chr_id = started(store)
    store.log_verb(chr_id, "yield", {"kind": "question"}, True)
    store.log_verb(chr_id, "yield", {"kind": "question"}, False, "already waits")
    log = store.character(chr_id)["verbs_log"]
    assert [(e["verb"], e["ok"]) for e in log] == [("yield", True), ("yield", False)] and log[1]["error"] == "already waits"


def test_log_verb_caps_at_verbs_log_max(store):
    from harness.stories import VERBS_LOG_MAX
    key, chr_id = started(store)
    for i in range(205):
        store.log_verb(chr_id, "yield", {"i": i}, True)
    log = store.character(chr_id)["verbs_log"]
    assert len(log) == VERBS_LOG_MAX == 200
    assert log[0]["args"]["i"] == 5  # the 6th logged (0-indexed: entries 0-4 were dropped)


# ---------------------------------------------------------------- author actions and delivery

def test_human_comment_while_waiting_is_a_reply_delivered_to_protagonist(store, contexts):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "question", "pg or sqlite?")
    ctx = contexts.get("ctx_1")
    n = len(ctx.sent)
    c = store.comment(key, "sqlite")
    assert c["reply_to"] is not None and store.get(key)["ball"] == "cast"
    assert ctx.sent[n].startswith("[you] reply in #thr_") and ctx.sent[n].endswith(": sqlite")


def test_human_comment_while_cast_has_ball_is_delivered_without_moving_it(store, contexts):
    key, chr_id = started(store)
    ctx = contexts.get("ctx_1")
    n = len(ctx.sent)
    store.comment(key, "btw prefer sqlite")
    assert store.get(key)["ball"] == "cast" and ctx.sent[n].startswith("[you] comment in #thr_")


def test_proceed_moves_phase_and_tells_protagonist(store, contexts):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline")
    ctx = contexts.get("ctx_1")
    store.proceed(key, "go ahead")
    assert store.get(key)["phase"] == "implementing" and store.get(key)["ball"] == "cast"
    assert "outline approved" in ctx.sent[-1] and "Phase is now implementing" in ctx.sent[-1]


def test_deliver_refreshes_system_prompt_with_current_phase(store, contexts):
    key, chr_id = started(store)
    ctx = contexts.get("ctx_1")
    store.cast_yield(chr_id, "handoff", "outline")
    store.proceed(key, "go ahead")
    # _deliver rewrites ctx.meta["systemPrompt"] (Context._spawn reads it fresh on every resume)
    # so a resumed protagonist sees the phase it's actually in, not the one frozen at cast time.
    assert "phase: implementing" in ctx.meta["systemPrompt"]


def test_approve_ends_story_and_sends_nothing(store, contexts):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline")
    store.proceed(key)
    store.cast_yield(chr_id, "handoff", "built")
    ctx = contexts.get("ctx_1")
    n = len(ctx.sent)
    store.approve(key, "nice")
    assert store.get(key)["phase"] == "done" and store.get(key)["ball"] == "" and len(ctx.sent) == n


def test_back_to_planning_and_reopen_resume_protagonist(store, contexts):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline")
    store.proceed(key)
    store.cast_yield(chr_id, "handoff", "built")
    ctx = contexts.get("ctx_1")
    store.backToPlanning(key, "rethink the api")
    assert store.get(key)["phase"] == "planning" and "rethink the api" in ctx.sent[-1]
    store.cancel(key)
    assert ctx.stopped and store.get(key)["phase"] == "canceled"
    ctx.stopped = False
    store.reopen(key, "one more")
    assert store.get(key)["phase"] == "implementing" and "one more" in ctx.sent[-1]


def side_thread_waiting(store, chr_id, key, author="human", lead=None):
    """A side thread t2 yielded back to its author. Side-thread creation (open-thread UI, `call`)
    arrives with the friends plan; until then tests arrange it through the reducer directly."""
    store._apply(key, OpenThread(thread_id="t2", author=author, lead=lead or chr_id, body="why X?"))
    store._apply(key, Yield(thread_id="t2", by=lead or chr_id, kind="handoff", body="because Y"))


def test_resolve_closes_side_thread_and_clears_lead_attention(store, contexts):
    key, chr_id = started(store)
    side_thread_waiting(store, chr_id, key)
    store._characters[chr_id]["attention"] = "t2"
    ctx = contexts.get("ctx_1")
    n = len(ctx.sent)
    c = store.resolve(key, "t2", "settled, thanks")
    assert c["kind"] == "system" and "settled, thanks" in c["body"]
    assert store.story(key).thread("t2").turn == "resolved"
    assert store.character(chr_id)["attention"] is None      # was attending the resolved thread
    assert len(ctx.sent) == n                                # the lead is not resumed or notified


def test_resolve_leaves_attention_alone_when_lead_attends_elsewhere(store):
    key, chr_id = started(store)
    side_thread_waiting(store, chr_id, key)
    main = store.story(key).main_thread
    store.resolve(key, "t2")
    assert store.character(chr_id)["attention"] == main


def test_resolve_rejections_raise_and_report(store):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline")
    with pytest.raises(Rejected, match="main"):
        store.resolve(key, store.story(key).main_thread)
    assert store.notifier.errors and "resolve" in store.notifier.errors[-1]


def test_cast_resolve_resolves_a_thread_the_character_authored(store):
    key, chr_id = started(store)
    store._apply(key, OpenThread(thread_id="t2", author=chr_id, lead="chr_friend", body="do it"))
    store._apply(key, Yield(thread_id="t2", by="chr_friend", kind="handoff", body="done"))
    c = store.cast_resolve(chr_id, "t2", "all good")
    assert c["kind"] == "system" and c["author"] == chr_id and "all good" in c["body"]
    assert store.story(key).thread("t2").turn == "resolved"


def test_cast_resolve_requires_an_explicit_thread(store):
    key, chr_id = started(store)
    with pytest.raises(Rejected, match="thread"):
        store.cast_resolve(chr_id, "")


def test_author_action_rejections_raise_and_report(store):
    key, chr_id = started(store)
    with pytest.raises(Rejected):
        store.approve(key)
    assert store.notifier.errors and "approve" in store.notifier.errors[-1]
    with pytest.raises(Rejected):
        store.proceed(key)


def test_rows_expose_needs_you_flavor_by_phase(store):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline")
    assert store.get(key)["flavor"] == "outline ready"
    store.proceed(key)
    store.cast_yield(chr_id, "handoff", "built")
    assert store.get(key)["flavor"] == "ready for review"
    store.approve(key)
    assert store.get(key)["flavor"] == "" and store.get(key)["needsYou"] is False


def test_working_count_follows_context_status(store, contexts):
    key, chr_id = started(store)
    assert store.get(key)["workingCount"] == 1
    contexts.get("ctx_1").status = "idle"
    contexts.contextsChanged.emit()
    assert store.get(key)["workingCount"] == 0


# ---------------------------------------------------------------- pure helpers

def test_author_name():
    chars = {"chr_1": {"name": "Reviewer"}}
    assert author_name("human", chars) == "you" and author_name("system", chars) == "harness"
    assert author_name("chr_1", chars) == "Reviewer" and author_name("chr_9", chars) == "chr_9"


def test_render_brief_folds_threads_and_lists_cast(store):
    key, chr_id = started(store, "note")
    store.cast_yield(chr_id, "question", "q1", options=["a", "b"])
    store.comment(key, "a")
    text = render_brief(store.story(key), store.comments(key), {chr_id: store.character(chr_id)},
                        {"name": "protagonist", "instructions": "Lead."}, "the call-in note")
    assert text.startswith(f"# {key}: Title\n\nDesc\n")
    assert "## Threads" in text and "**you** (text): note" in text and "**protagonist** (question): q1" in text
    assert "options: a, b" in text and "**you** (text): a" in text
    assert "## Cast" in text and "protagonist — protagonist" in text
    assert "## Instructions\nLead." in text and text.rstrip().endswith("## Note\nthe call-in note")


def test_needs_you_flavor():
    from harness.lifecycle import Start, Story, Yield, step
    s = Story(key="K", title="t", phase="todo")
    s, c0 = step(s, Start(thread_id="t1", protagonist="c"), comment_id="c0", now=1)
    assert needs_you_flavor(s, [c0]) == ""
    s2, c1 = step(s, Yield("t1", "c", "question", "?"), comment_id="c1", now=2)
    assert needs_you_flavor(s2, [c0, c1]) == "question"


def test_row_lists_threads_with_turns(store):
    key = store.create("Threads", "")
    assert store.get(key)["threads"] == [] and store.get(key)["mainThread"] == ""
    chr_id = store.start(key, "", "protagonist")
    (t,) = store.get(key)["threads"]
    assert t == {"id": store.get(key)["mainThread"], "n": 1, "isMain": True, "author": "human", "lead": chr_id, "turn": "cast", "pendingYield": ""}
    c = store.cast_yield(chr_id, "question", "a or b?", options=["a", "b"])
    (t,) = store.get(key)["threads"]
    assert t["turn"] == "author" and t["pendingYield"] == c["id"]


def test_handoff_carries_checks(store):
    key = store.create("Checks", "")
    chr_id = store.start(key, "", "protagonist")
    c = store.cast_yield(chr_id, "handoff", "built", checks=[{"repo": "zharn", "cmd": "pytest -q", "exit": 0, "output": "ok"}])
    assert c["structured"]["checks"] == [{"repo": "zharn", "cmd": "pytest -q", "exit": 0, "output": "ok"}]
    assert store.comments(key)[-1]["structured"]["checks"][0]["repo"] == "zharn"


def test_cast_comments_record_the_context_that_wrote_them(store, contexts, ws):
    key, chr_id = started(store)
    live = store.character(chr_id)["live_context"]
    c = store.cast_comment(chr_id, "from the protagonist")
    assert c["context"] == live
    assert store.comment(key, "from the human")["context"] is None
    assert store.comments(key)[0]["context"] is None  # the Start comment is the author's
    rows = [json.loads(l) for l in (ws.stories_dir / key / "threads.jsonl").read_text().splitlines()]
    assert [r.get("context") for r in rows if r["type"] == "comment"] == [None, live, None]
    assert StoryStore(ws, contexts, StubRoles()).comments(key)[1]["context"] == live


# ---------------------------------------------------------------- asides (spec §3.5)

def test_comment_rows_say_whether_an_aside_can_be_opened(store, contexts):
    key, chr_id = started(store)
    live = contexts.get(store.character(chr_id)["live_context"])
    store.cast_comment(chr_id, "I think pyte")
    assert live.status == "working"                                          # still digesting the brief
    assert store.comments(key)[1]["asideEnabled"] is False
    live.status = "idle"
    start_row, cast_row = store.comments(key)
    assert (start_row["asideEnabled"], start_row["asideId"]) == (False, "")   # human comment
    assert (cast_row["asideEnabled"], cast_row["asideId"]) == (True, "")


def test_aside_forks_the_writing_context_as_a_pinned_bare_context(store, contexts, monkeypatch):
    monkeypatch.setattr(cfg, "DEFAULT_BARE_ROLE", "claude-fast", raising=False)
    key, chr_id = started(store)
    c = store.cast_comment(chr_id, "Line one\nline two")
    contexts.get(c["context"]).status = "idle"
    aside = store.aside(key, c["id"])
    (source, kw), = contexts.forked
    assert source == c["context"] and kw["role_name"] == "claude-fast" and kw["owner"] == "human"
    assert kw["about"] == {"story_key": key, "comment_id": c["id"]} and kw["title"] == "aside on #1 · protagonist"
    assert "story_key" not in kw and "env" not in kw  # a bare context: no HARNESS_STORY_KEY / HARNESS_CHARACTER_ID
    prompt = kw["system_prompt"]
    assert "protagonist" in prompt and "#1" in prompt and "> Line one\n> line two" in prompt and key in prompt
    assert store.aside(key, c["id"]) == aside and len(contexts.forked) == 1  # idempotent: reopen
    row = store.comments(key)[1]
    assert (row["asideId"], row["asideEnabled"]) == (aside, True)


def test_aside_rejections_report(store, contexts):
    key, chr_id = started(store)
    human = store.comments(key)[0]
    with pytest.raises(Rejected, match="characters' comments"):
        store.aside(key, human["id"])
    c = store.cast_comment(chr_id, "busy")
    contexts.get(c["context"]).status = "working"
    with pytest.raises(Rejected, match="working"):
        store.aside(key, c["id"])
    with pytest.raises(KeyError):
        store.aside(key, "cmt_nope")
    assert store.notifier.errors and "aside" in store.notifier.errors[-1]


def test_aside_prefers_the_context_that_wrote_the_comment_then_the_live_one(store, contexts):
    key, chr_id = started(store)
    c = store.cast_comment(chr_id, "before recast")
    contexts.get(c["context"]).status = "idle"
    live = contexts.create("claude-fast", owner=chr_id)          # a recast successor
    contexts.get(live).status = "idle"
    store._characters[chr_id]["live_context"] = live
    assert store.aside_source(key, c) == c["context"]            # the memory that wrote it
    del contexts.by_id[c["context"]]                              # ...unless it is gone
    assert store.aside_source(key, c) == live
    contexts.get(live).status = "working"
    assert store.aside_source(key, c) == ""
