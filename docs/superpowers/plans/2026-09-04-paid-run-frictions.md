# Paid-run frictions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Question yields become a JSON document with one record per question; `wait` rejects only the go-quiet case; the main thread is `#main` wherever the harness speaks; an implementing handoff on main refuses a dirty tree.

**Architecture:** The lifecycle reducer owns the new `questions`/`answers` shapes and the `main` thread name. The store renders them to characters (brief, delivery) and the story view renders them to the human (rows of buttons, one Reply). The CLI reads the document from stdin and runs the tree gate beside the checks gate, inside the character's turn. The paid runner's assertions follow the new shapes and the two affected scenarios re-run for evidence.

**Tech Stack:** Python 3.12, PySide6/QML, pytest (`~/.venvs/mh-conda/bin/python -m pytest`), the zharn CLI over its local IPC.

**Spec:** `docs/superpowers/proposals/2026-09-04-paid-run-frictions.md` (then `docs/specs/story-lifecycle.md` §2.2, §4, §5 and `docs/specs/workspace-model.md` §4.6 once Task 7 rewrites them).

## Global Constraints

- No backward compatibility (DESIGN.md §0): `--options` and `Yield.options` are deleted, not aliased; tests are rewritten to the new shape.
- Specs describe the present tense; proposals and plans are not updated after they land.
- No explanatory copy in the UI; labels, placeholders and tooltips only.
- Tests: `~/.venvs/mh-conda/bin/python -m pytest -q` from the repo root; UI tests hot-reload on writes and `find()` wants exactly one visible item.
- Paid runs only under `HARNESS_PAID_TESTS=1 HARNESS_PAID_MODEL=claude-sonnet-5`; ~30 cents each; run one, check it, then the other.

---

## File structure

| File | Responsibility in this change |
|---|---|
| `harness/lifecycle.py` | `Yield.questions` (validated), `Comment.answers`/`Reply.answers` → `structured.answers`, `thread_label()`, `_require_thread` resolves `main`, `question_lines()` |
| `harness/stories.py` | `cast_yield(questions=)`, `render_brief` and `_format` print numbered question lines and `#main`, situation/owes/awaits labels, `cast_wait` guard, `answer()` slot for the story view, `env_checks` lists every environment |
| `harness/ipc.py` | `story.yield` forwards `questions` |
| `harness/cli.py` | `yield --question` reads stdin, `--body` only for handoffs, `dirty_trees()` and the tree gate, `run_checks` skips repos without `checks` |
| `harness/config_def.py` | the verb table in `CHARACTER_SYSTEM_PROMPT` |
| `harness/skills/skills/{being-a-character,planning-a-story,implementing-a-story}/SKILL.md` | the document shape; commit before the handoff |
| `qml/content/Story.qml` | one button row per question, picks per thread, Reply composes `answers` |
| `tests/fake_claude.py`, `tests/test_*.py`, `tests/skills/*` | rewritten to the new shapes; `committed` assertion |
| `docs/specs/story-lifecycle.md`, `docs/specs/workspace-model.md`, `README.md`, `docs/DESIGN.md` | present-tense description |

---

### Task 1: Lifecycle — questions, answers, `main`

**Files:**
- Modify: `harness/lifecycle.py:135-145` (Yield), `:83-86` (Reply), Comment dataclass, `_require_thread` (`:180`), Yield/Reply/Comment steps (`:236-283`)
- Test: `tests/test_lifecycle.py`

**Interfaces:**
- Produces: `Yield(thread_id, by, kind, body, questions: list[dict] = [], open_substories, checks, auto_for)`; `Comment(thread_id, by, body, answers: list[str] = [])`; `Reply(thread_id, body, by, answers: list[str] = [])`; `thread_label(story, thread_id) -> str` ("main" for the main thread, else the id); `question_lines(questions) -> list[str]` ("1. text (a, b; default a)"); `normalize_questions(raw) -> list[dict]` raising `Rejected` on a bad shape; `_require_thread(story, "main")` returns the main thread.

- [ ] **Step 1: Write the failing tests** (replace the existing `options` test at `tests/test_lifecycle.py:108-110` with these)

```python
def test_question_yield_carries_normalized_questions():
    s = started()  # whatever helper the file already uses to get a started story with thread t1 led by chr1
    qs = [{"text": "Format?", "options": ["toml", "json"], "default": "toml"}, {"text": "Anything else?"}]
    s, c = run(s, Yield("t1", "chr1", "question", "Three things.", questions=qs))
    assert c["structured"]["questions"] == [{"text": "Format?", "options": ["toml", "json"], "default": "toml"},
                                            {"text": "Anything else?", "options": []}]


@pytest.mark.parametrize("bad, msg", [
    ([], "at least one question"),
    ("nope", "a list"),
    ([{"options": ["a"]}], "text"),
    ([{"text": "", "options": ["a"]}], "text"),
    ([{"text": "q", "options": "a,b"}], "options"),
    ([{"text": "q", "options": ["a", ""]}], "options"),
    ([{"text": "q", "default": 3}], "default"),
])
def test_question_yield_rejects_a_bad_document(bad, msg):
    s = started()
    with pytest.raises(Rejected, match=msg):
        run(s, Yield("t1", "chr1", "question", "", questions=bad))


def test_handoff_yield_takes_no_questions():
    s = started()
    with pytest.raises(Rejected, match="handoff"):
        run(s, Yield("t1", "chr1", "handoff", "done", questions=[{"text": "q"}]))


def test_reply_carries_answers():
    s = started()
    s, q = run(s, Yield("t1", "chr1", "question", "", questions=[{"text": "a or b?", "options": ["a", "b"]}, {"text": "why?"}]))
    s, r = run(s, Comment("t1", "1. a\nbecause", by="human", answers=["a", ""]))
    assert r["reply_to"] == q["id"] and r["structured"]["answers"] == ["a", ""]
    s2, r2 = run(s, Yield("t1", "chr1", "question", "", questions=[{"text": "again?"}]))
    s2, r2 = run(s2, Comment("t1", "plain text", by="human"))
    assert "answers" not in r2["structured"]


def test_main_resolves_to_the_main_thread_and_labels():
    s = started()
    assert thread_label(s, "t1") == "main"
    s, c = run(s, Yield("main", "chr1", "question", "", questions=[{"text": "q"}]))
    assert c["thread_id"] == "t1"
    s, t2 = run(s, OpenThread("t2", "chr1", "chr2", "hi"))
    assert thread_label(s, "t2") == "t2"


def test_question_lines():
    assert question_lines([{"text": "Format?", "options": ["toml", "json"], "default": "toml"},
                           {"text": "Where?", "options": ["root", "user dir"]},
                           {"text": "Else?", "default": "no"},
                           {"text": "Free?"}]) == ["1. Format? (toml, json; default toml)", "2. Where? (root, user dir)",
                                                   "3. Else? (default no)", "4. Free?"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_lifecycle.py -q -k "question or answers or main_resolves or question_lines"`
Expected: FAIL (TypeError on `questions=`, ImportError on `thread_label`/`question_lines`)

- [ ] **Step 3: Implement**

In `harness/lifecycle.py`:

```python
@dataclass
class Reply:
    thread_id: str
    body: str
    by: str = "human"
    answers: list[str] = field(default_factory=list)   # by question index, "" where not picked


@dataclass
class Comment:            # (existing fields) + answers, forwarded when the comment is a reply
    ...
    answers: list[str] = field(default_factory=list)


@dataclass
class Yield:
    thread_id: str
    by: str
    kind: str
    body: str
    questions: list[dict] = field(default_factory=list)   # question yields: [{text, options?, default?}]
    open_substories: int = 0
    checks: list[dict] = field(default_factory=list)
    auto_for: str = ""


def normalize_questions(raw) -> list[dict]:
    """The question document's records, checked and filled: text (non-empty), options (a list, maybe empty),
    default (kept only when given)."""
    if not isinstance(raw, list):
        raise Rejected("questions must be a list of {text, options?, default?}")
    if not raw:
        raise Rejected("a question yield needs at least one question")
    out = []
    for i, q in enumerate(raw, 1):
        if not isinstance(q, dict) or not isinstance(q.get("text"), str) or not q["text"].strip():
            raise Rejected(f"question {i}: text must be a non-empty string")
        opts = q.get("options") or []
        if not isinstance(opts, list) or not all(isinstance(o, str) and o.strip() for o in opts):
            raise Rejected(f"question {i}: options must be a list of non-empty strings")
        rec = {"text": q["text"].strip(), "options": [o.strip() for o in opts]}
        if "default" in q and q["default"] is not None:
            if not isinstance(q["default"], str):
                raise Rejected(f"question {i}: default must be a string")
            rec["default"] = q["default"]
        out.append(rec)
    return out


def question_lines(questions: list[dict]) -> list[str]:
    """How a character reads a question yield: one numbered line per question."""
    lines = []
    for i, q in enumerate(questions, 1):
        notes = []
        if q.get("options"):
            notes.append(", ".join(q["options"]))
        if q.get("default"):
            notes.append(f"default {q['default']}")
        lines.append(f"{i}. {q['text']}" + (f" ({'; '.join(notes)})" if notes else ""))
    return lines


def thread_label(story: Story, thread_id: str) -> str:
    return "main" if thread_id == story.main_thread else thread_id


def _require_thread(story: Story, thread_id: str) -> Thread:
    if thread_id == "main":
        if story.main_thread is None:
            raise Rejected(f"{story.key} has not been started")
        thread_id = story.main_thread
    try:
        return story.thread(thread_id)
    except KeyError:
        raise Rejected(f"no thread {thread_id!r} on {story.key}") from None
```

In the `Yield` step replace the `options` block:

```python
        structured: dict = {}
        if action.kind == "question":
            structured["questions"] = normalize_questions(action.questions)
        elif action.questions:
            raise Rejected("a handoff carries no questions; use --body")
```

In the `Reply` step: `structured={"answers": list(action.answers)} if action.answers else None` on the `_comment` call. In the `Comment` step, forward: `Reply(thread_id=t.id, body=action.body, by=action.by, answers=action.answers)`.

- [ ] **Step 4: Run the lifecycle tests**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_lifecycle.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add harness/lifecycle.py tests/test_lifecycle.py
git commit -m "Lifecycle: question yields carry records, replies carry answers, the main thread is 'main'"
```

---

### Task 2: Store — rendering, `answer()`, the `wait` guard, `env_checks`

**Files:**
- Modify: `harness/stories.py:62-90` (render_brief), `:223-240` (situation, `_awaits_line`), `:372-381` (`_format`), `:741` (recast brief owes), `:800-822` (comment slot, cast_yield), `:893-904` (cast_wait), `:938-946` (env_checks)
- Test: `tests/test_stories.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `cast_yield(character_id, kind, body, questions=(), thread_id="", checks=())`; `answer(key, thread_id, answers, text) -> comment` (QML slot); `cast_wait` returns `{"awaits": [], "message": "you await nothing and owe nothing — end your turn; a reply will wake you"}` when nothing is owed; `env_checks` returns every environment (with `checks` possibly `""`).

- [ ] **Step 1: Rewrite the tests** in `tests/test_stories.py`

Every `cast_yield(..., options=[...])` becomes `cast_yield(..., questions=[{"text": ..., "options": [...]}])` (lines 131, 234-235, 485-490, 510). Then:

```python
def test_render_brief_prints_numbered_question_lines(store):
    key, chr_id = started(store, "note")
    store.cast_yield(chr_id, "question", "Two things.", questions=[{"text": "a or b?", "options": ["a", "b"], "default": "a"}, {"text": "why?"}])
    store.answer(key, "", ["a", ""], "because")
    text = render_brief(store.story(key), store.comments(key), {chr_id: store.character(chr_id)}, "the call-in note")
    assert "### #main —" in text
    assert "**protagonist** (question): Two things.\n  1. a or b? (a, b; default a)\n  2. why?\n" in text
    assert "**you** (text): 1. a\nbecause" in text


def test_answer_composes_the_reply_and_stores_answers(store, contexts):
    key, chr_id = started(store)
    q = store.cast_yield(chr_id, "question", "", questions=[{"text": "a or b?", "options": ["a", "b"]}, {"text": "c or d?", "options": ["c", "d"]}, {"text": "why?"}])
    r = store.answer(key, "", ["a", "", "d"], "  because  ")
    assert r["reply_to"] == q["id"] and r["body"] == "1. a\n3. d\nbecause" and r["structured"]["answers"] == ["a", "", "d"]
    assert store.get(key)["ball"] == "cast"
    with pytest.raises(Rejected, match="nothing to say"):
        store.cast_yield(chr_id, "question", "", questions=[{"text": "again?"}]); store.answer(key, "", [""], "  ")


def test_delivery_prints_question_lines_and_main(store, contexts):
    key, chr_id = started(store)
    ctx = contexts.get("ctx_1")
    store.cast_yield(chr_id, "question", "Pick.", questions=[{"text": "a or b?", "options": ["a", "b"]}])
    store.answer(key, "", ["b"], "")
    lines = ctx.sent[-1].splitlines()
    assert lines[0].startswith("[situation] phase planning · attending #main · you owe #main · you await nothing · ")
    assert lines[1] == "[you] reply in #main: 1. b"
    r = store.cast_call(chr_id, "claude-fast", "build it")
    friend = contexts.get(store.character(r["character"])["live_context"])
    store.cast_yield(chr_id, "question", "Pick.", questions=[{"text": "x?", "options": ["x", "y"]}], thread_id=r["thread"])
    # the friend's author is a character; the question lines reach it in the delivery
    assert f"[protagonist] question in #{r['thread']}: Pick.\n  1. x? (x, y)" in friend.sent[-1]


def test_thread_main_resolves_in_cast_verbs(store, contexts):
    key, chr_id = started(store)
    c = store.cast_yield(chr_id, "question", "", questions=[{"text": "q"}], thread_id="main")
    assert c["thread_id"] == store.get(key)["mainThread"]
    store.comment(key, "a")
    assert store.cast_recap(chr_id, "r", thread_id="main")["thread_id"] == store.get(key)["mainThread"]


def test_cast_wait_is_a_guard(store, contexts):
    key, chr_id = started(store)
    with pytest.raises(Rejected, match="you await nothing and owe #main — yield instead"):
        store.cast_wait(chr_id)
    store.cast_yield(chr_id, "question", "", questions=[{"text": "q"}])
    w = store.cast_wait(chr_id)          # owes nothing now: stopping is right, so the guard passes
    assert w["awaits"] == [] and "end your turn" in w["message"] and "a reply will wake you" in w["message"]
    store.comment(key, "a")
    r = store.cast_call(chr_id, "claude-fast", "build")
    w = store.cast_wait(chr_id)
    assert w["awaits"] == [{"thread": r["thread"], "lead": "claude-fast"}] and "end your turn" in w["message"]


def test_env_checks_lists_every_environment(store, ws, repo, contexts):
    # the `repo` fixture registers "client" with checks; register a second repo without any
    from tests.test_stories import make_repo  # or wherever make_repo lives in this file
    register_repo(ws, str(make_repo(ws.dir / "plain")), checks="")
    key, chr_id = started(store)
    store.cast_proceed(chr_id, "go")
    store.cast_env_open(chr_id, "client"); store.cast_env_open(chr_id, "plain")
    plan = store.env_checks(chr_id)
    assert plan["run"] and sorted(e["repo"] for e in plan["environments"]) == ["client", "plain"]
    assert {e["repo"]: e["checks"] for e in plan["environments"]} == {"client": "echo ok", "plain": ""}
```

Update the situation-line assertions that use `#{main}` (lines 361-362, 984 if it is main, 1144+) to `#main`; side-thread ids stay ids.

- [ ] **Step 2: Run to verify they fail**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_stories.py -q -x`
Expected: FAIL on the first rewritten test

- [ ] **Step 3: Implement** in `harness/stories.py`

```python
from .lifecycle import question_lines, thread_label   # beside the existing lifecycle imports

# render_brief: label and question lines
            label = lc.thread_label(story, t.id)
            ...
                out.append(f"- **{author_name(c['author'], characters)}** ({c['kind']}): {c['body']}")
                for line in question_lines(c.get("structured", {}).get("questions") or []):
                    out.append(f"  {line}")

# situation / awaits / recast brief
    def _label(self, key, tid): return lc.thread_label(self._stories[key], tid)
    def _awaits_line(self, ch):
        return ", ".join(("#" + a) if a.startswith("thr_") else a for a in self.awaits(ch)) or "nothing"   # a character never awaits its own main thread
    def situation(self, ch):
        s = self._stories[ch["story_key"]]
        owes = ", ".join("#" + lc.thread_label(s, t) for t in self.owes(ch)) or "nothing"
        attending = lc.thread_label(s, ch.get("attention") or s.main_thread)
        return (f"[situation] phase {s.phase} · attending #{attending} · you owe {owes} · " ...)
# line ~741 (the recast brief's "and owe" list) uses the same label

# _format
        s = self._stories[comment["story_key"]]
        where = f"#{lc.thread_label(s, comment['thread_id'])}" + (f" of {comment['story_key']}" if comment["story_key"] != ch["story_key"] else "")
        text = f"[{author_name(comment['author'], self._characters)}] {kind} in {where}: {comment['body']}"
        for line in question_lines(comment.get("structured", {}).get("questions") or []):
            text += f"\n  {line}"

# the story view's reply to a question
    @Slot(str, str, "QVariantList", str, result="QVariantMap")
    @intent
    def answer(self, key, thread_id, answers, text):
        """Spec §2.1 Reply from the story view: picks by question index, then the composer text, one comment."""
        key = self._key(key)
        s = self._stories[key]
        tid = thread_id or s.main_thread or ""
        picks = [str(a or "").strip() for a in answers]
        lines = [f"{i + 1}. {a}" for i, a in enumerate(picks) if a]
        if text.strip():
            lines.append(text.strip())
        if not lines:
            raise lc.Rejected("nothing to say: pick an option or write a reply")
        return self._author_action(key, lc.Comment(thread_id=tid, by=self._on_behalf(key), body="\n".join(lines),
                                                   answers=picks if any(picks) else []), resume=True)

# cast_yield
    def cast_yield(self, character_id, kind, body, questions=(), thread_id="", checks=()) -> dict:
        key, ch = self._char(character_id)
        s = self._stories[key]
        tid = thread_id or ch.get("attention") or s.main_thread
        if tid == "main": tid = s.main_thread
        open_subs = self._row(key)["openSubstories"] if tid == s.main_thread else 0
        c = self._apply(key, lc.Yield(thread_id=tid, by=character_id, kind=kind, body=body, questions=[dict(q) for q in questions],
                                      checks=[dict(c) for c in checks], open_substories=open_subs))

# cast_wait
        awaits = self.awaits(ch)
        if not awaits:
            owed = self.owes(ch)
            if owed:
                raise lc.Rejected(f"you await nothing and owe #{self._label(key, owed[0])} — yield instead")
            return {"awaits": [], "message": "you await nothing and owe nothing — end your turn; a reply will wake you"}

# env_checks: every environment, checks or not
        envs = self.cast_env_list(character_id) if run else []
```

`cast_recap` and `cast_comment` compute `tid` the same way; route `"main"` through `_require_thread` (it already does, since `_apply` → lifecycle) — only `cast_yield`'s `open_subs` comparison needs the explicit resolve above.

- [ ] **Step 4: Run the store tests**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_stories.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add harness/stories.py tests/test_stories.py
git commit -m "Store: question lines in the brief and deliveries, answer() from the story view, wait as a true guard, #main"
```

---

### Task 3: IPC forwards `questions`

**Files:**
- Modify: `harness/ipc.py:109-110`
- Test: `tests/test_ipc.py:106-107, 268-272, 462-463, 488-496`

- [ ] **Step 1: Rewrite the tests**: the fake stores' `cast_yield(self, ch, kind, body, questions, thread, checks=())` record `list(questions)`; `h("story.yield", {"character": "chr1", "kind": "question", "body": "q", "questions": [{"text": "q", "options": ["a", "b"]}]})` and the expected call tuples carry that list; `test_story_call_wait_inbox_cast_forward_and_log` keeps its `story.wait` reply as whatever the fake returns.

- [ ] **Step 2: Run**: `~/.venvs/mh-conda/bin/python -m pytest tests/test_ipc.py -q -k yield` → FAIL

- [ ] **Step 3: Implement**

```python
        if verb == "yield":
            return stories.cast_yield(ch, a["kind"], a.get("body", ""), a.get("questions") or [], a.get("thread", ""), a.get("checks") or [])
```

- [ ] **Step 4: Run**: `~/.venvs/mh-conda/bin/python -m pytest tests/test_ipc.py -q` → PASS

- [ ] **Step 5: Commit**: `git commit -am "IPC: story.yield forwards questions"`

---

### Task 4: CLI — the document on stdin, the tree gate

**Files:**
- Modify: `harness/cli.py:88-110` (run_checks), `:141-143` (parser), `:231-246` (yield)
- Test: `tests/test_cli.py:310-320, 495-522`

**Interfaces:**
- Produces: `dirty_trees(envs) -> list[{"repo", "path", "status"}]`; `story yield --question [--thread t]` with the document on stdin; `story yield --handoff --body … [--despite-checks] [--thread t]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_story_yield_question_reads_a_document_from_stdin(recorder, monkeypatch, capsys):
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr1")
    recorder.replies["story.yield"] = {"id": "c1", "kind": "question"}
    doc = {"body": "Two things.", "questions": [{"text": "a or b?", "options": ["a", "b"], "default": "a"}, {"text": "why?"}]}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(doc)))
    cli.main(["story", "yield", "--question", "--thread", "main"])
    assert recorder.calls == [("story.yield", {"character": "chr1", "kind": "question", "body": "Two things.",
                                               "questions": doc["questions"], "thread": "main", "checks": []})]


def test_story_yield_question_refuses_body_and_bad_json(recorder, monkeypatch):
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr1")
    with pytest.raises(SystemExit, match="--body belongs to --handoff"):
        cli.main(["story", "yield", "--question", "--body", "which?"])
    monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))
    with pytest.raises(SystemExit, match="not JSON"):
        cli.main(["story", "yield", "--question"])
    monkeypatch.setattr("sys.stdin", io.StringIO("[]"))
    with pytest.raises(SystemExit, match="JSON object"):
        cli.main(["story", "yield", "--question"])
    with pytest.raises(SystemExit, match="handoff needs --body"):
        cli.main(["story", "yield", "--handoff"])
    assert recorder.calls == []


def test_dirty_trees_reports_status_per_repo(tmp_path):
    clean, dirty = make_git_repo(tmp_path / "clean"), make_git_repo(tmp_path / "dirty")   # a helper: git init + one commit
    (dirty / "new.py").write_text("x")
    assert cli.dirty_trees([{"repo": "a", "path": str(clean)}, {"repo": "b", "path": str(dirty)}]) == [{"repo": "b", "path": str(dirty), "status": "?? new.py"}]
    assert cli.dirty_trees([{"repo": "c", "path": str(tmp_path / "missing")}]) == []


def test_handoff_refuses_a_dirty_tree_before_running_checks(fake_ipc, tmp_path, capsys):
    repo = make_git_repo(tmp_path / "api"); (repo / "hello.py").write_text("changed")
    st = fake_ipc({"run": True, "policy": "gate", "limit": 100, "timeout": 30,
                   "environments": [{"repo": "api", "checks": "false", "path": str(repo)}]})
    with pytest.raises(SystemExit) as e:
        cli.main(["story", "yield", "--handoff", "--body", "done", "--despite-checks"])
    assert "handoff refused: uncommitted changes in api" in str(e.value) and "commit them and retry" in str(e.value)
    assert "?? hello.py" in capsys.readouterr().err
    assert [r["cmd"] for r in st["received"]] == ["env.checks"]     # checks never ran, nothing posted


def test_handoff_skips_repos_without_checks(fake_ipc, tmp_path):
    repo = make_git_repo(tmp_path / "plain")
    st = fake_ipc({"run": True, "policy": "gate", "limit": 100, "timeout": 30,
                   "environments": [{"repo": "plain", "checks": "", "path": str(repo)}]}, {"id": "c1"})
    cli.main(["story", "yield", "--handoff", "--body", "done"])
    assert [r["args"]["checks"] for r in st["received"] if r["cmd"] == "story.yield"] == [[]]
```

Update `test_story_yield_uses_character_from_env` to the new shape (question via stdin) and the existing gate tests' environments to point at a committed `make_git_repo(tmp_path)` so the tree gate passes them.

- [ ] **Step 2: Run**: `~/.venvs/mh-conda/bin/python -m pytest tests/test_cli.py -q -k "yield or dirty or handoff"` → FAIL

- [ ] **Step 3: Implement** in `harness/cli.py`

```python
def dirty_trees(envs: list[dict]) -> list[dict]:
    """Workspace spec §4.6: environments with uncommitted work — `git status --porcelain` per environment."""
    out = []
    for e in envs:
        if not os.path.isdir(e["path"]):
            continue
        r = subprocess.run(["git", "status", "--porcelain"], cwd=e["path"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            out.append({"repo": e["repo"], "path": e["path"], "status": r.stdout.strip()})
    return out


def run_checks(envs, limit, timeout):
    results = []
    for e in envs:
        if not e.get("checks"):
            continue
        ...  # unchanged body

# parser
    y = stp.add_parser("yield", help="--question reads a JSON document {body?, questions: [{text, options?, default?}]} from stdin")
    y.add_argument("--question", action="store_true"); y.add_argument("--handoff", action="store_true")
    y.add_argument("--body", default=""); y.add_argument("--thread", default="")
    y.add_argument("--despite-checks", action="store_true", help="post a handoff even though checks failed")

# handler
        elif a.verb == "yield":
            if a.question == a.handoff:
                sys.exit("yield needs exactly one of --question / --handoff")
            if a.question:
                if a.body:
                    sys.exit("a question is a JSON document on stdin; --body belongs to --handoff")
                try:
                    doc = json.loads(sys.stdin.read())
                except ValueError as e:
                    sys.exit(f"the question document is not JSON: {e}")
                if not isinstance(doc, dict):
                    sys.exit('the question document must be a JSON object: {"body": "...", "questions": [...]}')
                out(request("story.yield", {"character": character(), "kind": "question", "body": str(doc.get("body") or ""),
                                            "questions": doc.get("questions"), "thread": a.thread, "checks": []}), a.json)
            else:
                if not a.body:
                    sys.exit("a handoff needs --body")
                plan = request("env.checks", {"character": character(), "thread": a.thread})
                dirty = dirty_trees(plan["environments"]) if plan["run"] else []
                if dirty:
                    for d in dirty:
                        print(f"[{d['repo']}] {d['path']}\n{d['status']}", file=sys.stderr)
                    sys.exit("handoff refused: uncommitted changes in " + ", ".join(d["repo"] for d in dirty) + " — commit them and retry")
                checks = run_checks(plan["environments"], plan["limit"], plan["timeout"])
                ...  # the existing gate
                out(request("story.yield", {"character": character(), "kind": "handoff", "body": a.body,
                                            "questions": [], "thread": a.thread, "checks": checks}), a.json)
```

- [ ] **Step 4: Run**: `~/.venvs/mh-conda/bin/python -m pytest tests/test_cli.py -q` → PASS

- [ ] **Step 5: Commit**: `git add harness/cli.py tests/test_cli.py && git commit -m "CLI: a question yield is a document on stdin; a handoff refuses a dirty tree"`

---

### Task 5: The fake claude and the end-to-end test

**Files:**
- Modify: `tests/fake_claude.py:63-66`, `tests/test_agents.py:171`

- [ ] **Step 1: Update the test**: `q["structured"]["questions"] == [{"text": "which one?", "options": ["a", "b"]}]`.
- [ ] **Step 2: Run**: `~/.venvs/mh-conda/bin/python -m pytest tests/test_agents.py -q -k yield` → FAIL
- [ ] **Step 3: Implement**

```python
        elif "yield-question" in prompt:
            cli = os.environ["HARNESS_CLI"].split() + ["story", "yield", "--question"]
            doc = json.dumps({"body": "", "questions": [{"text": "which one?", "options": ["a", "b"]}]})
            r = subprocess.run(cli, input=doc, capture_output=True, text=True, env=os.environ)
```

- [ ] **Step 4: Run**: `~/.venvs/mh-conda/bin/python -m pytest tests/test_agents.py -q` → PASS
- [ ] **Step 5: Commit**: `git commit -am "Tests: the fake claude writes a question document"`

---

### Task 6: The story view — rows per question, one Reply

**Files:**
- Modify: `qml/content/Story.qml:61-64` (pickedOption → answersTo), `:256-262` (thread props), `:304-307`, `:370-379` (choices), `:427-437` (composer)
- Test: `tests/test_ui_story.py:72-87`

- [ ] **Step 1: Rewrite the UI test**

```python
def test_question_yield_renders_rows_and_reply_posts_the_picks(ui):
    key = ui.store.stories.create("Q", "")
    ui.store.stories.start(key, "yield-question", "protagonist")     # the fake protagonist asks one question (a, b)
    open_story(ui, key)
    assert wait_until(lambda: any(r["kind"] == "question" for r in ui.store.stories.comments(key)))
    c = next(r for r in ui.store.stories.comments(key) if r["kind"] == "question")
    QTest.qWait(80)
    assert ui.visible(ui.find("needsYouBanner")) and "question" in ui.find("needsYouBanner").property("text")
    assert ui.find(f"questionRow_{c['id']}_0").property("text").startswith("1. which one?")
    assert not ui.find("replyButton").property("enabled")
    ui.click(ui.find(f"optionButton_{c['id']}_0_1"))
    assert ui.store.stories.get(key)["ball"] == "author"              # a pick alone posts nothing
    assert ui.find("replyButton").property("enabled")
    ui.focus_and_type(ui.find("replyInput"), "and quickly")
    ui.click(ui.find("replyButton"))
    assert ui.store.stories.get(key)["ball"] == "cast"
    last = ui.store.stories.comments(key)[-1]
    assert last["body"] == "1. b\nand quickly" and last["reply_to"] == c["id"] and last["structured"]["answers"] == ["b"]
    assert ui.find(f"optionButton_{c['id']}_0_1").property("icon_") == "check"     # the pick stays marked
    assert not ui.visible(ui.find("needsYouBanner"))
```

- [ ] **Step 2: Run**: `~/.venvs/mh-conda/bin/python -m pytest tests/test_ui_story.py -q -k question` → FAIL

- [ ] **Step 3: Implement** in `qml/content/Story.qml`

```qml
    // view: the reply that answered a question, and its picks
    function replyTo(c) { for (var i = 0; i < comments.length; i++) if (comments[i].reply_to === c.id) return comments[i]; return null }
    function answersTo(c) { var r = replyTo(c); return r && r.structured && r.structured.answers ? r.structured.answers : [] }

    // thread delegate (th): picks for the pending question, reset when the pending yield changes
    property var picks: []
    readonly property string pendingId: modelData.pendingYield || ""
    onPendingIdChanged: picks = []
    function pick(qi, option) { var p = picks.slice(); while (p.length <= qi) p.push(""); p[qi] = p[qi] === option ? "" : option; picks = p }
    readonly property bool anyPick: picks.some(function (x) { return !!x })

    // comment delegate (line)
    readonly property var questions: (modelData.structured && modelData.structured.questions) ? modelData.structured.questions : []
    readonly property var answered: questions.length ? view.answersTo(modelData) : []
    readonly property bool answerable: questions.length > 0 && pending && th.waitsOnYou

    // choices: one row per question, replacing the single Flow
    Repeater {
        model: line.questions
        delegate: ColumnLayout {
            id: qrow
            required property int index
            required property var modelData
            Layout.fillWidth: true; Layout.topMargin: 8; spacing: 4
            Text { objectName: "questionRow_" + line.modelData.id + "_" + qrow.index; Layout.fillWidth: true; wrapMode: Text.Wrap
                   text: (qrow.index + 1) + ". " + qrow.modelData.text + (qrow.modelData["default"] ? "  ·  default " + qrow.modelData["default"] : "")
                   color: app.theme.text; font.pixelSize: app.theme.fontSize }
            Flow {
                visible: qrow.modelData.options.length > 0; Layout.fillWidth: true; spacing: 6
                Repeater {
                    model: qrow.modelData.options
                    delegate: Btn {
                        required property int index
                        required property var modelData
                        objectName: "optionButton_" + line.modelData.id + "_" + qrow.index + "_" + index
                        small: true; text: modelData; enabled: line.answerable
                        icon_: (line.pending ? th.picks[qrow.index] : line.answered[qrow.index]) === modelData ? "check" : ""
                        onClicked: th.pick(qrow.index, modelData)
                    }
                }
            }
        }
    }

    // composer: Reply answers with the picks
    function post() {
        var body = text.trim()
        if (th.waitsOnYou && (th.anyPick || body.length)) { app.stories.answer(tabKey, th.modelData.isMain ? "" : th.modelData.id, th.picks, body); text = ""; th.picks = []; return }
        if (body.length) { app.stories.comment(tabKey, body, th.modelData.isMain ? "" : th.modelData.id); text = "" }
    }
    Btn { ... enabled: reply.text.trim().length > 0 || (th.waitsOnYou && th.anyPick); onClicked: reply.post() }
```

Delete `pickedOption`, `options`, `picked` and the old single `Flow`.

- [ ] **Step 4: Run**: `~/.venvs/mh-conda/bin/python -m pytest tests/test_ui_story.py -q` → PASS

- [ ] **Step 5: Commit**: `git add qml/content/Story.qml tests/test_ui_story.py && git commit -m "Story view: one row of options per question; Reply posts the picks as answers"`

---

### Task 7: The prompt, the skills, the specs

**Files:**
- Modify: `harness/config_def.py:129-146`, `harness/skills/skills/being-a-character/SKILL.md`, `.../planning-a-story/SKILL.md`, `.../implementing-a-story/SKILL.md`, `docs/specs/story-lifecycle.md` (§2.2 yield and wait rows, §2.3 last paragraph, §4 schema, §5.2, §5.3 situation line, §5.4 scenarios), `docs/specs/workspace-model.md` §4.6, `README.md:57`, `docs/DESIGN.md:285-296`
- Test: `tests/test_skills.py` or wherever the prompt/skill text is asserted (`grep -rn "options" tests/test_skills*.py tests/test_prompt*.py`)

- [ ] **Step 1: Verb table** in `CHARACTER_SYSTEM_PROMPT`:

```
  $HARNESS_CLI story yield --question [--thread t] <<'EOF'                          # ask the thread's author; only the thread's lead may
  {"body": "preamble", "questions": [{"text": "...", "options": ["a", "b"], "default": "a"}, {"text": "..."}]}
  EOF
  $HARNESS_CLI story yield --handoff --body "..." [--thread t]                    # hand off an outline, an answer, or finished work (main, implementing: commit first; the tree must be clean)
  ...
  $HARNESS_CLI story wait                                                        # what you await, or that stopping is safe; then END YOUR TURN
```

- [ ] **Step 2: Skills**. `being-a-character` law 6: "A yield ends your turn: ask everything at once — one `yield --question` whose document holds every question, `options` where choices exist, `default` where you have one. A handoff carries evidence: what changed, how verified, where to look first." `planning-a-story` "Asking": "One `yield --question` carries every unknown as its own record: `text`, `options` for the ones with natural choices, `default` for yours. The author answers once." and the table's Outline row. `implementing-a-story`: step 6 becomes "Before the handoff: `zharn:verification-before-completion`, then commit in your environment. Run the repo's checks yourself first; a refused handoff is a wasted turn." The handoff section adds "The tree is clean: a handoff with uncommitted changes is refused, and there is no flag past it. The handoff names the commit." Rationalization row: `"I'll leave committing to the author"` / `Approve merges the branch; what isn't committed isn't in the story.` Checklist: `- [ ] Committed; the handoff names the commit`.

- [ ] **Step 3: Specs**, present tense. `story-lifecycle.md` §2.2 yield rows:

```
| `yield --question [--thread t]` — a JSON document on stdin: `{body?, questions: [{text, options?, default?}]}` | `t`'s lead (default `t` = attended thread) | thread has no pending yield; at least one question, each with non-empty `text`, `options` a list of strings, `default` a string | `question` comment, `structured.questions` normalized; thread turn → author |
| `yield --handoff --body … [--despite-checks] [--thread t]` | `t`'s lead | as above; main thread in `implementing`: no open sub-stories, every environment of the story has a clean tree (workspace spec §4.6; no flag past it), then each repo's `checks` run and attach | `handoff` comment; thread turn → author |
| `wait` | any | not (`awaits = ∅` and `owes ≠ ∅`) | A guard, not a block: prints what the caller awaits and "end your turn"; with nothing awaited and nothing owed, says so and that a reply will wake it. Rejected only when stopping would go quiet: "you await nothing and owe #t — yield instead". |
```

§2.3 last paragraph: "`yield --question` with `options` is the only way to ask." §4 schema: `structured: { questions?: [{text, options: [str], default?: str}], answers?: [str], check?, transition? }` and "`question.questions` render one numbered row each, buttons for its options; picks accumulate and Reply posts them as `answers` with the composer text." §5.2 law 6 text; §5.3 situation line: "the main thread is `#main`; `--thread main` resolves to it in every verb". §5.4: batch-questions "(planning with three unknowns: one yield whose document carries options)", handoff-not-silence "(implementing: a committed handoff with evidence, not a harness yield)". `workspace-model.md` §4.6 opens with a paragraph "The tree first": the status check, the refusal, no knob; `README.md:57` shows the heredoc; `DESIGN.md` item 4 gains a line naming the four changes and the date.

- [ ] **Step 4: Run the whole suite**: `~/.venvs/mh-conda/bin/python -m pytest -q` → PASS (fix any prompt-text assertions)

- [ ] **Step 5: Commit**: `git add -A && git commit -m "Prompt, skills, specs: the question document, the tree at handoff, wait as a guard, #main"`

---

### Task 8: The paid runner and the evidence

**Files:**
- Modify: `tests/skills/runner.py:79-84, 101-112, 160-165`, `tests/skills/test_scenarios.py:28-36`, `tests/skills/handoff-not-silence/expected.json`
- Evidence: `tests/skills/batch-questions/{baseline,skilled}.json`, `tests/skills/handoff-not-silence/{baseline,skilled}.json`

- [ ] **Step 1: Tests** in `test_scenarios.py`: `good`'s yield uses `questions=[{"text": "q", "options": ["a", "b"]}]`; `bad`'s uses `questions=[{"text": "q", "options": []}]`; add `"committed": True` to `exp`, `"committed": True` to `good` and `"committed": False` to `bad`, and assert `any("not committed" in x for x in out)`.

- [ ] **Step 2: Run**: `~/.venvs/mh-conda/bin/python -m pytest tests/skills -q` → FAIL

- [ ] **Step 3: Implement**

```python
    if expected.get("question_has_options"):
        for e in log:
            if e["verb"] == "yield" and e["ok"] and e["args"].get("kind") == "question" \
                    and not any(q.get("options") for q in (e["args"].get("questions") or [])):
                out.append("a question yield without options")
    if expected.get("committed") and not result["committed"]:
        out.append("the work was not committed: " + result["dirty"])


def _committed(store, key, repo: Path) -> bool:
    """Every environment of the story is clean and at least one commit past the fixture's HEAD."""
    base = git(repo, "rev-parse", "HEAD")
    envs = [Path(r["path"]) for r in store.stories.environments.records(key)]
    return bool(envs) and all(p.is_dir() and not git(p, "status", "--porcelain") and git(p, "log", "--oneline", f"{base}..HEAD") for p in envs)
```

and `"committed": _committed(store, key, repo)` in the result. `handoff-not-silence/expected.json` gains `"committed": true`.

- [ ] **Step 4: Run**: `~/.venvs/mh-conda/bin/python -m pytest tests/skills -q` → PASS; commit `Tests: the paid runner reads questions and asserts the commit`.

- [ ] **Step 5: Paid runs**, one at a time, with the app's Windows-side claude reachable as before:

```bash
HARNESS_PAID_TESTS=1 HARNESS_PAID_MODEL=claude-sonnet-5 ~/.venvs/mh-conda/bin/python -m pytest tests/skills/test_scenarios.py -q -k batch-questions -x
```

Check `tests/skills/batch-questions/skilled.json`: one `yield` with `questions` (three records, options on all three), `ok: true`, no rejected yield before it. Then the same for `-k handoff-not-silence`; check `committed` and that no handoff was refused for a dirty tree more than once. If Sonnet cannot write the document first try, stop and report before spending more.

- [ ] **Step 6: Commit the evidence**: `git add tests/skills && git commit -m "Skills: the paid run after the frictions — question documents and committed handoffs on Sonnet 5"`
