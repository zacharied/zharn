# Characters and Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Characters beyond the protagonist — friends (fresh or forked), guests, routing and delivery by attention, the quiet check at every turn end, `call`/`wait`, retirement, sub-stories authored by characters, and recast — so a story can be worked by a cast rather than one agent on one thread.

**Architecture:** The pure reducer (`harness/lifecycle.py`) gains "only the lead yields" (with the harness yielding *for* a lead), per-thread recaps, system notes, and two pure helpers `owes()`/`awaits()`. `StoryStore` derives each character's `status` from those plus its context's status, routes every comment to addressees (spec §3.2), delivers by attention (push mid-turn vs inbox), and runs the turn-end pipeline off `ContextStore.contextSettled`. A `Context` learns when a `result` is really a turn end by counting pushed messages against their `--replay-user-messages` echoes. Sub-stories and recast reuse all of the above — a sub-story's yield is just a comment addressed to a character of another story, and a recast is a new context handed the brief plus a situation line.

**Tech Stack:** Python ≥3.10, PySide6 6.11, pytest, `tests/fake_claude.py` (extended: replay echoes).

**Spec:** `docs/superpowers/specs/2026-08-28-story-lifecycle-design.md` §1 (character state), §2.1 (Approve/Cancel/Reopen/Open a thread/Recast rows), §2.2 (cast verbs), §2.3 (delivery, turn end, mechanics table), §2.4 (invariants), §3.1 (brief), §3.2 (routing), §3.4 (recast ladder); `docs/AGENT-MODEL.md` §2–§8. Read §2.2–§3.2 before every task; they are short.

## Global Constraints

- **No backward compatibility** (DESIGN.md §0): no migration for character records lacking new keys — use `.get()` with defaults; old `Start.role` data is simply ignored.
- **Nobody sets status.** Phase and turns change only through `lifecycle.step`. No new setter anywhere.
- Every QML-facing mutation is an `@intent`; every cast verb reaches the store through `harness/ipc.py` and is logged to `verbs_log` by the existing wrapper in `make_handler.h`.
- Character records are plain dicts in `local/characters.json`: `{id, story_key, role, name, live_context, forked_from, attention, inbox, recaps, recap_turns, recast_pending, verbs_log}`. `owes`, `awaits`, `status` are **derived, never stored**.
- Cast-facing text names threads by **id** (`#thr_…`), because that is what `--thread` takes; the UI shows `#n`.
- Tests run with `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q`. Full suite green at the end of every task.
- Commit after every task, message style `Component: what changed`, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **Out of scope (deferred, say so in DESIGN §8):** context-usage tracking and therefore auto-recast at `CONTEXT_WARN`/`CONTEXT_MAX`; recast rung 2 (a final restricted recap turn); repo `checks` at handoff (workspace plan); `harness/skills/`; the QML for cast panel, `/fork`, `wait`, sub-stories (UI thread — briefed at the end).

## File map

| File | Change |
|---|---|
| `harness/lifecycle.py` | `Start` loses `role`; `Yield.auto_for`; `Recap.thread_id`; `Note`; `OpenThread` rejects self-addressing; `owes()`/`awaits()`; invariants. |
| `harness/stories.py` | Character state; routing; delivery; turn end; `_cast`; `openThread`; `cast_call`/`cast_wait`/`cast_create`/`cast_author`; retirement; recast; brief additions. |
| `harness/contexts.py` | `_unacked` turn-end tracking. |
| `harness/agents.py` | `--replay-user-messages`. |
| `harness/config_def.py` | `CHARACTER_SYSTEM_PROMPT` rewrite; `FORK_NOTE`; `RECAP_STALE_TURNS`. |
| `harness/ipc.py`, `harness/cli.py` | `call`, `wait`, `cast`, `inbox`, `create`, `recast`, `<key>` author verbs; `recap --thread`; `comment --to`. |
| `tests/fake_claude.py` | Echo user messages when `--replay-user-messages` is on. |
| `tests/test_lifecycle.py`, `test_stories.py`, `test_contexts_unit.py`, `test_ipc.py`, `test_cli.py` | Per task. |
| `docs/DESIGN.md` §8 | Status. |

---

### Task 1: Reducer — only the lead yields; the harness may yield for it; recaps per thread; notes

**Files:**
- Modify: `harness/lifecycle.py` (`Start`, `Yield`, `Recap`, new `Note`, `step`, helpers)
- Modify: `harness/stories.py:296` (drop `role=` from the `lc.Start(...)` call)
- Test: `tests/test_lifecycle.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass
  class Start:  thread_id: str; protagonist: str; note: str = ""            # role removed
  @dataclass
  class Yield:  thread_id; by; kind; body; options=[]; open_substories=0; checks=[]; auto_for: str = ""
  @dataclass
  class Recap:  by: str; body: str; thread_id: str | None = None            # None → main
  @dataclass
  class Note:   thread_id: str; body: str                                   # system comment, no turn change
  def owes(story: Story, character: str) -> list[Thread]     # led by character, turn == "cast"
  def awaits(story: Story, character: str) -> list[Thread]   # authored by character, turn == "cast"
  ```
  Rejections (exact prefixes tests match on): `"only the thread's lead yields in it"`, `"the harness yields only for the thread's lead"`, `"a thread cannot be opened to its own author"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lifecycle.py` (note the import line at the top must also gain `Note, awaits, owes`):

```python
def with_friend():
    """(planning, cast) plus side thread t2: human → chr2."""
    s = started()
    s, _ = run(s, OpenThread(thread_id="t2", author="human", lead="chr2", body="review this"))
    return s


def test_only_the_threads_lead_yields_in_it():
    s = with_friend()
    with pytest.raises(Rejected, match="only the thread's lead yields in it"):
        run(s, Yield("t2", "chr1", "handoff", "not mine"))
    with pytest.raises(Rejected, match="only the thread's lead yields in it"):
        run(s, Yield("t1", "chr2", "handoff", "not mine either"))
    s2, c = run(s, Yield("t2", "chr2", "handoff", "done"))
    assert s2.thread("t2").turn == "author" and c["author"] == "chr2"


def test_the_harness_yields_for_the_lead():
    s = with_friend()
    with pytest.raises(Rejected, match="harness yields only for the thread's lead"):
        run(s, Yield("t2", "system", "handoff", "went quiet", auto_for="chr1"))
    s2, c = run(s, Yield("t2", "system", "handoff", "chr2 went quiet: last words", auto_for="chr2"))
    assert s2.thread("t2").turn == "author" and c["author"] == "system" and c["kind"] == "handoff"
    assert c["structured"]["auto_for"] == "chr2"
    s3, _ = run(s2, Reply(thread_id="t2", body="carry on", by="human"))  # the author replies as usual
    assert s3.thread("t2").turn == "cast"


def test_recap_lands_in_the_given_thread_or_main():
    s = with_friend()
    _, c = run(s, Recap(by="chr2", body="cleared A", thread_id="t2"))
    assert c["thread_id"] == "t2" and c["kind"] == "recap"
    _, c = run(s, Recap(by="chr1", body="on main"))
    assert c["thread_id"] == "t1"


def test_note_is_a_system_comment_that_moves_nothing():
    s = with_friend()
    s2, c = run(s, Note(thread_id="t1", body="recast protagonist (rung 1)"))
    assert c["author"] == "system" and c["kind"] == "system" and c["body"] == "recast protagonist (rung 1)"
    assert [t.turn for t in s2.threads] == [t.turn for t in s.threads] and s2.phase == s.phase
    canceled, _ = run(s, Cancel())
    with pytest.raises(Rejected, match="terminal"):
        run(canceled, Note(thread_id="t1", body="x"))


def test_a_thread_cannot_be_opened_to_its_own_author():
    with pytest.raises(Rejected, match="cannot be opened to its own author"):
        run(started(), OpenThread(thread_id="t2", author="chr1", lead="chr1", body="me"))


def test_owes_and_awaits_are_read_off_turns():
    s = with_friend()
    s, _ = run(s, OpenThread(thread_id="t3", author="chr1", lead="chr3", body="build it"))
    assert [t.id for t in owes(s, "chr1")] == ["t1"] and [t.id for t in awaits(s, "chr1")] == ["t3"]
    assert [t.id for t in owes(s, "chr3")] == ["t3"] and awaits(s, "chr3") == []
    s, _ = run(s, Yield("t3", "chr3", "handoff", "built"))
    assert owes(s, "chr3") == [] and awaits(s, "chr1") == []          # waiting on chr1 now
    s, _ = run(s, Yield("t1", "chr1", "question", "which?"))
    assert owes(s, "chr1") == []
```

Also change the existing expectation: any test asserting `"only the protagonist yields on the main thread"` now expects `"only the thread's lead yields in it"`; any test asserting `"a thread's author cannot yield in it"` is covered by the same message (`grep -n "protagonist yields\|author cannot yield" tests/`).

- [ ] **Step 2: Run to verify failure**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q tests/test_lifecycle.py`
Expected: ImportError on `Note`/`owes`/`awaits`, then the new tests fail.

- [ ] **Step 3: Implement**

`harness/lifecycle.py` dataclasses:

```python
@dataclass
class Start:
    thread_id: str
    protagonist: str
    note: str = ""


@dataclass
class Yield:
    thread_id: str
    by: str                          # a character, or "system" with auto_for (the harness yielding for a lead)
    kind: str
    body: str
    options: list[str] = field(default_factory=list)
    open_substories: int = 0
    checks: list[dict] = field(default_factory=list)
    auto_for: str = ""


@dataclass
class Recap:
    by: str
    body: str
    thread_id: str | None = None     # None → main


@dataclass
class Note:
    """A system comment: something the harness did (a recast, a call-in). Moves nothing."""
    thread_id: str
    body: str
```

Pure helpers after `_with_note`:

```python
def owes(story: Story, character: str) -> list[Thread]:
    """Threads `character` leads that wait on the cast (AGENT-MODEL §2: what a character owes)."""
    return [t for t in story.threads if t.lead == character and t.turn == "cast"]


def awaits(story: Story, character: str) -> list[Thread]:
    """Threads `character` opened that wait on their cast (sub-stories are added by the store)."""
    return [t for t in story.threads if t.author == character and t.turn == "cast"]
```

In `step`: `OpenThread` gains, before appending,

```python
        if action.author == action.lead:
            raise Rejected("a thread cannot be opened to its own author")
```

`Yield` — replace the two checks `if t.id == s.main_thread and action.by != s.protagonist` and `if action.by == t.author` with:

```python
        if action.by == "system":
            if action.auto_for != t.lead:
                raise Rejected(f"the harness yields only for the thread's lead ({t.lead})")
        elif action.by != t.lead:
            raise Rejected(f"only the thread's lead yields in it (thread {t.id} is led by {t.lead})")
```

and add `auto_for` to `structured`:

```python
        if action.auto_for:
            structured["auto_for"] = action.auto_for
```

`Recap` — thread selection:

```python
    elif isinstance(action, Recap):
        if s.main_thread is None:
            raise Rejected(f"{s.key} has not been started")
        if s.phase in TERMINAL:
            raise Rejected(f"{s.key} is terminal ({s.phase}); its threads are read-only until Reopen")
        t = _require_thread(s, action.thread_id) if action.thread_id else s.main
        c = _comment(s, comment_id, now, thread_id=t.id, author=action.by, kind="recap", body=action.body)
```

New branch before `else: raise Rejected(f"unknown action …")`:

```python
    elif isinstance(action, Note):
        if s.phase in TERMINAL:
            raise Rejected(f"{s.key} is terminal ({s.phase}); its threads are read-only until Reopen")
        t = _require_thread(s, action.thread_id)
        c = _comment(s, comment_id, now, thread_id=t.id, author="system", kind="system", body=action.body)
```

`harness/stories.py:296`: `self._apply(key, lc.Start(thread_id=thread_id, protagonist=chr_id, note=note))`.

- [ ] **Step 4: Run the tests, then the full suite**

Expected: PASS; suite green (fix the two message expectations found by the grep in Step 1).

- [ ] **Step 5: Commit**

```bash
git add harness/lifecycle.py harness/stories.py tests/test_lifecycle.py tests/test_stories.py
git commit -m "Lifecycle: only the lead yields (the harness may yield for it), recaps per thread, system notes, owes/awaits

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Character state — `owes`, `awaits`, `status`; cast rows; needs-you side threads; the planning gate

**Files:**
- Modify: `harness/stories.py` (`needs_you_flavor`, `_row`, `cast`, `cast_proceed`, `_apply`, `start`; new `owes`/`awaits`/`status`)
- Test: `tests/test_stories.py`

**Interfaces:**
- Produces:
  ```python
  StoryStore.owes(ch: dict) -> list[str]      # thread ids
  StoryStore.awaits(ch: dict) -> list[str]    # thread ids + sub-story keys (stories authored by ch with ball == "cast")
  StoryStore.status(ch: dict) -> str          # "retired" | "working" | "waiting" | "idle"
  StoryStore._apply(key, action, extra: dict | None = None) -> dict   # extra merges into comment["structured"]
  cast(key) rows gain: status, owes, awaits, inboxDepth, forkedFrom
  _row(key) gains needsYou for human-authored side threads; flavor "a side thread waits on you"
  ```
  The Start comment's `structured["role"]` names the protagonist's role (spec §2.1).

- [ ] **Step 1: Write the failing tests**

```python
def test_cast_rows_carry_derived_state(store, contexts):
    key, chr_id = started(store)
    live = contexts.get(store.character(chr_id)["live_context"])
    row, = store.cast(key)
    assert (row["status"], row["owes"], row["awaits"], row["inboxDepth"], row["forkedFrom"]) == ("working", [store.get(key)["mainThread"]], [], 0, "")
    live.status = "idle"
    assert store.cast(key)[0]["status"] == "idle"
    tid = new_thread(store, key, author=chr_id, lead="chr_friend")           # helper below
    assert store.cast(key)[0]["status"] == "waiting" and store.cast(key)[0]["awaits"] == [tid]
    store.cancel(key)
    assert store.cast(key)[0]["status"] == "retired"


def new_thread(store, key, *, author, lead, body="hey"):
    tid = f"thr_{len(store.story(key).threads) + 1}"
    store._apply(key, OpenThread(thread_id=tid, author=author, lead=lead, body=body))
    return tid


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
```

Move the `new_thread` helper above its first use.

- [ ] **Step 2: Run to verify failure**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q tests/test_stories.py -k "derived_state or names_the_role or side_threads or last_planning"`
Expected: KeyError `status` / `structured['role']`, needsYou False, gate passes when it should not.

- [ ] **Step 3: Implement**

`needs_you_flavor` (module level):

```python
def needs_you_flavor(story: lc.Story, comments: list[dict]) -> str:
    if story.author != "human":
        return ""
    if story.ball == "author":
        pending = story.main.pending_yield
        kind = next((c["kind"] for c in comments if c["id"] == pending), "")
        if kind == "question":
            return "question"
        if kind == "handoff":
            return "outline ready" if story.phase == "planning" else "ready for review"
        return "waiting on you"
    if any(t.author == "human" and t.turn == "author" and t.id != story.main_thread for t in story.threads):
        return "a side thread waits on you"
    return ""
```

Store methods (after `character`):

```python
    # ---------------------------------------------------------------- derived character state (spec §1)
    def owes(self, ch: dict) -> list[str]:
        return [t.id for t in lc.owes(self._stories[ch["story_key"]], ch["id"])]

    def awaits(self, ch: dict) -> list[str]:
        threads = [t.id for t in lc.awaits(self._stories[ch["story_key"]], ch["id"])]
        subs = [k for k, s in self._stories.items() if s.author == ch["id"] and s.ball == "cast"]
        return threads + subs

    def status(self, ch: dict) -> str:
        if self._stories[ch["story_key"]].phase in lc.TERMINAL:
            return "retired"
        ctx = self._contexts.get(ch["live_context"]) if ch.get("live_context") else None
        if ctx is not None and ctx.status in WORKING:
            return "working"
        return "waiting" if self.awaits(ch) else "idle"
```

`cast()` rows: `out.append({**ch, "contextStatus": ..., "status": self.status(ch), "owes": self.owes(ch), "awaits": self.awaits(ch), "inboxDepth": len(ch.get("inbox", [])), "forkedFrom": ch.get("forked_from") or ""})`.

`_apply(self, key, action, extra=None)`: after the `context` stamp, `if extra: comment["structured"].update(extra)`. `start()`: `self._apply(key, lc.Start(thread_id=thread_id, protagonist=chr_id, note=note), extra={"role": role_cfg["name"]})`.

`cast_proceed` gate:

```python
        if role_cfg.get("outline_first"):
            comments = self._comments.get(key, [])
            last_planning = max((i for i, c in enumerate(comments)
                                 if (c.get("structured", {}).get("transition") or {}).get("to", [None])[0] == "planning"), default=-1)
            approved = {"from": ["planning", "author"], "to": ["implementing", "cast"]}
            if not any(c.get("structured", {}).get("transition") == approved for c in comments[last_planning + 1:]):
                raise lc.Rejected("your role requires an approved outline first: `yield --handoff` the outline and wait for Proceed")
```

(The Start comment's transition is `[todo, None] → [planning, cast]`, so `last_planning` is the Start or the latest Back to planning.)

- [ ] **Step 4: Run the tests, then the full suite** — PASS.

- [ ] **Step 5: Commit**

```bash
git add harness/stories.py tests/test_stories.py
git commit -m "Stories: derived character state (owes/awaits/status), cast rows, needs-you side threads, planning gate since last entry

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Casting and routing — `_cast`, mentions, `addressees`, `openThread`

**Files:**
- Modify: `harness/stories.py` (`start` refactored onto `_cast`; new `_mentions`, `addressees`, `_route`, `_deliver_to` (first version), `_format`, `openThread`; `_deliver` removed)
- Modify: `harness/config_def.py` (`FORK_NOTE`)
- Test: `tests/test_stories.py`

**Interfaces:**
- Consumes: `ContextStore.fork(source_id, *, role_name, owner, story_key, title, system_prompt, env, about)`.
- Produces:
  ```python
  StoryStore._cast(key, role_cfg, *, thread_id, author, note, name="", fork_from: str | None = None) -> dict   # the character record; context created; first message sent
  StoryStore._mentions(key, body) -> list[str]                    # character ids named by @Name (case-insensitive), story-local
  StoryStore.addressees(key, comment) -> list[str]                # spec §3.2, never the comment's own author, characters only
  StoryStore._route(key, comment, phase_before="")                # _deliver_to for each addressee
  StoryStore._deliver_to(ch, comment, phase_before="")            # this task: push + attention := thread (Task 4 adds inbox)
  StoryStore._format(ch, comment, phase_before="") -> str         # "[name] kind in #thr_x: body" (+ " of ZH-n" when cross-story)
  StoryStore.openThread(key, body) -> str                         # @intent; "@Name …" | "/call role [note]" | "/fork @Name [note]" | plain
  config.FORK_NOTE                                                # format keys: name, source
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_open_thread_addresses_the_protagonist_by_default(store, contexts):
    key, chr_id = started(store)
    live = contexts.get(store.character(chr_id)["live_context"])
    tid = store.openThread(key, "why pyte?")
    t = store.story(key).thread(tid)
    assert (t.author, t.lead) == ("human", chr_id)
    assert live.sent[-1].startswith("[you] comment in #" + tid) and store.character(chr_id)["attention"] == tid


def test_open_thread_to_a_named_character(store, contexts):
    key, chr_id = started(store)
    friend = store._cast(key, StubRoles().get("claude-fast"), thread_id="thr_f", author=chr_id, note="build it")
    store._apply(key, OpenThread(thread_id="thr_f", author=chr_id, lead=friend["id"], body="build it"))
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
    assert "you are a fork of protagonist" in first and "what did you mean by X?" in first and not first.startswith("#")


def test_open_thread_rejections(store, contexts):
    key, chr_id = started(store)
    with pytest.raises(Rejected, match="no character named"):
        store.openThread(key, "@nobody hi")
    with pytest.raises(ValueError, match="unknown role"):
        store.openThread(key, "/call wizard do magic")
    with pytest.raises(Rejected, match="working"):
        store.openThread(key, "/fork @protagonist now")      # its context is still working on the brief


def test_addressees_follow_the_routing_rules(store, contexts):
    key, chr_id = started(store)
    friend = store._cast(key, StubRoles().get("claude-fast"), thread_id="thr_f", author=chr_id, note="build")
    c_root = store._apply(key, OpenThread(thread_id="thr_f", author=chr_id, lead=friend["id"], body="build"))
    assert store.addressees(key, c_root) == [friend["id"]]                       # root → lead
    c_yield = store._apply(key, Yield(thread_id="thr_f", by=friend["id"], kind="question", body="which db? @protagonist"))
    assert store.addressees(key, c_yield) == [chr_id]                             # yield → author (mention == author: once)
    c_reply = store._apply(key, Comment(thread_id="thr_f", by=chr_id, body="postgres"))
    assert c_reply["reply_to"] == c_yield["id"] and store.addressees(key, c_reply) == [friend["id"]]   # reply to a yield → yielder
    c_guest = store._apply(key, Comment(thread_id="thr_f", by="human", body="fyi @protagonist"))
    assert store.addressees(key, c_guest) == [friend["id"], chr_id]               # reply → lead, plus mentions
    c_auto = store._apply(key, Yield(thread_id="thr_f", by="system", kind="handoff", body="quiet", auto_for=friend["id"]))
    assert store.addressees(key, c_auto) == [chr_id]
    c_answer = store._apply(key, Comment(thread_id="thr_f", by=chr_id, body="ok"))
    assert store.addressees(key, c_answer) == [friend["id"]]                      # reply to a harness yield → the lead
```

Also update `test_start_casts_protagonist_with_context_brief_and_env` only if it asserts `_deliver`'s old message format (it should not).

- [ ] **Step 2: Run to verify failure** — `-k "open_thread or addressees"`: AttributeError `openThread` / `_cast` / `addressees`.

- [ ] **Step 3: Implement**

`harness/config_def.py`:

```python
# First message of a forked friend (spec §3.1): no brief — it already knows — just who it is and the call note.
FORK_NOTE = ("You are {name}, a fork of {source}: a new character with a copy of its memory as of now. You cannot change "
             "{source}'s plan; if something must reach it, say `@{source}` in a comment. Your call-in note follows.\n\n")
```

`harness/stories.py` — replace the body of `start()` from `taken = …` through `self._contexts.get(cid).send(render_brief(...))` with the shared caster:

```python
    def _cast(self, key: str, role_cfg: dict, *, thread_id: str, author: str, note: str, name: str = "",
              fork_from: str | None = None) -> dict:
        """Cast a character on `key` to lead `thread_id` (spec §2.1 Open a thread, §2.2 call): a record, a live
        context (fresh from the role, or forked from `fork_from`'s live context), and its first message."""
        provider = role_cfg.get("provider", "claude-code")
        if provider != "claude-code":
            raise ValueError(f"role {role_cfg['name']!r} uses provider {provider!r}, which is not implemented yet")
        taken = {ch["name"] for ch in self._characters.values() if ch["story_key"] == key}
        base = name or role_cfg["name"]
        name, n = base, 2
        while name in taken:
            name, n = f"{base}-{n}", n + 1
        chr_id = new_id("chr_")
        ch = {"id": chr_id, "story_key": key, "role": role_cfg["name"], "name": name, "live_context": None,
              "forked_from": fork_from, "attention": thread_id, "inbox": [], "recaps": [], "verbs_log": []}
        self._characters[chr_id] = ch
        s = self._stories[key]
        env = {"HARNESS_CHARACTER_ID": chr_id}
        title = f"{key} · {name}"
        try:
            if fork_from is None:
                cid = self._contexts.create(role_cfg["name"], story_key=key, owner=chr_id, title=title,
                                            system_prompt=self._system_prompt(s, ch, role_cfg), env=env)
                first = render_brief(s, self._comments[key], self._characters, role_cfg, note)
            else:
                src = self._characters[fork_from]
                src_ctx = self._contexts.get(src["live_context"]) if src.get("live_context") else None
                if src_ctx is None or src_ctx.status in WORKING or not getattr(src_ctx, "sessionId", ""):
                    raise lc.Rejected(f"{src['name']} is working or has never run; fork it when it stops")
                cid = self._contexts.fork(src["live_context"], role_name=role_cfg["name"], owner=chr_id, story_key=key,
                                          title=title, system_prompt=self._system_prompt(s, ch, role_cfg), env=env)
                first = getattr(cfg, "FORK_NOTE", "").format(name=name, source=src["name"]) + note
        except Exception:
            del self._characters[chr_id]
            raise
        ch["live_context"] = cid
        self._save_characters()
        self._contexts.get(cid).send(first)
        return ch
```

`start()` becomes: resolve `role_cfg`; `chr_id, thread_id = new_id("chr_"), new_id("thr_")` → instead mint only `thread_id`, snapshot `prev_story`/`prev_comments`, then

```python
        chr_id = new_id("chr_")
        self._apply(key, lc.Start(thread_id=thread_id, protagonist=chr_id, note=note), extra={"role": role_cfg["name"]})
        try:
            ch = self._cast_with_id(key, role_cfg, chr_id=chr_id, thread_id=thread_id, author="human", note=note)
        except Exception:
            ...restore prev_story / prev_comments as today...
            raise
        self._refresh()
        return chr_id
```

To keep one caster, give `_cast` a keyword `chr_id: str | None = None` (used when the reducer already knows the id, as Start does): `chr_id = chr_id or new_id("chr_")`. Drop the separate `_cast_with_id` name — call `_cast(..., chr_id=chr_id)`.

Routing and delivery:

```python
    # ---------------------------------------------------------------- routing (spec §3.2) and delivery (§2.3)
    def _mentions(self, key: str, body: str) -> list[str]:
        names = {ch["name"].lower(): ch["id"] for ch in self._characters.values() if ch["story_key"] == key}
        out = []
        for m in re.findall(r"@([\w-]+)", body or ""):
            cid = names.get(m.lower())
            if cid and cid not in out:
                out.append(cid)
        return out

    def _comment_by_id(self, comment_id: str) -> dict | None:
        for comments in self._comments.values():
            for c in comments:
                if c["id"] == comment_id:
                    return c
        return None

    def addressees(self, key: str, comment: dict) -> list[str]:
        s = self._stories[key]
        t = s.thread(comment["thread_id"])
        if comment["kind"] in lc.YIELD_KINDS:
            target = t.author
        elif comment.get("reply_to"):
            pending = self._comment_by_id(comment["reply_to"])
            target = pending["author"] if pending and pending["author"] in self._characters else t.lead
        else:
            target = t.lead
        out = []
        for cid in [target] + self._mentions(key, comment["body"]):
            if cid in self._characters and cid != comment["author"] and cid not in out:
                out.append(cid)
        return out

    def _format(self, ch: dict, comment: dict, phase_before: str = "") -> str:
        kind = "reply" if comment.get("reply_to") else ("comment" if comment["kind"] == "text" else comment["kind"])
        where = f"#{comment['thread_id']}" + (f" of {comment['story_key']}" if comment["story_key"] != ch["story_key"] else "")
        text = f"[{author_name(comment['author'], self._characters)}] {kind} in {where}: {comment['body']}"
        opts = comment.get("structured", {}).get("options")
        if opts:
            text += f"\n(options: {', '.join(opts)})"
        phase = self._stories[comment["story_key"]].phase
        if phase_before and phase != phase_before:
            text += f"\nPhase is now {phase}."
        return text

    def _deliver_to(self, ch: dict, comment: dict, phase_before: str = ""):
        """Push to the character's context and move its attention (Task 4 adds the mid-turn inbox branch)."""
        if self._stories[ch["story_key"]].phase in lc.TERMINAL:
            return  # retired
        ctx = self._contexts.get(ch["live_context"]) if ch.get("live_context") else None
        if ctx is None:
            return
        ch["attention"] = comment["thread_id"]
        self._save_characters()
        role_cfg = self._roles.get(ch["role"]) or {}
        ctx.meta["systemPrompt"] = self._system_prompt(self._stories[ch["story_key"]], ch, role_cfg)
        ctx.send(self._format(ch, comment, phase_before))

    def _route(self, key: str, comment: dict, phase_before: str = ""):
        for cid in self.addressees(key, comment):
            self._deliver_to(self._characters[cid], comment, phase_before)
```

Add `import re` at the top. `_author_action`: `if resume: self._route(key, comment, before)`. Delete `_protagonist_context` and `_deliver`. Human `comment()` already goes through `_author_action(..., resume=True)`; `resolve` keeps `resume=False`.

`openThread`:

```python
    @Slot(str, str, result=str)
    @intent
    def openThread(self, key, body):
        """Spec §2.1 Open a thread: plain → protagonist; "@Name …" → Name; "/call <role> [note]" → a fresh friend;
        "/fork @Name [note]" → a friend forked from Name. Returns the thread id."""
        key = self._key(key)
        s = self._stories[key]
        body = (body or "").strip()
        thread_id = new_id("thr_")
        m_call = re.match(r"/call\s+(\S+)\s*(.*)", body, re.S)
        m_fork = re.match(r"/fork\s+@([\w-]+)\s*(.*)", body, re.S)
        m_name = re.match(r"@([\w-]+)\b", body)
        if m_call:
            role_cfg = self._roles.get(m_call.group(1))
            if not role_cfg:
                raise ValueError(f"unknown role {m_call.group(1)!r}")
            note = m_call.group(2).strip() or f"called in as {role_cfg['name']}"
            before = (s, list(self._comments.get(key, [])))
            ch = self._cast(key, role_cfg, thread_id=thread_id, author="human", note=note)
            self._apply(key, lc.OpenThread(thread_id=thread_id, author="human", lead=ch["id"], body=note))
            return thread_id
        if m_fork:
            source = self._by_name(key, m_fork.group(1))
            note = m_fork.group(2).strip() or "a side question"
            ch = self._cast(key, self._roles.get(source["role"]) or {"name": source["role"]}, thread_id=thread_id,
                            author="human", note=note, fork_from=source["id"])
            self._apply(key, lc.OpenThread(thread_id=thread_id, author="human", lead=ch["id"], body=note))
            return thread_id
        lead = self._by_name(key, m_name.group(1))["id"] if m_name else s.protagonist
        comment = self._apply(key, lc.OpenThread(thread_id=thread_id, author="human", lead=lead, body=body))
        self._route(key, comment)
        return thread_id

    def _by_name(self, key: str, name: str) -> dict:
        for ch in self._characters.values():
            if ch["story_key"] == key and ch["name"].lower() == name.lower():
                return ch
        raise lc.Rejected(f"no character named {name!r} on {key}")
```

For `/call` and `/fork` the friend's first message *is* the call note (brief or fork note), so the root comment is not routed again — the thread record gets the note via `OpenThread`. Note the ordering: `_cast` first (so a failing provider/fork leaves no half-thread), then `OpenThread`; if `OpenThread` raises after a cast succeeded, delete the character and stop its context — wrap in `try/except` mirroring `start()`.

- [ ] **Step 4: Run the tests, then the full suite** — PASS. Existing delivery tests (`test_human_comment_while_waiting_is_a_reply_delivered_to_protagonist`, `test_proceed_moves_phase_and_tells_protagonist`, `test_deliver_refreshes_system_prompt_with_current_phase`) must still pass through `_route`; if one asserts `#<thread_id>` formatting it is unchanged.

- [ ] **Step 5: Commit**

```bash
git add harness/stories.py harness/config_def.py tests/test_stories.py
git commit -m "Stories: cast friends (fresh or forked), mentions, routing to addressees, openThread with @Name / /call / /fork

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Delivery by status — push vs inbox, and a `result` that is really a turn end

**Files:**
- Modify: `harness/agents.py:117-119` (`--replay-user-messages`)
- Modify: `harness/contexts.py` (`Context.__init__`, `send`, `_on_event`, `_on_finished`)
- Modify: `tests/fake_claude.py` (echo user messages when the flag is on)
- Modify: `harness/stories.py` (`_deliver_to`)
- Test: `tests/test_contexts_unit.py`, `tests/test_stories.py`

**Interfaces:**
- Produces: `Context._unacked: int` — messages pushed to a running process not yet echoed. A `result` while `_unacked > 0` keeps status `working` (no `contextSettled`). Spike 2026-09-02: claude echoes a pushed message when it consumes it — mid-turn (folded into the running turn, before its `result`) or at the start of the next turn — so this rule is exact.
- `_deliver_to`: target `working` and attention ≠ thread → `ch["inbox"].append(comment_id)`; otherwise push now and `attention := thread`.

- [ ] **Step 1: Teach the fake to echo**

In `tests/fake_claude.py` `main()`, inside the `for line in sys.stdin` loop, right after `prompt = …`:

```python
        if "--replay-user-messages" in args:
            emit({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": prompt}]}})
```

- [ ] **Step 2: Write the failing tests**

`tests/test_contexts_unit.py`:

```python
def test_a_result_is_not_a_turn_end_while_a_pushed_message_is_unechoed(store):
    settled = []
    store.contextSettled.connect(settled.append)
    c = store.get(store.spawn("claude-fast", "slow one"))
    assert wait_until(lambda: c.status == "working")
    c.send("two")                                  # pushed mid-turn; the fake echoes it only when it reads it
    assert c._unacked == 2 or c._unacked == 1        # "slow one" may or may not be echoed yet
    assert wait_until(lambda: c.turns == 2 and c.status == "idle", timeout_ms=8000), (c.turns, c.status)
    assert settled == [c.id]                       # one settle for two results: the first was not a turn end
    assert [r["text"] for r in c.transcript.rows() if r["role"] == "user"] == ["slow one", "two"]   # no double rows
    assert c._unacked == 0


def test_a_crash_settles_regardless_of_unechoed_pushes(store, monkeypatch):
    c = store.get(store.spawn("claude-fast", "slow one"))
    assert wait_until(lambda: c.status == "working")
    c.send("never echoed")
    c.stop()
    assert wait_until(lambda: c.status == "stopped") and c._unacked == 0
```

`tests/test_stories.py`:

```python
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
```

- [ ] **Step 3: Run to verify failure** — `_unacked` AttributeError; inbox stays `[]`.

- [ ] **Step 4: Implement**

`harness/agents.py`: `args = cmd[1:] + ["-p", "--output-format", "stream-json", "--input-format", "stream-json", "--verbose", "--include-partial-messages", "--replay-user-messages"]`.

`harness/contexts.py`, `Context.__init__`: `self._unacked = 0`. `send()`: after the spawn-or-working branch, before `self._proc.send_user(text)`: `self._unacked += 1`. `_on_event`:

```python
    def _on_event(self, ev: dict):
        self._log(ev)
        if ev.get("type") == "user" and _has_text_block(ev):
            self._unacked = max(0, self._unacked - 1)          # claude echoed a pushed message: it has been consumed
        hint = self._interp.apply(ev)
        if hint == "idle" and self._unacked > 0:
            hint = "working"                                    # a pushed message is still queued: not a turn end
        if hint:
            self._set_status(hint)
        else:
            self.changed.emit()
```

with, at module level:

```python
def _has_text_block(ev: dict) -> bool:
    content = (ev.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content)
    return any(isinstance(b, dict) and b.get("type") == "text" for b in content or [])
```

`_on_finished` and `stop()`: reset `self._unacked = 0` (a dead process echoes nothing). `replay()` never touches `_unacked`.

`harness/stories.py` `_deliver_to`:

```python
    def _deliver_to(self, ch: dict, comment: dict, phase_before: str = ""):
        """Spec §2.3 delivery: mid-turn, the attended thread is pushed now and everything else waits in the inbox;
        a waiting or idle character is woken by whatever arrives and attends its thread."""
        if self._stories[ch["story_key"]].phase in lc.TERMINAL:
            return  # retired
        ctx = self._contexts.get(ch["live_context"]) if ch.get("live_context") else None
        if ctx is None:
            return
        if ctx.status in WORKING and ch.get("attention") != comment["thread_id"]:
            ch.setdefault("inbox", []).append(comment["id"])
            self._save_characters()
            self._refresh()
            return
        ch["attention"] = comment["thread_id"]
        self._save_characters()
        role_cfg = self._roles.get(ch["role"]) or {}
        ctx.meta["systemPrompt"] = self._system_prompt(self._stories[ch["story_key"]], ch, role_cfg)
        ctx.send(self._format(ch, comment, phase_before))
```

- [ ] **Step 5: Run the tests, then the full suite** — PASS.

- [ ] **Step 6: Commit**

```bash
git add harness/agents.py harness/contexts.py harness/stories.py tests/fake_claude.py tests/test_contexts_unit.py tests/test_stories.py
git commit -m "Delivery: push the attended thread mid-turn, inbox the rest; a result is a turn end only once pushed messages are echoed

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Turn end — attention clears, the quiet check, one inbox pop

**Files:**
- Modify: `harness/stories.py` (`__init__` connects `contextSettled`; new `_character_by_context`, `_thread_anywhere`, `_on_turn_end`)
- Modify: `tests/test_stories.py` (`StubContexts` gains `contextSettled = Signal(str)`)
- Test: `tests/test_stories.py`

**Interfaces:**
- Produces: `StoryStore._on_turn_end(context_id)` — spec §2.3 steps 1–3. Quiet-check yields: `lc.Yield(thread_id, by="system", kind="handoff", body=f"{name} {why}: {text}", auto_for=id)` with `why ∈ {"went quiet", "crashed", "was stopped"}` from the context status (`idle` / `failed` / `stopped`).

- [ ] **Step 1: Write the failing tests**

```python
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
    store.cast_yield(chr_id, "question", "which?")                 # attended main yields, then the turn ends
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
```

Extend the stub: `StubContext` gains `self.transcript_text = ""`, `self.last_error = ""`, `def last_assistant_text(self): return self.transcript_text`, `@property def lastError(self): return self.last_error`; `StubContexts` gains `contextSettled = Signal(str)`.

- [ ] **Step 2: Run to verify failure** — `-k "quiet or waiting_character or crash_or_stop or pops_one or retired"`.

- [ ] **Step 3: Implement**

`StoryStore.__init__`: after `contexts.contextsChanged.connect(self._refresh)`: `contexts.contextSettled.connect(self._on_turn_end)`.

```python
    # ---------------------------------------------------------------- turn end (spec §2.3)
    def _character_by_context(self, context_id: str) -> dict | None:
        return next((ch for ch in self._characters.values() if ch.get("live_context") == context_id), None)

    def _thread_anywhere(self, thread_id: str):
        for key, s in self._stories.items():
            for t in s.threads:
                if t.id == thread_id:
                    return key, t
        return None, None

    def _on_turn_end(self, context_id: str):
        ch = self._character_by_context(context_id)
        if ch is None:
            return
        key = ch["story_key"]
        s = self._stories[key]
        if s.phase in lc.TERMINAL:
            return  # retired
        ctx = self._contexts.get(context_id)
        # 1. attention clears once the attended thread no longer waits on the cast
        _, att = self._thread_anywhere(ch.get("attention") or "")
        if att is None or att.turn != "cast":
            ch["attention"] = None
        # 2. the quiet check: nothing awaited ⇒ every owed thread is yielded for it
        if not self.awaits(ch):
            status = getattr(ctx, "status", "idle")
            why = {"failed": "crashed", "stopped": "was stopped"}.get(status, "went quiet")
            text = (ctx.last_assistant_text() if ctx is not None else "") or (getattr(ctx, "lastError", "") if ctx is not None else "") or "(no output)"
            for t in lc.owes(s, ch["id"]):
                c = self._apply(key, lc.Yield(thread_id=t.id, by="system", kind="handoff",
                                              body=f"{ch['name']} {why}: {text}", auto_for=ch["id"]))
                self._route(key, c)
        # 3. one inbox item
        inbox = ch.setdefault("inbox", [])
        while inbox:
            comment = self._comment_by_id(inbox.pop(0))
            if comment is not None:
                ch["attention"] = comment["thread_id"]
                self._save_characters()
                if ctx is not None:
                    role_cfg = self._roles.get(ch["role"]) or {}
                    ctx.meta["systemPrompt"] = self._system_prompt(s, ch, role_cfg)
                    ctx.send(self._format(ch, comment))
                break
        self._save_characters()
        self._refresh()
```

- [ ] **Step 4: Run the tests, then the full suite** — PASS.

- [ ] **Step 5: Commit**

```bash
git add harness/stories.py tests/test_stories.py
git commit -m "Turn end: attention clears, the quiet check yields owed threads for a character that awaits nothing, one inbox pop per turn

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Cast verbs — `call`, `wait`, `recap --thread`, `comment --to`, `cast`, `inbox`; the system prompt; IPC and CLI

**Files:**
- Modify: `harness/stories.py` (`cast_call`, `cast_wait`, `cast_recap`, `cast_comment`, `cast_inbox`, `_system_prompt`)
- Modify: `harness/config_def.py` (`CHARACTER_SYSTEM_PROMPT`)
- Modify: `harness/ipc.py` (`story_cmd`), `harness/cli.py` (`main`)
- Test: `tests/test_stories.py`, `tests/test_ipc.py`, `tests/test_cli.py`

**Interfaces:**
- Produces:
  ```python
  StoryStore.cast_call(character_id, role, note, as_name="", fork=False) -> dict   # {"thread": tid, "character": id, "name": name}
  StoryStore.cast_wait(character_id) -> dict                                       # {"awaits": [...], "message": "..."}; Rejected when nothing awaited
  StoryStore.cast_recap(character_id, body, thread_id="")                          # default: attended thread, else main
  StoryStore.cast_comment(character_id, body, thread_id="", to=())                 # no thread + to → root thread to to[0]
  StoryStore.cast_inbox(character_id) -> list[dict]                                # comment rows waiting in the inbox
  StoryStore.speak(character_id, text) -> dict                                     # @intent, spec §2.3: the human typing in a character's context view → a human comment in its attended thread, or a root thread to it
  IPC: story.call {character, role, note, as, fork}; story.wait {character}; story.recap {character, body, thread};
       story.comment {character, body, thread, to}; story.cast {key}; story.inbox {character}
  CLI: story call --role R [--as N] [--fork] --note …; story wait; story recap --body … [--thread t];
       story comment --body … [--thread t] [--to @Name …]; story cast [key]; story inbox
  ```

- [ ] **Step 1: Write the failing tests**

`tests/test_stories.py`:

```python
def test_cast_call_opens_a_thread_led_by_a_fresh_friend(store, contexts):
    key, chr_id = started(store)
    r = store.cast_call(chr_id, "claude-fast", "build the screen model", as_name="Implementor")
    t = store.story(key).thread(r["thread"])
    assert (t.author, t.lead, r["name"]) == (chr_id, r["character"], "Implementor")
    friend = store.character(r["character"])
    assert contexts.get(friend["live_context"]).sent[0].endswith("build the screen model") and friend["attention"] == r["thread"]
    assert store.awaits(store.character(chr_id)) == [r["thread"]]


def test_cast_call_fork_clones_the_caller(store, contexts):
    key, chr_id = started(store)
    contexts.get(store.character(chr_id)["live_context"]).status = "idle"
    r = store.cast_call(chr_id, "claude-fast", "review my work so far", fork=True)
    assert store.character(r["character"])["forked_from"] == chr_id and contexts.forked[0][0] == store.character(chr_id)["live_context"]
    assert "fork of protagonist" in contexts.get(store.character(r["character"])["live_context"]).sent[0]


def test_cast_wait_is_a_guard(store, contexts):
    key, chr_id = started(store)
    with pytest.raises(Rejected, match="you await nothing and owe #"):
        store.cast_wait(chr_id)
    r = store.cast_call(chr_id, "claude-fast", "build")
    w = store.cast_wait(chr_id)
    assert w["awaits"] == [{"thread": r["thread"], "lead": "claude-fast"}] and "end your turn" in w["message"]


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
```

`tests/test_ipc.py` — extend `FakeStories` with `cast_call`, `cast_wait`, `cast_inbox`, `cast` (already) and the new signature of `cast_recap`/`cast_comment`, then:

```python
def test_story_call_wait_inbox_cast_forward_and_log(h, store):
    assert h("story.call", {"character": "chr1", "role": "claude-fast", "note": "build", "as": "Impl", "fork": True}) == {"thread": "thr_x", "character": "chr2", "name": "Impl"}
    assert h("story.wait", {"character": "chr1"}) == {"awaits": [], "message": "end your turn"}
    assert h("story.inbox", {"character": "chr1"}) == []
    assert h("story.cast", {"key": "ABC-1"})[0]["name"] == "protagonist"
    assert h("story.recap", {"character": "chr1", "body": "r", "thread": "thr_x"}) == {"id": "c7", "kind": "recap"}
    assert h("story.comment", {"character": "chr1", "body": "b", "thread": "", "to": ["@x"]}) == {"id": "c8", "kind": "text"}
    assert [v[1] for v in store.stories.verbs] == ["call", "wait", "inbox", "recap", "comment"]
    assert store.stories.calls[-2:] == [("cast_recap", "chr1", "r", "thr_x"), ("cast_comment", "chr1", "b", "", ["@x"])]
```

with fakes: `def cast_call(self, character_id, role, note, as_name="", fork=False): self.calls.append(("cast_call", character_id, role, note, as_name, fork)); return {"thread": "thr_x", "character": "chr2", "name": as_name or role}` · `def cast_wait(self, character_id): self.calls.append(("cast_wait", character_id)); return {"awaits": [], "message": "end your turn"}` · `def cast_inbox(self, character_id): return []` · `cast_recap(self, character_id, body, thread_id="")` · `cast_comment(self, character_id, body, thread_id="", to=())`.

`tests/test_cli.py`:

```python
def test_story_call_wait_inbox_cast_recap_comment_args(recorder, monkeypatch):
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr1")
    recorder.replies["story.call"] = {"thread": "thr_x", "character": "chr2", "name": "Impl"}
    recorder.replies["story.wait"] = {"awaits": [], "message": "end your turn"}
    cli.main(["story", "call", "--role", "claude-fast", "--as", "Impl", "--fork", "--note", "build it"])
    cli.main(["story", "wait"])
    cli.main(["story", "inbox"])
    cli.main(["story", "cast"])
    cli.main(["story", "recap", "--body", "r", "--thread", "thr_x"])
    cli.main(["story", "comment", "--body", "b", "--to", "@Impl", "--to", "@Rev"])
    assert recorder.calls == [
        ("story.call", {"character": "chr1", "role": "claude-fast", "note": "build it", "as": "Impl", "fork": True}),
        ("story.wait", {"character": "chr1"}),
        ("story.inbox", {"character": "chr1"}),
        ("story.cast", {"key": ""}),
        ("story.recap", {"character": "chr1", "body": "r", "thread": "thr_x"}),
        ("story.comment", {"character": "chr1", "body": "b", "thread": "", "to": ["@Impl", "@Rev"]}),
    ]
```

- [ ] **Step 2: Run to verify failure** — new tests fail on missing methods/commands/args.

- [ ] **Step 3: Implement**

`harness/stories.py`:

```python
    def cast_call(self, character_id, role, note, as_name="", fork=False) -> dict:
        key, ch = self._char(character_id)
        if self._stories[key].phase in lc.TERMINAL:
            raise lc.Rejected(f"{key} is terminal")
        role_cfg = self._roles.get(role)
        if not role_cfg:
            raise ValueError(f"unknown role {role!r}")
        if not note:
            raise lc.Rejected("call needs a --note: the friend's call-in note is the root of its thread")
        thread_id = new_id("thr_")
        friend = self._cast(key, role_cfg, thread_id=thread_id, author=character_id, note=note, name=as_name,
                            fork_from=character_id if fork else None)
        try:
            self._apply(key, lc.OpenThread(thread_id=thread_id, author=character_id, lead=friend["id"], body=note))
        except Exception:
            ctx = self._contexts.get(friend["live_context"])
            if ctx is not None:
                ctx.stop()
            del self._characters[friend["id"]]
            self._save_characters()
            raise
        self._refresh()
        return {"thread": thread_id, "character": friend["id"], "name": friend["name"]}

    def cast_wait(self, character_id) -> dict:
        key, ch = self._char(character_id)
        awaits = self.awaits(ch)
        if not awaits:
            owed = self.owes(ch)
            what = f"owe #{owed[0]}" if owed else "owe nothing either"
            raise lc.Rejected(f"you await nothing and {what} — " + ("yield instead" if owed else "just end your turn"))
        s = self._stories[key]
        rows = []
        for item in awaits:
            t = next((t for t in s.threads if t.id == item), None)
            rows.append({"thread": item, "lead": author_name(t.lead, self._characters)} if t else {"story": item})
        return {"awaits": rows, "message": "end your turn now; you will be woken when any of these yields to you"}

    def cast_recap(self, character_id, body, thread_id="") -> dict:
        key, ch = self._char(character_id)
        tid = thread_id or ch.get("attention") or self._stories[key].main_thread
        c = self._apply(key, lc.Recap(by=character_id, body=body, thread_id=tid))
        ch.setdefault("recaps", []).append(c["id"])
        ctx = self._contexts.get(ch["live_context"]) if ch.get("live_context") else None
        ch["recap_turns"] = getattr(ctx, "turns", 0) if ctx is not None else 0
        self._save_characters()
        return c

    def cast_comment(self, character_id, body, thread_id="", to=()) -> dict:
        key, ch = self._char(character_id)
        mentions = " ".join(m if m.startswith("@") else "@" + m for m in to)
        if not thread_id and to:
            lead = self._by_name(key, mentions.split()[0].lstrip("@"))["id"]
            tid = new_id("thr_")
            c = self._apply(key, lc.OpenThread(thread_id=tid, author=character_id, lead=lead, body=body))
        else:
            tid = thread_id or ch.get("attention") or self._stories[key].main_thread
            c = self._apply(key, lc.Comment(thread_id=tid, by=character_id, body=(body + (" " + mentions if mentions else ""))))
        self._route(key, c)
        return c

    def cast_inbox(self, character_id) -> list[dict]:
        key, ch = self._char(character_id)
        return [dict(c) for i in ch.get("inbox", []) if (c := self._comment_by_id(i)) is not None]

    @Slot(str, str, result="QVariantMap")
    @intent
    def speak(self, character_id, text):
        """Spec §2.3: typing in a character's context view is a human comment in its attended thread — the
        same channel, a different skin; a root thread to it when it attends nothing."""
        key, ch = self._char(character_id)
        if ch.get("attention"):
            skey, _ = self._thread_anywhere(ch["attention"])
            return self._author_action(skey, lc.Comment(thread_id=ch["attention"], by=self._on_behalf(skey), body=text), resume=True)
        tid = new_id("thr_")
        c = self._apply(key, lc.OpenThread(thread_id=tid, author="human", lead=character_id, body=text))
        self._route(key, c)
        return c
```

(`_on_behalf` arrives in Task 8; until then use `"human"` and switch in Task 8.)

(`cast_yield`, `cast_resolve`, `cast_proceed` already route? — `cast_yield` must now `self._route(key, c)` after applying, so a friend's yield reaches its author; `cast_proceed` and `cast_recap` need no routing.)

`_system_prompt`: add `attention=ch.get("attention") or s.main_thread or ""`, `owes=", ".join("#" + t for t in self.owes(ch)) or "nothing"`, `awaits=…` to the format call. `CHARACTER_SYSTEM_PROMPT` in `config_def.py`:

```python
CHARACTER_SYSTEM_PROMPT = """You are {name} ({character_id}), a character in zharn on story {story_key} ("{title}"), phase: {phase}.
You are attending thread #{attention}. You owe: {owes}. You await: {awaits}. Everything you say to anyone is a comment posted with the CLI below — nothing else reaches them.

Iron laws:
1. Never stop while you owe a thread unless a friend or a sub-story is out (`wait` tells you) — the harness will yield for you and say so.
2. Status is not yours to set. Phases move only when you `yield` and the author answers, or when you `proceed`.
3. Everything you say to a human is a comment.
4. When told your context is low, `recap` before anything else.
5. Questions carry options when there are natural choices; handoffs carry evidence (what changed, how verified, where to look first).

CLI (HARNESS_CLI is set; every call prints a reason and exits non-zero when refused):
  $HARNESS_CLI story yield --question --body "..." [--options a,b] [--thread t]   # ask the thread's author; only the thread's lead may
  $HARNESS_CLI story yield --handoff --body "..." [--thread t]                    # hand off an outline, an answer, or finished work
  $HARNESS_CLI story proceed [--note "..."]                                      # planning -> implementing (main thread's lead only)
  $HARNESS_CLI story comment --body "..." [--thread t] [--to @Name]              # a note; no --thread + --to opens a thread to Name
  $HARNESS_CLI story call --role R [--as Name] [--fork] --note "..."             # a friend on its own thread; --fork copies your memory
  $HARNESS_CLI story wait                                                        # lists what you await, then END YOUR TURN
  $HARNESS_CLI story resolve --thread t [--note "..."]                           # close a thread you opened that waits on you
  $HARNESS_CLI story recap --body "..." [--thread t]                             # done / in flight / gotchas / next
  $HARNESS_CLI story show · cast · inbox                                         # the record, the cast, what waits for you
{outline_rule}"""
```

`harness/ipc.py` `story_cmd`, after the `ch = a.get("character", "")` line:

```python
        if verb == "cast":
            return stories.cast(a.get("key") or stories.character(ch)["story_key"])
        if verb == "inbox":
            return stories.cast_inbox(ch)
        if verb == "call":
            return stories.cast_call(ch, a["role"], a.get("note", ""), a.get("as", ""), bool(a.get("fork")))
        if verb == "wait":
            return stories.cast_wait(ch)
```

and change `recap` → `stories.cast_recap(ch, a["body"], a.get("thread", ""))`, `comment` (character form) → `stories.cast_comment(ch, a["body"], a.get("thread", ""), a.get("to") or [])`. Note `cast` without a character must not hit the verbs_log wrapper — it is a read; `h()` only wraps when `character` is present, and the CLI sends `{"key": …}` for `cast`.

`harness/cli.py` parsers:

```python
    cl = stp.add_parser("call", help="Cast a friend on its own thread"); cl.add_argument("--role", required=True)
    cl.add_argument("--as", dest="as_name", default=""); cl.add_argument("--fork", action="store_true"); cl.add_argument("--note", required=True)
    stp.add_parser("wait", help="List what you await; then end your turn")
    stp.add_parser("inbox", help="Comments waiting for you")
    stp.add_parser("cast").add_argument("key", nargs="?", default=os.environ.get("HARNESS_STORY_KEY", ""))
    rc = stp.add_parser("recap"); rc.add_argument("--body", required=True); rc.add_argument("--thread", default="")
    cm.add_argument("--to", action="append", default=[])
```

(replace the existing one-line `recap` parser) and dispatch:

```python
        elif a.verb == "call": out(request("story.call", {"character": character(), "role": a.role, "note": a.note, "as": a.as_name, "fork": a.fork}), a.json)
        elif a.verb == "wait": out(request("story.wait", {"character": character()}), a.json)
        elif a.verb == "inbox": out(request("story.inbox", {"character": character()}), a.json)
        elif a.verb == "cast": out(request("story.cast", {"key": a.key}), a.json)
        elif a.verb == "recap": out(request("story.recap", {"character": character(), "body": a.body, "thread": a.thread}), a.json)
        elif a.verb == "comment":
            args = {"character": ch, "body": a.body, "thread": a.thread, "to": a.to} if ch else {"key": a.story, "body": a.body, "thread": a.thread}
            out(request("story.comment", args), a.json)
```

`out()` for dicts prints `awaits` lists reasonably (it prints non-special keys as `k: v`), fine.

- [ ] **Step 4: Run the tests, then the full suite** — PASS (existing `test_story_cast_verbs_forward_and_log` may need the new `cast_recap` signature in its expected call tuple).

- [ ] **Step 5: Commit**

```bash
git add harness/stories.py harness/config_def.py harness/ipc.py harness/cli.py tests/test_stories.py tests/test_ipc.py tests/test_cli.py
git commit -m "Cast verbs: call (fresh or --fork), wait as a guard, recap --thread, comment --to, cast, inbox; system prompt with owes/awaits

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Retirement — Approve lets turns finish, Cancel stops the cast, nothing reaches the retired

**Files:**
- Modify: `harness/stories.py` (`approve`, `cancel`)
- Test: `tests/test_stories.py`

**Interfaces:** none new. `cancel(key)` stops every character's live context on `key` (already) and every open sub-story's cast (Task 8 adds the cascade).

- [ ] **Step 1: Write the failing tests**

```python
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
    settle(store, contexts, r["character"])                        # its turn ends: no quiet check, no pop
    assert len(friend_ctx.sent) == sent and len(store.comments(key)) == 6


def test_cancel_stops_every_character(store, contexts):
    key, chr_id = started(store)
    r = store.cast_call(chr_id, "claude-fast", "build")
    store.cancel(key)
    assert all(contexts.get(store.character(c)["live_context"]).stopped for c in (chr_id, r["character"]))
```

- [ ] **Step 2: Run to verify failure** — the approve test passes already if Task 5's terminal guard holds; the cancel test must pass too. If both pass on first run, keep them (they pin the behaviour) and skip Step 3.

- [ ] **Step 3: Implement (only if needed)** — `approve()` stays `resume=False`; `cancel()` already stops the cast. No change expected.

- [ ] **Step 4: Full suite** — PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_stories.py harness/stories.py
git commit -m "Retirement: approve lets turns finish and delivers nothing after; cancel stops the whole cast (pinned by tests)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Sub-stories — `create`, cross-story delivery, author verbs by key, the human acting for a character

**Files:**
- Modify: `harness/stories.py` (`start` → `_start(key, note, role)`; new `cast_create`, `cast_author`; `_row` fields; `cancel` cascade; `cast_yield` passes `open_substories`; human intents on character-owned stories; brief lists sub-stories)
- Modify: `harness/ipc.py`, `harness/cli.py`
- Test: `tests/test_stories.py`, `tests/test_ipc.py`, `tests/test_cli.py`

**Interfaces:**
- Produces:
  ```python
  StoryStore.cast_create(character_id, title, description="", start=False, role="") -> str    # the new key
  StoryStore.cast_author(character_id, verb, key, **kw) -> dict   # verb ∈ reply|resolve|proceed|approve|cancel|reopen; Rejected unless story.author == character_id
  _row gains: parentStory: str, openSubstories: int
  IPC: story.create {character?, title, description, start, role}; story.<verb> with {character, key, …} routes through cast_author when key ≠ the character's own story
  CLI: story create [--start --role R] (character form when HARNESS_CHARACTER_ID is set); reply/resolve/proceed/approve/cancel/reopen <key> from a character
  ```
  Human intents (`proceed`, `approve`, `backToPlanning`, `cancel`, `reopen`, `comment`, `resolve`) on a story whose `author` is a character apply with `by = story.author` and deliver the resulting comment to that character as well.

- [ ] **Step 1: Write the failing tests**

```python
def test_character_creates_and_starts_a_sub_story_it_authors(store, contexts):
    key, chr_id = started(store)
    sub = store.cast_create(chr_id, "screen model", "pyte-backed", start=True, role="claude-fast")
    s = store.story(sub)
    assert (s.author, s.parent_story, s.phase, s.ball) == (chr_id, key, "planning", "cast")
    assert store.get(key)["openSubstories"] == 1 and store.get(sub)["parentStory"] == key
    assert store.awaits(store.character(chr_id)) == [sub]
    sub_lead = store.story(sub).protagonist
    assert contexts.get(store.character(sub_lead)["live_context"]).sent[0].startswith(f"# {sub}:")


def test_sub_story_yield_reaches_the_author_character_cross_story(store, contexts):
    key, chr_id = started(store)
    live = contexts.get(store.character(chr_id)["live_context"]); live.status = "idle"
    sub = store.cast_create(chr_id, "screen model", start=True, role="claude-fast")
    lead = store.story(sub).protagonist
    store.cast_yield(lead, "question", "rows or cells?")
    assert live.sent[-1].startswith(f"[claude-fast] question in #{store.get(sub)['mainThread']} of {sub}: rows or cells?")
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
    assert live.sent[-1].startswith(f"[protagonist] system in #{store.get(sub)['mainThread']} of {sub}: outline approved")


def test_cancel_cascades_to_open_sub_stories(store, contexts):
    key, chr_id = started(store)
    sub = store.cast_create(chr_id, "part", start=True, role="claude-fast")
    store.cancel(key)
    assert store.story(sub).phase == "canceled" and store.cast(sub)[0]["status"] == "retired"
```

IPC: `FakeStories` gains `cast_create(self, character_id, title, description="", start=False, role="")` → `"SUB-1"` and `cast_author(self, character_id, verb, key, **kw)` → `{"id": "c12"}`, and `character(self, cid)` → `{"story_key": "ABC-1"}`; test:

```python
def test_story_create_and_author_verbs_from_a_character(h, store):
    assert h("story.create", {"character": "chr1", "title": "t", "start": True, "role": "claude-fast"}) == "SUB-1"
    assert h("story.approve", {"character": "chr1", "key": "SUB-1", "note": "ok"}) == {"id": "c12"}
    assert h("story.reply", {"character": "chr1", "key": "SUB-1", "thread": "t", "body": "b"}) == {"id": "c12"}
    assert store.stories.calls[-2:] == [("cast_author", "chr1", "approve", "SUB-1", {"note": "ok"}),
                                        ("cast_author", "chr1", "reply", "SUB-1", {"thread_id": "t", "body": "b"})]
```

CLI: `cli.main(["story", "create", "--title", "t", "--start", "--role", "claude-fast"])` with `HARNESS_CHARACTER_ID` set sends `("story.create", {"character": "chr1", "title": "t", "description": "", "start": True, "role": "claude-fast"})`; `cli.main(["story", "approve", "SUB-1", "--note", "ok"])` sends `("story.approve", {"character": "chr1", "key": "SUB-1", "note": "ok"})`.

- [ ] **Step 2: Run to verify failure**.

- [ ] **Step 3: Implement**

`harness/stories.py`:

- Split `start(key, note, role)` (the `@Slot`) into a thin wrapper around `_start(key, note, role)`; `_start` is what `cast_create(..., start=True)` calls.
- `_row`: `"parentStory": s.parent_story or ""`, `"openSubstories": sum(1 for x in self._stories.values() if x.parent_story == s.key and x.phase not in lc.TERMINAL)`.
- `cast_yield`: `open_substories=self._row(key)["openSubstories"]` when `tid == s.main_thread`, and `self._route(key, c)` afterwards.
- New:

```python
    def cast_create(self, character_id, title, description="", start=False, role="") -> str:
        parent, ch = self._char(character_id)
        key = self.workspace.next_key()
        self._stories[key] = lc.Story(key=key, title=title, description=description, phase="todo",
                                      author=character_id, parent_story=parent)
        self._created[key] = time.time()
        self._comments[key] = []
        self.workspace.story_dir(key)
        self._save_story(key)
        if start:
            self._start(key, "", role)
        self._refresh()
        return key

    _AUTHOR_VERBS = ("reply", "resolve", "proceed", "approve", "cancel", "reopen", "back")

    def cast_author(self, character_id, verb, key, **kw) -> dict:
        key = self._key(key)
        if self._stories[key].author != character_id:
            raise lc.Rejected(f"only the author of {key} ({author_name(self._stories[key].author, self._characters)}) can {verb} it")
        by = character_id
        if verb == "reply":
            return self._author_action(key, lc.Comment(thread_id=kw.get("thread_id") or self._stories[key].main_thread, by=by, body=kw["body"]), resume=True)
        if verb == "resolve":
            c = self._author_action(key, lc.Resolve(thread_id=kw["thread_id"], by=by, note=kw.get("note", "")), resume=False)
            self._clear_attention(key, kw["thread_id"])
            return c
        action = {"proceed": lc.Proceed(by=by, note=kw.get("note", "")), "approve": lc.Approve(by=by, note=kw.get("note", "")),
                  "cancel": lc.Cancel(by=by, note=kw.get("note", "")), "reopen": lc.Reopen(by=by, note=kw.get("note", "")),
                  "back": lc.BackToPlanning(by=by, note=kw.get("note", ""))}[verb]
        c = self._author_action(key, action, resume=verb != "approve")
        if verb == "cancel":
            self._stop_cast(key)
        return c
```

- Human intents: introduce `_on_behalf(key) -> str` returning `self._stories[key].author` (a character id or `"human"`), and pass `by=self._on_behalf(key)` in `proceed`, `approve`, `backToPlanning`, `cancel`, `reopen`, `comment`, `resolve`. In `_author_action`, after routing, if `self._stories[key].author in self._characters` and the comment's author is that character (the human acted for it), also `self._deliver_to(self._characters[author], comment, before)` — the spec's "owning character notified".
- `cancel(key)`: after applying, `self._stop_cast(key)` (extracted from today's loop) and cascade: `for sub in [k for k, x in self._stories.items() if x.parent_story == key and x.phase not in lc.TERMINAL]: self.cancel(sub)`.
- `render_brief`: after Cast, `## Sub-stories` lines `- {key}: {title} ({phase}, ball {ball})` for stories with `parent_story == story.key`; for a sub-story, a first line `Sub-story of {parent}.` — pass `substories: list[dict]` and `parent` as new keyword parameters (default empty) so existing callers still work; `_cast` supplies them.

`harness/ipc.py` `story_cmd`: `create` → if `ch`: `stories.cast_create(ch, a["title"], a.get("description", ""), bool(a.get("start")), a.get("role", ""))`; the author verbs (`reply`, `resolve`, `proceed`, `approve`, `cancel`, `reopen`, `back`) → if `ch` and `a.get("key")` and `a["key"].lower() != stories.character(ch)["story_key"].lower()`: `stories.cast_author(ch, verb, a["key"], **{k: v for k, v in a.items() if k in ("thread_id", "body", "note")})` — with the CLI sending `thread_id` (rename from `thread` in the CLI for these verbs, or map `thread` → `thread_id` in `story_cmd`). The character's own-story verbs (`proceed` without key, `resolve` without key) keep their current paths.

`harness/cli.py`: `create` gains `--start` and `--role`; when `ch` is set it sends `{"character": ch, …}`. For `approve|back|cancel|reopen|reply|proceed <key>` when `ch` is set, include `"character": ch`.

- [ ] **Step 4: Run the tests, then the full suite** — PASS.

- [ ] **Step 5: Commit**

```bash
git add harness/stories.py harness/ipc.py harness/cli.py tests/test_stories.py tests/test_ipc.py tests/test_cli.py
git commit -m "Sub-stories: characters create and author stories; yields reach them cross-story; humans may act for the owner; cancel cascades

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Recast — rungs 1 and 3, the situation line, lineage; docs

**Files:**
- Modify: `harness/stories.py` (`recast` intent, `_recast_now`, `_on_turn_end` honours `recast_pending`, `render_brief(situation=…)`, `cast_author("recast")`)
- Modify: `harness/config_def.py` (`RECAP_STALE_TURNS = 20`)
- Modify: `harness/ipc.py`, `harness/cli.py` (`story.recast {key?, character, role, model}`; `story recast <key> <character> [--role R] [--model M]`)
- Modify: `docs/DESIGN.md` §8
- Test: `tests/test_stories.py`

**Interfaces:**
- Produces:
  ```python
  StoryStore.recast(key, character_id, role="", model="") -> str    # @intent; new context id, or "" when deferred to the turn boundary
  StoryStore._recast_now(ch, role_cfg) -> str
  render_brief(..., situation: str = "")                            # appended as "## Situation" when non-empty
  ```
  Rung 1: the character's latest recap exists and `ctx.turns - ch["recap_turns"] <= config.RECAP_STALE_TURNS`; rung 3: otherwise (brief alone). Rung 2 is out of scope (say so in the system note: "rung 3 (no fresh recap; a final recap turn is not implemented)").

- [ ] **Step 1: Write the failing tests**

```python
def test_recast_replaces_the_live_context_and_hands_it_the_situation(store, contexts):
    key, chr_id = started(store)
    old = store.character(chr_id)["live_context"]
    contexts.get(old).status = "idle"; contexts.get(old).turns = 3
    side = store.openThread(key, "btw")
    store.cast_recap(chr_id, "done: outline; next: build")
    new = store.recast(key, chr_id, role="claude-fast")
    ch = store.character(chr_id)
    assert ch["live_context"] == new and ch["role"] == "claude-fast" and contexts.get(old).stopped
    assert contexts.get(new).meta["predecessor"] == old and contexts.get(new).meta["owner"] == chr_id
    first = contexts.get(new).sent[0]
    assert "you are a recast of protagonist" in first and "done: outline; next: build" in first and f"attending #{side}" in first
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
    assert contexts.get(ch["live_context"]).meta["role"] == "protagonist"
```

Extend `StubContext` with `self.turns = 0` and `stop()` already sets `stopped`.

- [ ] **Step 2: Run to verify failure**.

- [ ] **Step 3: Implement**

`config_def.py`: `RECAP_STALE_TURNS = 20  # a recap older than this many turns of its context is stale (rung 1 → rung 3)`.

`render_brief(..., situation: str = "")`: append `["## Situation", situation]` when given; also add `## Recaps` listing each character's latest recap (`{name}: {body}`) instead of the single "Latest recap" (pass `characters` already has `recaps` ids; look each up in `comments`).

`stories.py`:

```python
    @Slot(str, str, str, str, result=str)
    @intent
    def recast(self, key, character_id, role="", model=""):
        """Spec §2.1 Recast / §3.4: replace the live context at the next turn boundary; same character, fresh memory."""
        key = self._key(key)
        ch = self._characters[character_id]
        if ch["story_key"] != key:
            raise lc.Rejected(f"{ch['name']} is not on {key}")
        ctx = self._contexts.get(ch["live_context"]) if ch.get("live_context") else None
        if ctx is not None and ctx.status in WORKING:
            ch["recast_pending"] = {"role": role, "model": model}
            self._save_characters()
            return ""
        return self._recast_now(ch, role, model)

    def _recast_now(self, ch: dict, role: str = "", model: str = "") -> str:
        key = ch["story_key"]
        s = self._stories[key]
        role_cfg = dict(self._roles.get(role or ch["role"]) or {})
        if not role_cfg:
            raise ValueError(f"unknown role {role!r}")
        if model:
            role_cfg["model"] = model
        old_id = ch.get("live_context")
        old = self._contexts.get(old_id) if old_id else None
        recap = self._comment_by_id(ch["recaps"][-1]) if ch.get("recaps") else None
        fresh = recap is not None and old is not None and (getattr(old, "turns", 0) - ch.get("recap_turns", 0)) <= getattr(cfg, "RECAP_STALE_TURNS", 20)
        rung = "rung 1: fresh recap" if fresh else "rung 3: no fresh recap"
        ch["role"] = role_cfg["name"]
        situation = (f"you are a recast of {ch['name']}; your predecessor's recap is above. "
                     f"You were attending #{ch.get('attention') or s.main_thread}; {len(ch.get('inbox', []))} items wait in your inbox; "
                     f"you await {', '.join(self.awaits(ch)) or 'nothing'} and owe {', '.join('#' + t for t in self.owes(ch)) or 'nothing'}.")
        cid = self._contexts.create(role_cfg["name"], story_key=key, owner=ch["id"], title=f"{key} · {ch['name']}",
                                    system_prompt=self._system_prompt(s, ch, role_cfg), env={"HARNESS_CHARACTER_ID": ch["id"]},
                                    predecessor=old_id)
        if old is not None:
            old.stop()
        ch["live_context"] = cid
        ch.pop("recast_pending", None)
        self._save_characters()
        self._apply(key, lc.Note(thread_id=s.main_thread, body=f"recast {ch['name']} as {role_cfg['name']} ({rung})"))
        self._contexts.get(cid).send(render_brief(s, self._comments[key], self._characters, role_cfg, "", situation=situation))
        self._refresh()
        return cid
```

(`create` with a role dict: `ContextStore.create` takes a role *name* and looks it up; for a model override pass the name and set `self._contexts.get(cid).meta["roleConfig"]["model"] = model` after creation — do that instead of passing a dict.)

`_on_turn_end`: first thing after the terminal check: `if ch.get("recast_pending") is not None: p = ch.pop("recast_pending"); self._recast_now(ch, p["role"], p["model"]); return`.

`cast_author`: add `"recast"` → `self.recast(key, kw["character"], kw.get("role", ""), kw.get("model", ""))`.

IPC `story.recast {key, character, role, model}` (author form) and `{character, key, target, role, model}` (cast form → `cast_author`). CLI: `rc = stp.add_parser("recast"); rc.add_argument("key"); rc.add_argument("character"); rc.add_argument("--role", default=""); rc.add_argument("--model", default="")`.

`docs/DESIGN.md` §8 item 3: status "Characters and delivery shipped 2026-09-02: friends (fresh/fork), routing, delivery by attention, quiet check, call/wait, retirement, sub-stories, recast rungs 1 and 3. Deferred: context-usage tracking (auto-recast at CONTEXT_WARN/MAX), recast rung 2, checks at handoff, skills."

- [ ] **Step 4: Run the tests, then the full suite** — PASS.

- [ ] **Step 5: Commit**

```bash
git add harness/stories.py harness/config_def.py harness/ipc.py harness/cli.py docs/DESIGN.md tests/test_stories.py tests/test_ipc.py tests/test_cli.py
git commit -m "Recast: rungs 1 and 3 at the turn boundary, the situation line in the brief, lineage; DESIGN status

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### After Task 9

Tell the UI thread (`thr_h2eg7mfy7u`) what the cast panel, composer, and story page can now read: `cast(key)` rows (`status`, `owes`, `awaits`, `inboxDepth`, `forkedFrom`, `attention`), `openThread(key, body)` for the composer (`@Name`, `/call`, `/fork`), `recast(key, characterId, role, model)`, `_row` fields `parentStory` / `openSubstories`, and the per-thread action bar's Resolve (already there) now joined by system "went quiet" handoffs (`author == "system"`, `structured.auto_for`) that render as the harness speaking for a character.
