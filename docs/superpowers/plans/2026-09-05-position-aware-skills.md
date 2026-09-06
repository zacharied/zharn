# Position-aware skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A character's injected skill is chosen by its position as well as the story's phase, so a friend wakes up with a short `being-a-friend` instead of the protagonist's `implementing-a-story`.

**Architecture:** One lookup gains an axis (`skill_name(position, phase)`), and the bookkeeping field that decides when a skill is due changes from the phase to the skill's *name* (`Character.phase_seen` → `Character.skill_seen`). Every delivery case — fresh cast, fork, recast, Proceed, inbox pop — falls out of that substitution with no special-casing. A new skill file and a spec rewrite carry the rest.

**Tech Stack:** Python 3.10+, PySide6, pytest. No new dependencies.

**Spec:** `docs/superpowers/proposals/2026-09-05-position-aware-skills.md`

## Global Constraints

- **This plan runs on top of ZHAR-5** (model/effort/preset), which deletes `harness/roles.py`, adds `harness/casting.py`, and renames `Character.role` → `Character.position` with `CAST_POSITIONS = {"protagonist", "friend", "bare"}`. Do not start until ZHAR-5 is approved and merged to `main`. Every line number below is from ZHAR-5's branch at the time of writing and is a hint; **the names are the contract, the line numbers are not** — locate by name.
- **No backward compatibility** (DESIGN.md §0). `Character.phase_seen` is renamed in place. No migration, no dual read, no fallback for records on disk written by an older build. Delete `skills.phase_skill` rather than deprecating it.
- **Spec tense.** `docs/specs/` is present tense, describing how the program *is*. No migration notes, no old-to-new vocabulary tables; delete what a change replaces (CLAUDE.md).
- **Skill file hygiene**, all asserted by `tests/test_skills.py`. Every `SKILL.md` frontmatter `description` starts with `Use when` or `Use always`. No file under a skill directory may contain any of: `superpowers:`, `human partner`, `partner`, `subagent`, `Subagent`, `Task tool`, `TodoWrite`. Every *injected* skill body (`being-a-character`, `planning-a-story`, `implementing-a-story`, and now `being-a-friend`) must contain neither `fail` nor `slow` in any case — `tests/fake_claude.py` treats those as trigger words, and these bodies ride every brief. `being-a-character` stays under 150 words.
- **Running the suite.** The venv lives only in the main checkout, and `HARNESS_*` environment variables must be cleared or the suite lies. From the worktree, in bash:

  ```sh
  env $(env | grep -o '^HARNESS_[A-Z_]*' | sed 's/^/-u /') \
      "C:/Users/zachd/Code/zharn/.venv/Scripts/python.exe" -m pytest tests/ -q --ignore=tests/skills
  ```

  Every `pytest` command below is shorthand for that invocation with the paths swapped in.
- **`tests/test_app.py` rewrites `harness/content.py`, `qml/Main.qml` and `qml/content/Welcome.qml` LF→CRLF on every full run.** `git checkout --` them afterwards. Never `git add -A` blind.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `harness/skills/skills/being-a-friend/SKILL.md` | **Create.** The friend's playbook: one thread, one piece, no gate. | 1 |
| `harness/skills.py` | **Modify.** `POSITION_SKILLS`, `skill_name`, `skill_for`, `always_on`; `plugin_dir` unions the always-on set; `phase_skill` deleted. | 2, 4 |
| `harness/stories.py` | **Modify.** `_phase_skill_due` → `_skill_due`; `phase_seen` → `skill_seen` at every site. | 3 |
| `harness/skills/skills/being-a-character/SKILL.md` | **Modify.** Law 4 stops naming the two phase skills by hand. | 5 |
| `harness/skills/skills/implementing-a-story/SKILL.md` | **Modify.** One line naming what its friends were told. | 5 |
| `docs/specs/story-lifecycle.md` | **Modify.** §1, §5.1, §5.2, §5.3, §5.4. | 6 |
| `tests/test_skills.py` | **Modify.** Hygiene sets gain `being-a-friend`; `skill_name` matrix; always-on-in-the-tree. | 1, 2, 4 |
| `tests/test_stories.py` | **Modify.** The §5.3 delivery block, rewritten around positions. | 3 |
| `tests/test_agents.py` | **Modify.** One `phase_skill` call site. | 3 |
| `tests/skills/friend-stays-in-lane/` | **Create.** Paid scenario. | 7 |

---

### Task 1: The `being-a-friend` skill file

The file first, with nothing reading it yet: it is a document, and a reviewer can accept or reject its prose without any behaviour riding on it.

**Files:**
- Create: `harness/skills/skills/being-a-friend/SKILL.md`
- Modify: `tests/test_skills.py` (the `ZHARN` set; the injected-skills parametrize list)
- Test: `tests/test_skills.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a skill directory named `being-a-friend`, readable by `skills.skill_body("being-a-friend")`.

- [ ] **Step 1: Add the skill to the two sets the tree tests assert over**

In `tests/test_skills.py`, near the top of the plugin-tree section:

```python
ZHARN = {"being-a-character", "being-a-friend", "planning-a-story", "implementing-a-story", "delegating"}
```

and extend the trigger-word parametrize (the test is named `test_injected_skills_avoid_the_fake_claudes_trigger_words`):

```python
@pytest.mark.parametrize("name", ["being-a-character", "being-a-friend", "planning-a-story", "implementing-a-story"])
def test_injected_skills_avoid_the_fake_claudes_trigger_words(name):
    """tests/fake_claude.py fails a turn on "fail" and sleeps on "slow"; these bodies ride every brief and delivery."""
    body = skills.skill_body(name).lower()
    assert "fail" not in body and "slow" not in body
```

- [ ] **Step 2: Run the tree tests to verify they fail**

Run: `pytest tests/test_skills.py -q -k "tree_holds or frontmatter or vocabulary or trigger_words"`

Expected: FAIL. `test_the_tree_holds_exactly_the_spec_skills` reports a set difference missing `being-a-friend`; the parametrized cases for `being-a-friend` fail on an empty body.

- [ ] **Step 3: Write the skill**

Create `harness/skills/skills/being-a-friend/SKILL.md` with exactly this content:

````markdown
---
name: being-a-friend
description: Use when you were called onto a thread for one piece of a story — before you build, commit, or end a turn
---

# Being a friend

You were called onto one thread for one piece of this story. The note that called you is your brief. Whoever called you reads your handoff, not your diff.

## The Iron Law

```
YOUR TURN ENDS IN YOUR OWN THREAD — A HANDOFF, A QUESTION, OR A WAIT
```

Stop with nothing yielded and nothing awaited, and the harness posts your last words as a handoff under your name. `#main` is not yours: only a thread's lead yields in it, and that is the protagonist.

## Where you stand

| | |
|---|---|
| Your author | whoever called you — usually a character, not the human. Your yields reach them. |
| Your thread | the one you lead. Comment elsewhere only when your note sends you. |
| Your tree | the lead's, shared. Commit only when your note says to; never rebase. |
| Your gate | none. No tree check, no ancestry check, no repo checks — those are the lead's, on `#main`. |
| Not yours | `proceed`, `approve`, the outline, calling reviewers. |

Planning phase — the situation line names it — you read, run what changes nothing, and report; edits wait for `implementing`. Otherwise `env open`, stay in the files your note named, build test-first (`zharn:test-driven-development`), prove it (`zharn:verification-before-completion`), and send a minion for anything large to read (`zharn:delegating`). What the note leaves open, you decide — and name the decision in your handoff.

## The handoff

`yield --handoff` in your thread, body in this order: **what changed** (files and behaviour, one line each), **how verified** (the commands you ran and what they printed — counts, not adjectives), **where to look first** (the one file or test that shows it working).

## Rationalizations

| Excuse | Reality |
|---|---|
| "The other skill said to commit before handing off" | That one is the lead's. Your thread is not gated and the tree is shared; the lead declares the work done. |
| "I'll hand off on `#main` so the author sees it" | Only its lead yields there. Your handoff in your own thread wakes whoever called you — that is how it reaches `#main`. |
| "The outline needs splitting into tasks" | It was split already. Your task is the note. |
| "I'm nearly done, I'll fix the next thing too" | Two writers, one tree. What you touch outside your note collides with someone. |
| "I'll ask a quick question" | Decide it and record it, unless the answer changes what you were asked to build. |
| "I finished; my last message says so" | Prose outside the CLI reaches nobody. `yield --handoff`. |

## Checklist

- [ ] The note's task, and only it
- [ ] Test-first; verified by commands you ran and quoted
- [ ] Open decisions made, and named in the handoff
- [ ] Tree left as the note asks
- [ ] `yield --handoff` in your own thread
````

- [ ] **Step 4: Run the tree tests to verify they pass**

Run: `pytest tests/test_skills.py -q`

Expected: PASS, all of it. If `test_no_superpowers_vocabulary_survives[being-a-friend]` fails, a forbidden substring crept in — the likely one is `partner`. If `test_injected_skills_avoid_the_fake_claudes_trigger_words[being-a-friend]` fails, search the body case-insensitively for `fail` and `slow`, including inside longer words.

- [ ] **Step 5: Commit**

```bash
git add harness/skills/skills/being-a-friend/SKILL.md tests/test_skills.py
git commit -m "A friend's playbook: one thread, one piece, and no gate at its handoff"
```

---

### Task 2: `skill_name(position, phase)`

**Files:**
- Modify: `harness/skills.py` (the module-level tables, and next to `phase_skill`)
- Test: `tests/test_skills.py`

**Interfaces:**
- Consumes: `being-a-friend` from Task 1.
- Produces:
  - `skills.POSITION_SKILLS: dict[str, str]` — `{"friend": "being-a-friend"}`
  - `skills.skill_name(position: str, phase: str) -> str` — the skill directory name, or `""`
  - `skills.skill_for(position: str, phase: str) -> str` — that skill's body, or `""`
  - `skills.PHASE_SKILLS` keeps its current shape and meaning.
  - `skills.phase_skill` still exists after this task; Task 3 removes it with its last caller. Leaving it here keeps the suite green at this commit.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_skills.py`, directly after `test_phase_skill_maps_phases_to_skills`:

```python
def test_skill_name_keys_on_position_then_phase():
    assert skills.skill_name("protagonist", "planning") == "planning-a-story"
    assert skills.skill_name("protagonist", "implementing") == "implementing-a-story"
    assert skills.skill_name("friend", "planning") == "being-a-friend"
    assert skills.skill_name("friend", "implementing") == "being-a-friend"


def test_skill_name_is_empty_where_no_skill_belongs():
    assert skills.skill_name("bare", "planning") == ""        # a bare context is on no story
    assert skills.skill_name("bare", "implementing") == ""
    assert skills.skill_name("protagonist", "done") == ""     # terminal and pre-start phases carry none
    assert skills.skill_name("protagonist", "todo") == ""
    assert skills.skill_name("protagonist", "") == ""
    assert skills.skill_name("", "implementing") == "implementing-a-story"   # no position: the phase decides


def test_skill_for_reads_the_body_of_whatever_skill_name_picked(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_SKILLS_DIR", str(tmp_path))
    write_skill(tmp_path, "implementing-a-story", "BUILD")
    write_skill(tmp_path, "being-a-friend", "ONE PIECE")
    assert skills.skill_for("protagonist", "implementing") == "BUILD"
    assert skills.skill_for("friend", "implementing") == "ONE PIECE"
    assert skills.skill_for("friend", "done") == ""
    assert skills.skill_for("bare", "implementing") == ""
```

Note on the last case of `test_skill_name_is_empty_where_no_skill_belongs`: an empty position falls through to the phase table. That is what a record written before positions existed, or a caller passing nothing, gets — the protagonist's skill, which is today's behaviour and the safer of the two defaults.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_skills.py -q -k "skill_name or skill_for"`

Expected: FAIL with `AttributeError: module 'harness.skills' has no attribute 'skill_name'`.

- [ ] **Step 3: Write the implementation**

In `harness/skills.py`, beside `PHASE_SKILLS`:

```python
PHASE_SKILLS = {"planning": "planning-a-story", "implementing": "implementing-a-story"}
# A position that leads no story of its own takes one skill in every phase (spec §5.3).
POSITION_SKILLS = {"friend": "being-a-friend"}
# Not on a story at all: the phase skills are inert there, so it takes none (spec §5.1).
NO_SKILL_POSITIONS = {"bare"}
```

and beside `phase_skill`:

```python
def skill_name(position: str, phase: str) -> str:
    """The skill directory a character in `position` wakes up with while the story is in `phase`; "" for a
    position or a phase that carries none (spec §5.3)."""
    if position in POSITION_SKILLS:
        return POSITION_SKILLS[position]
    if position in NO_SKILL_POSITIONS:
        return ""
    return PHASE_SKILLS.get(phase, "")


def skill_for(position: str, phase: str) -> str:
    name = skill_name(position, phase)
    return skill_body(name) if name else ""
```

Both position tables are membership tests, not `.get(...) or ...` fallbacks. That matters for `bare`: a single `POSITION_SKILLS.get(position) or PHASE_SKILLS.get(phase, "")` would hand a bare context the protagonist's phase skill, since neither `None` nor `""` stops the fallthrough. `NO_SKILL_POSITIONS` is what makes "takes none" different from "not listed".

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_skills.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add harness/skills.py tests/test_skills.py
git commit -m "The skill a character wakes up with is a function of its position and the phase"
```

---

### Task 3: `skill_seen` — delivery keys on the skill's name

The behaviour change. Everything before this task was inert.

**Files:**
- Modify: `harness/stories.py` — `_phase_skill_due` (≈line 428), `_push` (≈441), `_cast` (≈575–615), `_recast_now` (≈834–866), `cast_proceed` (≈1107)
- Modify: `harness/skills.py` — delete `phase_skill`
- Modify: `tests/test_stories.py` — the whole "the phase skill in messages (spec §5.3)" block, ≈line 1395 to the end of it
- Modify: `tests/test_agents.py` — ≈line 215
- Modify: `tests/test_skills.py` — `test_phase_skills_exist`
- Test: `tests/test_stories.py`, `tests/test_agents.py`

**Interfaces:**
- Consumes: `skills.skill_name`, `skills.skill_for` (Task 2).
- Produces:
  - `Character.skill_seen: str | None` — the *name* of the skill last delivered. Replaces `Character.phase_seen`.
  - `StoryStore._skill_due(ch: dict) -> str` — the body to append, or `""`. Replaces `_phase_skill_due`. Mutates `ch["skill_seen"]`; the caller saves.
  - `StoryStore.cast_proceed` still returns `{**comment, "skill": <implementing-a-story body>}`.

- [ ] **Step 1: Write the failing tests**

Replace the entire block in `tests/test_stories.py` that begins with the comment `# ---- the phase skill in messages (spec §5.3)` — from that header down to the end of `test_a_recast_brief_ends_with_the_current_skill` — with the following. Every `skills.phase_skill(p)` call becomes `skills.skill_for(position, p)`, and every `phase_seen` assertion becomes `skill_seen` against a name.

```python
# ---------------------------------------------------------------- the skill in messages (spec §5.3)

PLAN = "planning-a-story"
BUILD = "implementing-a-story"
FRIEND = "being-a-friend"


def test_a_fresh_brief_ends_with_the_positions_skill_and_records_it(store, contexts):
    key, chr_id = started(store)
    first = contexts.get("ctx_1").sent[0]
    assert first.rstrip().endswith(skills.skill_body(PLAN)) and store.character(chr_id)["skill_seen"] == PLAN


def test_a_missing_skill_notifies_once(store, contexts, monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_SKILLS_DIR", str(tmp_path))               # an empty tree: no skills at all
    key, chr_id = started(store)
    assert store.character(chr_id)["skill_seen"] == PLAN
    assert len(store.notifier.errors) == 1 and PLAN in store.notifier.errors[0]
    store.comment(key, "same phase")                                     # a second delivery, same skill due
    assert len(store.notifier.errors) == 1


def test_a_fork_of_the_protagonist_becomes_a_friend_and_is_told_so(store, contexts):
    """Proposal §2: the fork's conversation holds the protagonist's skill, which is the wrong one now."""
    key, chr_id = started(store)
    contexts.get(store.character(chr_id)["live_context"]).status = "idle"
    r = store.cast_call(chr_id, "second opinion", fork=True)
    friend = store.character(r["character"])
    first = contexts.get(friend["live_context"]).sent[0]
    assert friend["skill_seen"] == FRIEND
    assert first.rstrip().endswith(skills.skill_body(FRIEND))
    assert skills.skill_body(PLAN) not in first


def test_proceed_delivers_the_implementing_skill_to_the_protagonist_once(store, contexts):
    key, chr_id = started(store)
    ctx = contexts.get("ctx_1")
    store.cast_yield(chr_id, "handoff", "outline")
    store.proceed(key, "go")
    build = skills.skill_body(BUILD)
    assert ctx.sent[-1].rstrip().endswith(build) and store.character(chr_id)["skill_seen"] == BUILD
    store.comment(key, "same phase")
    assert build not in ctx.sent[-1] and ctx.sent[-1].startswith("[situation] phase implementing")


def test_back_to_planning_and_reopen_deliver_the_new_skill(store, contexts):
    key, chr_id = started(store)
    ctx = contexts.get("ctx_1")
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    store.cast_yield(chr_id, "handoff", "built")
    store.backToPlanning(key, "rethink")
    assert ctx.sent[-1].rstrip().endswith(skills.skill_body(PLAN)) and store.character(chr_id)["skill_seen"] == PLAN
    store.cancel(key)
    store.reopen(key, "one more")
    assert ctx.sent[-1].rstrip().endswith(skills.skill_body(BUILD)) and store.character(chr_id)["skill_seen"] == BUILD


def test_a_friend_is_sent_nothing_new_when_the_phase_moves_under_it(store, contexts):
    """The defect this replaces: a friend used to be handed implementing-a-story mid-thread."""
    key, chr_id = started(store)
    r = store.cast_call(chr_id, "read the docs")
    friend = store.character(r["character"])
    fctx = contexts.get(friend["live_context"])
    assert friend["skill_seen"] == FRIEND
    store.openThread(key, "@Friend btw")                      # the friend is working → its inbox
    assert store.character(r["character"])["inbox"]
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    settle(store, contexts, r["character"])                   # its turn ends: the item pops
    assert fctx.sent[-1].startswith("[situation] phase implementing")
    assert skills.skill_body(BUILD) not in fctx.sent[-1]
    assert store.character(r["character"])["skill_seen"] == FRIEND


def test_an_inbox_item_popped_after_a_proceed_carries_the_new_skill_for_the_protagonist(store, contexts):
    """The pop, not the Proceed, is where the protagonist learns: attention was elsewhere."""
    key, chr_id = started(store)
    ctx = contexts.get("ctx_1")
    r = store.cast_call(chr_id, "build it")
    store.cast_yield(chr_id, "handoff", "outline", thread=None)
    store.proceed(key)
    assert ctx.sent[-1].rstrip().endswith(skills.skill_body(BUILD))
    assert store.character(chr_id)["skill_seen"] == BUILD


def test_cast_proceed_returns_the_skill_and_the_next_delivery_does_not_repeat_it(store, contexts, monkeypatch):
    key = store.create("Plain", "no outline rule")
    chr_id = store.start(key, "go")
    monkeypatch.setitem(StubCasting.POSITIONS["protagonist"], "outline_first", False)
    ctx = contexts.get(store.character(chr_id)["live_context"])
    r = store.cast_proceed(chr_id, "bounded")
    assert r["kind"] == "system" and r["skill"] == skills.skill_body(BUILD)
    assert store.character(chr_id)["skill_seen"] == BUILD
    store.comment(key, "hi")
    assert skills.skill_body(BUILD) not in ctx.sent[-1]


def test_a_friend_cast_in_implementing_gets_the_friend_skill_and_not_the_leads(store, contexts):
    """The ZHAR-5 defect, as a test: Scribe was cast here and handed implementing-a-story."""
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    r = store.cast_call(chr_id, "build it")
    friend = store.character(r["character"])
    first = contexts.get(friend["live_context"]).sent[0]
    assert first.rstrip().endswith(skills.skill_body(FRIEND))
    assert skills.skill_body(BUILD) not in first
    assert friend["skill_seen"] == FRIEND


def test_a_recast_brief_ends_with_the_current_skill(store, contexts):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    contexts.get(store.character(chr_id)["live_context"]).status = "idle"
    new = store.recast(key, chr_id)
    first = contexts.get(new).sent[0]
    assert "## Situation" in first and first.rstrip().endswith(skills.skill_body(BUILD))
    assert store.character(chr_id)["skill_seen"] == BUILD


def test_a_recast_friend_gets_the_friend_skill(store, contexts):
    key, chr_id = started(store)
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    r = store.cast_call(chr_id, "build it")
    fid = r["character"]
    contexts.get(store.character(fid)["live_context"]).status = "idle"
    new = store.recast(key, fid)
    assert contexts.get(new).sent[0].rstrip().endswith(skills.skill_body(FRIEND))
    assert store.character(fid)["skill_seen"] == FRIEND
```

Two of these lean on helpers already in the file — `started`, `settle`, `StubCasting.POSITIONS` — and on `store.cast_yield(chr_id, "handoff", "outline")` defaulting to the attended thread. If `cast_yield` has no `thread` keyword, drop the `thread=None` argument in `test_an_inbox_item_popped_after_a_proceed_carries_the_new_skill_for_the_protagonist` and let it default.

Also change, in `tests/test_agents.py` (≈line 215):

```python
    assert delivered.startswith("[situation] phase implementing") and delivered.rstrip().endswith(skills.skill_body("implementing-a-story"))
```

and in `tests/test_skills.py`, replace `test_phase_skills_exist`:

```python
def test_every_injected_skill_exists_in_the_tree():
    for name in ("being-a-character", "being-a-friend", "planning-a-story", "implementing-a-story"):
        assert skills.skill_body(name)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_stories.py -q -k "skill"`

Expected: FAIL. `KeyError: 'skill_seen'` or `assert None == 'planning-a-story'` on every case, because the store still writes `phase_seen`.

- [ ] **Step 3: Rename the field and the method**

In `harness/stories.py`, replace `_phase_skill_due` with:

```python
    def _skill_due(self, ch: dict) -> str:
        """Spec §5.3: the skill rides a message whenever the one due for this character's position and the story's
        phase differs from what it was last told — not from the action that moved the phase, since an inbox item can
        be popped after the Proceed that preceded it. Terminal phases carry none. Updates skill_seen; the caller
        saves."""
        phase = self._stories[ch["story_key"]].phase
        if phase in lc.TERMINAL:
            return ""
        name = skills.skill_name(ch.get("position", ""), phase)
        if not name or ch.get("skill_seen") == name:
            return ""
        ch["skill_seen"] = name
        body = skills.skill_body(name)
        if not body and self.notifier is not None:
            self.notifier.error(f"no {name} skill under {skills.skills_dir()} — {ch['name']} runs without it")
        return body
```

`skill_seen` is set before the body is read, so a missing file notifies once and not on every delivery — the behaviour the old code got from setting `phase_seen` first, and what `test_a_missing_skill_notifies_once` asserts.

Then, in the same file:

- `_push` (≈441): `skill = self._phase_skill_due(ch)` → `skill = self._skill_due(ch)`. Its docstring's "the phase skill when it is new" → "the skill for its position when it is new".
- `_cast` (≈602), the fresh branch: `skill=self._phase_skill_due(ch)` → `skill=self._skill_due(ch)`.
- `_cast` (≈605), the fork branch: **delete** the line

  ```python
                  ch["phase_seen"] = src.get("phase_seen")   # its conversation already holds the skill (spec §5.3)
  ```

  and append the due skill to the fork's first message. The line that builds it becomes:

  ```python
                  first = getattr(cfg, "FORK_NOTE", "").format(name=name, source=src["name"]) + note
                  skill = self._skill_due(ch)
                  if skill:
                      first += f"\n\n{skill}"
  ```

  A fork of the protagonist into a friend now has `skill_seen = None`, so `being-a-friend` is due and rides the note. A fork of a friend into a friend has `skill_seen = None` too and gets the same skill again — harmless, and one less special case than reading the source's record.
- `_recast_now` (≈846): `ch["phase_seen"] = None` → `ch["skill_seen"] = None`, comment → `# a fresh context: the brief ends with the skill for its position`. Next line: `skill = self._skill_due(ch)`.
- `cast_proceed` (≈1117): `ch["phase_seen"] = "implementing"` → `ch["skill_seen"] = "implementing-a-story"`, and the return becomes `{**c, "skill": skills.skill_body("implementing-a-story")}`. `proceed` is main's lead only, so the position is always `protagonist` here.

- [ ] **Step 4: Delete `phase_skill`**

In `harness/skills.py`, delete:

```python
def phase_skill(phase: str) -> str:
    name = PHASE_SKILLS.get(phase)
    return skill_body(name) if name else ""
```

Then confirm nothing calls it:

Run: `grep -rn "phase_skill\|phase_seen" harness/ tests/ docs/specs/`

Expected: no hits outside `docs/superpowers/` (proposals and plans are scaffolding and are left stale on purpose, per CLAUDE.md). `docs/specs/story-lifecycle.md` still names `phase_seen` at this point; Task 6 fixes it, and this grep is a reminder, not a gate.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_stories.py tests/test_agents.py tests/test_skills.py -q`

Expected: PASS.

- [ ] **Step 6: Run the whole suite**

Run: `pytest tests/ -q --ignore=tests/skills`

Expected: PASS, with the same counts as before the task plus the new tests. Then `git checkout -- harness/content.py qml/Main.qml qml/content/Welcome.qml` for the CRLF rewrite.

- [ ] **Step 7: Commit**

```bash
git add harness/stories.py harness/skills.py tests/test_stories.py tests/test_agents.py tests/test_skills.py
git commit -m "A friend is told it is a friend: delivery keys on the skill's name, not the phase"
```

---

### Task 4: The always-on skills are in every built tree

Separable from the rest — the proposal (§4) says so. If it is cut, skip to Task 5 and drop its bullet from Task 6.

**Files:**
- Modify: `harness/skills.py` (`always_on`, and `plugin_dir` before it stamps)
- Test: `tests/test_skills.py`

**Interfaces:**
- Consumes: `skills.PHASE_SKILLS`, `skills.POSITION_SKILLS` (Task 2).
- Produces: `skills.always_on() -> set[str]` — the skill names the harness injects, which every built tree must therefore contain. `plugin_dir` and `plugin_args` keep their signatures.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_skills.py`, in the preset-filtered-tree section (it has a `tree` fixture and a `names_in` helper already):

```python
def test_the_always_on_set_is_the_injected_skills():
    assert skills.always_on() == {"being-a-character", "being-a-friend",
                                  "planning-a-story", "implementing-a-story"}


def test_a_filtered_tree_carries_the_always_on_skills_the_preset_left_out(tmp_path, monkeypatch):
    """Spec §5.1: being-a-character law 4 tells a character to re-read its skill, so it must be listable."""
    src = tmp_path / "src"
    (src / ".claude-plugin").mkdir(parents=True)
    (src / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "zharn", "version": "0.0.1"}))
    for name in ("being-a-character", "being-a-friend", "planning-a-story",
                 "implementing-a-story", "delegating"):
        write_skill(src, name, f"body of {name}")
    monkeypatch.setenv("HARNESS_SKILLS_DIR", str(src))
    out = skills.plugin_dir("builder", ["delegating"], tmp_path / "cache")
    assert names_in(out) == {"delegating"} | skills.always_on()


def test_the_whole_tree_is_still_handed_over_untouched(tree, tmp_path):
    assert skills.plugin_dir(names=None, cache=tmp_path / "cache") == tree
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_skills.py -q -k "always_on"`

Expected: FAIL with `AttributeError: module 'harness.skills' has no attribute 'always_on'`.

- [ ] **Step 3: Write the implementation**

In `harness/skills.py`, beside the tables:

```python
META_SKILL = "being-a-character"


def always_on() -> set[str]:
    """The skills the harness injects itself (spec §5.3). Every built tree carries them whatever a preset says:
    `being-a-character` tells a character to re-read its skill with the Skill tool, and it must be there to read."""
    return {META_SKILL, *PHASE_SKILLS.values(), *POSITION_SKILLS.values()}
```

and at the top of `plugin_dir`, immediately after the `names is None or cache is None` early return:

```python
    names = sorted(set(names) | always_on())
```

It must go before `_stamp(src, names)` so the cache key covers the added skills and a change to one of them rebuilds the tree.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_skills.py -q`

Expected: PASS. A pre-existing test asserting an exact `names_in(out)` for a filtered tree will now see the always-on names too; update its expected set to `{...} | skills.always_on()` rather than weakening the assertion.

- [ ] **Step 5: Commit**

```bash
git add harness/skills.py tests/test_skills.py
git commit -m "A preset cannot hide the skills the harness injects: every built tree carries them"
```

---

### Task 5: The two skills that mention the phase skills by hand

**Files:**
- Modify: `harness/skills/skills/being-a-character/SKILL.md` (law 4)
- Modify: `harness/skills/skills/implementing-a-story/SKILL.md` (the "Protect your context" section)
- Test: `tests/test_skills.py`

**Interfaces:**
- Consumes: `being-a-friend` (Task 1).
- Produces: nothing other code reads.

- [ ] **Step 1: Reword law 4 of `being-a-character`**

Replace:

```
4. The phase skill in your conversation is mandatory; unsure, re-read `zharn:planning-a-story` or `zharn:implementing-a-story`.
```

with:

```
4. The skill in your messages is mandatory; re-read it with the Skill tool.
```

**Word budget, measured.** `being-a-character` is at 149 words and `test_being_a_character_is_short` asserts `< 150`. The old law 4 is 14 words and so is this replacement, so the body stays at 149 — one word of headroom, exactly. Do not add a word to this skill without taking one out. Verify before committing:

```sh
python -c "from pathlib import Path; t=Path('harness/skills/skills/being-a-character/SKILL.md').read_text(encoding='utf-8'); b=t[t.find(chr(10)+'---',3)+4:].strip(); print(len(b.split()))"
```

Expected: `149`.

- [ ] **Step 2: Add one line to `implementing-a-story`**

In the "Protect your context" section, after "Minions read, friends build, you hold the plot.", add:

```
A friend wakes up with `zharn:being-a-friend`, not this: it hands off in its own thread, and its tree is not gated. What it must not decide for itself belongs in the note you call it with.
```

Check the addition for the trigger words: no `fail`, no `slow`, no `partner`.

- [ ] **Step 3: Run the skill tests**

Run: `pytest tests/test_skills.py -q`

Expected: PASS, `test_being_a_character_is_short` included. If it fails on the word count, cut words from law 4 — the point it must carry is "mandatory, and re-readable with the Skill tool".

- [ ] **Step 4: Commit**

```bash
git add harness/skills/skills/being-a-character/SKILL.md harness/skills/skills/implementing-a-story/SKILL.md
git commit -m "The meta skill stops naming the phase skills by hand, and the lead's playbook says what its friends were told"
```

---

### Task 6: The spec

`docs/specs/` describes how the program *is*. Everything below is present tense, and replaces text rather than annotating it.

**Files:**
- Modify: `docs/specs/story-lifecycle.md` — §1, §5.1, §5.2, §5.3, §5.4
- Test: none (prose). The gate is that the spec matches the code Tasks 1–5 shipped.

**Interfaces:**
- Consumes: everything above.
- Produces: the standing description. The proposal expires when this lands.

- [ ] **Step 1: §1, the Character record**

Replace:

```
            phase_seen: <phase> | null }                    # the phase whose skill it last received (§5.3)
```

with:

```
            skill_seen: <skill name> | null }               # the skill it last received (§5.3)
```

- [ ] **Step 2: §5.1, the tree listing**

In the code block, after the `being-a-character` line, add:

```
    being-a-friend/                   # position: one thread, one piece, no gate at the handoff
```

and reword the two phase lines so the listing says which position each belongs to:

```
    planning-a-story/                 # protagonist, planning: classify, ask once, outline, proceed
    implementing-a-story/             # protagonist, implementing: TDD, delegate, verify, hand off
```

- [ ] **Step 3: §5.1, the paragraph about what a preset cannot switch off**

Replace:

```
Claude lists every skill as `zharn:<name>`; a character re-reads its phase skill that way when
unsure. Every spawn gets a plugin — bare contexts and asides too; the phase skills are inert
without a story. `being-a-character` and the phase skills reach every character whatever its preset
says: the harness reads them out of the source tree and delivers them itself (§5.3), so no preset can
switch them off, and a preset that leaves them out of the plugin only means the character cannot
re-read them with the Skill tool.
```

with:

```
Claude lists every skill as `zharn:<name>`; a character re-reads the skill it was sent that way
when unsure. Every spawn gets a plugin — bare contexts and asides too; the phase skills are inert
without a story. The **injected** skills — `being-a-character`, `planning-a-story`,
`implementing-a-story`, `being-a-friend` — reach every character whatever its preset says: the
harness reads them out of the source tree and delivers them itself (§5.3). A preset cannot switch
them off, and a filtered tree carries them regardless of what the preset names, because
`being-a-character` tells a character to re-read its skill with the Skill tool and a skill absent
from the plugin cannot be re-read.
```

If Task 4 was cut, keep the old sentence about the character being unable to re-read them, and drop the last clause of the replacement.

- [ ] **Step 4: §5.2, the contract**

Replace law 4 in the `being-a-character` sentence:

```
(4) the phase skill in your conversation is
mandatory — re-read it with the Skill tool when unsure;
```

with:

```
(4) the skill your messages carried is
mandatory — re-read it with the Skill tool when unsure;
```

Then add a `being-a-friend` paragraph after the `implementing-a-story` one, in the same shape as its neighbours:

```
`being-a-friend`: one thread, one piece; your author is whoever called you and your yields reach
them, not the human; you hand off in the thread you lead, never `#main`, which only its lead may
yield in; you share the lead's tree and it is not gated — commit only when the note says to, never
rebase; no edits while the story is planning; `proceed` and `approve` are not yours; decide what
the note leaves open and name the decision in the handoff. REQUIRED test-driven-development,
verification-before-completion.
```

And in the `implementing-a-story` paragraph, after "you hold the plot", add: "; the friends you call are told `being-a-friend`, so what they must not decide alone belongs in the call note".

- [ ] **Step 5: §5.3, the delivery rule and its table**

Replace the **Phase skill** paragraph and its table:

```
**Phase skill.** In messages only, never in the system prompt. Sent whenever the story's phase
differs from `Character.phase_seen`, which is then updated — the comparison is against what the
character was last told, not against the action that moved the phase, because an inbox item can be
popped after the Proceed that preceded it.

| Moment | The character receives |
|---|---|
| Fresh context, recast included | The brief ends with the current phase skill (§3.1). |
| Forked friend | No skill; `phase_seen` copies from the source, whose conversation holds it. |
| Any delivery with `phase ≠ phase_seen` | The new phase's skill appended after the comment. |
| Cast `proceed` | `implementing-a-story` on stdout (§2.2). |
| Respawn in the same phase | Nothing — the resumed conversation holds it. |

Friends get the phase skill like the protagonist: the story's phase binds everyone on it.
```

with:

```
**The injected skill.** In messages only, never in the system prompt. Which one is due is a
function of the character's position and the story's phase: a protagonist takes the phase's skill,
a friend takes `being-a-friend` in every phase, a bare context takes none, and a terminal phase
carries none. It is sent whenever the skill due differs from `Character.skill_seen`, which is then
updated — the comparison is against the skill the character was last told, not against the action
that moved the phase, because an inbox item can be popped after the Proceed that preceded it.

| Moment | The character receives |
|---|---|
| Fresh context, recast included | The brief ends with the skill due for its position (§3.1). |
| Forked friend | `being-a-friend` after the fork note: the conversation it inherited holds its source's skill, which is the wrong one now. |
| Any delivery where the skill due ≠ `skill_seen` | That skill, appended after the comment. |
| Cast `proceed` | `implementing-a-story` on stdout (§2.2) — only main's lead may `proceed`. |
| A friend across a phase change | Nothing: the skill due is unchanged. |
| Respawn with the same skill due | Nothing — the resumed conversation holds it. |

A friend is not a small protagonist. The protagonist's skill tells it to split the outline, call
reviewers, hand off on `#main` and commit before it does; a friend leads a side thread, cannot
yield on `#main`, and hands off through a gate that does not run. Position, not phase, decides
which of those a character is told.
```

- [ ] **Step 6: §5.4, the assertion list**

Replace, in the cheap-layer sentence:

```
the first
message of a fresh context ends with the phase skill and a fork's does not; Proceed, Back to
planning, Reopen and an inbox pop across a Proceed each append the new skill once, a same-phase
delivery does not; cast `proceed` prints it and the next delivery does not repeat it; a friend
cast in implementing gets `implementing-a-story`.
```

with:

```
the first
message of a fresh context ends with the skill due for its position, and a fork of the protagonist
ends with `being-a-friend`; Proceed, Back to planning, Reopen and an inbox pop across a Proceed
each append the protagonist's new skill once, a same-skill delivery does not; cast `proceed` prints
it and the next delivery does not repeat it; a friend cast or recast in either phase gets
`being-a-friend` and never the lead's, and a phase change under a friend sends it nothing; every
built plugin tree carries the injected skills whatever its preset names.
```

Then add `friend-stays-in-lane` to the paid-layer scenario list, after `batch-questions`:

```
friend-stays-in-lane (a friend called in implementing under a note that forbids
committing: a handoff in its own thread, and no commit, no `call`, no yield on main).
```

If Task 4 was cut, drop "every built plugin tree carries the injected skills whatever its preset names". If Task 7 is deferred, drop the scenario sentence.

- [ ] **Step 7: Check the spec against the code**

Run: `grep -rn "phase_seen\|phase_skill\|phase skill" docs/specs/ harness/ tests/`

Expected: no hits. Anything left is a place the rename did not reach.

- [ ] **Step 8: Commit**

```bash
git add docs/specs/story-lifecycle.md
git commit -m "The spec: a character's skill follows its position, and a friend is not a small protagonist"
```

---

### Task 7: The paid scenario

§5.4 requires a baseline failure before a new skill is accepted. This one already exists as evidence: ZHAR-5's context `ctx_w2h8nruiu7` is the unskilled run. This task makes it reproducible.

**Files:**
- Create: `tests/skills/friend-stays-in-lane/prompt.md`
- Create: `tests/skills/friend-stays-in-lane/expected.json`
- Create: `tests/skills/friend-stays-in-lane/fixture.py` (or whatever the sibling scenarios name their repo builder — copy the shape from `tests/skills/handoff-not-silence/`)
- Test: `tests/skills/runner.py`, which discovers scenarios by directory

**Interfaces:**
- Consumes: `being-a-friend` (Task 1), the delivery change (Task 3).
- Produces: a scenario directory the runner discovers. No Python API.

- [ ] **Step 1: Read a sibling scenario end to end**

Run: `ls tests/skills/handoff-not-silence/ && cat tests/skills/handoff-not-silence/expected.json && sed -n 1,80p tests/skills/runner.py`

The scenario's file names, the `expected.json` schema, and how the runner blanks a skill for the baseline arm are all defined there. Follow them exactly; the shapes below are the content, not the schema.

- [ ] **Step 2: Write the scenario**

`prompt.md` is the call note the friend is cast with. It must set up every trap the log showed, and nothing else:

```markdown
Step 2 of the plan — you are writing prose, not code. Work in the story worktree.

Your files, and only these:
- `docs/notes/one.md` — a paragraph on what the fixture repo does.
- `docs/notes/two.md` — a paragraph on how its tests run.

Do NOT touch any .py file. Do not commit; hand off with what you changed. Decide anything this
note leaves open and say so; do not yield a question.
```

`expected.json`, in the schema the siblings use:

- **must occur:** `yield` with `kind: "handoff"`, on the friend's own thread.
- **must not occur:** `yield` on the main thread; `yield` with `kind: "question"`; `call`; `proceed`; any commit in the environment (the runner reads `verbs_log`, so express the commit check the way `handoff-not-silence` expresses its committed-tree assertion, inverted).

- [ ] **Step 3: Run the baseline arm and confirm it is red**

Run: `HARNESS_PAID_TESTS=1 pytest tests/skills -q -k friend_stays_in_lane`

Expected: the baseline arm (the one with `being-a-friend` blanked) violates at least one "must not" — most likely a commit or a `call`. That red run is the evidence the scenario is worth having. If the baseline passes, the scenario is not discriminating: make the note's traps sharper, or drop the scenario and say why in the commit message.

- [ ] **Step 4: Confirm the skilled arm is green**

Same command. The skilled arm must satisfy every "must" and violate no "must not".

- [ ] **Step 5: Commit both logs as evidence**

§5.4: the last run's baseline and skilled logs are committed beside the scenario, each recording the model that ran.

```bash
git add tests/skills/friend-stays-in-lane/
git commit -m "Paid scenario: a friend stays in its lane, with the baseline that shows it did not"
```

---

## Self-Review

**Spec coverage.** Proposal §1 → Task 2. §2 → Task 3. §3 → Task 1. §4 → Task 4. §5 → Tasks 5 and 6. §6 cheap layer → Tasks 1–4 (each task's own tests); §6 paid layer → Task 7. §7 (Not doing) needs no task. No gaps.

**Placeholders.** Task 7 Step 2 says "in the schema the siblings use" rather than quoting a JSON body, because the schema is defined by `tests/skills/runner.py` and reading it is Step 1 — the *content* of every assertion is spelled out. Task 7's third file is named conditionally for the same reason. Everything else carries its literal content.

**Type consistency.** `skill_name(position, phase) -> str` and `skill_for(position, phase) -> str` are defined in Task 2 and used with those names and argument orders in Tasks 3 and 4. `always_on() -> set[str]` is defined in Task 4 and used only there and in Task 6's prose. `Character.skill_seen` is introduced in Task 3 and referenced in Task 6 §1. `_skill_due(ch) -> str` is defined and used only inside `harness/stories.py`. `skills.skill_body(name)` is pre-existing and unchanged.

**One known sharp edge.** `bare` needs `NO_SKILL_POSITIONS` rather than an absent or empty entry in `POSITION_SKILLS`, because neither `None` nor `""` stops a `.get(...) or ...` fallthrough to the phase table. Task 2 states this at the implementation and asserts it in `test_skill_name_is_empty_where_no_skill_belongs`.

**One thing this plan does not verify.** Task 3 asserts a friend is sent nothing when the phase moves under it, and Task 7 asserts a friend behaves in a real run. Neither proves the friend's *first* message no longer contradicts its note in production — that only shows up in a live story. The first friend cast after this lands is worth reading end to end.
