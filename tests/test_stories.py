"""StoryStore against a stub context store: persistence, Start casts a protagonist, author actions deliver
to the protagonist, cast verbs, brief and system prompt, needs-you rows."""
import json

import pytest
from PySide6.QtCore import QObject, Signal

from harness import config as cfg
from harness import skills
from harness.lifecycle import Comment, OpenThread, Rejected, Yield

Q = [{"text": "?"}]   # the smallest question document
from harness.stories import StoryStore, author_name, needs_you_flavor, render_brief
from harness.workspace import Workspace


class StubContext:
    def __init__(self, cid, meta):
        self.id, self.meta, self.status, self.sent, self.stopped = cid, meta, "idle", [], False
        self.sessionId = "sess-" + cid
        self.transcript_text, self.last_error, self.turns = "", "", 0
        self.contextTokens, self.contextWindow = 0, 0

    def last_assistant_text(self):
        return self.transcript_text

    @property
    def lastError(self):
        return self.last_error

    def send(self, text):
        self.sent.append(text)
        self.status = "working"

    def stop(self):
        self.stopped = True
        self.status = "stopped"


class StubContexts(QObject):
    contextsChanged = Signal()
    contextSettled = Signal(str)
    contextUsage = Signal(str)

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
    a.cast_yield(chr_id, "question", "which db?", questions=[{"text": "which db?", "options": ["pg", "sqlite"]}])
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


def test_model_exposes_repos_and_environments_to_qml(store):
    """M6: the board model must expose repos/environments, not just carry them in the row dict."""
    role_names = {bytes(v) for v in store.model.roleNames().values()}
    assert b"repos" in role_names and b"environments" in role_names


# ---------------------------------------------------------------- Start

def test_start_casts_protagonist_with_context_brief_and_env(store, contexts, ws):
    key, chr_id = started(store, "please build it")
    ch = store.character(chr_id)
    assert ch["name"] == "protagonist" and ch["role"] == "protagonist" and ch["story_key"] == key
    assert ch["attention"] == store.story(key).main_thread and ch["inbox"] == [] and ch["live_context"] == "ctx_1"
    role_name, kw = contexts.created[0]
    assert role_name == "protagonist" and kw["story_key"] == key and kw["owner"] == chr_id
    assert kw["env"] == {"HARNESS_CHARACTER_ID": chr_id} and kw["title"] == f"{key} · protagonist"
    assert kw.get("system_prompt", "") == ""      # never stored (spec §5.3)
    prompt = store.system_prompt(contexts.get("ctx_1"))
    assert "protagonist" in prompt and key in prompt and "story yield" in prompt and "outline" in prompt.lower() and "Lead." in prompt
    brief = contexts.get("ctx_1").sent[0]
    assert brief.startswith(f"# {key}: Title") and "Desc" in brief and "please build it" in brief and "## Instructions" not in brief
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
    c = store.cast_yield(chr_id, "question", "pg or sqlite?", questions=[{"text": "pg or sqlite?", "options": ["pg", "sqlite"]}])
    assert c["kind"] == "question" and c["structured"]["questions"] == [{"text": "pg or sqlite?", "options": ["pg", "sqlite"]}] and c["author"] == chr_id
    row = store.get(key)
    assert row["ball"] == "author" and row["needsYou"] and row["flavor"] == "question"
    assert store.notifier.infos[-1] == f"{key} needs you: question"


def test_cast_yield_rejections_surface(store):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline")
    with pytest.raises(Rejected, match="already waits"):
        store.cast_yield(chr_id, "question", "again", questions=Q)
    with pytest.raises(KeyError):
        store.cast_yield("chr_nobody", "question", "x", questions=Q)


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
    store.cast_yield(chr_id, "question", "pg or sqlite?", questions=Q)
    ctx = contexts.get("ctx_1")
    n = len(ctx.sent)
    c = store.comment(key, "sqlite")
    assert c["reply_to"] is not None and store.get(key)["ball"] == "cast"
    assert "\n[you] reply in #main: sqlite" in ctx.sent[n]


def test_human_comment_while_cast_has_ball_is_delivered_without_moving_it(store, contexts):
    key, chr_id = started(store)
    ctx = contexts.get("ctx_1")
    n = len(ctx.sent)
    store.comment(key, "btw prefer sqlite")
    assert store.get(key)["ball"] == "cast" and "\n[you] comment in #main: btw" in ctx.sent[n]


def test_proceed_moves_phase_and_tells_protagonist(store, contexts):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline")
    ctx = contexts.get("ctx_1")
    store.proceed(key, "go ahead")
    assert store.get(key)["phase"] == "implementing" and store.get(key)["ball"] == "cast"
    assert "outline approved" in ctx.sent[-1] and ctx.sent[-1].startswith("[situation] phase implementing")


def test_system_prompt_is_stable_across_a_proceed_and_carries_no_situation(store, contexts):
    key, chr_id = started(store)
    ctx = contexts.get("ctx_1")
    before = store.system_prompt(ctx)
    store.cast_yield(chr_id, "handoff", "outline")
    store.proceed(key, "go ahead")
    after = store.system_prompt(ctx)
    assert before == after
    meta = skills.skill_body("being-a-character")
    assert meta and meta in after and "story yield" in after and "Role: protagonist. Lead." in after and cfg.OUTLINE_RULE_REQUIRED in after
    main = store.story(key).main_thread
    assert "phase planning" not in after and "phase implementing" not in after and main not in after and "you owe #" not in after
    assert str(store.workspace.dir) not in after
    assert ctx.meta.get("systemPrompt", "") == ""


def test_system_prompt_is_none_for_contexts_no_character_owns(store, contexts):
    cid = contexts.create("claude-fast", owner="human", title="bare")
    assert store.system_prompt(contexts.get(cid)) is None


def test_every_delivery_opens_with_the_situation_line(store, contexts):
    key, chr_id = started(store)
    ctx = contexts.get("ctx_1")
    main = store.story(key).main_thread
    store.cast_yield(chr_id, "question", "which?", questions=Q)
    store.comment(key, "that one")
    lines = ctx.sent[-1].splitlines()
    assert lines[0] == ("[situation] phase planning · attending #main · you owe #main · you await nothing · "
                        f"in the workspace dir {store.workspace.dir}; run `env open <repo>` before touching a repo")
    assert lines[1] == "[you] reply in #main: that one"
    r = store.cast_call(chr_id, "claude-fast", "build it")
    store.cast_yield(chr_id, "question", "and?", questions=Q)
    store.comment(key, "so")
    assert f"you await #{r['thread']}" in ctx.sent[-1].splitlines()[0]


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
    store.cast_yield(chr_id, "question", "Two things.", questions=[{"text": "a or b?", "options": ["a", "b"], "default": "a"}, {"text": "why?"}])
    store.answer(key, "", ["a", ""], "because")
    text = render_brief(store.story(key), store.comments(key), {chr_id: store.character(chr_id)}, "the call-in note")
    assert text.startswith(f"# {key}: Title\n\nDesc\n")
    assert "## Threads" in text and "### #main — author you" in text and "**you** (text): note" in text
    assert "**protagonist** (question): Two things.\n  1. a or b? (a, b; default a)\n  2. why?\n" in text
    assert "**you** (text): 1. a\nbecause" in text
    assert "## Cast" in text and "protagonist — protagonist" in text
    assert "## Instructions" not in text and text.rstrip().endswith("## Note\nthe call-in note")


def test_needs_you_flavor():
    from harness.lifecycle import Start, Story, Yield, step
    s = Story(key="K", title="t", phase="todo")
    s, c0 = step(s, Start(thread_id="t1", protagonist="c"), comment_id="c0", now=1)
    assert needs_you_flavor(s, [c0]) == ""
    s2, c1 = step(s, Yield("t1", "c", "question", "?", questions=Q), comment_id="c1", now=2)
    assert needs_you_flavor(s2, [c0, c1]) == "question"


def test_row_lists_threads_with_turns(store):
    key = store.create("Threads", "")
    assert store.get(key)["threads"] == [] and store.get(key)["mainThread"] == ""
    chr_id = store.start(key, "", "protagonist")
    (t,) = store.get(key)["threads"]
    assert t == {"id": store.get(key)["mainThread"], "n": 1, "isMain": True, "author": "human", "lead": chr_id, "turn": "cast", "pendingYield": ""}
    c = store.cast_yield(chr_id, "question", "a or b?", questions=[{"text": "a or b?", "options": ["a", "b"]}])
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


def test_aside_forks_only_the_context_that_wrote_the_comment(store, contexts):
    key, chr_id = started(store)
    c = store.cast_comment(chr_id, "before recast")
    contexts.get(c["context"]).status = "idle"
    live = contexts.create("claude-fast", owner=chr_id)          # a recast successor: a different mind
    contexts.get(live).status = "idle"
    store._characters[chr_id]["live_context"] = live
    assert store.aside_source(key, c) == c["context"]            # the memory that wrote it
    contexts.get(c["context"]).status = "working"
    assert store.aside_source(key, c) == ""                       # ...disabled while it works
    del contexts.by_id[c["context"]]
    assert store.aside_source(key, c) == ""                       # ...and when it is gone: never the successor


# ---------------------------------------------------------------- derived character state (characters plan, Task 2)

def new_thread(store, key, *, author, lead, body="hey"):
    tid = f"thr_{len(store.story(key).threads) + 1}"
    store._apply(key, OpenThread(thread_id=tid, author=author, lead=lead, body=body))
    return tid


def test_cast_rows_carry_derived_state(store, contexts):
    key, chr_id = started(store)
    live = contexts.get(store.character(chr_id)["live_context"])
    row, = store.cast(key)
    assert (row["status"], row["owes"], row["awaits"], row["inboxDepth"], row["forkedFrom"]) == ("working", [store.get(key)["mainThread"]], [], 0, "")
    live.status = "idle"
    assert store.cast(key)[0]["status"] == "idle"
    tid = new_thread(store, key, author=chr_id, lead="chr_friend")
    assert store.cast(key)[0]["status"] == "waiting" and store.cast(key)[0]["awaits"] == [tid]
    store.cancel(key)
    assert store.cast(key)[0]["status"] == "retired"


def test_start_comment_names_the_role(store):
    key, chr_id = started(store)
    assert store.comments(key)[0]["structured"]["role"] == "protagonist"


def test_needs_you_includes_human_side_threads(store):
    key, chr_id = started(store)
    tid = new_thread(store, key, author="human", lead=chr_id)
    assert store.get(key)["needsYou"] is False
    store._apply(key, Yield(thread_id=tid, by=chr_id, kind="handoff", body="answer"))
    row = store.get(key)
    assert row["needsYou"] is True and row["flavor"] == "a side thread waits on you"
    store.resolve(key, tid)
    assert store.get(key)["needsYou"] is False


def test_proceed_gate_counts_only_outlines_approved_since_the_last_planning_entry(store):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline")
    store.proceed(key)                      # (implementing, cast)
    store.cast_yield(chr_id, "handoff", "built")
    store.backToPlanning(key)               # back in planning: the old approval no longer counts
    with pytest.raises(Rejected, match="approved outline"):
        store.cast_proceed(chr_id)
    store.cast_yield(chr_id, "handoff", "outline v2")
    store.proceed(key)
    assert store.get(key)["phase"] == "implementing"


# ---------------------------------------------------------------- casting and routing (characters plan, Task 3)

def test_open_thread_addresses_the_protagonist_by_default(store, contexts):
    key, chr_id = started(store)
    live = contexts.get(store.character(chr_id)["live_context"])
    live.status = "idle"
    tid = store.openThread(key, "why pyte?")
    t = store.story(key).thread(tid)
    assert (t.author, t.lead) == ("human", chr_id)
    assert ("\n[you] comment in #" + tid) in live.sent[-1] and store.character(chr_id)["attention"] == tid


def test_open_thread_to_a_named_character(store, contexts):
    key, chr_id = started(store)
    friend = store._cast(key, StubRoles().get("claude-fast"), thread_id="thr_f", author=chr_id, note="build it")
    store._apply(key, OpenThread(thread_id="thr_f", author=chr_id, lead=friend["id"], body="build it"))
    contexts.get(friend["live_context"]).status = "idle"
    tid = store.openThread(key, "@claude-fast how far along?")
    assert store.story(key).thread(tid).lead == friend["id"]
    assert contexts.get(friend["live_context"]).sent[-1].endswith("how far along?")


def test_open_thread_with_call_casts_a_fresh_friend_with_a_brief(store, contexts):
    key, chr_id = started(store)
    tid = store.openThread(key, "/call claude-fast review the outline")
    t = store.story(key).thread(tid)
    friend = store.character(t.lead)
    assert friend["role"] == "claude-fast" and friend["forked_from"] is None and t.author == "human"
    ctx = contexts.get(friend["live_context"])
    assert ctx.meta["owner"] == friend["id"] and ctx.meta["env"]["HARNESS_CHARACTER_ID"] == friend["id"]
    assert ctx.sent[0].startswith(f"# {key}:") and "review the outline" in ctx.sent[0]      # the brief, note last
    assert store.comments(key)[-1]["body"] == "review the outline" and friend["attention"] == tid


def test_open_thread_with_fork_casts_a_forked_friend_without_a_brief(store, contexts):
    key, chr_id = started(store)
    contexts.get(store.character(chr_id)["live_context"]).status = "idle"
    tid = store.openThread(key, "/fork @protagonist what did you mean by X?")
    friend = store.character(store.story(key).thread(tid).lead)
    assert friend["forked_from"] == chr_id and friend["name"] == "protagonist-2" and friend["role"] == "protagonist"
    (source, kw), = contexts.forked
    assert source == store.character(chr_id)["live_context"] and kw["owner"] == friend["id"] and kw["story_key"] == key
    assert kw["env"]["HARNESS_CHARACTER_ID"] == friend["id"]
    first = contexts.get(friend["live_context"]).sent[0]
    assert "a fork of protagonist" in first and "what did you mean by X?" in first and not first.startswith("#")


def test_open_thread_rejections(store, contexts):
    key, chr_id = started(store)
    with pytest.raises(Rejected, match="no character named"):
        store.openThread(key, "@nobody hi")
    with pytest.raises(ValueError, match="unknown role"):
        store.openThread(key, "/call wizard do magic")
    with pytest.raises(Rejected, match="working"):
        store.openThread(key, "/fork @protagonist now")      # its context is still working on the brief
    assert len(store.cast(key)) == 1 and len(store.story(key).threads) == 1


def test_addressees_follow_the_routing_rules(store, contexts):
    key, chr_id = started(store)
    friend = store._cast(key, StubRoles().get("claude-fast"), thread_id="thr_f", author=chr_id, note="build")
    c_root = store._apply(key, OpenThread(thread_id="thr_f", author=chr_id, lead=friend["id"], body="build"))
    assert store.addressees(key, c_root) == [friend["id"]]                       # root → lead
    c_yield = store._apply(key, Yield(thread_id="thr_f", by=friend["id"], kind="question", body="which db? @protagonist", questions=Q))
    assert store.addressees(key, c_yield) == [chr_id]                             # yield → author (mention == author: once)
    c_reply = store._apply(key, Comment(thread_id="thr_f", by=chr_id, body="postgres"))
    assert c_reply["reply_to"] == c_yield["id"] and store.addressees(key, c_reply) == [friend["id"]]   # reply to a yield → yielder
    c_guest = store._apply(key, Comment(thread_id="thr_f", by="human", body="fyi @protagonist"))
    assert store.addressees(key, c_guest) == [friend["id"], chr_id]               # reply → lead, plus mentions
    c_auto = store._apply(key, Yield(thread_id="thr_f", by="system", kind="handoff", body="quiet", auto_for=friend["id"]))
    assert store.addressees(key, c_auto) == [chr_id]
    c_answer = store._apply(key, Comment(thread_id="thr_f", by=chr_id, body="ok"))
    assert store.addressees(key, c_answer) == [friend["id"]]                      # reply to a harness yield → the lead


# ---------------------------------------------------------------- delivery by status (characters plan, Task 4)

def test_delivery_pushes_to_the_attended_thread_and_inboxes_the_rest(store, contexts):
    key, chr_id = started(store)
    ch = store.character(chr_id)
    live = contexts.get(ch["live_context"])
    main = store.get(key)["mainThread"]
    assert ch["attention"] == main and live.status == "working"
    store.comment(key, "steer")                                   # attended, mid-turn → pushed now
    assert live.sent[-1].endswith("steer") and store.character(chr_id)["inbox"] == []
    side = store.openThread(key, "btw?")                          # other thread, mid-turn → inbox
    btw = store.comments(key)[-1]
    assert store.character(chr_id)["inbox"] == [btw["id"]] and store.character(chr_id)["attention"] == main
    assert not live.sent[-1].endswith("btw?") and store.cast(key)[0]["inboxDepth"] == 1
    live.status = "idle"
    store.comment(key, "now you are free", side)                  # idle → pushed, attention moves
    assert live.sent[-1].endswith("now you are free") and store.character(chr_id)["attention"] == side


# ---------------------------------------------------------------- turn end (characters plan, Task 5)

def settle(store, contexts, chr_id, status="idle"):
    ch = store.character(chr_id)
    contexts.get(ch["live_context"]).status = status
    contexts.contextSettled.emit(ch["live_context"])


def test_quiet_check_yields_every_owed_thread_when_nothing_is_awaited(store, contexts):
    key, chr_id = started(store)
    contexts.get(store.character(chr_id)["live_context"]).transcript_text = "half done"
    settle(store, contexts, chr_id)
    s = store.story(key)
    assert s.ball == "author"
    last = store.comments(key)[-1]
    assert (last["author"], last["kind"], last["structured"]["auto_for"]) == ("system", "handoff", chr_id)
    assert last["body"].startswith("protagonist went quiet: half done")
    assert store.get(key)["needsYou"] is True and store.character(chr_id)["attention"] is None
    settle(store, contexts, chr_id)                                # nothing owed now: nothing happens
    assert len(store.comments(key)) == 2


def test_a_waiting_character_is_not_quiet(store, contexts):
    key, chr_id = started(store)
    friend = store._cast(key, StubRoles().get("claude-fast"), thread_id="thr_f", author=chr_id, note="build")
    store._apply(key, OpenThread(thread_id="thr_f", author=chr_id, lead=friend["id"], body="build"))
    settle(store, contexts, chr_id)
    assert store.story(key).ball == "cast" and store.cast(key)[0]["status"] == "waiting"
    store._apply(key, Yield(thread_id="thr_f", by=friend["id"], kind="handoff", body="built"))
    settle(store, contexts, chr_id)                                # awaits nothing now, still owes main → quiet
    assert store.story(key).ball == "author"


def test_a_crash_or_stop_yields_with_the_reason(store, contexts):
    key, chr_id = started(store)
    contexts.get(store.character(chr_id)["live_context"]).last_error = "exit 1"
    settle(store, contexts, chr_id, status="failed")
    assert store.comments(key)[-1]["body"].startswith("protagonist crashed: exit 1")


def test_turn_end_pops_one_inbox_item_and_moves_attention(store, contexts):
    key, chr_id = started(store)
    ch = store.character(chr_id)
    live = contexts.get(ch["live_context"])
    a = store.openThread(key, "first btw"); b = store.openThread(key, "second btw")
    assert [store._comment_by_id(i)["thread_id"] for i in store.character(chr_id)["inbox"]] == [a, b]
    store.cast_yield(chr_id, "question", "which?", questions=Q)                 # attended main yields, then the turn ends
    settle(store, contexts, chr_id)
    ch = store.character(chr_id)
    assert ch["attention"] == a and live.sent[-1].endswith("first btw") and len(ch["inbox"]) == 1
    settle(store, contexts, chr_id)                                # a is owed and unanswered → quiet yield there, then pop b
    assert store.story(key).thread(a).turn == "author" and store.character(chr_id)["attention"] == b


def test_retired_characters_get_no_turn_end_processing(store, contexts):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    store.cast_yield(chr_id, "handoff", "built"); store.approve(key)
    n = len(store.comments(key))
    settle(store, contexts, chr_id)
    assert len(store.comments(key)) == n


# ---------------------------------------------------------------- cast verbs (characters plan, Task 6)

def test_cast_call_opens_a_thread_led_by_a_fresh_friend(store, contexts):
    key, chr_id = started(store)
    r = store.cast_call(chr_id, "claude-fast", "build the screen model", as_name="Implementor")
    t = store.story(key).thread(r["thread"])
    assert (t.author, t.lead, r["name"]) == (chr_id, r["character"], "Implementor")
    friend = store.character(r["character"])
    assert "build the screen model" in contexts.get(friend["live_context"]).sent[0] and friend["attention"] == r["thread"]
    assert store.awaits(store.character(chr_id)) == [r["thread"]]


def test_cast_call_fork_clones_the_caller(store, contexts):
    key, chr_id = started(store)
    contexts.get(store.character(chr_id)["live_context"]).status = "idle"
    r = store.cast_call(chr_id, "claude-fast", "review my work so far", fork=True)
    assert store.character(r["character"])["forked_from"] == chr_id and contexts.forked[0][0] == store.character(chr_id)["live_context"]
    assert "a fork of protagonist" in contexts.get(store.character(r["character"])["live_context"]).sent[0]


def test_cast_wait_is_a_guard(store, contexts):
    key, chr_id = started(store)
    with pytest.raises(Rejected, match="you await nothing and owe #main — yield instead"):
        store.cast_wait(chr_id)
    store.cast_yield(chr_id, "question", "", questions=Q)
    w = store.cast_wait(chr_id)          # owes nothing now: stopping is right, so the guard passes
    assert w["awaits"] == [] and "end your turn" in w["message"] and "a reply will wake you" in w["message"]
    store.comment(key, "a")
    r = store.cast_call(chr_id, "claude-fast", "build")
    w = store.cast_wait(chr_id)
    assert w["awaits"] == [{"thread": r["thread"], "lead": "claude-fast"}] and "end your turn" in w["message"]


def test_answer_composes_the_reply_and_stores_answers(store, contexts):
    key, chr_id = started(store)
    q = store.cast_yield(chr_id, "question", "", questions=[{"text": "a or b?", "options": ["a", "b"]}, {"text": "c or d?", "options": ["c", "d"]}, {"text": "why?"}])
    r = store.answer(key, "", ["a", "", "d"], "  because  ")
    assert r["reply_to"] == q["id"] and r["body"] == "1. a\n3. d\nbecause" and r["structured"]["answers"] == ["a", "", "d"]
    assert store.get(key)["ball"] == "cast"
    store.cast_yield(chr_id, "question", "", questions=[{"text": "again?"}])
    with pytest.raises(Rejected, match="nothing to say"):
        store.answer(key, "", [""], "  ")
    r = store.answer(key, "", [], "free text only")
    assert r["body"] == "free text only" and "answers" not in r["structured"]


def test_delivery_prints_question_lines_and_main(store, contexts):
    key, chr_id = started(store)
    ctx = contexts.get("ctx_1")
    store.cast_yield(chr_id, "question", "Pick.", questions=[{"text": "a or b?", "options": ["a", "b"]}])
    store.answer(key, "", ["b"], "")
    lines = ctx.sent[-1].splitlines()
    assert lines[0].startswith("[situation] phase planning · attending #main · you owe #main · you await nothing · ")
    assert lines[1] == "[you] reply in #main: 1. b"
    r = store.cast_call(chr_id, "claude-fast", "build it")
    ctx.status = "idle"
    store.cast_yield(r["character"], "question", "Pick.", questions=[{"text": "x?", "options": ["x", "y"], "default": "x"}], thread_id=r["thread"])
    assert f"[claude-fast] question in #{r['thread']}: Pick.\n  1. x? (x, y; default x)" in ctx.sent[-1]
    assert f"attending #{r['thread']} · you owe #main" in ctx.sent[-1].splitlines()[0]


def test_thread_main_resolves_in_cast_verbs(store, contexts):
    key, chr_id = started(store)
    main = store.get(key)["mainThread"]
    c = store.cast_yield(chr_id, "question", "", questions=Q, thread_id="main")
    assert c["thread_id"] == main and store.get(key)["ball"] == "author"
    store.comment(key, "a")
    assert store.cast_recap(chr_id, "r", thread_id="main")["thread_id"] == main
    assert store.cast_comment(chr_id, "c", thread_id="main")["thread_id"] == main
    assert store.env_checks(chr_id, "main")["run"] is False


def test_cast_recap_defaults_to_the_attended_thread(store, contexts):
    key, chr_id = started(store)
    side = store.openThread(key, "btw")
    contexts.get(store.character(chr_id)["live_context"]).status = "idle"
    store.comment(key, "still there?", side)                       # attention moves to side
    c = store.cast_recap(chr_id, "cleared A, B open")
    assert c["thread_id"] == side and store.character(chr_id)["recaps"] == [c["id"]]
    assert store.cast_recap(chr_id, "on main", thread_id=store.get(key)["mainThread"])["thread_id"] == store.get(key)["mainThread"]


def test_cast_comment_to_opens_a_root_thread_when_no_thread_is_given(store, contexts):
    key, chr_id = started(store)
    r = store.cast_call(chr_id, "claude-fast", "build")
    c = store.cast_comment(chr_id, "one more thing", to=["@claude-fast"])
    t = store.story(key).thread(c["thread_id"])
    assert (t.author, t.lead) == (chr_id, r["character"]) and c["thread_id"] != r["thread"]
    c2 = store.cast_comment(chr_id, "fyi", thread_id=r["thread"], to=["@claude-fast"])
    assert c2["thread_id"] == r["thread"] and store.addressees(key, c2) == [r["character"]]


def test_cast_inbox_lists_waiting_comments(store, contexts):
    key, chr_id = started(store)
    a = store.openThread(key, "first btw")
    rows = store.cast_inbox(chr_id)
    assert [r["thread_id"] for r in rows] == [a] and rows[0]["body"] == "first btw"


def test_speak_posts_into_the_attended_thread_or_opens_one(store, contexts):
    key, chr_id = started(store)
    main = store.get(key)["mainThread"]
    c = store.speak(chr_id, "typed in the context view")
    assert (c["author"], c["thread_id"]) == ("human", main)
    store._characters[chr_id]["attention"] = None
    c2 = store.speak(chr_id, "while it attends nothing")
    assert c2["thread_id"] != main and store.story(key).thread(c2["thread_id"]).lead == chr_id


def test_cast_yield_reaches_the_threads_author(store, contexts):
    key, chr_id = started(store)
    live = contexts.get(store.character(chr_id)["live_context"]); live.status = "idle"
    r = store.cast_call(chr_id, "claude-fast", "build")
    store.cast_yield(r["character"], "handoff", "built it")
    assert f"\n[claude-fast] handoff in #{r['thread']}: built it" in live.sent[-1]


# ---------------------------------------------------------------- retirement (characters plan, Task 7)

def test_approve_lets_a_working_friend_finish_and_delivers_nothing_after(store, contexts):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    r = store.cast_call(chr_id, "claude-fast", "build")
    friend_ctx = contexts.get(store.character(r["character"])["live_context"])
    store._apply(key, Yield(thread_id=r["thread"], by=r["character"], kind="handoff", body="built"))
    store.cast_yield(chr_id, "handoff", "done")
    store.approve(key)
    assert not friend_ctx.stopped and friend_ctx.status == "working"
    assert [row["status"] for row in store.cast(key)] == ["retired", "retired"]
    sent = len(friend_ctx.sent)
    with pytest.raises(Rejected):
        store.comment(key, "hello?", r["thread"])                  # read-only after terminal
    n = len(store.comments(key))
    settle(store, contexts, r["character"])                        # its turn ends: no quiet check, no pop
    assert len(friend_ctx.sent) == sent and len(store.comments(key)) == n


def test_cancel_stops_every_character(store, contexts):
    key, chr_id = started(store)
    r = store.cast_call(chr_id, "claude-fast", "build")
    store.cancel(key)
    assert all(contexts.get(store.character(c)["live_context"]).stopped for c in (chr_id, r["character"]))


# ---------------------------------------------------------------- sub-stories (characters plan, Task 8)

def test_character_creates_and_starts_a_sub_story_it_authors(store, contexts):
    key, chr_id = started(store)
    sub = store.cast_create(chr_id, "screen model", "pyte-backed", start=True, role="claude-fast")
    s = store.story(sub)
    assert (s.author, s.parent_story, s.phase, s.ball) == (chr_id, key, "planning", "cast")
    assert store.get(key)["openSubstories"] == 1 and store.get(sub)["parentStory"] == key
    assert store.awaits(store.character(chr_id)) == [sub]
    sub_lead = store.story(sub).protagonist
    assert contexts.get(store.character(sub_lead)["live_context"]).sent[0].startswith(f"# {sub}:")


def test_a_sub_story_await_is_the_bare_key_in_the_situation_line(store, contexts):
    key, chr_id = started(store)
    contexts.get(store.character(chr_id)["live_context"]).status = "idle"
    sub = store.cast_create(chr_id, "Sub", start=True, role="claude-fast")
    store.comment(key, "status?")
    ctx = contexts.get(store.character(chr_id)["live_context"])
    assert f"you await {sub}" in ctx.sent[-1].splitlines()[0]
    assert f"you await #{sub}" not in ctx.sent[-1]


def test_sub_story_yield_reaches_the_author_character_cross_story(store, contexts):
    key, chr_id = started(store)
    live = contexts.get(store.character(chr_id)["live_context"]); live.status = "idle"
    sub = store.cast_create(chr_id, "screen model", start=True, role="claude-fast")
    lead = store.story(sub).protagonist
    store.cast_yield(lead, "question", "rows or cells?", questions=Q)
    assert f"attending #main of {sub} · " in live.sent[-1] and f"\n[claude-fast] question in #main of {sub}: rows or cells?" in live.sent[-1]
    assert store.character(chr_id)["attention"] == store.get(sub)["mainThread"]
    c = store.cast_author(chr_id, "reply", sub, body="rows", thread_id=store.get(sub)["mainThread"])
    assert store.story(sub).ball == "cast" and c["reply_to"]
    with pytest.raises(Rejected, match="only the author"):
        store.cast_author(lead, "approve", sub)


def test_main_handoff_is_blocked_while_a_sub_story_is_open(store, contexts):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    sub = store.cast_create(chr_id, "part", start=True, role="claude-fast")
    with pytest.raises(Rejected, match="still open"):
        store.cast_yield(chr_id, "handoff", "done")
    lead = store.story(sub).protagonist
    store.cast_yield(lead, "handoff", "outline"); store.cast_author(chr_id, "proceed", sub)
    store.cast_yield(lead, "handoff", "built"); store.cast_author(chr_id, "approve", sub)
    assert store.cast_yield(chr_id, "handoff", "done")["kind"] == "handoff"


def test_human_acting_on_a_character_owned_sub_story_notifies_the_owner(store, contexts):
    key, chr_id = started(store)
    live = contexts.get(store.character(chr_id)["live_context"]); live.status = "idle"
    sub = store.cast_create(chr_id, "part", start=True, role="claude-fast")
    lead = store.story(sub).protagonist
    store.cast_yield(lead, "handoff", "outline")
    store.proceed(sub)                                              # the human, on behalf of the owner
    assert store.story(sub).phase == "implementing"
    assert f"\n[protagonist] system in #main of {sub}: outline approved" in live.sent[-1]


def test_cancel_cascades_to_open_sub_stories(store, contexts):
    key, chr_id = started(store)
    sub = store.cast_create(chr_id, "part", start=True, role="claude-fast")
    store.cancel(key)
    assert store.story(sub).phase == "canceled" and store.cast(sub)[0]["status"] == "retired"


# ---------------------------------------------------------------- recast (characters plan, Task 9)

def test_recast_replaces_the_live_context_and_hands_it_the_situation(store, contexts):
    key, chr_id = started(store)
    old = store.character(chr_id)["live_context"]
    contexts.get(old).status = "idle"; contexts.get(old).turns = 3
    side = store.openThread(key, "btw")                          # pushed: the stub goes "working" again
    call = store.cast_call(chr_id, "claude-fast", "second opinion")   # a thread this character awaits
    store.cast_recap(chr_id, "done: outline; next: build")
    contexts.get(old).status = "idle"                             # ...and its turn ends
    new = store.recast(key, chr_id, role="claude-fast")
    ch = store.character(chr_id)
    assert ch["live_context"] == new and ch["role"] == "claude-fast" and contexts.get(old).stopped
    assert contexts.get(new).meta["predecessor"] == old and contexts.get(new).meta["owner"] == chr_id
    first = contexts.get(new).sent[0]
    assert "you are a recast of protagonist" in first and "done: outline; next: build" in first and f"attending #{side}" in first
    assert f"you await #{call['thread']}" in first
    note = store.comments(key)[-1]
    assert note["author"] == "system" and note["body"] == "recast protagonist as claude-fast (rung 1: fresh recap)"
    assert store.cast(key)[0]["status"] == "working"


def test_recast_without_a_fresh_recap_is_rung_3(store, contexts, monkeypatch):
    monkeypatch.setattr(cfg, "RECAP_STALE_TURNS", 2, raising=False)
    key, chr_id = started(store)
    old = store.character(chr_id)["live_context"]
    contexts.get(old).status = "idle"; contexts.get(old).turns = 1
    store.cast_recap(chr_id, "early recap")
    contexts.get(old).turns = 10
    store.recast(key, chr_id)
    assert store.comments(key)[-1]["body"].endswith("(rung 3: no fresh recap)")


def test_recast_of_a_working_character_waits_for_the_turn_boundary(store, contexts):
    key, chr_id = started(store)
    old = store.character(chr_id)["live_context"]
    assert store.recast(key, chr_id, model="claude-opus-5") == "" and store.character(chr_id)["recast_pending"] == {"role": "", "model": "claude-opus-5"}
    settle(store, contexts, chr_id)
    ch = store.character(chr_id)
    assert ch["live_context"] != old and "recast_pending" not in ch
    assert contexts.get(ch["live_context"]).meta["role"] == "protagonist" and contexts.get(ch["live_context"]).meta["roleConfig"]["model"] == "claude-opus-5"


def test_reopen_with_a_role_recasts_instead_of_resuming(store, contexts):
    key, chr_id = started(store)
    old = store.character(chr_id)["live_context"]
    contexts.get(old).status = "idle"
    store.cast_yield(chr_id, "handoff", "outline")
    store.proceed(key)
    contexts.get(old).status = "idle"
    store.cast_yield(chr_id, "handoff", "built")
    store.approve(key)
    contexts.get(old).status = "idle"
    before_old_sent = list(contexts.get(old).sent)
    store.reopen(key, "try again, differently", "claude-fast")
    ch = store.character(chr_id)
    new = ch["live_context"]
    assert new != old and ch["role"] == "claude-fast"
    assert store.get(key)["phase"] == "implementing"
    assert "you are a recast of protagonist" in contexts.get(new).sent[0]
    assert any("try again, differently" in t for t in contexts.get(new).sent[1:])  # the note reaches the fresh memory
    assert contexts.get(old).sent == before_old_sent                               # the old one was never resumed


# ---------------------------------------------------------------- environments (workspace spec §4)
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from gitfix import make_repo, branch_of  # noqa: E402
from harness.environments import register_repo  # noqa: E402


@pytest.fixture
def repo(tmp_path, ws):
    p = make_repo(tmp_path / "ws" / "client")
    register_repo(ws, str(p), checks="echo ok")
    return p


def test_env_open_creates_the_worktree_records_it_on_the_character_and_the_story(store, ws, repo, contexts):
    key, chr_id = started(store)
    assert store.get(key)["repos"] == [] and store.get(key)["environments"] == []
    d = store.cast_env_open(chr_id, "client")
    assert branch_of(_Path(d["path"])) == f"zharn/{key}" and d["checks"] == "echo ok"
    assert store.character(chr_id)["environment"] == "client"
    assert store.get(key)["repos"] == ["client"] and json.loads((ws.stories_dir / key / "story.json").read_text())["repos"] == ["client"]
    assert store.get(key)["environments"] == [{"repo": "client", "path": d["path"], "branch": f"zharn/{key}", "parent": None, "into": "main"}]
    assert store.cast(key)[0]["environment"] == "client"
    assert store.cast_env_list(chr_id) == [d]
    assert store.cast_env_open(chr_id, "client") == d and store.get(key)["repos"] == ["client"]


def test_placement_falls_back_to_the_workspace_dir_when_the_worktree_is_gone(store, ws, repo, contexts):
    """I4: a character whose worktree was deleted out from under it must still be able to start a turn (and run
    `env open` again) rather than have the harness try to spawn a process into a path that no longer exists."""
    import shutil
    key, chr_id = started(store)
    d = store.cast_env_open(chr_id, "client")
    shutil.rmtree(d["path"])
    ctx = contexts.get(store.character(chr_id)["live_context"])
    cwd, place_env = store._placement(ctx)
    assert cwd == str(ws.dir) and place_env == {}


def test_env_open_errors_are_the_repos_message(store, repo):
    key, chr_id = started(store)
    from harness.environments import EnvError
    with pytest.raises(EnvError, match="unknown repo 'nope'"):
        store.cast_env_open(chr_id, "nope")
    with pytest.raises(EnvError, match="env open needs a repo name"):
        store.cast_env_open(chr_id, "")
    assert store.character(chr_id)["environment"] is None and store.get(key)["repos"] == []


def test_substory_opens_its_own_worktree_cut_from_the_parents_branch(store, repo):
    key, chr_id = started(store)
    parent_env = store.cast_env_open(chr_id, "client")
    sub = store.cast_create(chr_id, "Contained", start=True, role="claude-fast")
    d = store.cast_env_open(store.get(sub)["protagonist"], "client")
    assert d["branch"] == f"zharn/{sub}" and d["parent"] == f"{key}:client" and d["path"] != parent_env["path"]
    assert store.get(sub)["environments"][0]["parent"] == f"{key}:client"
    assert store.get(sub)["environments"][0]["into"] == f"zharn/{key}"   # the row names the branch it merges into (§4.2)


def test_friends_inherit_the_callers_environment_and_the_protagonist_starts_with_none(store, repo, contexts):
    key, chr_id = started(store)
    assert store.character(chr_id)["environment"] is None
    store.cast_env_open(chr_id, "client")
    fresh = store.cast_call(chr_id, "claude-fast", "review")["character"]
    assert store.character(fresh)["environment"] == "client"
    contexts.get(store.character(chr_id)["live_context"]).status = "idle"
    forked = store.cast_call(chr_id, "claude-fast", "second opinion", fork=True)["character"]
    assert store.character(forked)["environment"] == "client"
    tid = store.openThread(key, "/fork @protagonist quick question")
    guest = store.story(key).thread(tid).lead
    assert store.character(guest)["environment"] == "client"
    tid2 = store.openThread(key, "/call claude-fast from the human")
    assert store.character(store.story(key).thread(tid2).lead)["environment"] is None


def test_recast_keeps_the_environment(store, repo, contexts):
    key, chr_id = started(store)
    store.cast_env_open(chr_id, "client")
    contexts.get(store.character(chr_id)["live_context"]).status = "idle"
    store.recast(key, chr_id)
    assert store.character(chr_id)["environment"] == "client"


def test_repo_add_registers_and_posts_a_system_note_in_the_attended_thread(store, ws, tmp_path):
    key, chr_id = started(store)
    p = make_repo(tmp_path / "ws" / "api")
    rec = store.cast_repo_add(chr_id, str(p), checks="pytest -q")
    assert rec["name"] == "api" and ws.repo("api")["checks"] == "pytest -q" and rec["base"] == "main"
    last = store.comments(key)[-1]
    assert last["author"] == "system" and last["kind"] == "system" and last["thread_id"] == store.get(key)["mainThread"]
    assert "Registered repo `api` at `api`" in last["body"]
    assert store.repo_list() == [{**ws.repo("api"), "status": "ok"}]


def test_env_checks_only_for_an_implementing_handoff_on_the_main_thread(store, repo, monkeypatch):
    from harness import config as cfg
    monkeypatch.setattr(cfg, "HANDOFF_CHECKS", "attach", raising=False)
    key, chr_id = started(store)
    store.cast_env_open(chr_id, "client")
    plan = store.env_checks(chr_id)
    assert plan["run"] is False and plan["environments"] == [] and plan["policy"] == "attach"
    store.cast_yield(chr_id, "handoff", "outline")
    store.proceed(key)
    plan = store.env_checks(chr_id)
    assert plan["run"] is True and [e["repo"] for e in plan["environments"]] == ["client"] and plan["environments"][0]["checks"] == "echo ok"
    assert plan["limit"] > 0 and plan["timeout"] > 0
    side = store.cast_call(chr_id, "claude-fast", "review")["thread"]
    assert store.env_checks(chr_id, side)["run"] is False


def test_situation_line_names_the_environment(store, repo):
    key, chr_id = started(store)
    ch = store.character(chr_id)
    assert "workspace dir" in store.environment_line(ch) and "env open" in store.environment_line(ch)
    d = store.cast_env_open(chr_id, "client")
    line = store.environment_line(store.character(chr_id))
    assert d["path"] in line and "client" in line and f"zharn/{key}" in line
    ctx = store._contexts.get(store.character(chr_id)["live_context"])
    store.comment(key, "reply")
    assert f"in client at {d['path']}" in ctx.sent[-1].splitlines()[0]


# ---------------------------------------------------------------- the phase skill in messages (spec §5.3)

def test_a_fresh_brief_ends_with_the_phase_skill_and_records_it(store, contexts):
    key, chr_id = started(store)
    first = contexts.get("ctx_1").sent[0]
    assert first.rstrip().endswith(skills.phase_skill("planning")) and store.character(chr_id)["phase_seen"] == "planning"


def test_a_missing_phase_skill_notifies_once(store, contexts, monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_SKILLS_DIR", str(tmp_path))               # an empty tree: no skills at all
    key, chr_id = started(store)
    assert store.character(chr_id)["phase_seen"] == "planning"
    assert len(store.notifier.errors) == 1 and "planning-a-story" in store.notifier.errors[0]
    store.comment(key, "same phase")                                     # a second delivery in the same phase
    assert len(store.notifier.errors) == 1


def test_a_fork_gets_no_skill_and_copies_phase_seen(store, contexts):
    key, chr_id = started(store)
    contexts.get(store.character(chr_id)["live_context"]).status = "idle"
    r = store.cast_call(chr_id, "claude-fast", "second opinion", fork=True)
    friend = store.character(r["character"])
    assert friend["phase_seen"] == "planning"
    assert skills.phase_skill("planning") not in contexts.get(friend["live_context"]).sent[0]


def test_proceed_delivers_the_implementing_skill_once(store, contexts):
    key, chr_id = started(store)
    ctx = contexts.get("ctx_1")
    store.cast_yield(chr_id, "handoff", "outline")
    store.proceed(key, "go")
    build = skills.phase_skill("implementing")
    assert ctx.sent[-1].rstrip().endswith(build) and store.character(chr_id)["phase_seen"] == "implementing"
    store.comment(key, "same phase")
    assert build not in ctx.sent[-1] and ctx.sent[-1].startswith("[situation] phase implementing")


def test_back_to_planning_and_reopen_deliver_the_new_phase_skill(store, contexts):
    key, chr_id = started(store)
    ctx = contexts.get("ctx_1")
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    store.cast_yield(chr_id, "handoff", "built")
    store.backToPlanning(key, "rethink")
    assert ctx.sent[-1].rstrip().endswith(skills.phase_skill("planning")) and store.character(chr_id)["phase_seen"] == "planning"
    store.cancel(key)
    store.reopen(key, "one more")
    assert ctx.sent[-1].rstrip().endswith(skills.phase_skill("implementing")) and store.character(chr_id)["phase_seen"] == "implementing"


def test_an_inbox_item_popped_after_a_proceed_carries_the_new_skill(store, contexts):
    """Proposal §7: a friend cast in planning learns of Proceed at its next delivery — here an inbox pop."""
    key, chr_id = started(store)
    r = store.cast_call(chr_id, "claude-fast", "read the docs")
    friend = store.character(r["character"])
    fctx = contexts.get(friend["live_context"])
    assert friend["phase_seen"] == "planning"
    store.openThread(key, "@claude-fast btw")                      # the friend is working → its inbox
    assert store.character(r["character"])["inbox"]
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    settle(store, contexts, r["character"])                         # its turn ends: the item pops
    assert fctx.sent[-1].startswith("[situation] phase implementing")
    assert fctx.sent[-1].rstrip().endswith(skills.phase_skill("implementing"))
    assert store.character(r["character"])["phase_seen"] == "implementing"


def test_cast_proceed_returns_the_skill_and_the_next_delivery_does_not_repeat_it(store, contexts):
    key = store.create("Plain", "no outline rule")
    chr_id = store.start(key, "go", "claude-fast")
    ctx = contexts.get(store.character(chr_id)["live_context"])
    r = store.cast_proceed(chr_id, "bounded")
    assert r["kind"] == "system" and r["skill"] == skills.phase_skill("implementing")
    assert store.character(chr_id)["phase_seen"] == "implementing"
    store.comment(key, "hi")
    assert skills.phase_skill("implementing") not in ctx.sent[-1]


def test_a_friend_cast_in_implementing_gets_the_implementing_skill(store, contexts):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    r = store.cast_call(chr_id, "claude-fast", "build it")
    friend = store.character(r["character"])
    assert contexts.get(friend["live_context"]).sent[0].rstrip().endswith(skills.phase_skill("implementing"))
    assert friend["phase_seen"] == "implementing"


def test_a_recast_brief_ends_with_the_current_skill(store, contexts):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    contexts.get(store.character(chr_id)["live_context"]).status = "idle"
    new = store.recast(key, chr_id)
    first = contexts.get(new).sent[0]
    assert "## Situation" in first and first.rstrip().endswith(skills.phase_skill("implementing"))
    assert store.character(chr_id)["phase_seen"] == "implementing"


def test_env_checks_lists_every_environment(store, ws, repo, contexts, tmp_path):
    register_repo(ws, str(make_repo(tmp_path / "ws" / "plain")), checks="")
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key, "go")
    store.cast_env_open(chr_id, "client"); store.cast_env_open(chr_id, "plain")
    plan = store.env_checks(chr_id)
    assert plan["run"] and {e["repo"]: e["checks"] for e in plan["environments"]} == {"client": "echo ok", "plain": ""}


# ---------------------------------------------------------------- context usage (spec §2.3)

def reading(store, contexts, chr_id, tokens, window=1_000_000):
    """The character's live context reports a reading, as the real store does on every assistant event."""
    ctx = contexts.get(store.character(chr_id)["live_context"])
    ctx.contextTokens, ctx.contextWindow = tokens, window
    contexts.contextUsage.emit(ctx.id)
    return ctx


def test_warn_line_pushes_one_recap_request_and_marks_recap_due(store, contexts):
    key, chr_id = started(store)                        # the stub is working: the brief was just sent
    ctx = reading(store, contexts, chr_id, 299_999)
    assert len(ctx.sent) == 1                            # under the line: nothing
    reading(store, contexts, chr_id, 300_000)
    assert len(ctx.sent) == 2
    lines = ctx.sent[-1].splitlines()
    assert lines[0].startswith("[situation] phase planning · attending #main") and lines[0].endswith(" · recap due")
    assert lines[1] == ("[harness] context past the warn line: post a `recap` in #main now — "
                        "your successor is built from the story record and that recap.")
    reading(store, contexts, chr_id, 350_000)
    assert len(ctx.sent) == 2                            # once per context
    assert store.character(chr_id)["context_warned"] == 0 and store.cast(key)[0]["recapDue"] is True


def test_a_recap_clears_recap_due_but_neither_the_reading_nor_the_crossing(store, contexts):
    key, chr_id = started(store)
    ctx = reading(store, contexts, chr_id, 300_000)
    assert store.situation(store.character(chr_id)).endswith(" · recap due")
    store.cast_recap(chr_id, "so far: the outline")
    assert not store.situation(store.character(chr_id)).endswith("recap due")
    assert ctx.contextTokens == 300_000 and store.cast(key)[0]["recapDue"] is False
    reading(store, contexts, chr_id, 400_000)
    assert len(ctx.sent) == 2                            # the warn push does not re-arm


def test_max_line_pushes_then_recasts_at_the_turn_boundary_naming_the_cause(store, contexts):
    key, chr_id = started(store)
    old = store.character(chr_id)["live_context"]
    ctx = reading(store, contexts, chr_id, 500_000)
    assert len(ctx.sent) == 3                            # both lines in one reading: warn first, then max
    assert "[harness] context past the warn line" in ctx.sent[1]
    assert ctx.sent[2].splitlines()[1] == ("[harness] context at the limit: finish the step in hand and post a `recap` in #main now. "
                                           "You are recast when this turn ends.")
    assert store.character(chr_id)["recast_pending"] == {"role": "", "model": "", "cause": "context"}
    assert store.character(chr_id)["context_maxed"] is True
    store.cast_recap(chr_id, "done: half the plan")
    settle(store, contexts, chr_id)
    ch = store.character(chr_id)
    assert ch["live_context"] != old and "recast_pending" not in ch
    assert "context_warned" not in ch and "context_maxed" not in ch
    assert store.comments(key)[-1]["body"] == "recast protagonist as protagonist (context; rung 1: fresh recap)"
    assert not store.situation(ch).endswith("recap due")


def test_a_manual_recast_already_pending_keeps_its_role_when_the_max_line_hits(store, contexts):
    key, chr_id = started(store)
    store.recast(key, chr_id, role="claude-fast")        # working: waits for the boundary
    reading(store, contexts, chr_id, 500_000)
    assert store.character(chr_id)["recast_pending"] == {"role": "claude-fast", "model": ""}
    settle(store, contexts, chr_id)
    assert store.comments(key)[-1]["body"] == "recast protagonist as claude-fast (rung 3: no fresh recap)"


def test_thresholds_scale_to_a_small_window(store, contexts):
    key, chr_id = started(store)
    ctx = reading(store, contexts, chr_id, 59_999, window=200_000)
    assert len(ctx.sent) == 1
    reading(store, contexts, chr_id, 60_000, window=200_000)
    assert len(ctx.sent) == 2 and "warn line" in ctx.sent[-1]
    reading(store, contexts, chr_id, 100_000, window=200_000)
    assert len(ctx.sent) == 3 and "at the limit" in ctx.sent[-1]


def test_readings_on_a_context_that_is_not_working_do_nothing(store, contexts):
    key, chr_id = started(store)
    settle(store, contexts, chr_id)                      # idle: no turn to push into
    ctx = reading(store, contexts, chr_id, 500_000)
    assert not any("[harness]" in s for s in ctx.sent)
    ch = store.character(chr_id)
    assert "context_warned" not in ch and "context_maxed" not in ch and "recast_pending" not in ch


def test_readings_after_approve_do_nothing(store, contexts):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline")
    store.proceed(key)
    store.cast_yield(chr_id, "handoff", "built")
    store.approve(key)
    ctx = contexts.get(store.character(chr_id)["live_context"])
    ctx.status = "working"                               # a turn still finishing after Approve
    reading(store, contexts, chr_id, 500_000)
    assert not any("[harness]" in s for s in ctx.sent) and "context_warned" not in store.character(chr_id)


def test_a_fork_inherits_no_crossings(store, contexts):
    key, chr_id = started(store)
    reading(store, contexts, chr_id, 300_000)
    settle(store, contexts, chr_id)
    forked = store.cast_call(chr_id, "claude-fast", "second opinion", fork=True)["character"]
    assert "context_warned" not in store.character(forked) and store.character(chr_id)["context_warned"] == 0
    assert not store.situation(store.character(forked)).endswith("recap due")
