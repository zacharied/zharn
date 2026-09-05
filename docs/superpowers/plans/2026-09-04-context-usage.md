# Context Usage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every context knows how full it is, the harness turns Claude Code's own compaction off, and a character past the warn line is asked for a recap once, past the max line recast at its next turn boundary.

**Architecture:** The stream interpreter reads two numbers off events it already sees: the input side of the latest `assistant` event's `usage` (the context's size) and the `result` event's `modelUsage[…].contextWindow`. The context exposes them as Qt properties, in its summary row, and through a new store signal. The story store listens, compares against two token thresholds in config, pushes a `[harness]` line into the live context at each crossing, and uses the existing pending-recast path for the max line. Nothing new is stored on contexts; two small fields land on the character.

**Tech Stack:** Python 3.10+, PySide6 6.11 (QObject Properties/Signals), pytest offscreen. `claude -p --output-format stream-json` is the provider; `tests/fake_claude.py` stands in for it.

**Spec:** `docs/superpowers/proposals/2026-09-04-context-usage.md` (the proposal); standing text lands in `docs/specs/story-lifecycle.md` in Task 5.

## Global Constraints

- No backward compatibility (DESIGN.md §0): no migrations, no aliases, no shims. Old `.zharn/local` data may be deleted.
- Thresholds are tokens, not fractions: `CONTEXT_WARN = 300_000`, `CONTEXT_MAX = 500_000`, for a 1M window; a smaller known window scales both by `window / 1_000_000`.
- Every spawned process gets `DISABLE_AUTO_COMPACT=1` in its environment, bare contexts and asides included.
- The situation line never carries a number. It gains only a trailing ` · recap due`.
- Each line is crossed once per context. A crossing is acted on only while the context is working (mid-turn).
- Context usage is a reading, never a sum: the latest `assistant` event's `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`.
- The recap-due test compares recap *counts*, not turns: `context_warned` holds `len(recaps)` at the crossing; due while `len(recaps) <= context_warned`. (The proposal said turns; a count is equivalent and does not need clearing `recap_turns` on recast.)
- Run tests with `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest …` from the worktree root. The whole suite takes ~30 s.
- Commit messages are prose, one line, in the repo's voice (see `git log --oneline -5`). End with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

### Task 1: The interpreter reads the two numbers

**Files:**
- Modify: `harness/agents.py:209-250` (`StreamInterpreter.__init__` and `apply`)
- Test: `tests/test_stream_interpreter.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `StreamInterpreter.context_tokens: int` (0 until the first assistant event with usage), `StreamInterpreter.context_window: int` (0 until the first result with `modelUsage`). A `system`/`compact_boundary` event appends `role="system", kind="error", isError=True` to the transcript and returns `None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_stream_interpreter.py` (after the `result` tests, before any replay section; the builders `assistant_ev`, `result_ev`, `init_ev` and the `interp`/`model` fixtures already exist at the top of the file):

```python
# --------------------------------------------------------------------------- context usage (lifecycle spec §2.3)
def usage_ev(input_tokens, cache_read, cache_creation):
    ev = assistant_ev({"type": "text", "text": "hi"})
    ev["message"]["usage"] = {"input_tokens": input_tokens, "cache_read_input_tokens": cache_read,
                              "cache_creation_input_tokens": cache_creation, "output_tokens": 4}
    return ev


def test_assistant_usage_is_a_reading_not_a_sum(interp):
    assert interp.context_tokens == 0
    interp.apply(usage_ev(10, 13615, 8249))
    assert interp.context_tokens == 21874
    interp.apply(usage_ev(10, 13615, 8249))     # one API message → one assistant event per block, same usage each
    assert interp.context_tokens == 21874
    interp.apply(usage_ev(5, 30000, 0))
    assert interp.context_tokens == 30005


def test_assistant_without_usage_keeps_the_reading(interp):
    interp.apply(usage_ev(10, 1000, 0))
    interp.apply(assistant_ev({"type": "text", "text": "no usage here"}))
    assert interp.context_tokens == 1010


def test_result_model_usage_sets_the_window(interp):
    interp.apply(init_ev(model="claude-haiku-4-5"))
    assert interp.context_window == 0
    interp.apply(result_ev(modelUsage={"claude-haiku-4-5": {"contextWindow": 200000, "maxOutputTokens": 32000}}))
    assert interp.context_window == 200000
    interp.apply(result_ev())                  # a result without modelUsage keeps it
    assert interp.context_window == 200000


def test_result_window_prefers_the_sessions_model(interp):
    interp.apply(init_ev(model="claude-opus-5"))
    interp.apply(result_ev(modelUsage={"claude-haiku-4-5": {"contextWindow": 200000},
                                       "claude-opus-5": {"contextWindow": 1000000}}))
    assert interp.context_window == 1000000


def test_compact_boundary_is_a_visible_error(interp, model):
    ev = {"type": "system", "subtype": "compact_boundary", "compact_metadata": {"trigger": "auto", "pre_tokens": 150000}}
    assert interp.apply(ev) is None
    row = model.rows()[-1]
    assert row["role"] == "system" and row["kind"] == "error" and row["isError"] and "compacted" in row["text"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_stream_interpreter.py -k "usage or window or compact_boundary" -v`
Expected: 5 failures — `AttributeError: 'StreamInterpreter' object has no attribute 'context_tokens'` and the compact_boundary row missing.

- [ ] **Step 3: Implement**

In `harness/agents.py`, `StreamInterpreter.__init__`, after `self.turns = 0`:

```python
        self.context_tokens = 0   # the input side of the latest API call: what the context holds (lifecycle spec §2.3)
        self.context_window = 0   # the model's window, from the latest result's modelUsage; 0 until the first
```

In `apply`, replace the `system`, `assistant` and `result` branches so the method reads:

```python
    def apply(self, ev: dict) -> str | None:
        """Returns a status hint ('working' | 'idle' | 'failed') or None."""
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            self.session_id = ev.get("session_id", self.session_id)
            self.model_name = ev.get("model", self.model_name)
            return "working"
        if t == "system" and ev.get("subtype") == "compact_boundary":
            # Never expected: every spawn sets DISABLE_AUTO_COMPACT=1. Visible rather than silent if it happens.
            self.model.append(role="system", kind="error", isError=True,
                              text="the CLI compacted this context on its own; the reading below is no longer the whole conversation")
            return None
        if t == "stream_event":
            self._stream(ev.get("event") or {})
            return None
        if t == "assistant":
            msg = ev.get("message") or {}
            usage = msg.get("usage") or {}
            if usage:
                self.context_tokens = sum(int(usage.get(k) or 0) for k in
                                          ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            for block in msg.get("content", []):
                self._finalize_block(block)
            return None
        if t == "user":
            for block in (ev.get("message") or {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    self.model.append(role="tool", kind="tool_result", toolId=block.get("tool_use_id", ""),
                                      text=_block_text(block.get("content")), isError=bool(block.get("is_error")))
            return None
        if t == "result":
            self.turns += int(ev.get("num_turns") or 0)
            self.cost_usd += float(ev.get("total_cost_usd") or 0.0)
            self.session_id = ev.get("session_id", self.session_id)
            per_model = ev.get("modelUsage") or {}
            mu = per_model.get(self.model_name) or next(iter(per_model.values()), {})
            if mu.get("contextWindow"):
                self.context_window = int(mu["contextWindow"])
            self._current = -1
            if ev.get("is_error"):
                self.model.append(role="system", kind="error", text=_block_text(ev.get("result")) or ev.get("subtype", "error"), isError=True)
                return "failed"
            return "idle"
        return None
```

- [ ] **Step 4: Run the interpreter tests**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_stream_interpreter.py -v`
Expected: all pass (the five new ones and everything that was there).

- [ ] **Step 5: Commit**

```bash
git add harness/agents.py tests/test_stream_interpreter.py
git commit -m "Interpreter: the context reading from the latest assistant usage, the window from modelUsage, a compact boundary is an error row

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: The context exposes the reading, forks inherit it, compaction is off

**Files:**
- Modify: `harness/contexts.py` (`CONTEXT_ROLES`, `Context.__init__`, properties after `turns`, `summary`, `_env`, `_on_event`, `ContextStore` signals, `create`, `fork`, `_context_changed`)
- Modify: `tests/fake_claude.py` (usage on assistant events, `modelUsage` on results, `tokens=<n>`, `auto_compact_disabled` on init)
- Test: `tests/test_contexts_unit.py`

**Interfaces:**
- Consumes: `StreamInterpreter.context_tokens`, `.context_window` (Task 1).
- Produces:
  - `Context.contextTokens: int` and `Context.contextWindow: int` — Qt `Property(int, notify=changed)`.
  - `Context.summary()` gains `"contextTokens"` and `"contextWindow"`; `CONTEXT_ROLES` gains the same two names so the Contexts list model carries them.
  - `ContextStore.contextUsage = Signal(str)` — emitted with the context id whenever either number changes on a live event (not on replay).
  - `ContextStore.create(..., seed_usage: dict | None = None)` stores `meta["seedUsage"] = {"tokens": int, "window": int}`; `Context.__init__` seeds the interpreter from it. `fork()` passes the source's reading.
  - Every spawn's environment contains `DISABLE_AUTO_COMPACT=1`.
  - `tests/fake_claude.py`: assistant events carry `usage` (`input_tokens` 10, `cache_read_input_tokens` 1000 by default, or `<n>` when the prompt contains `tokens=<n>`, `cache_creation_input_tokens` 0); success results carry `modelUsage: {"fake-model": {"contextWindow": 1000000, "maxOutputTokens": 32000}}`; the init event carries `auto_compact_disabled: bool`.

- [ ] **Step 1: Teach the fake CLI usage**

In `tests/fake_claude.py`:

Add `import re` to the imports. After `SESSION = "fake-session-1"` add:

```python
USAGE = {"input_tokens": 10, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 0, "output_tokens": 4}
WINDOW = {"fake-model": {"contextWindow": 1000000, "maxOutputTokens": 32000}}
```

In `text_turn`, change the `assistant` emit to:

```python
    emit({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}], "model": "fake-model",
                                           "usage": dict(USAGE)}})
```

In `tool_turn`, change the `assistant` emit to:

```python
    emit({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_fake1", "name": name, "input": inp}],
                                           "model": "fake-model", "usage": dict(USAGE)}})
```

In `main`, add `"auto_compact_disabled": os.environ.get("DISABLE_AUTO_COMPACT") == "1",` to the init event's dict (after `"harness_env": …`).

In `main`'s loop, right after `last = …`, add:

```python
        m = re.search(r"tokens=(\d+)", prompt)
        if m:   # the next readings say the context holds this many cached tokens (+10 input)
            USAGE["cache_read_input_tokens"] = int(m.group(1))
```

Change the success result emit to include the window:

```python
        emit({"type": "result", "subtype": "success", "is_error": False, "result": f"echo: {last}", "num_turns": 1,
              "total_cost_usd": 0.0123, "duration_ms": 42, "stop_reason": "end_turn", "modelUsage": WINDOW})
```

Update the module docstring's behaviour list with one line: `  contains "tokens=<n>"  → assistant usage reports n cached tokens from then on`.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_contexts_unit.py` after `test_fork_rejects_a_source_that_never_ran_or_is_working` (the `inits(tmp_path, cid)` helper and `wait_until` exist above):

```python
# --------------------------------------------------------------------------- context usage (lifecycle spec §2.3)
def test_every_spawn_turns_the_clis_auto_compaction_off(store, tmp_path):
    cid = store.spawn("claude-fast", "hello")
    assert wait_until(lambda: store.get(cid).status == "idle")
    assert inits(tmp_path, cid)[0]["auto_compact_disabled"] is True
    bare = store.get(store.newBare("claude-default"))
    assert bare._env()["DISABLE_AUTO_COMPACT"] == "1"


def test_usage_reaches_the_context_its_row_and_a_signal(store):
    seen = []
    store.contextUsage.connect(seen.append)
    cid = store.spawn("claude-fast", "hello tokens=4321")
    c = store.get(cid)
    assert wait_until(lambda: c.status == "idle"), (c.status, c.lastError)
    assert c.contextTokens == 4331 and c.contextWindow == 1000000      # 10 input + 4321 cached
    assert cid in seen
    row = next(r for r in store.model.rows() if r["id"] == cid)
    assert row["contextTokens"] == 4331 and row["contextWindow"] == 1000000
    assert c.summary()["contextTokens"] == 4331


def test_usage_survives_a_restart_through_replay(store, tmp_path):
    cid = store.spawn("claude-fast", "hello tokens=4321")
    assert wait_until(lambda: store.get(cid).status == "idle")
    fresh = ContextStore(ROOT, tmp_path / "contexts", RoleStore(tmp_path), workspace_dir=tmp_path)
    assert fresh.get(cid).contextTokens == 4331 and fresh.get(cid).contextWindow == 1000000


def test_a_fork_starts_with_its_sources_reading_and_keeps_it_across_a_restart(store, tmp_path):
    src = store.get(store.spawn("claude-fast", "hello tokens=4321"))
    assert wait_until(lambda: src.status == "idle")
    fid = store.fork(src.id, role_name="claude-default")
    f = store.get(fid)
    assert f.contextTokens == 4331 and f.contextWindow == 1000000 and f._proc is None
    fresh = ContextStore(ROOT, tmp_path / "contexts", RoleStore(tmp_path), workspace_dir=tmp_path)
    assert fresh.get(fid).contextTokens == 4331
    f.send("what was said?")                  # its own first call replaces the seed with a real reading
    assert wait_until(lambda: f.status == "idle"), (f.status, f.lastError)
    assert f.contextTokens == 1010


def test_a_recast_successor_starts_at_zero(store):
    cid = store.create("claude-fast", predecessor="ctx_old")
    assert store.get(cid).contextTokens == 0 and store.get(cid).contextWindow == 0
```

- [ ] **Step 3: Run them to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_contexts_unit.py -k "compaction or usage or sources_reading or starts_at_zero" -v`
Expected: 5 failures (`auto_compact_disabled` False, no `contextUsage`, no `contextTokens`).

- [ ] **Step 4: Implement in `harness/contexts.py`**

`CONTEXT_ROLES`:

```python
CONTEXT_ROLES = ["id", "title", "storyKey", "owner", "status", "roleName", "costUsd", "turns", "createdAt", "contextTokens", "contextWindow"]
```

`Context.__init__`, after `self._interp.session_id = meta.get("sessionId", "")`:

```python
        seed = meta.get("seedUsage") or {}                       # a fork starts with its source's reading (spec §2.3)
        self._interp.context_tokens = int(seed.get("tokens") or 0)
        self._interp.context_window = int(seed.get("window") or 0)
```

After the `turns` property:

```python
    @Property(int, notify=changed)
    def contextTokens(self): return self._interp.context_tokens   # the input side of its latest API call (spec §2.3)

    @Property(int, notify=changed)
    def contextWindow(self): return self._interp.context_window   # 0 until its first result
```

`summary()`: add `"contextTokens": self._interp.context_tokens, "contextWindow": self._interp.context_window,` to the dict (after `"turns"`).

`_env()`: add `"DISABLE_AUTO_COMPACT": "1",` to the base `env` dict (after `"HARNESS_CLI"`), with the comment `# the ladder is the only compaction (spec §2.3)`.

`_on_event`:

```python
    def _on_event(self, ev: dict):
        self._log(ev)
        if ev.get("type") == "user" and _has_text_block(ev):
            self._unacked = max(0, self._unacked - 1)   # claude echoed a pushed message: it has been consumed
        before = (self._interp.context_tokens, self._interp.context_window)
        hint = self._interp.apply(ev)
        if hint == "idle" and self._unacked > 0:
            hint = "working"                             # a pushed message is still queued: not a turn end
        if hint:
            self._set_status(hint)
        else:
            self.changed.emit()
        if (self._interp.context_tokens, self._interp.context_window) != before:
            self._store._usage_changed(self)
```

`ContextStore` signals, after `contextSettled`:

```python
    contextUsage = Signal(str)     # a context's reading or window moved (lifecycle spec §2.3)
```

`create`: add the keyword `seed_usage: dict | None = None` after `fork_session: str = ""`, and `"seedUsage": dict(seed_usage or {}),` to `meta` (after `"forkSession"`).

`fork`: pass `seed_usage={"tokens": src.contextTokens, "window": src.contextWindow}` in the `self.create(...)` call.

After `_context_changed`:

```python
    def _usage_changed(self, c: Context):
        self._model.upsert(c.summary())
        self.contextUsage.emit(c.id)
```

- [ ] **Step 5: Run the unit tests and the fake-driven suites**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_contexts_unit.py tests/test_agents.py tests/test_stream_interpreter.py -v`
Expected: all pass. `test_spawn_sends_env_and_settles` still passes because `harness_env` in the fake's init only lists `HARNESS_*` keys.

- [ ] **Step 6: Commit**

```bash
git add harness/contexts.py tests/fake_claude.py tests/test_contexts_unit.py
git commit -m "Contexts: the reading and window as properties and rows, a fork inherits its source's, auto-compaction off at every spawn

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: The story store acts on the two lines

**Files:**
- Modify: `harness/config_def.py:97` (after `RECAP_STALE_TURNS`)
- Modify: `harness/stories.py` (`__init__`, `situation`, `cast`, `_on_turn_end`, `_recast_now`, new `_thresholds`/`recap_due`/`_nudge`/`_on_usage`)
- Modify: `tests/test_stories.py` (`StubContext`, `StubContexts`, new tests), `tests/test_workspace_store.py:26` (the stub there)

**Interfaces:**
- Consumes: `ContextStore.contextUsage(str)`, `Context.contextTokens`, `Context.contextWindow` (Task 2). `Context.status`, `.send()`, `recast_pending` and `_recast_now` as they exist.
- Produces:
  - `cfg.CONTEXT_WARN = 300_000`, `cfg.CONTEXT_MAX = 500_000`.
  - `Character.context_warned: int | absent` (the recap count at the crossing) and `Character.context_maxed: True | absent`; both popped by `_recast_now`.
  - `StoryStore.recap_due(ch) -> bool`; `situation()` ends with ` · recap due` when it is; `cast()` rows carry `"recapDue": bool`.
  - `recast_pending` may carry `"cause": "context"`; the recast note then reads `recast <name> as <role> (context; rung …)`.
  - Pushed lines: `[situation] …\n[harness] context past the warn line: post a `recap` in #<attended> now — your successor is built from the story record and that recap.` and `[situation] …\n[harness] context at the limit: finish the step in hand and post a `recap` in #<attended> now. You are recast when this turn ends.`

- [ ] **Step 1: Config knobs**

In `harness/config_def.py`, after the `RECAP_STALE_TURNS = 20` line:

```python
# Context usage (lifecycle spec §2.3), in tokens: the input side of a context's latest API call, read off the CLI's
# usage fields. For a 1M window; a smaller known window scales both by window/1M. Past WARN the harness asks for a
# recap once and the situation line says `recap due` until one lands; past MAX the character is asked to finish
# the step in hand and is recast at the turn boundary. Claude Code's own auto-compaction is off in every context.
CONTEXT_WARN = 300_000
CONTEXT_MAX = 500_000
```

- [ ] **Step 2: Extend the stubs**

In `tests/test_stories.py`, `StubContext.__init__`, after `self.transcript_text, self.last_error, self.turns = "", "", 0` add:

```python
        self.contextTokens, self.contextWindow = 0, 0
```

In `StubContexts`, after `contextSettled = Signal(str)` add:

```python
    contextUsage = Signal(str)
```

In `tests/test_workspace_store.py` line 26, the stub that has `contextSettled = Signal(str)`: add `contextUsage = Signal(str)` on the next line.

- [ ] **Step 3: Write the failing tests**

Append to `tests/test_stories.py` after the recast section (the `started`, `settle` helpers and `Q` exist above):

```python
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
```

Check the existing author verbs used above exist with these names before running: `grep -n "def proceed\|def approve\|def cast_yield" harness/stories.py`. If `cast_yield`'s handoff form takes different arguments, copy the call shape from `test_cast_yield_moves_ball_and_notifies` in the same file.

- [ ] **Step 4: Run them to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_stories.py -k "warn_line or recap_due or max_line or manual_recast_already or scale_to_a_small or not_working or after_approve or inherits_no_crossings" -v`
Expected: 8 failures (no pushes happen, `recapDue` missing, notes without `context;`).

- [ ] **Step 5: Implement in `harness/stories.py`**

`__init__`, after `contexts.contextSettled.connect(self._on_turn_end)`:

```python
        contexts.contextUsage.connect(self._on_usage)
```

`situation()`:

```python
    def situation(self, ch: dict) -> str:
        """Spec §5.3: the volatile facts — one line at the top of every message, never in the system prompt."""
        s = self._stories[ch["story_key"]]
        return (f"[situation] phase {s.phase} · attending {self._where(ch, ch.get('attention') or s.main_thread)} · you owe {self._owes_line(ch)} · "
                f"you await {self._awaits_line(ch)} · {self.environment_line(ch)}"
                + (" · recap due" if self.recap_due(ch) else ""))
```

`cast()` rows: add `"recapDue": self.recap_due(ch),` after `"inboxDepth": …`.

New methods, placed after `_owes_line`/`_where` (the situation helpers):

```python
    # ---------------------------------------------------------------- context usage (spec §2.3)
    def recap_due(self, ch: dict) -> bool:
        """Past the warn line with no recap since the crossing."""
        warned = ch.get("context_warned")
        return warned is not None and len(ch.get("recaps", [])) <= warned

    def _thresholds(self, ctx) -> tuple[int, int]:
        """CONTEXT_WARN/MAX are for a 1M window; a smaller known window scales both."""
        window = getattr(ctx, "contextWindow", 0) or 0
        scale = window / 1_000_000 if 0 < window < 1_000_000 else 1
        return int(getattr(cfg, "CONTEXT_WARN", 300_000) * scale), int(getattr(cfg, "CONTEXT_MAX", 500_000) * scale)

    def _nudge(self, ch: dict, ctx, text: str):
        """A harness line into a live context mid-turn, dressed like a delivery: the situation line, then `[harness] …`."""
        ctx.send(self.situation(ch) + f"\n[harness] {text}")

    def _on_usage(self, context_id: str):
        """A context's reading moved. Each line is crossed once per context, only mid-turn: warn asks for a recap and
        the situation line says `recap due` until one lands; max asks the character to finish the step in hand and
        marks a recast for the turn boundary (§3.4)."""
        ch = self._character_by_context(context_id)
        if ch is None:
            return
        s = self._stories[ch["story_key"]]
        ctx = self._contexts.get(context_id)
        if s.phase in lc.TERMINAL or ctx is None or ctx.status not in WORKING:
            return
        tokens = getattr(ctx, "contextTokens", 0) or 0
        warn, limit = self._thresholds(ctx)
        where = self._where(ch, ch.get("attention") or s.main_thread)
        if tokens >= warn and ch.get("context_warned") is None:
            ch["context_warned"] = len(ch.get("recaps", []))
            self._nudge(ch, ctx, f"context past the warn line: post a `recap` in {where} now — "
                                 "your successor is built from the story record and that recap.")
        if tokens >= limit and not ch.get("context_maxed"):
            ch["context_maxed"] = True
            ch.setdefault("recast_pending", {"role": "", "model": "", "cause": "context"})   # a manual one keeps its role
            self._nudge(ch, ctx, f"context at the limit: finish the step in hand and post a `recap` in {where} now. "
                                 "You are recast when this turn ends.")
        self._save_characters()
        self._refresh()
```

`_on_turn_end`: change the pending-recast call to pass the cause:

```python
        if ch.get("recast_pending") is not None:  # a recast waited for this boundary
            pending = ch.pop("recast_pending")
            self._recast_now(ch, pending.get("role", ""), pending.get("model", ""), pending.get("cause", ""))
            return
```

`_recast_now`: signature `def _recast_now(self, ch: dict, role: str = "", model: str = "", cause: str = "") -> str:`. After `ch.pop("recast_pending", None)` add:

```python
        ch.pop("context_warned", None)              # the crossings belong to the context that is gone (§3.4)
        ch.pop("context_maxed", None)
```

And the note:

```python
        self._apply(key, lc.Note(thread_id=s.main_thread,
                                 body=f"recast {ch['name']} as {role_cfg['name']} ({'context; ' if cause == 'context' else ''}{rung})"))
```

- [ ] **Step 6: Run the store tests, then the whole suite**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_stories.py -v`
Expected: all pass, including `test_every_delivery_opens_with_the_situation_line` (no `recap due` there) and the older recast tests (notes unchanged without a cause).

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q`
Expected: all pass. If `tests/test_cli.py` or `tests/test_ipc.py` fail on a missing `contextUsage`, they build a real `ContextStore` and should not; if they use their own stub, add `contextUsage = Signal(str)` to it as in Step 2.

- [ ] **Step 7: Commit**

```bash
git add harness/config_def.py harness/stories.py tests/test_stories.py tests/test_workspace_store.py
git commit -m "Store: warn and max in tokens — a recap request once past 300K with 'recap due' on the situation line, a recast marked for the boundary past 500K

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: The reading reaches the cast panel

**Files:**
- Test: `tests/test_ui_cast.py`

**Interfaces:**
- Consumes: `Context.contextTokens`/`contextWindow` (Task 2), `StoryStore.cast()[…]["recapDue"]` (Task 3). The `ui`, `settled`, `open_story` helpers in the file.
- Produces: nothing; this pins the surface the visual work builds on. No QML changes here — the meter is a separate piece of work.

- [ ] **Step 1: Write the test**

Append to `tests/test_ui_cast.py`:

```python
def test_cast_row_context_carries_its_reading(ui):
    key = ui.store.stories.create("Reading", "")
    chr_id = ui.store.stories.start(key, "tokens=2500", "protagonist")   # the note rides the brief; the fake reads it
    ctx = settled(ui, chr_id)
    assert ctx.contextTokens == 2510 and ctx.contextWindow == 1000000
    row = next(r for r in ui.store.contexts.summaries() if r["id"] == ctx.id)
    assert row["contextTokens"] == 2510 and row["contextWindow"] == 1000000
    assert ui.store.stories.cast(key)[0]["recapDue"] is False
```

- [ ] **Step 2: Run it**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_ui_cast.py -v`
Expected: all pass. If `contextTokens` reads 1010, the note did not reach the prompt: check `render_brief` in `harness/stories.py` still appends `## Note` with the start note, and that `start()` passes it.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ui_cast.py
git commit -m "UI test: a cast row's context carries its reading and window

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Specs in the present tense

**Files:**
- Modify: `docs/specs/story-lifecycle.md` (§1, §2.3, §3.4, §5.3, §7, §8)
- Modify: `docs/DESIGN.md` §8 item 3

**Interfaces:** none. Rewrite, don't annotate: no "renamed", no "was", no migration notes (CLAUDE.md).

- [ ] **Step 1: §1 — the character fields and the reading**

In the `Character { … }` block, after the `recaps: [<comment_id>],` line add:

```
            context_warned: <int> | absent,                 # recaps it had when its context crossed CONTEXT_WARN (§2.3)
            context_maxed: true | absent,                   # its context crossed CONTEXT_MAX; a recast is pending (§3.4)
```

After the `Context { … }` block's closing line, add to the `Derived …` block a new entry:

```
Derived per context, never stored:
  reading = input_tokens + cache_read_input_tokens + cache_creation_input_tokens of its latest assistant
            event: what the context holds. A fork starts with its source's reading.
  window  = the model's context window, from the latest result's modelUsage; unknown until the first
```

- [ ] **Step 2: §2.3 — the two rows and compaction**

Replace the two rows

```
| Context passes `config.CONTEXT_WARN` (default 0.8) | Inject: "context low — post a `recap` in #<attended> now" |
| Context passes `config.CONTEXT_MAX`, or character unresumable when it must act | Auto-recast at the turn boundary per the ladder (§3.4); system comment says which rung |
```

with

```
| Reading passes `config.CONTEXT_WARN` mid-turn (300K tokens for a 1M window; a smaller window scales it) | Once per context: push `[harness] context past the warn line: post a `recap` in #<attended> now — your successor is built from the story record and that recap.`; the situation line ends `· recap due` until a recap lands (§5.3) |
| Reading passes `config.CONTEXT_MAX` mid-turn (500K, scaled likewise) | Once per context: push `[harness] context at the limit: finish the step in hand and post a `recap` in #<attended> now. You are recast when this turn ends.`; recast at the turn boundary per the ladder (§3.4), the system comment naming the cause |
| Character unresumable when it must act | Recast at the turn boundary per the ladder (§3.4) |
```

After the table (before the `AskUserQuestion` paragraph) add:

```
**The reading** is the input side of the context's latest API call (§1), pushed like a steering comment
the moment a line is crossed: the character is told mid-turn, not at the next delivery. A recap lowers
nothing; only recast does. Claude Code's own compaction is off in every context the harness spawns
(`DISABLE_AUTO_COMPACT=1`): the ladder is the only compaction, and a `compact_boundary` event is an
error row in the transcript.
```

- [ ] **Step 3: §3.4 — recast clears the crossings and names the cause**

At the end of §3.4's paragraph (after "…the ordinary delivery loop continues — nothing bespoke."), add:

```
A recast clears `context_warned` and `context_maxed`: the crossings belong to the context that is gone.
Its system comment reads `recast <name> as <role> (context; rung 1: fresh recap)` when the max line caused
it and `recast <name> as <role> (rung 1: fresh recap)` when the author did; a manual recast already
pending when the max line hits keeps its role and model.
```

- [ ] **Step 4: §5.3 — the situation line**

Change the code block to:

```
[situation] phase <phase> · attending #<thread> · you owe <threads> · you await <threads or nothing> · in <repo> at <path>[ · recap due]
[<author>] <kind> in #<thread>: <body>
```

And after the block add one sentence: "`· recap due` appears while the character's context is past the warn line with no recap since the crossing (§2.3); the line never carries the reading itself."

- [ ] **Step 5: §7 and §8**

§7, add a bullet:

```
* Context usage: the reading and window from hand-built events and through replay
  (`test_stream_interpreter.py`, `test_contexts_unit.py`); a fork's inherited reading; `DISABLE_AUTO_COMPACT`
  at every spawn; warn once with `recap due` until a recap, max marking a recast that fires at the boundary
  and names its cause, small-window scaling, nothing on an idle or retired character (`test_stories.py`).
```

§8: remove `; provider-side compaction (recast supersedes it)` from the closing sentence, so it ends `…a thread led by a forked friend is the manual path).`

- [ ] **Step 6: DESIGN.md §8 item 3**

In item 3's `**Deferred:**` sentence remove `context-usage tracking and therefore auto-recast at `CONTEXT_WARN`/`CONTEXT_MAX`; ` so it begins `**Deferred:** recast rung 2 …`. Then append to item 3:

```
   **Context usage shipped 2026-09-04** (proposal `docs/superpowers/proposals/2026-09-04-context-usage.md`, plan
   `docs/superpowers/plans/2026-09-04-context-usage.md`): the reading is the input side of the latest API call from the
   CLI's usage fields, the window from `modelUsage`; `CONTEXT_WARN`/`CONTEXT_MAX` are tokens (300K/500K, scaled to a
   smaller window); a `[harness]` line at each crossing, `recap due` on the situation line, recast at the boundary;
   Claude Code's auto-compaction is off in every context. The cast panel's meter is the UI thread's.
```

- [ ] **Step 7: Read the spec sections back**

Run: `sed -n 9,60p docs/specs/story-lifecycle.md; grep -n "recap due\|CONTEXT_\|compact" docs/specs/story-lifecycle.md docs/DESIGN.md`
Expected: every mention is present tense; no "renamed", "was", "migrat" anywhere in the diff (`git diff docs/ | grep -i "renam\|migrat\| was "` prints nothing).

- [ ] **Step 8: Commit**

```bash
git add docs/specs/story-lifecycle.md docs/DESIGN.md
git commit -m "Lifecycle spec: the reading and window, warn and max in tokens with 'recap due', recast names its cause, auto-compaction off

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review

**Spec coverage.** Measurement → Task 1 and 2. Compaction off → Task 2 (`_env`, fake init flag, test). Thresholds and scaling → Task 3 (`_thresholds`, config). The two crossings, once per context, mid-turn, `recap due`, cause on the note, cleared on recast → Task 3. Forks inherit the reading (Task 2) and not the crossings (Task 3). `compact_boundary` as an error row → Task 1. Summary/rows for the UI → Task 2, pinned in Task 4. Spec rewrite → Task 5.

**Deviation from the proposal, stated:** `context_warned` holds the recap count at the crossing rather than the turn count, and `context_maxed` is a flag. Same behaviour, no interaction with `recap_turns` across a recast. Task 5 writes the spec that way.

**Types.** `contextTokens`/`contextWindow` (Qt properties and summary keys), `context_tokens`/`context_window` (interpreter attributes), `contextUsage` (signal), `seed_usage`/`seedUsage` (create kwarg/meta key), `context_warned`/`context_maxed` (character keys), `recapDue` (cast row), `cause` (pending-recast key) — each used with one spelling across tasks.
