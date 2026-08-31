# Story Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the task/thread/preset model with the Story model's foundation — workspace storage, a pure lifecycle state machine, stories/characters/contexts/roles stores, `zharn story …` verbs, and a minimal board + story + context UI — so a human can create a story, Start it, watch the protagonist work, answer its yields, and Approve.

**Architecture:** `harness/workspace.py` (pure) owns the `.zharn/` layout and `workspace.toml`. `harness/lifecycle.py` (pure, no Qt) is `step(story, action) -> (story', comment)` over phases and per-thread turns. `harness/stories.py` (QObject) persists stories via the workspace, calls `step`, casts the protagonist as a **character** whose live **context** is spawned by `harness/contexts.py` (the renamed `threads.py`). QML is a projection of these stores, exactly as before.

**Tech Stack:** Python ≥3.10, PySide6 6.11 (QML), pytest, `tomllib`/`tomli`, `tests/fake_claude.py` as the agent.

**Spec:** `docs/AGENT-MODEL.md` (design), `docs/superpowers/specs/2026-08-28-story-lifecycle-design.md` (lifecycle mechanics — §1, §2, §3.1, §4, §7 apply here), `docs/superpowers/specs/2026-08-31-workspace-model-design.md` (§2, §5.1, §6 apply here). Read all three before starting any task.

## Global Constraints

- **No backward compatibility** (DESIGN.md §0): delete old modules, data and tests outright. No aliases (`Thread` for `Context`, `HARNESS_THREAD_ID`, `preset`), no `.harness/` migration.
- Vocabulary is the spec's: story/phase/ball, thread (comments), character, context (agent conversation), role, protagonist. `taskKey` → `storyKey`, `presetName` → `roleName`, `thr_` ids → `ctx_`.
- `Story.ball` is **derived** (main thread's turn while phase ∈ {planning, implementing}); never stored.
- **Nobody sets status.** No `setStatus`, no `status` verb, no phase setter anywhere.
- Every QML-facing mutation is an `@intent` (`harness/notify.py`); every interactive QML control has a stable `objectName`.
- Reloadable modules: never `@QmlElement`; new modules go into `harness/shell.py: RELOADABLE` in dependency order.
- Tests run with `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q` (there is no bare `python` on PATH in the WSL shell). Full suite must be green at the end of every task.
- Commit after every task; messages in the repo's existing style (`Component: what changed`), ending with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **Out of scope for this plan** (next plan — "characters and delivery"): friends (`call`), minions, sub-stories, `wait`, inbox/attention delivery beyond the main thread, per-thread auto-yield, recap/recast ladder, checks at handoff, `AskUserQuestion` interception, `harness/skills/`, repos/environments/worktrees, start screen, story move. `lifecycle.py` *does* already model non-main threads (`OpenThread`, `Yield` on any thread) because the state machine is cheap to complete now and expensive to retrofit; the store and UI only drive the main thread.

## File map

| File | Responsibility |
|---|---|
| `harness/workspace.py` (new) | `.zharn/` layout, `workspace.toml` read/write, key counter, repo registration records. Pure Python. |
| `harness/lifecycle.py` (new) | `Story`/`Thread` dataclasses, action dataclasses, `step()`, `Rejected`, `check_invariants()`. Pure Python. |
| `harness/roles.py` (renamed from `presets.py`) | `RoleStore`; `DEFAULT_ROLES` in config; `outline_first` field. |
| `harness/contexts.py` (renamed from `threads.py`) | `Context`, `ContextStore`: one agent conversation, owner, transcripts under `local/contexts/`. |
| `harness/stories.py` (new) | `StoryStore`: persists stories, applies `step`, casts the protagonist, renders the brief, exposes the board model. |
| `harness/config_def.py` | `DEFAULT_ROLES`, `DEFAULT_ROLE`, `CHARACTER_SYSTEM_PROMPT`, `BARE_CONTEXT_SYSTEM_PROMPT`. |
| `harness/ipc.py`, `harness/cli.py` | `story.*`, `context.*`, `role.*` commands; `verbs_log`. |
| `harness/__main__.py` | Opens the workspace (`HARNESS_WORKSPACE` or the checkout), wires stores. |
| `qml/content/StoryBoard.qml`, `Story.qml`, `Context.qml`, `Contexts.qml` | Board by phase; story page with Start / action bar / comments / composer / cast; context view; contexts list with New Context. |
| `tests/test_workspace.py`, `test_lifecycle.py`, `test_roles.py`, `test_contexts_unit.py`, `test_stories.py`, `test_ui_story.py`, `test_ui_context.py` | Per-layer tests; UI tests through `tests/ui.py`. |

---

### Task 1: Workspace storage

**Files:**
- Create: `harness/workspace.py`
- Modify: `pyproject.toml` (add `tomli` for Python < 3.11)
- Test: `tests/test_workspace.py`

**Interfaces:**
- Produces:
  ```python
  class Workspace:
      dir: Path; zharn_dir: Path; stories_dir: Path; local_dir: Path
      id: str; name: str; prefix: str; next: int; repos: list[dict]
      @staticmethod exists(dir: Path) -> bool
      @classmethod create(cls, dir: Path, name: str | None = None, prefix: str | None = None) -> "Workspace"
      @classmethod open(cls, dir: Path) -> "Workspace"            # raises FileNotFoundError if no .zharn/workspace.toml
      @classmethod open_or_create(cls, dir: Path) -> "Workspace"
      def save(self) -> None
      def next_key(self) -> str                                    # "ZHA-1", increments and saves
      def story_dir(self, key: str) -> Path                        # .zharn/stories/<key>/ (created)
      def story_keys(self) -> list[str]                            # sorted by number
      def add_repo(self, path: Path, name: str = "", checks: str = "", setup: str = "", base: str = "") -> dict
      def repo(self, name: str) -> dict | None
      def repo_path(self, repo: dict) -> Path                      # absolute
      def repo_status(self, name: str) -> str                      # "ok" | "missing" | "unknown"
  def default_prefix(name: str) -> str                             # "my-project" -> "MYPR", "zharn" -> "ZHAR", "" -> "WS"
  ```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workspace.py
"""Workspace: .zharn/ layout, workspace.toml, keys, repo records (workspace spec §2, §3.1, §5.1, §6)."""
import uuid

import pytest

from harness.workspace import Workspace, default_prefix


def test_default_prefix_from_folder_name():
    assert default_prefix("zharn") == "ZHAR"
    assert default_prefix("my-project") == "MYPR"
    assert default_prefix("ab") == "AB"
    assert default_prefix("") == "WS"
    assert default_prefix("---") == "WS"


def test_create_writes_toml_with_uuid_name_prefix_and_counter(tmp_path):
    ws = Workspace.create(tmp_path / "proj")
    toml = tmp_path / "proj" / ".zharn" / "workspace.toml"
    assert toml.exists()
    uuid.UUID(ws.id)  # valid uuid
    assert ws.name == "proj" and ws.prefix == "PROJ" and ws.next == 1 and ws.repos == []
    text = toml.read_text()
    assert f'id = "{ws.id}"' in text and 'prefix = "PROJ"' in text and "next = 1" in text


def test_create_with_explicit_name_and_prefix(tmp_path):
    ws = Workspace.create(tmp_path / "x", name="Scratch", prefix="scr")
    assert ws.name == "Scratch" and ws.prefix == "SCR"


def test_create_makes_local_dir_with_gitignore(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    assert ws.local_dir == tmp_path / "p" / ".zharn" / "local"
    assert ws.local_dir.is_dir()
    assert (tmp_path / "p" / ".zharn" / ".gitignore").read_text().strip() == "local/"


def test_create_twice_raises(tmp_path):
    Workspace.create(tmp_path / "p")
    with pytest.raises(FileExistsError):
        Workspace.create(tmp_path / "p")


def test_open_reads_what_create_wrote(tmp_path):
    a = Workspace.create(tmp_path / "p", prefix="ABC")
    b = Workspace.open(tmp_path / "p")
    assert (b.id, b.name, b.prefix, b.next) == (a.id, a.name, a.prefix, a.next)


def test_open_missing_raises_and_exists_reports(tmp_path):
    assert not Workspace.exists(tmp_path / "nope")
    with pytest.raises(FileNotFoundError):
        Workspace.open(tmp_path / "nope")
    Workspace.create(tmp_path / "p")
    assert Workspace.exists(tmp_path / "p")


def test_open_or_create_is_idempotent(tmp_path):
    a = Workspace.open_or_create(tmp_path / "p")
    b = Workspace.open_or_create(tmp_path / "p")
    assert a.id == b.id


def test_next_key_increments_and_persists(tmp_path):
    ws = Workspace.create(tmp_path / "p", prefix="ZH")
    assert ws.next_key() == "ZH-1"
    assert ws.next_key() == "ZH-2"
    assert Workspace.open(tmp_path / "p").next == 3


def test_story_dir_is_created_under_stories(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    d = ws.story_dir("PROJ-1")
    assert d == tmp_path / "p" / ".zharn" / "stories" / "PROJ-1" and d.is_dir()


def test_story_keys_sorted_numerically(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    for k in ("PROJ-10", "PROJ-2", "PROJ-1"):
        ws.story_dir(k)
    assert ws.story_keys() == ["PROJ-1", "PROJ-2", "PROJ-10"]


def test_add_repo_inside_workspace_is_stored_relative(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    (tmp_path / "p" / "client").mkdir()
    r = ws.add_repo(tmp_path / "p" / "client")
    assert r == {"name": "client", "path": "client", "checks": "", "setup": "", "base": ""}
    assert ws.repo_path(r) == tmp_path / "p" / "client"
    assert Workspace.open(tmp_path / "p").repos == [r]
    assert "[[repos]]" in (tmp_path / "p" / ".zharn" / "workspace.toml").read_text()


def test_add_repo_dot_registers_the_workspace_dir_itself(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    r = ws.add_repo(tmp_path / "p")
    assert r["path"] == "." and r["name"] == "p"
    assert ws.repo_path(r) == tmp_path / "p"


def test_add_repo_outside_workspace_is_stored_absolute(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    other = tmp_path / "elsewhere"
    other.mkdir()
    r = ws.add_repo(other, name="other", checks="pytest", base="main")
    assert r["path"] == str(other.resolve()) and r["checks"] == "pytest" and r["base"] == "main"


def test_add_repo_duplicate_name_raises(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    (tmp_path / "p" / "a").mkdir()
    ws.add_repo(tmp_path / "p" / "a")
    with pytest.raises(ValueError, match="already registered"):
        ws.add_repo(tmp_path / "p" / "a")


def test_repo_lookup_and_status(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    (tmp_path / "p" / "a").mkdir()
    ws.add_repo(tmp_path / "p" / "a")
    assert ws.repo("a")["path"] == "a"
    assert ws.repo("zzz") is None
    assert ws.repo_status("a") == "ok"
    assert ws.repo_status("zzz") == "unknown"
    (tmp_path / "p" / "a").rmdir()
    assert ws.repo_status("a") == "missing"


def test_toml_roundtrip_escapes_quotes_and_backslashes(tmp_path):
    ws = Workspace.create(tmp_path / "p", name='He said "hi" C:\\x')
    assert Workspace.open(tmp_path / "p").name == 'He said "hi" C:\\x'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_workspace.py -q`
Expected: `ModuleNotFoundError: No module named 'harness.workspace'`

- [ ] **Step 3: Add the TOML reader dependency**

In `pyproject.toml` change the dependency line to:

```toml
dependencies = ["PySide6-Essentials>=6.11", "tomli>=2; python_version < '3.11'"]
```

- [ ] **Step 4: Implement `harness/workspace.py`**

```python
"""Workspace: a directory with a `.zharn/` — one board, one story-key prefix, a set of repos
(docs/superpowers/specs/2026-08-31-workspace-model-design.md §2, §3.1, §5.1, §6). Pure Python."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

REPO_FIELDS = ("name", "path", "checks", "setup", "base")


def default_prefix(name: str) -> str:
    letters = re.sub(r"[^A-Za-z0-9]", "", name).upper()[:4]
    return letters or "WS"


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _dump_toml(data: dict) -> str:
    """Minimal writer for our flat schema: scalars first, then `[[repos]]` tables."""
    lines = []
    for k, v in data.items():
        if k == "repos":
            continue
        lines.append(f"{k} = {_toml_str(v) if isinstance(v, str) else v}")
    for repo in data.get("repos", []):
        lines.append("")
        lines.append("[[repos]]")
        for f in REPO_FIELDS:
            lines.append(f"{f} = {_toml_str(str(repo.get(f, '')))}")
    return "\n".join(lines) + "\n"


class Workspace:
    def __init__(self, dir: Path, data: dict):
        self.dir = Path(dir).resolve()
        self.zharn_dir = self.dir / ".zharn"
        self.stories_dir = self.zharn_dir / "stories"
        self.local_dir = self.zharn_dir / "local"
        self._data = data

    # ---------------------------------------------------------------- open / create
    @staticmethod
    def exists(dir: Path) -> bool:
        return (Path(dir) / ".zharn" / "workspace.toml").is_file()

    @classmethod
    def create(cls, dir: Path, name: str | None = None, prefix: str | None = None) -> "Workspace":
        dir = Path(dir).resolve()
        if cls.exists(dir):
            raise FileExistsError(f"{dir} is already a workspace")
        folder = dir.name
        data = {"id": str(uuid.uuid4()), "name": name or folder,
                "prefix": (prefix or default_prefix(folder)).upper(), "next": 1, "repos": []}
        ws = cls(dir, data)
        ws.stories_dir.mkdir(parents=True, exist_ok=True)
        ws.local_dir.mkdir(parents=True, exist_ok=True)
        (ws.zharn_dir / ".gitignore").write_text("local/\n")
        ws.save()
        return ws

    @classmethod
    def open(cls, dir: Path) -> "Workspace":
        path = Path(dir) / ".zharn" / "workspace.toml"
        if not path.is_file():
            raise FileNotFoundError(f"{dir} has no .zharn/workspace.toml")
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        data.setdefault("repos", [])
        ws = cls(dir, data)
        ws.stories_dir.mkdir(parents=True, exist_ok=True)
        ws.local_dir.mkdir(parents=True, exist_ok=True)
        return ws

    @classmethod
    def open_or_create(cls, dir: Path) -> "Workspace":
        return cls.open(dir) if cls.exists(dir) else cls.create(dir)

    def save(self) -> None:
        self.zharn_dir.mkdir(parents=True, exist_ok=True)
        (self.zharn_dir / "workspace.toml").write_text(_dump_toml(self._data), encoding="utf-8")

    # ---------------------------------------------------------------- identity
    @property
    def id(self) -> str: return self._data["id"]

    @property
    def name(self) -> str: return self._data["name"]

    @property
    def prefix(self) -> str: return self._data["prefix"]

    @property
    def next(self) -> int: return int(self._data["next"])

    @property
    def repos(self) -> list[dict]: return list(self._data["repos"])

    # ---------------------------------------------------------------- stories
    def next_key(self) -> str:
        key = f"{self.prefix}-{self.next}"
        self._data["next"] = self.next + 1
        self.save()
        return key

    def story_dir(self, key: str) -> Path:
        d = self.stories_dir / key
        d.mkdir(parents=True, exist_ok=True)
        return d

    def story_keys(self) -> list[str]:
        def num(k: str) -> int:
            try:
                return int(k.rsplit("-", 1)[1])
            except (IndexError, ValueError):
                return 0
        return sorted((p.name for p in self.stories_dir.iterdir() if p.is_dir()), key=num)

    # ---------------------------------------------------------------- repos
    def add_repo(self, path: Path, name: str = "", checks: str = "", setup: str = "", base: str = "") -> dict:
        path = Path(path).resolve()
        name = name or path.name
        if self.repo(name) is not None:
            raise ValueError(f"repo {name!r} is already registered")
        try:
            rel = path.relative_to(self.dir)
            stored = rel.as_posix() or "."
        except ValueError:
            stored = str(path)
        record = {"name": name, "path": stored, "checks": checks, "setup": setup, "base": base}
        self._data["repos"].append(record)
        self.save()
        return dict(record)

    def repo(self, name: str) -> dict | None:
        return next((dict(r) for r in self._data["repos"] if r["name"] == name), None)

    def repo_path(self, repo: dict) -> Path:
        p = Path(repo["path"])
        return p if p.is_absolute() else (self.dir / p).resolve()

    def repo_status(self, name: str) -> str:
        r = self.repo(name)
        if r is None:
            return "unknown"
        return "ok" if self.repo_path(r).is_dir() else "missing"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_workspace.py -q`
Expected: all pass. (`Path(".").relative_to` of the dir itself yields `Path(".")`, whose `as_posix()` is `"."` — the `or "."` guards the empty-string case on some Python versions.)

- [ ] **Step 6: Full suite, then commit**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q`
Expected: 266 + new tests pass.

```bash
git add harness/workspace.py tests/test_workspace.py pyproject.toml
git commit -m "Workspace: .zharn/ layout, workspace.toml, key counter, repo records

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Lifecycle state machine

**Files:**
- Create: `harness/lifecycle.py`
- Test: `tests/test_lifecycle.py`

**Interfaces:**
- Produces (all in `harness.lifecycle`):
  ```python
  PHASES = ("backlog", "todo", "planning", "implementing", "done", "canceled")
  ACTIVE = ("planning", "implementing"); TERMINAL = ("done", "canceled")
  class Rejected(Exception)
  @dataclass class Thread: id, author, lead, turn="cast", pending_yield=None
  @dataclass class Story: key, title, description="", priority="medium", phase="backlog", author="human",
                          protagonist=None, main_thread=None, parent_story=None, threads=[]
      .ball -> "cast" | "author" | None ; .main -> Thread | None ; .thread(id) -> Thread (KeyError)
      .to_dict() -> dict ; Story.from_dict(d) -> Story
  # actions (dataclasses):
  Start(thread_id, protagonist, note="", role="")
  Reply(thread_id, body, by="human")
  Proceed(by, note="")                     # by = story.author (from (planning, author)) or story.protagonist (from (planning, cast))
  Approve(note="", by="human"); BackToPlanning(note="", by="human"); Cancel(note="", by="human"); Reopen(note="", by="human")
  OpenThread(thread_id, author, lead, body)
  Yield(thread_id, by, kind, body, options=[], open_substories=0, checks=[])   # kind ∈ question | handoff
  Recap(by, body)
  Comment(thread_id, by, body)             # becomes a Reply when thread waits on `by`
  def step(story: Story, action, *, comment_id: str, now: float) -> tuple[Story, dict]   # never mutates `story`
  def check_invariants(story: Story) -> None   # raises AssertionError
  ```
- Comment dict shape (spec §4): `{id, story_key, thread_id, reply_to, author, kind, body, mentions, structured, attachments, created_at}`; `structured` may carry `options`, `checks`, `transition: {"from": [phase, ball], "to": [phase, ball]}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lifecycle.py
"""The pure state machine: every cell × every action of lifecycle spec §2, per-thread turns, rejections, §2.4 invariants."""
import copy
import itertools

import pytest

from harness.lifecycle import (ACTIVE, PHASES, TERMINAL, Approve, BackToPlanning, Cancel, Comment, OpenThread,
                               Proceed, Recap, Rejected, Reopen, Reply, Start, Story, Thread, Yield,
                               check_invariants, step)

_ids = itertools.count(1)


def cid() -> str:
    return f"c{next(_ids)}"


def run(story, action):
    """step + invariants, returning (story, comment)."""
    s2, c = step(story, action, comment_id=cid(), now=1000.0)
    check_invariants(s2)
    return s2, c


def fresh(phase="todo") -> Story:
    return Story(key="ZH-1", title="T", description="D", phase=phase)


def started() -> Story:
    s, _ = run(fresh(), Start(thread_id="t1", protagonist="chr1", note="go"))
    return s


def at(phase, ball):
    """A started story driven to the requested (phase, ball) cell."""
    s = started()  # (planning, cast)
    if phase == "planning" and ball == "author":
        s, _ = run(s, Yield("t1", "chr1", "handoff", "outline"))
    elif phase == "implementing":
        s, _ = run(s, Proceed(by="chr1"))
        if ball == "author":
            s, _ = run(s, Yield("t1", "chr1", "handoff", "done"))
    elif phase == "done":
        s = at("implementing", "author")
        s, _ = run(s, Approve())
    elif phase == "canceled":
        s, _ = run(s, Cancel())
    assert (s.phase, s.ball) == (phase, ball if phase in ACTIVE else None)
    return s


# ---------------------------------------------------------------- purity, ball, serialization

def test_step_does_not_mutate_input():
    s = fresh()
    before = copy.deepcopy(s)
    step(s, Start(thread_id="t1", protagonist="chr1"), comment_id="c", now=1.0)
    assert s == before


def test_ball_is_derived_from_main_turn_only_while_active():
    assert fresh("backlog").ball is None and fresh("todo").ball is None
    s = started()
    assert s.ball == "cast" and s.main.turn == "cast"
    s, _ = run(s, Yield("t1", "chr1", "question", "?"))
    assert s.ball == "author"
    assert at("done", None).ball is None and at("canceled", None).ball is None


def test_to_dict_roundtrip_has_no_ball_key():
    s = at("planning", "author")
    d = s.to_dict()
    assert "ball" not in d
    assert d["threads"][0] == {"id": "t1", "author": "human", "lead": "chr1", "turn": "author", "pending_yield": d["threads"][0]["pending_yield"]}
    assert Story.from_dict(d) == s


# ---------------------------------------------------------------- Start

@pytest.mark.parametrize("phase", ["backlog", "todo"])
def test_start_opens_main_thread_casts_protagonist_and_moves_to_planning(phase):
    s, c = run(fresh(phase), Start(thread_id="t1", protagonist="chr1", note="opening note", role="planner"))
    assert (s.phase, s.ball) == ("planning", "cast")
    assert s.protagonist == "chr1" and s.main_thread == "t1"
    assert s.main == Thread(id="t1", author="human", lead="chr1", turn="cast", pending_yield=None)
    assert c["kind"] == "text" and c["author"] == "human" and c["body"] == "opening note" and c["thread_id"] == "t1"
    assert c["reply_to"] is None and c["story_key"] == "ZH-1" and c["created_at"] == 1000.0 and c["id"].startswith("c")
    assert c["structured"]["transition"] == {"from": [phase, None], "to": ["planning", "cast"]}


def test_start_without_note_has_default_body():
    _, c = run(fresh(), Start(thread_id="t1", protagonist="chr1"))
    assert c["body"] == "Started."


@pytest.mark.parametrize("phase", ["planning", "implementing", "done", "canceled"])
def test_start_rejected_once_started(phase):
    s = at(phase, "cast" if phase in ACTIVE else None)
    with pytest.raises(Rejected, match="already started|terminal"):
        step(s, Start(thread_id="t9", protagonist="chr9"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- Yield

@pytest.mark.parametrize("kind", ["question", "handoff"])
def test_yield_on_main_flips_ball_to_author_and_records_transition(kind):
    s = started()
    s, c = run(s, Yield("t1", "chr1", kind, "body", options=["a", "b"]))
    assert s.ball == "author" and s.main.pending_yield == c["id"]
    assert c["kind"] == kind and c["author"] == "chr1" and c["structured"]["options"] == ["a", "b"]
    assert c["structured"]["transition"] == {"from": ["planning", "cast"], "to": ["planning", "author"]}


def test_yield_twice_in_same_thread_is_rejected():
    s, _ = run(started(), Yield("t1", "chr1", "question", "?"))
    with pytest.raises(Rejected, match="already waits"):
        step(s, Yield("t1", "chr1", "question", "again"), comment_id="x", now=1.0)


def test_only_protagonist_yields_on_main():
    with pytest.raises(Rejected, match="protagonist"):
        step(started(), Yield("t1", "chr2", "question", "?"), comment_id="x", now=1.0)


def test_yield_bad_kind_rejected():
    with pytest.raises(Rejected, match="kind"):
        step(started(), Yield("t1", "chr1", "status", "x"), comment_id="x", now=1.0)


def test_yield_unknown_thread_rejected():
    with pytest.raises(Rejected, match="thread"):
        step(started(), Yield("nope", "chr1", "question", "x"), comment_id="x", now=1.0)


def test_main_handoff_while_implementing_blocked_by_open_substories():
    s = at("implementing", "cast")
    with pytest.raises(Rejected, match="sub-stor"):
        step(s, Yield("t1", "chr1", "handoff", "done", open_substories=1), comment_id="x", now=1.0)
    s2, c = run(s, Yield("t1", "chr1", "question", "q", open_substories=1))  # questions are not blocked
    assert s2.ball == "author"


def test_implementing_handoff_carries_checks():
    s = at("implementing", "cast")
    checks = [{"repo": "r", "cmd": "pytest", "exit": 0, "output": "ok"}]
    _, c = run(s, Yield("t1", "chr1", "handoff", "done", checks=checks))
    assert c["structured"]["checks"] == checks


@pytest.mark.parametrize("phase", ["done", "canceled"])
def test_yield_on_terminal_story_rejected(phase):
    with pytest.raises(Rejected, match="terminal"):
        step(at(phase, None), Yield("t1", "chr1", "question", "?"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- Reply

@pytest.mark.parametrize("phase", ["planning", "implementing"])
def test_reply_on_main_answers_the_pending_yield_and_returns_ball(phase):
    s = at(phase, "author")
    pending = s.main.pending_yield
    s, c = run(s, Reply("t1", "here you go"))
    assert (s.phase, s.ball) == (phase, "cast") and s.main.pending_yield is None
    assert c["kind"] == "text" and c["author"] == "human" and c["reply_to"] == pending
    assert c["structured"]["transition"] == {"from": [phase, "author"], "to": [phase, "cast"]}


def test_reply_when_thread_not_waiting_is_rejected():
    with pytest.raises(Rejected, match="not waiting"):
        step(started(), Reply("t1", "x"), comment_id="x", now=1.0)


def test_reply_by_non_author_is_rejected():
    s = at("planning", "author")
    with pytest.raises(Rejected, match="author"):
        step(s, Reply("t1", "x", by="chr1"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- Proceed (both sides)

def test_author_proceed_from_planning_author_goes_to_implementing_cast():
    s = at("planning", "author")
    s, c = run(s, Proceed(by="human", note="looks good"))
    assert (s.phase, s.ball) == ("implementing", "cast") and s.main.pending_yield is None
    assert c["kind"] == "system" and c["author"] == "human" and "outline approved" in c["body"] and "looks good" in c["body"]
    assert c["structured"]["transition"] == {"from": ["planning", "author"], "to": ["implementing", "cast"]}


def test_protagonist_proceed_from_planning_cast_goes_to_implementing_cast():
    s, c = run(started(), Proceed(by="chr1"))
    assert (s.phase, s.ball) == ("implementing", "cast")
    assert c["kind"] == "system" and c["author"] == "chr1"
    assert c["structured"]["transition"] == {"from": ["planning", "cast"], "to": ["implementing", "cast"]}


def test_author_proceed_while_ball_with_cast_is_rejected():
    with pytest.raises(Rejected):
        step(started(), Proceed(by="human"), comment_id="x", now=1.0)


def test_protagonist_proceed_while_ball_with_author_is_rejected():
    with pytest.raises(Rejected):
        step(at("planning", "author"), Proceed(by="chr1"), comment_id="x", now=1.0)


def test_stranger_proceed_is_rejected():
    with pytest.raises(Rejected, match="protagonist|author"):
        step(started(), Proceed(by="chr9"), comment_id="x", now=1.0)


@pytest.mark.parametrize("phase,ball", [("implementing", "cast"), ("implementing", "author"), ("done", None), ("canceled", None), ("todo", None)])
def test_proceed_outside_planning_is_rejected(phase, ball):
    s = at(phase, ball) if phase != "todo" else fresh()
    with pytest.raises(Rejected):
        step(s, Proceed(by="human"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- Approve / Back to planning

def test_approve_from_implementing_author_goes_to_done():
    s = at("implementing", "author")
    s, c = run(s, Approve(note="ship it"))
    assert (s.phase, s.ball) == ("done", None) and s.main.pending_yield is None
    assert c["kind"] == "system" and "ship it" in c["body"]
    assert c["structured"]["transition"] == {"from": ["implementing", "author"], "to": ["done", None]}


def test_back_to_planning_from_implementing_author():
    s = at("implementing", "author")
    s, c = run(s, BackToPlanning(note="rethink"))
    assert (s.phase, s.ball) == ("planning", "cast")
    assert c["structured"]["transition"] == {"from": ["implementing", "author"], "to": ["planning", "cast"]}


@pytest.mark.parametrize("action", [Approve(), BackToPlanning()])
@pytest.mark.parametrize("phase,ball", [("planning", "cast"), ("planning", "author"), ("implementing", "cast"), ("done", None), ("canceled", None)])
def test_approve_and_back_rejected_outside_implementing_author(action, phase, ball):
    with pytest.raises(Rejected):
        step(at(phase, ball), action, comment_id="x", now=1.0)


def test_approve_by_non_author_rejected():
    with pytest.raises(Rejected, match="author"):
        step(at("implementing", "author"), Approve(by="chr1"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- Cancel / Reopen

@pytest.mark.parametrize("phase,ball", [("planning", "cast"), ("planning", "author"), ("implementing", "cast"), ("implementing", "author")])
def test_cancel_from_any_active_cell(phase, ball):
    s, c = run(at(phase, ball), Cancel(note="nah"))
    assert (s.phase, s.ball) == ("canceled", None)
    assert c["structured"]["transition"] == {"from": [phase, ball], "to": ["canceled", None]}


def test_cancel_unstarted_story():
    s, c = run(fresh("backlog"), Cancel())
    assert s.phase == "canceled" and s.main_thread is None
    assert c["thread_id"] is None


@pytest.mark.parametrize("phase", TERMINAL)
def test_cancel_terminal_rejected(phase):
    with pytest.raises(Rejected, match="terminal"):
        step(at(phase, None), Cancel(), comment_id="x", now=1.0)


@pytest.mark.parametrize("phase", TERMINAL)
def test_reopen_started_story_goes_to_implementing_cast(phase):
    s, c = run(at(phase, None), Reopen(note="one more thing"))
    assert (s.phase, s.ball) == ("implementing", "cast")
    assert "one more thing" in c["body"] and c["thread_id"] == "t1"
    assert c["structured"]["transition"] == {"from": [phase, None], "to": ["implementing", "cast"]}


def test_reopen_never_started_story_goes_back_to_todo():
    s, _ = run(fresh("backlog"), Cancel())
    s, c = run(s, Reopen(note="again"))
    assert s.phase == "todo" and s.protagonist is None
    assert c["structured"]["transition"] == {"from": ["canceled", None], "to": ["todo", None]}


@pytest.mark.parametrize("phase,ball", [("planning", "cast"), ("implementing", "author")])
def test_reopen_non_terminal_rejected(phase, ball):
    with pytest.raises(Rejected, match="terminal"):
        step(at(phase, ball), Reopen(note="x"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- Threads beyond main

def test_open_thread_creates_thread_with_author_and_lead_no_transition():
    s = started()
    s, c = run(s, OpenThread(thread_id="t2", author="human", lead="chr1", body="why X?"))
    assert s.thread("t2") == Thread(id="t2", author="human", lead="chr1", turn="cast", pending_yield=None)
    assert s.ball == "cast" and "transition" not in c["structured"]
    assert c["kind"] == "text" and c["thread_id"] == "t2" and c["reply_to"] is None


def test_open_thread_before_start_or_after_terminal_rejected():
    with pytest.raises(Rejected):
        step(fresh(), OpenThread(thread_id="t2", author="human", lead="chr1", body="x"), comment_id="x", now=1.0)
    with pytest.raises(Rejected):
        step(at("done", None), OpenThread(thread_id="t2", author="human", lead="chr1", body="x"), comment_id="x", now=1.0)


def test_open_thread_duplicate_id_rejected():
    with pytest.raises(Rejected, match="exists"):
        step(started(), OpenThread(thread_id="t1", author="human", lead="chr1", body="x"), comment_id="x", now=1.0)


def test_side_thread_yield_and_reply_never_touch_the_ball():
    s, _ = run(started(), OpenThread(thread_id="t2", author="human", lead="chr2", body="review?"))
    s, c = run(s, Yield("t2", "chr2", "handoff", "LGTM"))
    assert s.thread("t2").turn == "author" and s.ball == "cast" and "transition" not in c["structured"]
    s, c = run(s, Reply("t2", "thanks"))
    assert s.thread("t2").turn == "cast" and s.ball == "cast" and "transition" not in c["structured"]


def test_side_thread_yield_by_thread_author_rejected():
    s, _ = run(started(), OpenThread(thread_id="t2", author="chr1", lead="chr2", body="do it"))
    with pytest.raises(Rejected, match="author"):
        step(s, Yield("t2", "chr1", "handoff", "x"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- Comment / Recap

def test_comment_in_thread_waiting_on_commenter_is_a_reply():
    s = at("planning", "author")
    s, c = run(s, Comment("t1", "human", "answer"))
    assert s.ball == "cast" and c["reply_to"] is not None


def test_comment_otherwise_is_plain_text_with_no_transition():
    s = started()
    s2, c = run(s, Comment("t1", "human", "btw"))
    assert s2 == s and c["kind"] == "text" and c["reply_to"] is None and "transition" not in c["structured"]
    s3, c = run(s, Comment("t1", "chr1", "working on it"))
    assert s3 == s and c["author"] == "chr1"


def test_comment_unknown_thread_rejected():
    with pytest.raises(Rejected, match="thread"):
        step(started(), Comment("zz", "human", "x"), comment_id="x", now=1.0)


def test_recap_posts_on_main_without_state_change():
    s = at("implementing", "cast")
    s2, c = run(s, Recap(by="chr1", body="done: a; next: b"))
    assert s2 == s and c["kind"] == "recap" and c["thread_id"] == "t1" and c["author"] == "chr1"


def test_recap_before_start_rejected():
    with pytest.raises(Rejected, match="started"):
        step(fresh(), Recap(by="chr1", body="x"), comment_id="x", now=1.0)


# ---------------------------------------------------------------- invariants

def test_invariants_catch_turn_without_pending_yield():
    s = started()
    s.main.turn = "author"
    with pytest.raises(AssertionError):
        check_invariants(s)


def test_invariants_catch_pending_yield_without_turn():
    s = started()
    s.main.pending_yield = "c9"
    with pytest.raises(AssertionError):
        check_invariants(s)


def test_invariants_catch_active_phase_without_main_thread():
    s = fresh()
    s.phase = "planning"
    with pytest.raises(AssertionError):
        check_invariants(s)


def test_invariants_catch_bad_phase():
    s = fresh()
    s.phase = "in_progress"
    with pytest.raises(AssertionError):
        check_invariants(s)


def test_every_phase_transition_has_exactly_one_causing_comment():
    """Walk a full life; count transitions in comments == number of phase/ball changes."""
    s = fresh()
    log = []
    for a in [Start(thread_id="t1", protagonist="chr1"), Comment("t1", "chr1", "hi"),
              Yield("t1", "chr1", "question", "?"), Reply("t1", "a"), Yield("t1", "chr1", "handoff", "plan"),
              Proceed(by="human"), Recap(by="chr1", body="r"), Yield("t1", "chr1", "handoff", "built"),
              BackToPlanning(), Proceed(by="chr1"), Yield("t1", "chr1", "handoff", "built2"), Approve(), Reopen(note="x"), Cancel()]:
        before = (s.phase, s.ball)
        s, c = run(s, a)
        after = (s.phase, s.ball)
        log.append((before != after, "transition" in c["structured"]))
    assert all(changed == recorded for changed, recorded in log), log
    assert sum(1 for changed, _ in log if changed) == 12  # every action above except Comment and Recap
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_lifecycle.py -q`
Expected: `ModuleNotFoundError: No module named 'harness.lifecycle'`

- [ ] **Step 3: Implement `harness/lifecycle.py`**

```python
"""The story state machine — lifecycle spec §1, §2, §2.4. Pure: no Qt, no I/O, no ids minted here.

    step(story, action, comment_id=..., now=...) -> (story', comment)

`story` is never mutated. Rejections raise `Rejected(reason)`; the CLI prints the reason.
Nobody sets status: phase and turns change only as side effects of the actions below."""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field

PHASES = ("backlog", "todo", "planning", "implementing", "done", "canceled")
UNSTARTED = ("backlog", "todo")
ACTIVE = ("planning", "implementing")
TERMINAL = ("done", "canceled")
YIELD_KINDS = ("question", "handoff")


class Rejected(Exception):
    """The action is not allowed in this cell; str(e) is the reason."""


# ---------------------------------------------------------------- state

@dataclass
class Thread:
    id: str
    author: str                      # "human" | character id
    lead: str                        # character id
    turn: str = "cast"               # "cast" | "author"
    pending_yield: str | None = None  # comment id while turn == "author"


@dataclass
class Story:
    key: str
    title: str
    description: str = ""
    priority: str = "medium"
    phase: str = "backlog"
    author: str = "human"
    protagonist: str | None = None
    main_thread: str | None = None
    parent_story: str | None = None
    threads: list[Thread] = field(default_factory=list)

    @property
    def ball(self) -> str | None:
        m = self.main
        return m.turn if self.phase in ACTIVE and m is not None else None

    @property
    def main(self) -> Thread | None:
        return next((t for t in self.threads if t.id == self.main_thread), None) if self.main_thread else None

    def thread(self, thread_id: str) -> Thread:
        for t in self.threads:
            if t.id == thread_id:
                return t
        raise KeyError(thread_id)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Story":
        d = dict(d)
        d["threads"] = [Thread(**t) for t in d.get("threads", [])]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------- actions

@dataclass
class Start:
    thread_id: str
    protagonist: str
    note: str = ""
    role: str = ""


@dataclass
class Reply:
    thread_id: str
    body: str
    by: str = "human"


@dataclass
class Proceed:
    by: str
    note: str = ""


@dataclass
class Approve:
    note: str = ""
    by: str = "human"


@dataclass
class BackToPlanning:
    note: str = ""
    by: str = "human"


@dataclass
class Cancel:
    note: str = ""
    by: str = "human"


@dataclass
class Reopen:
    note: str = ""
    by: str = "human"


@dataclass
class OpenThread:
    thread_id: str
    author: str
    lead: str
    body: str


@dataclass
class Yield:
    thread_id: str
    by: str
    kind: str
    body: str
    options: list[str] = field(default_factory=list)
    open_substories: int = 0
    checks: list[dict] = field(default_factory=list)


@dataclass
class Recap:
    by: str
    body: str


@dataclass
class Comment:
    thread_id: str
    by: str
    body: str


# ---------------------------------------------------------------- helpers

def _comment(story: Story, comment_id: str, now: float, *, thread_id: str | None, author: str, kind: str,
             body: str, reply_to: str | None = None, structured: dict | None = None) -> dict:
    return {"id": comment_id, "story_key": story.key, "thread_id": thread_id, "reply_to": reply_to,
            "author": author, "kind": kind, "body": body, "mentions": [], "structured": structured or {},
            "attachments": [], "created_at": now}


def _cell(story: Story) -> list:
    return [story.phase, story.ball]


def _require_thread(story: Story, thread_id: str) -> Thread:
    try:
        return story.thread(thread_id)
    except KeyError:
        raise Rejected(f"no thread {thread_id!r} on {story.key}") from None


def _require_started_active(story: Story):
    if story.main_thread is None:
        raise Rejected(f"{story.key} has not been started")
    if story.phase in TERMINAL:
        raise Rejected(f"{story.key} is terminal ({story.phase})")


def _with_note(base: str, note: str) -> str:
    return f"{base} — {note}" if note else base


# ---------------------------------------------------------------- the machine

def step(story: Story, action, *, comment_id: str, now: float) -> tuple[Story, dict]:
    before = _cell(story)
    s = copy.deepcopy(story)

    if isinstance(action, Start):
        if s.phase in TERMINAL:
            raise Rejected(f"{s.key} is terminal ({s.phase}); Reopen it instead")
        if s.phase not in UNSTARTED:
            raise Rejected(f"{s.key} is already started ({s.phase})")
        s.threads.append(Thread(id=action.thread_id, author=s.author, lead=action.protagonist))
        s.main_thread, s.protagonist, s.phase = action.thread_id, action.protagonist, "planning"
        c = _comment(s, comment_id, now, thread_id=action.thread_id, author=s.author, kind="text",
                     body=action.note or "Started.")

    elif isinstance(action, OpenThread):
        _require_started_active(s)
        if any(t.id == action.thread_id for t in s.threads):
            raise Rejected(f"thread {action.thread_id!r} already exists")
        s.threads.append(Thread(id=action.thread_id, author=action.author, lead=action.lead))
        c = _comment(s, comment_id, now, thread_id=action.thread_id, author=action.author, kind="text", body=action.body)

    elif isinstance(action, Yield):
        if s.phase in TERMINAL:
            raise Rejected(f"{s.key} is terminal ({s.phase})")
        if action.kind not in YIELD_KINDS:
            raise Rejected(f"yield kind must be one of {YIELD_KINDS}, not {action.kind!r}")
        t = _require_thread(s, action.thread_id)
        if t.pending_yield is not None:
            raise Rejected(f"thread {t.id} already waits on its author")
        if t.id == s.main_thread and action.by != s.protagonist:
            raise Rejected("only the protagonist yields on the main thread")
        if action.by == t.author:
            raise Rejected("a thread's author cannot yield in it")
        if t.id == s.main_thread and s.phase == "implementing" and action.kind == "handoff" and action.open_substories:
            raise Rejected(f"{action.open_substories} sub-stor{'y is' if action.open_substories == 1 else 'ies are'} still open")
        t.turn, t.pending_yield = "author", comment_id
        structured: dict = {}
        if action.options:
            structured["options"] = list(action.options)
        if action.checks:
            structured["checks"] = list(action.checks)
        c = _comment(s, comment_id, now, thread_id=t.id, author=action.by, kind=action.kind, body=action.body,
                     structured=structured)

    elif isinstance(action, Reply):
        t = _require_thread(s, action.thread_id)
        if t.turn != "author":
            raise Rejected(f"thread {t.id} is not waiting on its author")
        if action.by != t.author:
            raise Rejected(f"only the thread's author ({t.author}) can reply here")
        pending, t.turn, t.pending_yield = t.pending_yield, "cast", None
        c = _comment(s, comment_id, now, thread_id=t.id, author=action.by, kind="text", body=action.body, reply_to=pending)

    elif isinstance(action, Comment):
        t = _require_thread(s, action.thread_id)
        if t.turn == "author" and action.by == t.author:
            return step(story, Reply(thread_id=t.id, body=action.body, by=action.by), comment_id=comment_id, now=now)
        c = _comment(s, comment_id, now, thread_id=t.id, author=action.by, kind="text", body=action.body)

    elif isinstance(action, Recap):
        if s.main_thread is None:
            raise Rejected(f"{s.key} has not been started")
        c = _comment(s, comment_id, now, thread_id=s.main_thread, author=action.by, kind="recap", body=action.body)

    elif isinstance(action, Proceed):
        if s.phase != "planning":
            raise Rejected(f"proceed is only allowed while planning ({s.key} is {s.phase})")
        m = s.main
        if action.by == s.author:
            if m.turn != "author":
                raise Rejected("the author can proceed only while the ball is theirs")
            body = _with_note("outline approved", action.note)
        elif action.by == s.protagonist:
            if m.turn != "cast":
                raise Rejected("the protagonist can proceed only while the ball is with the cast")
            body = _with_note("proceeding to implementing", action.note)
        else:
            raise Rejected("only the author or the protagonist can proceed")
        s.phase, m.turn, m.pending_yield = "implementing", "cast", None
        c = _comment(s, comment_id, now, thread_id=m.id, author=action.by, kind="system", body=body)

    elif isinstance(action, (Approve, BackToPlanning)):
        if action.by != s.author:
            raise Rejected(f"only the author ({s.author}) can do that")
        if (s.phase, s.ball) != ("implementing", "author"):
            raise Rejected(f"requires (implementing, author); {s.key} is ({s.phase}, {s.ball})")
        m = s.main
        m.turn, m.pending_yield = "cast", None
        if isinstance(action, Approve):
            s.phase, body = "done", _with_note("approved", action.note)
        else:
            s.phase, body = "planning", _with_note("back to planning", action.note)
        c = _comment(s, comment_id, now, thread_id=m.id, author=action.by, kind="system", body=body)

    elif isinstance(action, Cancel):
        if action.by != s.author:
            raise Rejected(f"only the author ({s.author}) can cancel")
        if s.phase in TERMINAL:
            raise Rejected(f"{s.key} is already terminal ({s.phase})")
        s.phase = "canceled"
        if s.main is not None:
            s.main.turn, s.main.pending_yield = "cast", None
        c = _comment(s, comment_id, now, thread_id=s.main_thread, author=action.by, kind="system",
                     body=_with_note("canceled", action.note))

    elif isinstance(action, Reopen):
        if action.by != s.author:
            raise Rejected(f"only the author ({s.author}) can reopen")
        if s.phase not in TERMINAL:
            raise Rejected(f"reopen requires a terminal story; {s.key} is {s.phase}")
        if s.main is None:
            s.phase = "todo"
            body = _with_note("reopened (never started) — back to todo", action.note)
        else:
            s.phase = "implementing"
            s.main.turn, s.main.pending_yield = "cast", None
            body = _with_note("reopened", action.note)
        c = _comment(s, comment_id, now, thread_id=s.main_thread, author=action.by, kind="system", body=body)

    else:
        raise Rejected(f"unknown action {type(action).__name__}")

    after = _cell(s)
    if after != before:
        c["structured"]["transition"] = {"from": before, "to": after}
    return s, c


# ---------------------------------------------------------------- invariants (§2.4)

def check_invariants(story: Story) -> None:
    assert story.phase in PHASES, f"bad phase {story.phase!r}"
    if story.phase in ACTIVE:
        assert story.main is not None and story.protagonist, "active story without main thread/protagonist"
    if story.main_thread is not None:
        assert story.main is not None, "main_thread points at no thread"
        assert story.main.lead == story.protagonist, "main thread lead must be the protagonist"
        assert story.main.author == story.author, "main thread author must be the story author"
    ids = [t.id for t in story.threads]
    assert len(ids) == len(set(ids)), "duplicate thread ids"
    for t in story.threads:
        assert t.turn in ("cast", "author"), f"bad turn {t.turn!r}"
        assert (t.turn == "author") == (t.pending_yield is not None), f"thread {t.id}: turn/pending_yield disagree"
        assert t.lead, f"thread {t.id} has no lead"
    if story.phase in ACTIVE:
        assert story.ball == story.main.turn
    else:
        assert story.ball is None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_lifecycle.py -q`
Expected: all pass.

- [ ] **Step 5: Full suite, then commit**

```bash
QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q
git add harness/lifecycle.py tests/test_lifecycle.py
git commit -m "Lifecycle: pure (phase, turn) state machine with every author/cast action and §2.4 invariants

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Rename presets → roles

A mechanical rename plus one new field. A **role** is what a character is cast from (spec §1, Appendix). No alias for the old name anywhere.

**Files:**
- Rename: `harness/presets.py` → `harness/roles.py`; `tests/test_presets.py` → `tests/test_roles.py`
- Modify: `harness/config_def.py`, `harness/shell.py:25-26`, `harness/threads.py`, `harness/tasks.py`, `harness/store.py`, `harness/__main__.py`, `harness/ipc.py`, `harness/cli.py`, `qml/content/TaskView.qml`, `tests/test_ipc.py`, `tests/test_cli.py`, `tests/test_agents.py`, `tests/test_ui_task.py`, `tests/test_threads_unit.py`, `tests/fake_claude.py`

**Interfaces:**
- Produces:
  ```python
  # harness/roles.py
  FIELDS = ("name", "provider", "model", "reasoning", "permission", "environment", "instructions", "outline_first")
  class RoleStore(QObject):
      rolesChanged = Signal()
      def __init__(self, data_dir: Path, parent=None)      # persists user roles to data_dir / "roles.json"
      roles: Property(QVariantList)                          # config DEFAULT_ROLES + user roles, user overrides by name
      def names(self) -> list[str]; def get(self, name) -> dict; def save(self, role: dict); def remove(self, name)
  # harness/config_def.py
  DEFAULT_ROLES = [...]        # same four entries as DEFAULT_PRESETS today, plus {"name": "protagonist", ..., "outline_first": True}
  DEFAULT_ROLE = "protagonist" # the role Start casts when none is chosen
  ```
- Thread meta keys `preset`/`presetConfig` become `role`/`roleConfig`; QML/IPC field `presetName` becomes `roleName`; IPC `preset.list` becomes `role.list`; CLI `preset list` becomes `role list`.

- [ ] **Step 1: Move the test file and rewrite it for roles**

`git mv tests/test_presets.py tests/test_roles.py`, then replace its contents:

```python
# tests/test_roles.py
"""RoleStore unit tests: config defaults, user overrides, persistence to roles.json, outline_first."""
import json

import pytest

from harness import config as cfg
from harness.roles import FIELDS, RoleStore

DEFAULT_NAMES = [r["name"] for r in cfg.DEFAULT_ROLES]


@pytest.fixture
def store(tmp_path):
    return RoleStore(tmp_path)


def read_json(tmp_path):
    return json.loads((tmp_path / "roles.json").read_text())


def test_defaults_come_from_config_in_order(store):
    assert store.names() == DEFAULT_NAMES


def test_every_role_has_all_fields(store):
    for r in store.roles:
        assert set(r) == set(FIELDS), r


def test_default_role_exists_and_is_outline_first(store):
    assert cfg.DEFAULT_ROLE in store.names()
    assert store.get(cfg.DEFAULT_ROLE)["outline_first"] is True


def test_fill_ins_for_missing_fields(store):
    r = store.get("claude-fast")
    assert r["environment"] == "project-default" and r["instructions"] == "" and r["outline_first"] is False
    assert r["provider"] == "claude-code" and r["reasoning"] == "medium" and r["permission"] == "auto"


def test_explicit_empty_values_in_config_are_kept(store):
    r = store.get("claude-default")
    assert r["model"] == "" and r["reasoning"] == ""


def test_no_roles_json_on_disk_until_something_is_saved(tmp_path, store):
    store.names()
    assert not (tmp_path / "roles.json").exists()


def test_get_is_case_insensitive_and_unknown_is_empty(store):
    assert store.get("CLAUDE-DEEP")["name"] == "claude-deep"
    assert store.get("nope") == {} and store.get("") == {}


def test_save_adds_user_role_persists_and_emits(tmp_path, store):
    emitted = []
    store.rolesChanged.connect(lambda: emitted.append(True))
    store.save({"name": "mine", "model": "m", "outline_first": True, "bogus": 1})
    assert store.names() == DEFAULT_NAMES + ["mine"]
    r = store.get("mine")
    assert r["outline_first"] is True and "bogus" not in r and r["provider"] == "claude-code"
    assert [x["name"] for x in read_json(tmp_path)] == ["mine"]
    assert emitted == [True]


def test_save_same_name_twice_replaces(store):
    store.save({"name": "mine", "model": "one"})
    store.save({"name": "MINE", "model": "two"})
    assert store.names().count("mine") + store.names().count("MINE") == 1
    assert store.get("mine")["model"] == "two"


def test_user_override_of_a_default_is_single_entry_in_place(store):
    store.save({"name": "claude-fast", "model": "custom"})
    assert store.names() == DEFAULT_NAMES
    assert store.get("claude-fast")["model"] == "custom"
    store.remove("claude-fast")
    assert store.get("claude-fast")["model"] == cfg.DEFAULT_ROLES[0]["model"]


def test_remove_drops_user_role_and_is_case_insensitive(tmp_path, store):
    store.save({"name": "mine"})
    store.remove("MINE")
    assert store.get("mine") == {} and read_json(tmp_path) == []
    store.remove("nope")
    assert store.names() == DEFAULT_NAMES


def test_fresh_store_sees_saved_roles_and_tolerates_corrupt_json(tmp_path):
    RoleStore(tmp_path).save({"name": "mine", "model": "m"})
    assert RoleStore(tmp_path).get("mine")["model"] == "m"
    (tmp_path / "roles.json").write_text("{not json")
    s = RoleStore(tmp_path)
    assert s.names() == DEFAULT_NAMES
    s.save({"name": "mine"})
    assert [r["name"] for r in read_json(tmp_path)] == ["mine"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_roles.py -q`
Expected: `ModuleNotFoundError: No module named 'harness.roles'`

- [ ] **Step 3: Create `harness/roles.py` and delete `presets.py`**

`git mv harness/presets.py harness/roles.py`, then replace its contents:

```python
"""Roles: what a character is cast from — provider, model, permission ceiling, instructions,
and whether it must get an outline approved before implementing (lifecycle spec §1, §7)."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from harness import config as cfg
from harness.notify import intent

FIELDS = ("name", "provider", "model", "reasoning", "permission", "environment", "instructions", "outline_first")
DEFAULTS = {"provider": "claude-code", "model": "", "reasoning": "medium", "permission": "auto",
            "environment": "project-default", "instructions": "", "outline_first": False}


class RoleStore(QObject):
    rolesChanged = Signal()
    notifier = None

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self._path = data_dir / "roles.json"
        self._user: list[dict] = []
        try:
            self._user = json.loads(self._path.read_text())
        except (OSError, ValueError):
            pass

    def _all(self) -> list[dict]:
        out, seen = [], set()
        for r in list(getattr(cfg, "DEFAULT_ROLES", [])) + self._user:
            full = {**DEFAULTS, **r}
            if full["name"] in seen:
                out = [x if x["name"] != full["name"] else full for x in out]  # user overrides default, in place
                continue
            seen.add(full["name"])
            out.append(full)
        return out

    @Property("QVariantList", notify=rolesChanged)
    def roles(self):
        return self._all()

    @Slot(result="QVariantList")
    def names(self):
        return [r["name"] for r in self._all()]

    @Slot(str, result="QVariantMap")
    def get(self, name):
        for r in self._all():
            if r["name"].lower() == (name or "").lower():
                return r
        return {}

    @Slot("QVariantMap")
    @intent
    def save(self, role):
        role = {k: role[k] for k in FIELDS if k in role}
        self._user = [r for r in self._user if r["name"].lower() != role["name"].lower()] + [role]
        self._persist()

    @Slot(str)
    @intent
    def remove(self, name):
        self._user = [r for r in self._user if r["name"].lower() != name.lower()]
        self._persist()

    def _persist(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._user, indent=1))
        self.rolesChanged.emit()
```

- [ ] **Step 4: Config**

In `harness/config_def.py` replace the `DEFAULT_PRESETS` block with:

```python
# Roles: what a character is cast from. `outline_first` = must get an outline approved before implementing.
DEFAULT_ROLES = [
    {"name": "protagonist", "provider": "claude-code", "model": "", "reasoning": "high", "permission": "auto", "outline_first": True,
     "instructions": "You lead this story: classify the work, ask the author what you must, outline when the work needs it, then build or delegate."},
    {"name": "claude-fast", "provider": "claude-code", "model": "claude-sonnet-5", "reasoning": "medium", "permission": "auto"},
    {"name": "claude-deep", "provider": "claude-code", "model": "claude-opus-5", "reasoning": "high", "permission": "auto"},
    {"name": "claude-default", "provider": "claude-code", "model": "", "reasoning": "", "permission": "auto"},
    {"name": "codex-review", "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "permission": "accept-edits"},
]
DEFAULT_ROLE = "protagonist"
```

Also update the example line in `harness/__main__.py: ensure_user_config` from `DEFAULT_PRESETS = DEFAULT_PRESETS + [...]` to `DEFAULT_ROLES = DEFAULT_ROLES + [...]`. Delete your local `harness/config.py` if it references `DEFAULT_PRESETS` (it is regenerated on next run).

- [ ] **Step 5: Rename every use**

Apply, file by file (use your editor's replace; then verify with grep):

| File | Change |
|---|---|
| `harness/shell.py:26` | `"harness.presets"` → `"harness.roles"` |
| `harness/threads.py` | `ThreadStore.__init__(self, root, data_dir, presets, …)` → `roles`; `self.presets` → `self.roles`; in `spawn`: `preset = self.presets.get(preset_name)` → `role = self.roles.get(role_name)`, error text `unknown role`, `provider` check on `role`; meta keys `"preset": role["name"], "roleConfig": role`; `Thread.presetName` → `roleName` reading `meta.get("role")`; `_system_prompt`/`_spawn`/`model` read `meta.get("roleConfig", {})`; `THREAD_ROLES` entry `"presetName"` → `"roleName"`; `summary()` key `"presetName"` → `"roleName"`; parameter names `preset_name` → `role_name` |
| `harness/tasks.py` | `dispatch(self, key, role_name, prompt, parent_id="")`; pass `role_name` to `self._threads.spawn`; docstring/prompt text "preset" → "role" |
| `harness/store.py` | ctor kwarg `presets=None` → `roles=None`; `self._presets` → `self._roles`; property `presets` → `roles` |
| `harness/__main__.py` | `from harness.roles import RoleStore`; `roles = RoleStore(data_dir)`; pass `roles` to `ThreadStore` and `AppStore(…, roles=roles, …)`; `HARNESS_SMOKE_PRESET` → `HARNESS_SMOKE_ROLE` (default `"claude-default"`) |
| `harness/ipc.py` | `presets` → `roles` in the unpack; `"preset.list"` → `"role.list"` returning `roles.roles`; `a["preset"]` → `a["role"]` in `thread.spawn` |
| `harness/cli.py` | subparser `preset` → `role` (`role list` → `request("role.list", {})`); `thread spawn --preset` → `--role`, sent as `"role"`; `out()` column list unchanged (`name`/`model` already there) |
| `qml/content/TaskView.qml` | `presetBox` → `roleBox` (id and objectName); `app.presets.names()` → `app.roles.names()`; `app.presets.get(…)` → `app.roles.get(…)`; delegate `required property string presetName` → `roleName` and its Label |
| `qml/content/AgentLog.qml` | `presetName` → `roleName` (property + Label) |
| `tests/test_ipc.py` | `FakePresets` → `FakeRoles` with attribute `roles`; `store.presets` → `store.roles`; `"preset.list"` → `"role.list"`; `"preset": "claude-fast"` → `"role": "claude-fast"` in spawn calls; `FakeThreads.spawn(self, task, role, …)` |
| `tests/test_cli.py` | `preset list` tests → `role list` / `role.list`; `--preset` → `--role` and dict key `"preset"` → `"role"` |
| `tests/test_agents.py` | `store.presets` → `store.roles`; `presetName` → `roleName`; `test_presets_and_demo_tasks` → `test_roles_and_demo_tasks` |
| `tests/test_ui_task.py` | `presetBox` → `roleBox` |
| `tests/test_threads_unit.py` | `from harness.roles import RoleStore`; `ThreadStore(ROOT, tmp_path, RoleStore(tmp_path))` |
| `tests/fake_claude.py` | the `spawn-child` branch: `"--preset"` → `"--role"` |
| `README.md` | `harness/config_def.py: DEFAULT_PRESETS` → `DEFAULT_ROLES`; `--preset` → `--role`; `preset list` → `role list` |

- [ ] **Step 6: Verify nothing is left, run the suite, commit**

```bash
grep -rni "preset" harness qml tests README.md docs/DESIGN.md | grep -v "docs/superpowers"   # must print nothing
QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q
git add -A harness qml tests README.md
git commit -m "Roles: rename presets → roles, add outline_first and the default protagonist role

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Rename threads → contexts

A **context** is one agent conversation (spec §1). This task renames the module, drops the parent/child notification model (replaced by `wait`/delivery in the next plan), adds `owner`/`predecessor`/`forked_from`, renames the env vars, and adds bare contexts (New Context). Nothing about the process driver (`agents.py`) changes.

**Files:**
- Rename: `harness/threads.py` → `harness/contexts.py`; `qml/content/Thread.qml` → `Context.qml`; `qml/content/AgentLog.qml` → `Contexts.qml`; `tests/test_threads_unit.py` → `tests/test_contexts_unit.py`; `tests/test_ui_thread.py` → `tests/test_ui_context.py`
- Modify: `harness/shell.py`, `harness/tasks.py`, `harness/store.py`, `harness/__main__.py`, `harness/ipc.py`, `harness/cli.py`, `harness/content.py`, `harness/layout.py:45-47`, `harness/config_def.py`, `qml/content/TaskView.qml`, `qml/content/Welcome.qml`, `tests/fake_claude.py`, `tests/ui.py`, `tests/test_ipc.py`, `tests/test_cli.py`, `tests/test_agents.py`, `tests/test_app.py`, `tests/test_layout.py`, `tests/test_ui_chrome.py`, `tests/test_tasks.py`, `README.md`

**Interfaces:**
- Produces:
  ```python
  # harness/contexts.py
  CONTEXT_ROLES = ["id", "title", "storyKey", "owner", "status", "roleName", "costUsd", "turns", "createdAt"]
  SETTLED = ("idle", "failed", "stopped")
  def new_context_id() -> str                               # "ctx_" + 10 [a-z0-9]
  class Context(QObject):                                   # properties: id, title, storyKey, owner, roleName, status, sessionId, model, costUsd, turns, lastError, transcriptModel
      meta: dict  # id, title, storyKey, owner, role, roleConfig, predecessor, forkedFrom, cwd, env, systemPrompt, createdAt, status, sessionId
      def send(self, text); def stop(self); def note(self, text); def summary(self) -> dict; def last_assistant_text(self) -> str; def replay(self)
  class ContextStore(QObject):
      contextsChanged = Signal(); contextSettled = Signal(str)
      def __init__(self, root: Path, data_dir: Path, roles, workspace_dir: Path | None = None, parent=None)
      # data_dir holds index.json and <id>.jsonl directly (it will be <workspace>/.zharn/local/contexts)
      def create(self, role_name: str, *, story_key="", owner="human", title="", system_prompt="", env=None, cwd="",
                 predecessor=None, forked_from=None) -> str      # record only; no process until the first send
      def spawn(self, role_name: str, prompt: str, **create_kwargs) -> str   # create + send(prompt)
      @Slot(str, result=str) def newBare(self, role_name) -> str            # QML: New Context (owner "human", no story)
      def get(self, cid) -> Context | None; def all(self) -> list[Context]; def contexts_for(self, story_key) -> list[Context]
      def send(self, cid, text); def stop(self, cid); def shutdown(self); def summaries(self) -> list[dict]
      extra_env: callable -> dict                              # set by __main__ (HARNESS_IPC)
  ```
- Env vars an agent process receives: `HARNESS_CONTEXT_ID`, `HARNESS_STORY_KEY`, `HARNESS_WORKSPACE`, `HARNESS_ROOT`, `HARNESS_CLI`, `HARNESS_IPC`, plus anything in `meta["env"]` (Task 5 adds `HARNESS_CHARACTER_ID`).
- Config: `AGENT_SYSTEM_PROMPT` is replaced by `BARE_CONTEXT_SYSTEM_PROMPT` (format keys `{context_id}`).
- Content kinds: `thread` → `context` (`Context.qml`), `agent_log` → `contexts` (`Contexts.qml`, panel, icon `≡`, title `Contexts`).
- IPC: `context.list {story}`, `context.show {id, transcript}`, `context.new {role, prompt, title, open}` (bare), `context.send {id, text}`, `context.stop {id}`. `thread.*` gone.
- CLI: `context list [--story K]`, `context show ID [--transcript]`, `context new --role R [--prompt P] [--title T] [--open] [--wait]`, `context wait ID [--timeout S]`, `context send ID --message M`, `context stop ID`.

- [ ] **Step 1: Unit test for the store (rename + rewrite)**

`git mv tests/test_threads_unit.py tests/test_contexts_unit.py`; contents:

```python
# tests/test_contexts_unit.py
"""Context lifecycle without the UI: a context must always settle and say why; bare contexts; env."""
import json
import sys
import time

import pytest
from PySide6.QtTest import QTest

from harness.__main__ import ROOT
from harness.contexts import ContextStore, new_context_id
from harness.roles import RoleStore

FAKE = f"{sys.executable} {ROOT / 'tests' / 'fake_claude.py'}"


def wait_until(cond, timeout_ms=5000, step=20):
    t0 = time.time()
    while time.time() - t0 < timeout_ms / 1000:
        QTest.qWait(step)
        if cond():
            return True
    return False


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", FAKE)
    s = ContextStore(ROOT, tmp_path / "contexts", RoleStore(tmp_path), workspace_dir=tmp_path)
    yield s
    s.shutdown()


def test_ids_have_ctx_prefix():
    assert new_context_id().startswith("ctx_") and len(new_context_id()) == 14


def test_create_is_a_record_without_a_process(store, tmp_path):
    cid = store.create("claude-fast", story_key="ZH-1", owner="chr1", title="hello", env={"HARNESS_CHARACTER_ID": "chr1"})
    c = store.get(cid)
    assert c.status == "idle" and c._proc is None and c.owner == "chr1" and c.storyKey == "ZH-1" and c.roleName == "claude-fast"
    assert json.loads((tmp_path / "contexts" / "index.json").read_text())[0]["id"] == cid
    assert store.contexts_for("ZH-1") == [c] and store.contexts_for("ZH-2") == []
    assert store.model.rows()[0] == {**store.model.rows()[0], "id": cid, "owner": "chr1", "storyKey": "ZH-1", "status": "idle"}


def test_spawn_sends_env_and_settles(store, tmp_path):
    cid = store.spawn("claude-fast", "hello agent", story_key="ZH-1", owner="chr1", env={"HARNESS_CHARACTER_ID": "chr1"})
    c = store.get(cid)
    assert wait_until(lambda: c.status == "idle"), (c.status, c.lastError)
    records = [json.loads(l) for l in (tmp_path / "contexts" / f"{cid}.jsonl").read_text().splitlines()]
    init = next(r for r in records if r.get("subtype") == "init")
    assert init["harness_env"] == {"HARNESS_CONTEXT_ID": cid, "HARNESS_STORY_KEY": "ZH-1", "HARNESS_CHARACTER_ID": "chr1",
                                   "HARNESS_WORKSPACE": str(tmp_path)}
    assert c.transcript.rows()[-1]["text"] == "echo: hello agent"


def test_new_bare_has_human_owner_and_no_story(store):
    cid = store.newBare("claude-default")
    c = store.get(cid)
    assert c.owner == "human" and c.storyKey == "" and c.title == "New context" and c.status == "idle"
    c.send("first message")
    assert wait_until(lambda: c.status == "idle")
    assert c.transcript.rows()[-1]["text"] == "echo: first message"


def test_unknown_role_and_unimplemented_provider_raise(store):
    with pytest.raises(ValueError, match="unknown role"):
        store.create("nope")
    with pytest.raises(ValueError, match="provider"):
        store.create("codex-review")


def test_unstartable_cli_fails_the_context_with_a_visible_reason(store, monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", "/nonexistent/claude-nope")
    cid = store.spawn("claude-fast", "hello")
    c = store.get(cid)
    assert wait_until(lambda: c.status == "failed"), c.status
    assert "claude-nope" in c.lastError and c.transcript.rows()[-1]["kind"] == "error"
    assert store.model.rows()[-1]["status"] == "failed"


def test_send_on_a_failed_context_retries_by_spawning_again(store, monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", "/nonexistent/claude-nope")
    cid = store.spawn("claude-fast", "hello")
    c = store.get(cid)
    assert wait_until(lambda: c.status == "failed")
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", FAKE)
    c.send("again")
    assert wait_until(lambda: c.status == "idle"), (c.status, c.lastError)
    assert c.transcript.rows()[-1]["text"] == "echo: again" and c.lastError == ""


def test_settled_signal_fires_once_per_settle(store):
    seen = []
    store.contextSettled.connect(seen.append)
    cid = store.spawn("claude-fast", "hi")
    assert wait_until(lambda: seen == [cid])
    store.get(cid).send("more")
    assert wait_until(lambda: seen == [cid, cid])


def test_transcripts_persist_and_replay(store, tmp_path):
    cid = store.spawn("claude-fast", "persist me", story_key="ZH-3", owner="chr9")
    assert wait_until(lambda: store.get(cid).status == "idle")
    fresh = ContextStore(ROOT, tmp_path / "contexts", RoleStore(tmp_path), workspace_dir=tmp_path)
    c = fresh.get(cid)
    assert c.owner == "chr9" and c.storyKey == "ZH-3" and c.status == "idle"
    assert [(r["role"], r["text"]) for r in c.transcript.rows()] == [("user", "persist me"), ("assistant", "echo: persist me")]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_contexts_unit.py -q`
Expected: `ModuleNotFoundError: No module named 'harness.contexts'`

- [ ] **Step 3: Write `harness/contexts.py`**

`git mv harness/threads.py harness/contexts.py`; replace contents:

```python
"""Contexts: one agent conversation each — system prompt, turns, tool calls — resumable and
viewable. Owned by a character, a minion, or the human (a *bare* context with no story).
What bb calls a thread (docs/AGENT-MODEL.md §2). Transcripts persist as JSONL under the
workspace's local dir."""
from __future__ import annotations

import json
import random
import string
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from harness import config as cfg
from harness.agents import ClaudeCodeProcess, StreamInterpreter, TranscriptModel
from harness.notify import intent
from harness.qmodels import DictListModel

CONTEXT_ROLES = ["id", "title", "storyKey", "owner", "status", "roleName", "costUsd", "turns", "createdAt"]
SETTLED = ("idle", "failed", "stopped")


def new_context_id() -> str:
    return "ctx_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))


class Context(QObject):
    changed = Signal()

    def __init__(self, store: "ContextStore", meta: dict):
        super().__init__(store)
        self._store = store
        self.meta = meta
        self._status = meta.get("status", "idle")
        self._last_error = ""
        self.transcript = TranscriptModel()
        self.transcript.setParent(self)
        self._interp = StreamInterpreter(self.transcript)
        self._interp.session_id = meta.get("sessionId", "")
        self._proc: ClaudeCodeProcess | None = None
        self._log_path = store.data_dir / f"{meta['id']}.jsonl"

    # ---------------------------------------------------------------- QML-facing state
    @Property(str, constant=True)
    def id(self): return self.meta["id"]

    @Property(str, notify=changed)
    def title(self): return self.meta.get("title", "")

    @Property(str, constant=True)
    def storyKey(self): return self.meta.get("storyKey", "")

    @Property(str, constant=True)
    def owner(self): return self.meta.get("owner", "human")

    @Property(str, constant=True)
    def roleName(self): return self.meta.get("role", "")

    @Property(str, notify=changed)
    def status(self): return self._status

    @Property(str, notify=changed)
    def sessionId(self): return self._interp.session_id

    @Property(str, notify=changed)
    def model(self): return self._interp.model_name or self.meta.get("roleConfig", {}).get("model", "")

    @Property(float, notify=changed)
    def costUsd(self): return self._interp.cost_usd

    @Property(int, notify=changed)
    def turns(self): return self._interp.turns

    @Property(str, notify=changed)
    def lastError(self): return self._last_error

    @Property(QObject, constant=True)
    def transcriptModel(self): return self.transcript

    @property
    def notifier(self): return getattr(self._store, "notifier", None)

    def last_assistant_text(self) -> str:
        for row in reversed(self.transcript.rows()):
            if row["role"] == "assistant" and row["kind"] == "text" and row["text"].strip():
                return row["text"]
        return ""

    def summary(self) -> dict:
        return {"id": self.id, "title": self.title, "storyKey": self.storyKey, "owner": self.owner, "status": self._status,
                "roleName": self.roleName, "costUsd": round(self._interp.cost_usd, 4), "turns": self._interp.turns,
                "createdAt": self.meta.get("createdAt", 0), "sessionId": self._interp.session_id, "model": self.model,
                "predecessor": self.meta.get("predecessor"), "forkedFrom": self.meta.get("forkedFrom"),
                "lastText": self.last_assistant_text()}

    # ---------------------------------------------------------------- lifecycle
    def _set_status(self, status: str):
        if status != self._status:
            self._status = status
            self.meta["status"] = status
            self._store._context_changed(self)
            if status in SETTLED:
                self._store.contextSettled.emit(self.id)
        self.changed.emit()

    def _log(self, record: dict):
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _env(self) -> dict:
        env = {"HARNESS_CONTEXT_ID": self.id, "HARNESS_STORY_KEY": self.storyKey, "HARNESS_ROOT": str(self._store.root),
               "HARNESS_WORKSPACE": str(self._store.workspace_dir), "HARNESS_CLI": f"{sys.executable} -m harness.cli"}
        env.update(self.meta.get("env") or {})
        env.update(self._store.extra_env())
        return env

    def _system_prompt(self) -> str:
        role = self.meta.get("roleConfig", {})
        base = self.meta.get("systemPrompt") or getattr(cfg, "BARE_CONTEXT_SYSTEM_PROMPT", "").format(context_id=self.id)
        return "\n\n".join(p for p in (base, role.get("instructions", "")) if p)

    def _spawn(self, resume: str = ""):
        role = self.meta.get("roleConfig", {})
        extra = list(getattr(cfg, "EFFORT_FLAGS", {}).get(role.get("reasoning", ""), []))
        self._proc = ClaudeCodeProcess(cwd=self.meta.get("cwd") or str(self._store.root), env=self._env(),
                                       model=role.get("model", ""), permission=role.get("permission", "auto"),
                                       resume=resume, system_prompt=self._system_prompt(), extra_args=extra)
        self._proc.event.connect(self._on_event)
        self._proc.stderrText.connect(self._on_stderr)
        self._proc.finished.connect(self._on_finished)
        self._proc.start()

    @Slot(str)
    @intent
    def send(self, text: str):
        text = (text or "").strip()
        if not text:
            return
        self._log({"type": "harness.user", "text": text, "ts": time.time()})
        self.transcript.append(role="user", kind="text", text=text)
        self._last_error = ""
        if self._proc is None or not self._proc.running():
            self._set_status("starting")
            self._spawn(resume=self._interp.session_id)
        else:
            self._set_status("working")
        self._proc.send_user(text)

    @Slot()
    @intent
    def stop(self):
        if self._proc and self._proc.running():
            self._proc.stop()
            self._set_status("stopped")

    def _on_event(self, ev: dict):
        self._log(ev)
        hint = self._interp.apply(ev)
        if hint:
            self._set_status(hint)
        else:
            self.changed.emit()

    def _on_stderr(self, text: str):
        if text.strip():
            self._last_error = text.strip()[-2000:]
            self.changed.emit()

    def _on_finished(self, code: int, status: str):
        self._proc = None
        if self._status in ("starting", "working"):
            self._last_error = self._last_error or f"process exited with code {code} ({status})"
            self.transcript.append(role="system", kind="error", text=self._last_error, isError=True)
            self._set_status("failed")

    def replay(self):
        """Rebuild the transcript from disk (no process)."""
        try:
            lines = self._log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") == "harness.user":
                self.transcript.append(role="user", kind="text", text=rec.get("text", ""))
            elif rec.get("type") == "harness.note":
                self.transcript.append(role="system", kind="note", text=rec.get("text", ""))
            elif rec.get("type") != "harness.meta":
                self._interp.apply(rec)
        for row in self.transcript.rows():
            row["streaming"] = False
        if self._status in ("starting", "working"):
            self._status = "idle"

    def note(self, text: str):
        """A harness note in the transcript (delivery notices etc.)."""
        self._log({"type": "harness.note", "text": text, "ts": time.time()})
        self.transcript.append(role="system", kind="note", text=text)


class ContextStore(QObject):
    contextsChanged = Signal()
    contextSettled = Signal(str)
    notifier = None

    def __init__(self, root: Path, data_dir: Path, roles, workspace_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self.root = root
        self.data_dir = Path(data_dir)
        self.workspace_dir = Path(workspace_dir) if workspace_dir else root
        self.roles = roles
        self.extra_env = lambda: {}
        self._contexts: dict[str, Context] = {}
        self._model = DictListModel(CONTEXT_ROLES, self)
        self._load()

    @Property(QObject, constant=True)
    def model(self): return self._model

    def _load(self):
        try:
            metas = json.loads((self.data_dir / "index.json").read_text())
        except (OSError, ValueError):
            metas = []
        for meta in metas:
            c = Context(self, meta)
            c.replay()
            self._contexts[c.id] = c
        self._model.reset([c.summary() for c in self.all()])

    def _persist_index(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "index.json").write_text(json.dumps([c.meta for c in self.all()], indent=1))

    def all(self) -> list[Context]:
        return sorted(self._contexts.values(), key=lambda c: c.meta.get("createdAt", 0))

    def contexts_for(self, story_key: str) -> list[Context]:
        return [c for c in self.all() if c.storyKey == story_key]

    def create(self, role_name: str, *, story_key: str = "", owner: str = "human", title: str = "", system_prompt: str = "",
               env: dict | None = None, cwd: str = "", predecessor: str | None = None, forked_from: str | None = None) -> str:
        role = self.roles.get(role_name)
        if not role:
            raise ValueError(f"unknown role {role_name!r}")
        if role.get("provider", "claude-code") != "claude-code":
            raise ValueError(f"provider {role['provider']!r} not implemented yet")
        meta = {"id": new_context_id(), "title": title or role["name"], "storyKey": story_key, "owner": owner,
                "role": role["name"], "roleConfig": role, "predecessor": predecessor, "forkedFrom": forked_from,
                "cwd": cwd or str(self.workspace_dir), "env": dict(env or {}), "systemPrompt": system_prompt,
                "createdAt": time.time(), "status": "idle"}
        c = Context(self, meta)
        self._contexts[c.id] = c
        c._log({"type": "harness.meta", **meta})
        self._persist_index()
        self._model.upsert(c.summary())
        self.contextsChanged.emit()
        return c.id

    def spawn(self, role_name: str, prompt: str, **create_kwargs) -> str:
        if not create_kwargs.get("title"):
            create_kwargs["title"] = prompt.strip().splitlines()[0][:60] if prompt.strip() else role_name
        cid = self.create(role_name, **create_kwargs)
        self._contexts[cid].send(prompt)
        return cid

    @Slot(str, result=str)
    @intent
    def newBare(self, role_name: str) -> str:
        return self.create(role_name or getattr(cfg, "DEFAULT_ROLE", "claude-default"), title="New context")

    @Slot(str, result=QObject)
    def get(self, cid: str):
        return self._contexts.get(cid)

    @Slot(str, str)
    @intent
    def send(self, cid: str, text: str):
        c = self._contexts.get(cid)
        if c:
            c.send(text)

    @Slot(str)
    @intent
    def stop(self, cid: str):
        c = self._contexts.get(cid)
        if c:
            c.stop()

    def shutdown(self):
        """App exit: end child processes cleanly. Contexts resume with --resume on next launch."""
        for c in self.all():
            if c._proc is not None:
                c._proc.shutdown()
                c._proc = None
                if c._status in ("starting", "working"):
                    c._status = "idle"
                    c.meta["status"] = "idle"
        self._persist_index()

    @Slot(result="QVariantList")
    def summaries(self):
        return [c.summary() for c in self.all()]

    def _context_changed(self, c: Context):
        self._model.upsert(c.summary())
        self._persist_index()
        self.contextsChanged.emit()
```

- [ ] **Step 4: Config and fake agent**

In `harness/config_def.py` replace `AGENT_SYSTEM_PROMPT` and `NOTIFY_PARENT_ON_CHILD_SETTLED` with:

```python
# System prompt for a bare context (no story). Characters get CHARACTER_SYSTEM_PROMPT (Task 5).
BARE_CONTEXT_SYSTEM_PROMPT = (
    "You are a bare context in zharn (context {context_id}, no story): a scratch conversation. "
    "HARNESS_CLI is set; `$HARNESS_CLI context list` and `$HARNESS_CLI context show <id>` are available."
)
```

In `tests/fake_claude.py`: the init event's `harness_env` becomes
`{k: os.environ[k] for k in ("HARNESS_CONTEXT_ID", "HARNESS_STORY_KEY", "HARNESS_CHARACTER_ID", "HARNESS_WORKSPACE") if k in os.environ}`;
delete the `spawn-child` branch (and its docstring line) — delegation returns as `call`/`minion` in the next plan.

- [ ] **Step 5: Rename every other use**

| File | Change |
|---|---|
| `harness/shell.py:26` | `"harness.threads"` → `"harness.contexts"` |
| `harness/tasks.py` | ctor param `threads` → `contexts` (attribute `self._contexts`); `contexts.contextsChanged.connect(self._refresh)`; `_row` uses `self._contexts.contexts_for(key)`; `dispatch` calls `self._contexts.spawn(role_name, full, story_key=key, owner="human", title=<first line or role>)` (drop `parent_id` entirely); `threadsFor(key)` → `contextsFor(key)`; row keys `threadCount`/`workingCount` → `contextCount`/`workingCount` (also in `ROLES`) |
| `harness/store.py` | kwarg/attr/property `threads` → `contexts` |
| `harness/__main__.py` | `from harness.contexts import ContextStore`; `contexts = ContextStore(ROOT, data_dir / "contexts", roles, workspace_dir=ROOT)`; `TaskStore(data_dir, contexts)`; `AppStore(…, contexts=contexts, …)`; `contexts.extra_env = …`; smoke hook uses `store.contexts` and `openContent("context", …)`; exit calls `store.contexts.shutdown()` |
| `harness/ipc.py` | unpack `contexts` instead of `threads`; commands `context.list` (filter `a.get("story")` on `storyKey`), `context.show`, `context.new` (`contexts.spawn(a["role"], a["prompt"], title=a.get("title",""))` when `a.get("prompt")` else `contexts.create(a["role"], title=a.get("title") or "New context")`; `open` → `layout.openContent("context", cid, title)`), `context.send`, `context.stop`; delete every `thread.*` branch; `task.show` attaches `t["contexts"] = tasks.contextsFor(key)` |
| `harness/cli.py` | `thread` subparser → `context` with the verbs listed in Interfaces; `wait` polls `context.show`; `out()` columns add `"owner"`, `"storyKey"`; drop `--task`/`--no-parent` |
| `harness/content.py` | `"agent_log"` → `"contexts": {"title": "Contexts", "qml": "content/Contexts.qml", "panel": True, "icon": "≡"}`; `"thread"` → `"context": {"title": "Context", "qml": "content/Context.qml", "panel": False, "icon": "💬"}` |
| `harness/layout.py:47` | bottom panels `"agent_log"` → `"contexts"` |
| `qml/content/Context.qml` (renamed) | `view.thread` → `view.context` = `app.contexts.get(tabKey)`; objectNames `threadMissing`→`contextMissing`, `threadTitle`→`contextTitle`, `threadStatus`→`contextStatus`, `threadTaskLink`→`contextStoryLink` (opens `("task", storyKey, storyKey)` for now; Task 7 switches it to `"story"`), `threadError`→`contextError`; texts "Thread … not found" → "Context … not found"; `taskKey` → `storyKey`; keep `stopButton`, `promptInput`, `sendButton`, `transcript` |
| `qml/content/Contexts.qml` (renamed) | model `app.contexts.model`; row objectName `contextRow_<id>`; properties `storyKey`, `owner`, `roleName`; label shows `owner === "human" ? "you" : owner`; tap opens `("context", id, title)`; add at the top a `Button { objectName: "newContextButton"; text: "+ New context"; onClicked: { var id = app.contexts.newBare(""); if (id) app.layout.openContent("context", id, "New context") } }`; empty label "No contexts yet" |
| `qml/content/TaskView.qml` | `app.threads.model` → `app.contexts.model`; `taskKey` → `storyKey`; `presetName`→`roleName` already done; `parentId` removed; `threadCount` → `contextCount`; dispatch opens `("context", id, app.contexts.get(id).title)`; section label "Contexts" |
| `qml/content/TaskBoard.qml` | `threadCount`/`workingCount` → `contextCount`/`workingCount`; label text "context(s)" |
| `qml/content/Welcome.qml` | `welcomeAgentLog` → `welcomeContexts` (`showPanel("contexts")`, text "Contexts"); add `Button { objectName: "welcomeNewContext"; text: "New context"; onClicked: { var id = app.contexts.newBare(""); if (id) app.layout.openContent("context", id, "New context") } }`; CLI hint line → `$HARNESS_CLI context new --role claude-fast --prompt "..." --wait` |
| `tests/ui.py` | `shutdown` calls `self.store.contexts.shutdown()` |
| `tests/test_ipc.py` | `FakeThread`/`FakeThreads` → `FakeContext`/`FakeContexts` (`storyKey`, `owner`, `create(role, title=…)`, `spawn(role, prompt, **kw)`), `FakeAppStore.contexts`; `FakeTasks.dispatch(task, role, prompt)`, `contextsFor`; tests for `context.*` mirror the old `thread.*` ones (list filter by `story`, show ± transcript, new with/without prompt and `open`, send, stop, unknown id); delete `thread.spawn` tests |
| `tests/test_cli.py` | `thread …` tests → `context …` (`context new --role p --prompt x` → `("context.new", {"role": "p", "prompt": "x", "title": "", "open": False})`; `--wait` polls `context.show`; `context list --story ABC-1` → `{"story": "ABC-1"}`); delete `HARNESS_TASK_KEY`/`HARNESS_THREAD_ID` env tests |
| `tests/test_agents.py` | `store.threads` → `store.contexts`; `spawn("ABC-1", "claude-fast", "hello agent")` → `spawn("claude-fast", "hello agent", story_key="ABC-1")`; transcript path `DATA / "contexts" / f"{cid}.jsonl"`; `harness_env` assertions per the new keys; `threadCount` → `contextCount`; **delete** `test_agent_spawns_child_on_same_task_and_parent_is_notified`; `test_transcripts_persist_and_replay` builds `ContextStore(ROOT, DATA / "contexts", store.roles, workspace_dir=ROOT)`; `test_thread_tab_renders_and_screenshot` → `test_context_tab_renders_and_screenshot` opening `("context", …)` |
| `tests/test_ui_context.py` (renamed) | `open_thread` → `open_context` using `ui.store.contexts.spawn("claude-fast", prompt, story_key="ABC-1")` and `openContent("context", …)`; objectNames per the QML row above; `test_task_link_in_header_opens_the_task` clicks `contextStoryLink` and expects `tab_task_ABC-1` |
| `tests/test_ui_chrome.py` | `welcomeAgentLog` → `welcomeContexts` expecting `"contexts"`; `test_agent_log_row_opens_the_thread` → `test_contexts_row_opens_the_context` (`contextRow_<id>`, `tab_context_<id>`); add `test_new_context_button_opens_a_bare_context`: click `newContextButton` in the contexts panel → `ui.store.contexts.model.count()` grows by one, the new context has `owner == "human"`, and `tab_context_<id>` exists |
| `tests/test_app.py` | `openContent("thread", "thr_1", …)` → `openContent("context", "ctx_1", …)` and `tab_context_ctx_1` |
| `tests/test_layout.py:260-264` | `"agent_log"` → `"contexts"` |
| `tests/test_tasks.py` | `StubThreads` → `StubContexts` with `contextsChanged`, `contexts_for`, `spawn(role_name, prompt, *, story_key, owner, title)`; adapt dispatch assertions (no `parent_id`); `threadsFor` → `contextsFor`; `threadCount` → `contextCount` |
| `README.md` | Agents section: env vars, `context new`, transcripts location |

- [ ] **Step 6: Verify, run, commit**

```bash
grep -rn "thread\|Thread\|THREAD" harness qml tests --include=*.py --include=*.qml | grep -iv "QThread\|threading\|thread_id\|threads\.jsonl\|main_thread\|Thread(\|lifecycle\|\"thread\"\|#thread\|comment thread"
```
Expected: nothing about agent conversations remains (the lifecycle module's comment-thread vocabulary is fine). Then:

```bash
QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q
git add -A harness qml tests README.md
git commit -m "Contexts: rename threads → contexts, owner/predecessor/forked_from, bare contexts, drop parent/child notification

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: StoryStore — stories, characters, brief, character system prompt

The store that owns stories on disk, applies `lifecycle.step`, casts the protagonist as a character with a live context, and delivers the author's comments to it. Main thread only (see Out of scope). Tested against a stub context store — no processes.

**Files:**
- Create: `harness/stories.py`
- Modify: `harness/config_def.py` (add `CHARACTER_SYSTEM_PROMPT`), `harness/shell.py:25-26` (RELOADABLE: add `"harness.workspace", "harness.lifecycle"` before `"harness.roles"`, and `"harness.stories"` after `"harness.contexts"`)
- Test: `tests/test_stories.py`

**Interfaces:**
- Consumes: `Workspace` (Task 1), `lifecycle` (Task 2), `RoleStore.get` (Task 3), `ContextStore.create/get/contexts_for/contextsChanged` and `Context.send/stop/status` (Task 4).
- Produces:
  ```python
  # harness/stories.py
  STORY_ROLES = ["key", "title", "description", "priority", "phase", "ball", "needsYou", "flavor", "author", "protagonist",
                 "castCount", "workingCount", "createdAt"]
  def new_id(prefix: str) -> str                      # "thr_x…", "cmt_x…", "chr_x…" (10 chars)
  def author_name(author: str, characters: dict[str, dict]) -> str   # "human"→"you", "system"→"harness", chr id→name, unknown→id
  def render_brief(story: Story, comments: list[dict], characters: dict[str, dict], role: dict, note: str) -> str
  def needs_you_flavor(story: Story, comments: list[dict]) -> str    # "" | "question" | "outline ready" | "ready for review"
  class StoryStore(QObject):
      storiesChanged = Signal()
      def __init__(self, workspace, contexts, roles, parent=None)
      model: Property(QObject)                          # DictListModel(STORY_ROLES)
      # queries (Slots)
      def get(self, key) -> dict (row or {}); def list(self) -> list[dict]; def comments(self, key) -> list[dict]  (+ "authorName")
      def cast(self, key) -> list[dict]   # character dicts + "contextStatus"
      def character(self, character_id) -> dict | None; def story(self, key) -> Story | None  (python only)
      # author intents (Slots, @intent; all raise lifecycle.Rejected on misuse)
      def create(self, title, description="") -> str
      def update(self, key, title, description)          # unstarted only, else Rejected
      def start(self, key, note="", role="") -> str        # returns protagonist character id
      def proceed(self, key, note=""); def approve(self, key, note=""); def backToPlanning(self, key, note="")
      def cancel(self, key, note=""); def reopen(self, key, note="")
      def comment(self, key, body, thread_id="") -> dict    # human comment (a Reply when the thread waits on the human)
      # cast verbs (python; IPC calls them with the character id from HARNESS_CHARACTER_ID)
      def cast_yield(self, character_id, kind, body, options=(), thread_id="") -> dict
      def cast_proceed(self, character_id, note="") -> dict
      def cast_recap(self, character_id, body) -> dict
      def cast_comment(self, character_id, body, thread_id="") -> dict
      def log_verb(self, character_id, verb, args: dict, ok: bool, error: str = "")
  ```
- On disk (workspace spec §6): `stories/<key>/story.json` = `Story.to_dict()` + `created`; `stories/<key>/threads.jsonl` = `{"type":"thread",…}` and `{"type":"comment",…}` records, append-only; `local/characters.json` = `{chr_id: {id, story_key, role, name, live_context, attention, inbox, recaps, verbs_log}}`.
- Delivery (main thread only): every accepted human action that leaves the ball with the cast **and** resumes the protagonist (Reply/Comment, Proceed, Back to planning, Reopen) sends `"[you] <kind> in #<thread>: <body>"` (plus `"Phase is now <phase>."` on a phase change) to the protagonist's live context via `Context.send`. Cancel stops every context of the story. Approve sends nothing.
- Needs-you: after every action, if `story.ball == "author"` and `story.author == "human"`, `notifier.info(f"{key} needs you: {flavor}")` when a notifier is set.
- Config: `CHARACTER_SYSTEM_PROMPT` with keys `{name} {character_id} {story_key} {title} {phase} {thread_id} {outline_rule}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_stories.py
"""StoryStore against a stub context store: persistence, Start casts a protagonist, author actions deliver
to the protagonist, cast verbs, brief and system prompt, needs-you rows."""
import json

import pytest
from PySide6.QtCore import QObject, Signal

from harness import config as cfg
from harness.lifecycle import Rejected
from harness.stories import StoryStore, author_name, needs_you_flavor, render_brief
from harness.workspace import Workspace


class StubContext:
    def __init__(self, cid, meta):
        self.id, self.meta, self.status, self.sent, self.stopped = cid, meta, "idle", [], False

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

    def create(self, role_name, **kw):
        cid = f"ctx_{len(self.by_id) + 1}"
        self.by_id[cid] = StubContext(cid, {"role": role_name, **kw})
        self.created.append((role_name, kw))
        return cid

    def get(self, cid):
        return self.by_id.get(cid)

    def contexts_for(self, key):
        return [c for c in self.by_id.values() if c.meta.get("story_key") == key]


class StubRoles:
    def get(self, name):
        return {"protagonist": {"name": "protagonist", "instructions": "Lead.", "outline_first": True},
                "claude-fast": {"name": "claude-fast", "instructions": "", "outline_first": False}}.get(name, {})


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
```

- [ ] **Step 2: Run to verify failure**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_stories.py -q`
Expected: `ModuleNotFoundError: No module named 'harness.stories'`

- [ ] **Step 3: Config — the character system prompt**

Append to `harness/config_def.py`:

```python
# System prompt for a character (rebuilt on every spawn/resume). Phase skills arrive in the next plan.
CHARACTER_SYSTEM_PROMPT = """You are {name} ({character_id}), a character in zharn on story {story_key} ("{title}"), phase: {phase}.
You lead the main thread #{thread_id}; its author is the story's author. Everything you say to the author is a comment posted with the CLI below — nothing else reaches them.

Iron laws:
1. Status is not yours to set. Phases move only when you `yield` and the author answers, or when you `proceed`.
2. Never end a turn without either a pending `yield` (question or handoff) or work still in flight that you will report on.
3. When told your context is low, `recap` before anything else.
4. Questions carry options when there are natural choices; handoffs carry evidence (what changed, how verified, where to look first).

CLI (HARNESS_CLI is set; every call prints a reason and exits non-zero when refused):
  $HARNESS_CLI story yield --question --body "..." [--options a,b]   # ask the author; the ball moves to them
  $HARNESS_CLI story yield --handoff --body "..."                    # hand off an outline (planning) or finished work (implementing)
  $HARNESS_CLI story proceed [--note "..."]                          # planning -> implementing
  $HARNESS_CLI story comment --body "..."                            # a note in the thread; does not move the ball
  $HARNESS_CLI story recap --body "..."                              # done / in flight / gotchas / next
  $HARNESS_CLI story show                                            # the story record so far
{outline_rule}"""

OUTLINE_RULE_REQUIRED = ("Your role requires an outline: while planning, ask what you must, then `yield --handoff` an outline "
                         "and wait for the author to Proceed. Do not edit files while planning.")
OUTLINE_RULE_OPTIONAL = "You may `proceed` straight to implementing when the work is bounded; outline first when it is not."
```

- [ ] **Step 4: Implement `harness/stories.py`**

```python
"""Stories: the unit of work an author describes and validates (docs/AGENT-MODEL.md). This store
persists stories in the workspace, applies the pure state machine (harness/lifecycle.py), casts the
protagonist as a character with a live context, and delivers the author's comments to it.

This plan drives the main thread only; friends, minions, inbox delivery and recast come next."""
from __future__ import annotations

import json
import random
import string
import time
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from harness import config as cfg
from harness import lifecycle as lc
from harness.notify import intent
from harness.qmodels import DictListModel

STORY_ROLES = ["key", "title", "description", "priority", "phase", "ball", "needsYou", "flavor", "author", "protagonist",
               "castCount", "workingCount", "createdAt"]
WORKING = ("starting", "working")


def new_id(prefix: str) -> str:
    return prefix + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))


def author_name(author: str, characters: dict[str, dict]) -> str:
    if author == "human":
        return "you"
    if author == "system":
        return "harness"
    ch = characters.get(author)
    return ch["name"] if ch else author


def needs_you_flavor(story: lc.Story, comments: list[dict]) -> str:
    if story.ball != "author" or story.author != "human":
        return ""
    pending = story.main.pending_yield
    kind = next((c["kind"] for c in comments if c["id"] == pending), "")
    if kind == "question":
        return "question"
    if kind == "handoff":
        return "outline ready" if story.phase == "planning" else "ready for review"
    return "waiting on you"


def render_brief(story: lc.Story, comments: list[dict], characters: dict[str, dict], role: dict, note: str) -> str:
    """Lifecycle spec §3.1: the story record as markdown, then the role's instructions, then the note."""
    out = [f"# {story.key}: {story.title}", "", story.description or "(no description)", "",
           f"Phase: {story.phase}" + (f" · ball: {story.ball}" if story.ball else ""), ""]
    if story.threads:
        out += ["## Threads", ""]
        for t in story.threads:
            label = "main" if t.id == story.main_thread else t.id
            out.append(f"### #{label} — author {author_name(t.author, characters)}, lead {author_name(t.lead, characters)}, turn: {t.turn}")
            for c in comments:
                if c["thread_id"] != t.id:
                    continue
                out.append(f"- **{author_name(c['author'], characters)}** ({c['kind']}): {c['body']}")
                opts = c.get("structured", {}).get("options")
                if opts:
                    out.append(f"  - options: {', '.join(opts)}")
            out.append("")
    recaps = [c for c in comments if c["kind"] == "recap"]
    if recaps:
        out += ["## Latest recap", "", recaps[-1]["body"], ""]
    cast = [ch for ch in characters.values() if ch["story_key"] == story.key]
    if cast:
        out += ["## Cast", ""] + [f"- {ch['name']} — {ch['role']}" + (" (protagonist)" if ch["id"] == story.protagonist else "") for ch in cast] + [""]
    if role.get("instructions"):
        out += ["## Instructions", role["instructions"], ""]
    if note:
        out += ["## Note", note]
    return "\n".join(out).rstrip() + "\n"


class StoryStore(QObject):
    storiesChanged = Signal()
    notifier = None

    def __init__(self, workspace, contexts, roles, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self._contexts = contexts
        self._roles = roles
        self._stories: dict[str, lc.Story] = {}
        self._created: dict[str, float] = {}
        self._comments: dict[str, list[dict]] = {}
        self._characters: dict[str, dict] = {}
        self._model = DictListModel(STORY_ROLES, self)
        self._load()
        contexts.contextsChanged.connect(self._refresh)

    # ---------------------------------------------------------------- persistence
    def _load(self):
        for key in self.workspace.story_keys():
            d = self.workspace.story_dir(key)
            try:
                data = json.loads((d / "story.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            self._created[key] = data.pop("created", 0)
            self._stories[key] = lc.Story.from_dict(data)
            comments = []
            try:
                for line in (d / "threads.jsonl").read_text(encoding="utf-8").splitlines():
                    rec = json.loads(line)
                    if rec.get("type") == "comment":
                        rec.pop("type")
                        comments.append(rec)
            except (OSError, ValueError):
                pass
            self._comments[key] = comments
        try:
            self._characters = json.loads((self.workspace.local_dir / "characters.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._characters = {}
        self._refresh()

    def _save_story(self, key: str):
        s = self._stories[key]
        path = self.workspace.story_dir(key) / "story.json"
        path.write_text(json.dumps({**s.to_dict(), "created": self._created.get(key, 0)}, indent=1), encoding="utf-8")

    def _append_record(self, key: str, record: dict):
        with (self.workspace.story_dir(key) / "threads.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _save_characters(self):
        (self.workspace.local_dir / "characters.json").write_text(json.dumps(self._characters, indent=1), encoding="utf-8")

    # ---------------------------------------------------------------- rows / queries
    def _row(self, key: str) -> dict:
        s = self._stories[key]
        cast = [ch for ch in self._characters.values() if ch["story_key"] == key]
        live = [self._contexts.get(ch["live_context"]) for ch in cast if ch.get("live_context")]
        flavor = needs_you_flavor(s, self._comments.get(key, []))
        return {"key": s.key, "title": s.title, "description": s.description, "priority": s.priority, "phase": s.phase,
                "ball": s.ball or "", "needsYou": bool(flavor), "flavor": flavor, "author": s.author,
                "protagonist": s.protagonist or "", "castCount": len(cast),
                "workingCount": sum(1 for c in live if c is not None and c.status in WORKING),
                "createdAt": self._created.get(key, 0)}

    def _refresh(self):
        self._model.reset([self._row(k) for k in self._stories])
        self.storiesChanged.emit()

    def _key(self, key: str) -> str:
        for k in self._stories:
            if k.lower() == (key or "").lower():
                return k
        raise KeyError(key)

    def story(self, key: str) -> lc.Story | None:
        try:
            return self._stories[self._key(key)]
        except KeyError:
            return None

    @Property(QObject, constant=True)
    def model(self): return self._model

    @Slot(str, result="QVariantMap")
    def get(self, key):
        try:
            return self._row(self._key(key))
        except KeyError:
            return {}

    @Slot(result="QVariantList")
    def list(self):
        return [self._row(k) for k in self._stories]

    @Slot(str, result="QVariantList")
    def comments(self, key):
        try:
            key = self._key(key)
        except KeyError:
            return []
        return [{**c, "authorName": author_name(c["author"], self._characters)} for c in self._comments.get(key, [])]

    @Slot(str, result="QVariantList")
    def cast(self, key):
        try:
            key = self._key(key)
        except KeyError:
            return []
        out = []
        for ch in self._characters.values():
            if ch["story_key"] == key:
                ctx = self._contexts.get(ch["live_context"]) if ch.get("live_context") else None
                out.append({**ch, "contextStatus": ctx.status if ctx is not None else "none"})
        return out

    @Slot(str, result="QVariantMap")
    def character(self, character_id):
        return dict(self._characters[character_id]) if character_id in self._characters else None

    # ---------------------------------------------------------------- the one way state changes
    def _apply(self, key: str, action) -> dict:
        s = self._stories[key]
        s2, comment = lc.step(s, action, comment_id=new_id("cmt_"), now=time.time())
        lc.check_invariants(s2)
        self._stories[key] = s2
        for t in s2.threads:
            if not any(t.id == old.id for old in s.threads):
                self._append_record(key, {"type": "thread", "id": t.id, "author": t.author, "lead": t.lead, "opened_at": comment["created_at"]})
        self._comments.setdefault(key, []).append(comment)
        self._append_record(key, {"type": "comment", **comment})
        self._save_story(key)
        self._refresh()
        flavor = needs_you_flavor(s2, self._comments[key])
        if flavor and self.notifier is not None:
            self.notifier.info(f"{key} needs you: {flavor}")
        return comment

    def _protagonist_context(self, key: str):
        s = self._stories[key]
        ch = self._characters.get(s.protagonist or "")
        return self._contexts.get(ch["live_context"]) if ch and ch.get("live_context") else None

    def _deliver(self, key: str, comment: dict, phase_before: str):
        """Main thread only: tell the protagonist what the author just did."""
        ctx = self._protagonist_context(key)
        if ctx is None:
            return
        kind = "reply" if comment.get("reply_to") else comment["kind"]
        text = f"[{author_name(comment['author'], self._characters)}] {kind} in #{comment['thread_id']}: {comment['body']}"
        phase = self._stories[key].phase
        if phase != phase_before:
            text += f"\nPhase is now {phase}."
        ctx.send(text)

    # ---------------------------------------------------------------- author intents
    @Slot(str, str, result=str)
    @intent
    def create(self, title, description=""):
        key = self.workspace.next_key()
        self._stories[key] = lc.Story(key=key, title=title, description=description, phase="todo")
        self._created[key] = time.time()
        self._comments[key] = []
        self.workspace.story_dir(key)
        self._save_story(key)
        self._refresh()
        return key

    @Slot(str, str, str)
    @intent
    def update(self, key, title, description):
        key = self._key(key)
        s = self._stories[key]
        if s.phase not in lc.UNSTARTED:
            raise lc.Rejected(f"{key} is already started; the description is fixed")
        s.title, s.description = title, description
        self._save_story(key)
        self._refresh()

    @Slot(str, str, str, result=str)
    @intent
    def start(self, key, note="", role=""):
        key = self._key(key)
        role_name = role or getattr(cfg, "DEFAULT_ROLE", "protagonist")
        role_cfg = self._roles.get(role_name)
        if not role_cfg:
            raise ValueError(f"unknown role {role_name!r}")
        taken = {ch["name"] for ch in self._characters.values() if ch["story_key"] == key}
        name, n = role_cfg["name"], 2
        while name in taken:
            name, n = f"{role_cfg['name']}-{n}", n + 1
        chr_id, thread_id = new_id("chr_"), new_id("thr_")
        self._apply(key, lc.Start(thread_id=thread_id, protagonist=chr_id, note=note, role=role_cfg["name"]))
        ch = {"id": chr_id, "story_key": key, "role": role_cfg["name"], "name": name, "live_context": None,
              "attention": thread_id, "inbox": [], "recaps": [], "verbs_log": []}
        self._characters[chr_id] = ch
        s = self._stories[key]
        cid = self._contexts.create(role_cfg["name"], story_key=key, owner=chr_id, title=f"{key} · {name}",
                                    system_prompt=self._system_prompt(s, ch, role_cfg),
                                    env={"HARNESS_CHARACTER_ID": chr_id})
        ch["live_context"] = cid
        self._save_characters()
        self._contexts.get(cid).send(render_brief(s, self._comments[key], self._characters, role_cfg, note))
        self._refresh()
        return chr_id

    def _system_prompt(self, s: lc.Story, ch: dict, role_cfg: dict) -> str:
        rule = getattr(cfg, "OUTLINE_RULE_REQUIRED", "") if role_cfg.get("outline_first") else getattr(cfg, "OUTLINE_RULE_OPTIONAL", "")
        return getattr(cfg, "CHARACTER_SYSTEM_PROMPT", "").format(
            name=ch["name"], character_id=ch["id"], story_key=s.key, title=s.title, phase=s.phase,
            thread_id=s.main_thread or "", outline_rule=rule)

    def _author_action(self, key, action, *, resume: bool):
        key = self._key(key)
        before = self._stories[key].phase
        comment = self._apply(key, action)
        if resume:
            self._deliver(key, comment, before)
        return comment

    @Slot(str, str)
    @intent
    def proceed(self, key, note=""):
        self._author_action(key, lc.Proceed(by="human", note=note), resume=True)

    @Slot(str, str)
    @intent
    def approve(self, key, note=""):
        self._author_action(key, lc.Approve(note=note), resume=False)

    @Slot(str, str)
    @intent
    def backToPlanning(self, key, note=""):
        self._author_action(key, lc.BackToPlanning(note=note), resume=True)

    @Slot(str, str)
    @intent
    def cancel(self, key, note=""):
        key = self._key(key)
        self._author_action(key, lc.Cancel(note=note), resume=False)
        for ch in self._characters.values():
            if ch["story_key"] == key and ch.get("live_context"):
                ctx = self._contexts.get(ch["live_context"])
                if ctx is not None:
                    ctx.stop()
        self._refresh()

    @Slot(str, str)
    @intent
    def reopen(self, key, note=""):
        self._author_action(key, lc.Reopen(note=note), resume=True)

    @Slot(str, str, result="QVariantMap")
    @Slot(str, str, str, result="QVariantMap")
    @intent
    def comment(self, key, body, thread_id=""):
        key = self._key(key)
        s = self._stories[key]
        tid = thread_id or s.main_thread or ""
        return self._author_action(key, lc.Comment(thread_id=tid, by="human", body=body), resume=True)

    # ---------------------------------------------------------------- cast verbs (via IPC)
    def _char(self, character_id: str) -> tuple[str, dict]:
        ch = self._characters[character_id]  # KeyError for unknown characters
        return ch["story_key"], ch

    def cast_yield(self, character_id, kind, body, options=(), thread_id="") -> dict:
        key, ch = self._char(character_id)
        tid = thread_id or ch.get("attention") or self._stories[key].main_thread
        return self._apply(key, lc.Yield(thread_id=tid, by=character_id, kind=kind, body=body, options=list(options)))

    def cast_proceed(self, character_id, note="") -> dict:
        key, ch = self._char(character_id)
        role_cfg = self._roles.get(ch["role"]) or {}
        if role_cfg.get("outline_first") and not any(
                c["kind"] == "system" and c["body"].startswith("outline approved") for c in self._comments.get(key, [])):
            raise lc.Rejected("your role requires an approved outline first: `yield --handoff` the outline and wait for Proceed")
        return self._apply(key, lc.Proceed(by=character_id, note=note))

    def cast_recap(self, character_id, body) -> dict:
        key, ch = self._char(character_id)
        c = self._apply(key, lc.Recap(by=character_id, body=body))
        ch.setdefault("recaps", []).append(c["id"])
        self._save_characters()
        return c

    def cast_comment(self, character_id, body, thread_id="") -> dict:
        key, ch = self._char(character_id)
        tid = thread_id or ch.get("attention") or self._stories[key].main_thread
        return self._apply(key, lc.Comment(thread_id=tid, by=character_id, body=body))

    def log_verb(self, character_id, verb, args: dict, ok: bool, error: str = ""):
        ch = self._characters.get(character_id)
        if ch is None:
            return
        ch.setdefault("verbs_log", []).append({"verb": verb, "args": dict(args), "ok": ok, "error": error, "ts": time.time()})
        self._save_characters()
```

- [ ] **Step 5: Register the modules for hot reload**

`harness/shell.py` RELOADABLE becomes (dependency order):

```python
RELOADABLE = ["harness.config_def", "harness.config", "harness.notify", "harness.layout", "harness.content", "harness.qmodels",
              "harness.workspace", "harness.lifecycle", "harness.agents", "harness.roles", "harness.contexts",
              "harness.tasks", "harness.stories", "harness.ipc", "harness.store"]
```

- [ ] **Step 6: Run, fix, commit**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_stories.py tests/test_lifecycle.py -q`
Expected: all pass. Note `test_author_action_rejections_raise_and_report` relies on `@intent` reporting to `store.notifier.error` before re-raising; the stub `Notes` has both `info` and `error`.

```bash
QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q
git add harness/stories.py harness/config_def.py harness/shell.py tests/test_stories.py
git commit -m "Stories: StoryStore over the workspace — Start casts a protagonist, author actions deliver to it, cast verbs, brief

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Wire the workspace and StoryStore into the app; `story.*` over IPC and CLI

After this task the app opens a workspace, exposes `app.stories`, and a character can `zharn story yield …` from inside its context. `tasks` still exists alongside (the QML still renders it); Task 8 removes it.

**Files:**
- Modify: `harness/__main__.py`, `harness/store.py`, `harness/ipc.py`, `harness/cli.py`, `.gitignore`, `tests/ui.py`, `tests/test_agents.py`, `tests/test_ipc.py`, `tests/test_cli.py`, `tests/fake_claude.py`

**Interfaces:**
- Consumes: `Workspace.open_or_create/add_repo/local_dir` (Task 1), `StoryStore` (Task 5), `ContextStore` (Task 4).
- Produces:
  - `build()` opens `Workspace.open_or_create(Path(os.environ.get("HARNESS_WORKSPACE") or ROOT))`; registers `.` as a repo when the dir has a `.git` and no repos yet; `data_dir = workspace.local_dir`; session at `local/session.json` unless `HARNESS_SESSION`; contexts at `local/contexts`; `AppStore(…, stories=stories, workspace=workspace)`.
  - `AppStore.stories` (QObject property), `AppStore.workspaceDir` (str, constant).
  - IPC commands (in addition to Task 4's): `story.list`, `story.show {key}` → row + `comments`, `cast`, `contexts`; `story.create {title, description}`; `story.start {key, note, role}` → row + `character`; `story.comment {key?, character?, body, thread}`; `story.yield {character, kind, body, options, thread}`; `story.proceed {character?, key?, note}`; `story.recap {character, body}`; `story.approve|story.back|story.cancel|story.reopen {key, note}`. Every `story.*` call carrying `character` is appended to that character's `verbs_log` (accepted or rejected) before the result/error is returned.
  - CLI (`zharn story …`): `list`, `show [KEY]`, `create --title T [--description D]`, `start KEY [--note N] [--role R]`, `yield (--question|--handoff) --body B [--options a,b] [--thread T]`, `proceed [KEY] [--note N]`, `recap --body B`, `comment --body B [--thread T] [--story KEY]`, `reply KEY --body B [--thread T]`, `approve KEY [--note N]`, `back KEY [--note N]`, `cancel KEY [--note N]`, `reopen KEY --note N`. Character identity comes from `HARNESS_CHARACTER_ID`; `yield`/`recap` exit with `"HARNESS_CHARACTER_ID is not set (run this inside a character)"` without it; `KEY` defaults to `HARNESS_STORY_KEY` where optional.
  - `tests/fake_claude.py` gains a `yield-question` behaviour: runs `$HARNESS_CLI story yield --question --body "which one?" --options a,b` as a tool call and echoes the CLI's output.

- [ ] **Step 1: IPC tests (fakes)**

Add to `tests/test_ipc.py` a `FakeStories` and tests. The fake records calls and returns simple rows:

```python
class FakeStories:
    def __init__(self):
        self.calls, self.verbs = [], []
        self.rows = {"ABC-1": {"key": "ABC-1", "title": "one", "phase": "todo", "ball": ""}}

    def list(self): return list(self.rows.values())
    def get(self, key): return dict(self.rows.get(key, {}))
    def comments(self, key): return [{"id": "c1", "kind": "text", "body": "hi", "authorName": "you"}] if key in self.rows else []
    def cast(self, key): return [{"id": "chr1", "name": "protagonist", "live_context": "t1"}] if key in self.rows else []
    def create(self, title, description=""):
        self.calls.append(("create", title, description)); self.rows["ABC-2"] = {"key": "ABC-2", "title": title, "phase": "todo", "ball": ""}; return "ABC-2"
    def start(self, key, note="", role=""):
        self.calls.append(("start", key, note, role)); self.rows[key].update(phase="planning", ball="cast"); return "chr1"
    def comment(self, key, body, thread_id=""): self.calls.append(("comment", key, body, thread_id)); return {"id": "c9", "kind": "text"}
    def proceed(self, key, note=""): self.calls.append(("proceed", key, note))
    def approve(self, key, note=""): self.calls.append(("approve", key, note))
    def backToPlanning(self, key, note=""): self.calls.append(("back", key, note))
    def cancel(self, key, note=""): self.calls.append(("cancel", key, note))
    def reopen(self, key, note=""): self.calls.append(("reopen", key, note))
    def cast_yield(self, character_id, kind, body, options=(), thread_id=""):
        self.calls.append(("cast_yield", character_id, kind, body, list(options), thread_id))
        if body == "boom":
            from harness.lifecycle import Rejected
            raise Rejected("thread already waits on its author")
        return {"id": "c5", "kind": kind}
    def cast_proceed(self, character_id, note=""): self.calls.append(("cast_proceed", character_id, note)); return {"id": "c6", "kind": "system"}
    def cast_recap(self, character_id, body): self.calls.append(("cast_recap", character_id, body)); return {"id": "c7", "kind": "recap"}
    def cast_comment(self, character_id, body, thread_id=""): self.calls.append(("cast_comment", character_id, body, thread_id)); return {"id": "c8", "kind": "text"}
    def log_verb(self, character_id, verb, args, ok, error=""): self.verbs.append((character_id, verb, dict(args), ok, error))
```

`FakeAppStore` gets `self.stories = FakeStories()`. Tests:

```python
def test_story_list_and_show_attach_comments_cast_and_contexts(h, store):
    assert [s["key"] for s in h("story.list", {})] == ["ABC-1"]
    s = h("story.show", {"key": "ABC-1"})
    assert s["title"] == "one" and s["comments"][0]["body"] == "hi" and s["cast"][0]["name"] == "protagonist"
    assert [c["id"] for c in s["contexts"]] == ["t1"]   # FakeContexts entries whose storyKey == "ABC-1"
    with pytest.raises(KeyError):
        h("story.show", {"key": "ZZZ-9"})


def test_story_create_and_start(h, store):
    assert h("story.create", {"title": "new", "description": "d"})["key"] == "ABC-2"
    r = h("story.start", {"key": "ABC-1", "note": "go", "role": "protagonist"})
    assert store.stories.calls[-1] == ("start", "ABC-1", "go", "protagonist") and r["character"] == "chr1" and r["phase"] == "planning"


def test_story_author_verbs_forward(h, store):
    h("story.proceed", {"key": "ABC-1", "note": "n"}); h("story.approve", {"key": "ABC-1"}); h("story.back", {"key": "ABC-1", "note": "b"})
    h("story.cancel", {"key": "ABC-1"}); h("story.reopen", {"key": "ABC-1", "note": "r"}); h("story.comment", {"key": "ABC-1", "body": "hey"})
    assert store.stories.calls == [("proceed", "ABC-1", "n"), ("approve", "ABC-1", ""), ("back", "ABC-1", "b"),
                                   ("cancel", "ABC-1", ""), ("reopen", "ABC-1", "r"), ("comment", "ABC-1", "hey", "")]
    assert store.stories.verbs == []   # no character → nothing logged


def test_story_cast_verbs_forward_and_log(h, store):
    assert h("story.yield", {"character": "chr1", "kind": "question", "body": "q", "options": ["a", "b"]})["kind"] == "question"
    h("story.proceed", {"character": "chr1", "note": "bounded"})
    h("story.recap", {"character": "chr1", "body": "r"})
    h("story.comment", {"character": "chr1", "body": "c", "thread": "t2"})
    assert store.stories.calls == [("cast_yield", "chr1", "question", "q", ["a", "b"], ""), ("cast_proceed", "chr1", "bounded"),
                                   ("cast_recap", "chr1", "r"), ("cast_comment", "chr1", "c", "t2")]
    assert [(v[1], v[3]) for v in store.stories.verbs] == [("yield", True), ("proceed", True), ("recap", True), ("comment", True)]
    assert "character" not in store.stories.verbs[0][2]


def test_story_cast_rejection_is_logged_and_raised(h, store):
    with pytest.raises(Exception, match="already waits"):
        h("story.yield", {"character": "chr1", "kind": "question", "body": "boom"})
    assert store.stories.verbs[-1][3] is False and "already waits" in store.stories.verbs[-1][4]
```

- [ ] **Step 2: CLI tests (recorder)**

Add to `tests/test_cli.py` (the `recorder` fixture must also `monkeypatch.delenv` `HARNESS_CHARACTER_ID` and `HARNESS_STORY_KEY`):

```python
def test_story_list_show_create_start(recorder, monkeypatch):
    recorder.replies.update({"story.list": [], "story.show": {"key": "ABC-1"}, "story.create": {"key": "ABC-2"}, "story.start": {"key": "ABC-1", "character": "chr1"}})
    cli.main(["story", "list"]); cli.main(["story", "show", "ABC-1"])
    monkeypatch.setenv("HARNESS_STORY_KEY", "ABC-7"); cli.main(["story", "show"])
    cli.main(["story", "create", "--title", "T", "--description", "D"])
    cli.main(["story", "start", "ABC-1", "--note", "go", "--role", "protagonist"])
    assert recorder.calls == [("story.list", {}), ("story.show", {"key": "ABC-1"}), ("story.show", {"key": "ABC-7"}),
                              ("story.create", {"title": "T", "description": "D"}),
                              ("story.start", {"key": "ABC-1", "note": "go", "role": "protagonist"})]


def test_story_yield_uses_character_from_env(recorder, monkeypatch, capsys):
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr1")
    recorder.replies["story.yield"] = {"id": "c1", "kind": "question"}
    cli.main(["story", "yield", "--question", "--body", "which?", "--options", "a,b", "--thread", "t2"])
    assert recorder.calls == [("story.yield", {"character": "chr1", "kind": "question", "body": "which?", "options": ["a", "b"], "thread": "t2"})]
    cli.main(["story", "yield", "--handoff", "--body", "done"])
    assert recorder.calls[-1][1]["kind"] == "handoff" and recorder.calls[-1][1]["options"] == []


def test_story_yield_requires_exactly_one_kind_and_a_character(recorder, monkeypatch):
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr1")
    with pytest.raises(SystemExit):
        cli.main(["story", "yield", "--body", "x"])
    with pytest.raises(SystemExit):
        cli.main(["story", "yield", "--question", "--handoff", "--body", "x"])
    monkeypatch.delenv("HARNESS_CHARACTER_ID")
    with pytest.raises(SystemExit) as e:
        cli.main(["story", "yield", "--question", "--body", "x"])
    assert "HARNESS_CHARACTER_ID" in str(e.value)
    assert recorder.calls == []


def test_story_proceed_recap_comment_inside_a_character(recorder, monkeypatch):
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr1")
    for cmd in ("story.proceed", "story.recap", "story.comment"):
        recorder.replies[cmd] = {"id": "c"}
    cli.main(["story", "proceed", "--note", "bounded"]); cli.main(["story", "recap", "--body", "r"]); cli.main(["story", "comment", "--body", "c"])
    assert recorder.calls == [("story.proceed", {"character": "chr1", "note": "bounded"}), ("story.recap", {"character": "chr1", "body": "r"}),
                              ("story.comment", {"character": "chr1", "body": "c", "thread": ""})]


def test_story_author_verbs_outside_a_character(recorder):
    for cmd in ("story.proceed", "story.approve", "story.back", "story.cancel", "story.reopen", "story.reply", "story.comment"):
        recorder.replies[cmd] = {"key": "ABC-1"}
    cli.main(["story", "proceed", "ABC-1", "--note", "ok"]); cli.main(["story", "approve", "ABC-1"]); cli.main(["story", "back", "ABC-1", "--note", "b"])
    cli.main(["story", "cancel", "ABC-1"]); cli.main(["story", "reopen", "ABC-1", "--note", "r"])
    cli.main(["story", "reply", "ABC-1", "--body", "yes", "--thread", "t1"]); cli.main(["story", "comment", "--story", "ABC-1", "--body", "c"])
    assert recorder.calls == [("story.proceed", {"key": "ABC-1", "note": "ok"}), ("story.approve", {"key": "ABC-1", "note": ""}),
                              ("story.back", {"key": "ABC-1", "note": "b"}), ("story.cancel", {"key": "ABC-1", "note": ""}),
                              ("story.reopen", {"key": "ABC-1", "note": "r"}), ("story.comment", {"key": "ABC-1", "body": "yes", "thread": "t1"}),
                              ("story.comment", {"key": "ABC-1", "body": "c", "thread": ""})]
```

(`reply` and a human `comment` are the same IPC command: lifecycle makes a comment in a waiting thread the reply.)

- [ ] **Step 3: Run both to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_ipc.py tests/test_cli.py -q`
Expected: the new tests fail (`unknown command 'story.list'`, argparse errors).

- [ ] **Step 4: `harness/ipc.py`**

Replace `make_handler` with a version that adds the story commands and the verbs log:

```python
def make_handler(app_store):
    """Command table. Names mirror the CLI: <noun>.<verb>."""
    def story_cmd(cmd: str, a: dict):
        stories, contexts = app_store.stories, app_store.contexts
        verb = cmd.split(".", 1)[1]
        if verb == "list":
            return stories.list()
        if verb == "show":
            row = stories.get(a["key"])
            if not row:
                raise KeyError(a["key"])
            key = row["key"]
            return {**row, "comments": stories.comments(key), "cast": stories.cast(key),
                    "contexts": [c for c in contexts.summaries() if c["storyKey"] == key]}
        if verb == "create":
            return stories.get(stories.create(a["title"], a.get("description", "")))
        if verb == "start":
            chr_id = stories.start(a["key"], a.get("note", ""), a.get("role", ""))
            return {**stories.get(a["key"]), "character": chr_id}
        ch = a.get("character", "")
        if verb == "yield":
            return stories.cast_yield(ch, a["kind"], a["body"], a.get("options") or [], a.get("thread", ""))
        if verb == "recap":
            return stories.cast_recap(ch, a["body"])
        if verb == "comment":
            if ch:
                return stories.cast_comment(ch, a["body"], a.get("thread", ""))
            return stories.comment(a["key"], a["body"], a.get("thread", ""))
        if verb == "proceed":
            if ch:
                return stories.cast_proceed(ch, a.get("note", ""))
            stories.proceed(a["key"], a.get("note", ""))
            return stories.get(a["key"])
        author = {"approve": stories.approve, "back": stories.backToPlanning, "cancel": stories.cancel, "reopen": stories.reopen}.get(verb)
        if author is not None:
            author(a["key"], a.get("note", ""))
            return stories.get(a["key"])
        raise ValueError(f"unknown command {cmd!r}")

    def h(cmd: str, a: dict):
        contexts, roles, layout = app_store.contexts, app_store.roles, app_store.layout
        if cmd == "ping":
            return {"pid": os.getpid()}
        if cmd == "role.list":
            return roles.roles
        if cmd.startswith("story."):
            ch = a.get("character", "")
            if not ch:
                return story_cmd(cmd, a)
            logged = {k: v for k, v in a.items() if k != "character"}
            try:
                result = story_cmd(cmd, a)
            except Exception as e:
                app_store.stories.log_verb(ch, cmd.split(".", 1)[1], logged, False, f"{type(e).__name__}: {e}")
                raise
            app_store.stories.log_verb(ch, cmd.split(".", 1)[1], logged, True)
            return result
        # … the context.*, task.*, layout.open branches from Task 4 stay here unchanged …
        raise ValueError(f"unknown command {cmd!r}")
    return h
```

- [ ] **Step 5: `harness/cli.py`**

Add the `story` noun. Parser:

```python
    st = sub.add_parser("story").add_subparsers(dest="verb", required=True)
    st.add_parser("list")
    st.add_parser("show").add_argument("key", nargs="?", default=os.environ.get("HARNESS_STORY_KEY", ""))
    c = st.add_parser("create"); c.add_argument("--title", required=True); c.add_argument("--description", default="")
    s = st.add_parser("start"); s.add_argument("key"); s.add_argument("--note", default=""); s.add_argument("--role", default="")
    y = st.add_parser("yield"); y.add_argument("--question", action="store_true"); y.add_argument("--handoff", action="store_true")
    y.add_argument("--body", required=True); y.add_argument("--options", default=""); y.add_argument("--thread", default="")
    pr = st.add_parser("proceed"); pr.add_argument("key", nargs="?", default=""); pr.add_argument("--note", default="")
    st.add_parser("recap").add_argument("--body", required=True)
    cm = st.add_parser("comment"); cm.add_argument("--body", required=True); cm.add_argument("--thread", default=""); cm.add_argument("--story", default=os.environ.get("HARNESS_STORY_KEY", ""))
    rp = st.add_parser("reply"); rp.add_argument("key"); rp.add_argument("--body", required=True); rp.add_argument("--thread", default="")
    for v in ("approve", "back", "cancel", "reopen"):
        x = st.add_parser(v); x.add_argument("key"); x.add_argument("--note", default="")
```

Dispatch:

```python
    def character() -> str:
        ch = os.environ.get("HARNESS_CHARACTER_ID", "")
        if not ch:
            sys.exit("HARNESS_CHARACTER_ID is not set (run this inside a character)")
        return ch

    elif a.noun == "story":
        ch = os.environ.get("HARNESS_CHARACTER_ID", "")
        if a.verb == "list": out(request("story.list", {}), a.json)
        elif a.verb == "show": out(request("story.show", {"key": a.key}), a.json)
        elif a.verb == "create": out(request("story.create", {"title": a.title, "description": a.description}), a.json)
        elif a.verb == "start": out(request("story.start", {"key": a.key, "note": a.note, "role": a.role}), a.json)
        elif a.verb == "yield":
            if a.question == a.handoff:
                sys.exit("yield needs exactly one of --question / --handoff")
            opts = [o.strip() for o in a.options.split(",") if o.strip()]
            out(request("story.yield", {"character": character(), "kind": "question" if a.question else "handoff",
                                        "body": a.body, "options": opts, "thread": a.thread}), a.json)
        elif a.verb == "recap": out(request("story.recap", {"character": character(), "body": a.body}), a.json)
        elif a.verb == "proceed":
            args = {"character": ch, "note": a.note} if ch and not a.key else {"key": a.key, "note": a.note}
            out(request("story.proceed", args), a.json)
        elif a.verb == "comment":
            args = {"character": ch, "body": a.body, "thread": a.thread} if ch else {"key": a.story, "body": a.body, "thread": a.thread}
            out(request("story.comment", args), a.json)
        elif a.verb == "reply": out(request("story.comment", {"key": a.key, "body": a.body, "thread": a.thread}), a.json)
        else: out(request(f"story.{a.verb}", {"key": a.key, "note": a.note}), a.json)
```

`out()`'s column list becomes `("id", "key", "name", "phase", "ball", "status", "title", "storyKey", "owner", "kind", "model")`; when a dict has `comments`, print each as `[{authorName}/{kind}] {body}` after the scalar fields (extend the existing transcript-style branch: skip `comments`, `cast`, `contexts`, `transcript` keys in the scalar loop; print comments and transcript rows afterwards).

- [ ] **Step 6: `harness/__main__.py`, `store.py`, `.gitignore`, test harnesses**

`build()`:

```python
    from harness.stories import StoryStore
    from harness.workspace import Workspace
    …
    ws_dir = Path(os.environ.get("HARNESS_WORKSPACE") or ROOT)
    workspace = Workspace.open_or_create(ws_dir)
    if not workspace.repos and (ws_dir / ".git").exists():
        workspace.add_repo(ws_dir)
    data_dir = workspace.local_dir
    session = Session(Path(os.environ.get("HARNESS_SESSION") or data_dir / "session.json"))
    layout_store = LayoutStore(session)
    content = ContentRegistry(QML_DIR)
    roles = RoleStore(data_dir)
    contexts = ContextStore(ROOT, data_dir / "contexts", roles, workspace_dir=workspace.dir)
    tasks = TaskStore(data_dir, contexts)
    stories = StoryStore(workspace, contexts, roles)
    notifier = Notifier()
    for s in (layout_store, roles, contexts, tasks, stories):
        s.notifier = notifier
    store = AppStore(session, layout_store, content, cfg.THEME, contexts=contexts, roles=roles, tasks=tasks,
                     stories=stories, workspace=workspace, notifier=notifier)
```

`AppStore.__init__` takes `stories=None, workspace=None`; add `@Property(QObject, constant=True) def stories(self)` and `@Property(str, constant=True) def workspaceDir(self): return str(self._workspace.dir) if self._workspace else ""`.

`.gitignore`: replace the `.harness/` and `.harness-session.json` lines with `.zharn/` (the checkout's own workspace state is not tracked while the project is experimental).

`tests/ui.py: start()` and `tests/test_agents.py: harness`: replace `HARNESS_DATA_DIR` with `HARNESS_WORKSPACE = str(OUT / f"{name}-ws")` (agents: `OUT / "agents-ws"`), `shutil.rmtree` it first, and read transcripts from `<ws>/.zharn/local/contexts/<id>.jsonl`. Remove every remaining `HARNESS_DATA_DIR` read in `__main__.py`.

- [ ] **Step 7: End-to-end through the fake agent**

`tests/fake_claude.py`: add, before the `"tool" in prompt` branch:

```python
        elif "yield-question" in prompt:
            cli = os.environ["HARNESS_CLI"].split() + ["story", "yield", "--question", "--body", "which one?", "--options", "a,b"]
            r = subprocess.run(cli, capture_output=True, text=True, env=os.environ)
            tool_turn("Bash", {"command": "zharn story yield --question …"}, (r.stdout + r.stderr).strip(), is_error=r.returncode != 0)
```

Add to `tests/test_agents.py`:

```python
def test_story_start_yield_over_cli_and_reply(harness):
    app, store, _ = harness
    key = store.stories.create("E2E", "end to end")
    chr_id = store.stories.start(key, "yield-question", "protagonist")
    ch = store.stories.character(chr_id)
    ctx = store.contexts.get(ch["live_context"])
    assert ctx.owner == chr_id and ctx.storyKey == key
    assert wait_until(lambda: store.stories.get(key)["ball"] == "author", timeout_ms=15000), store.stories.get(key)
    q = store.stories.comments(key)[-1]
    assert q["kind"] == "question" and q["structured"]["options"] == ["a", "b"] and q["authorName"] == "protagonist"
    assert store.stories.get(key)["flavor"] == "question" and store.notify.status == f"{key} needs you: question"
    assert store.stories.character(chr_id)["verbs_log"][-1]["verb"] == "yield"
    assert wait_until(lambda: ctx.status == "idle", timeout_ms=15000)
    store.stories.comment(key, "a")
    assert store.stories.get(key)["ball"] == "cast"
    assert wait_until(lambda: ctx.status == "idle" and rows(ctx)[-1]["role"] == "assistant", timeout_ms=15000)
    assert rows(ctx)[-1]["text"].startswith("echo: ")
    assert "[you] reply in #thr_" in rows(ctx)[-2]["text"]


def test_cli_story_show_over_ipc(harness):
    app, store, _ = harness
    key = store.stories.list()[-1]["key"]
    env = {**os.environ, "HARNESS_IPC": store.ipcPath}
    p = subprocess.Popen([sys.executable, "-m", "harness.cli", "--json", "story", "show", key], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, env=env, cwd=ROOT)
    assert wait_until(lambda: p.poll() is not None, timeout_ms=30000)
    out, err = p.communicate()
    assert p.returncode == 0, err
    data = json.loads(out)
    assert data["key"] == key and data["comments"] and data["cast"][0]["name"] == "protagonist" and data["contexts"]
```

- [ ] **Step 8: Run everything, commit**

```bash
QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q
git add -A harness tests .gitignore
git commit -m "Wire the workspace and StoryStore into the app; zharn story verbs over IPC/CLI with verbs_log

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Board and story UI

`StoryBoard.qml` (columns by phase, needs-you highlight and count) and `Story.qml` (edit while unstarted, Start with a role and a note, phase/ball chips, the author's action bar per cell, comments with option buttons, a composer, the cast). Minimal but complete for the main-thread flow; the fuller story page (side panel, `@`/`/call`, threads folding) is the UI plan later.

**Files:**
- Create: `qml/content/StoryBoard.qml`, `qml/content/Story.qml`, `tests/test_ui_story.py`
- Modify: `harness/content.py`, `harness/layout.py:44-47`, `qml/content/Context.qml` (story link), `qml/content/Contexts.qml`, `qml/content/Welcome.qml`, `tests/test_layout.py`, `tests/test_ui_chrome.py`, `tests/test_ui_context.py`, `tests/test_app.py:81-85`

**Interfaces:**
- Consumes: `app.stories` (`model`, `list()`, `get(key)`, `comments(key)`, `cast(key)`, `create`, `update`, `start`, `proceed`, `approve`, `backToPlanning`, `cancel`, `reopen`, `comment`), `app.roles.names()`, `app.contexts.get(id)`, `app.layout.openContent("story"|"context", key, title)`.
- Produces content kinds `board` (panel, title "Board", icon "☰", `content/StoryBoard.qml`) and `story` (title "Story", icon "☐", `content/Story.qml`). `task`/`tasks`/`task_details` are deleted from `KINDS` here (their QML files go in Task 8).
- Default layout: left `["board", "files"]` active `board`; right `["contexts"]` active `contexts` docked; bottom `["terminal", "git"]` active `terminal`, mode `strip`.
- objectNames (tests depend on them): board — `needsYouCount`, `newStoryButton`, `card_<key>`, `cardBadge_<key>`; story — `storyMissing`, `storyTitle`, `storyTitleEdit`, `storyDescriptionEdit`, `storyDescription`, `roleBox`, `startNote`, `startButton`, `storyPhase`, `storyBall`, `needsYouBanner`, `proceedButton`, `approveButton`, `backButton`, `cancelButton`, `reopenButton`, `comment_<id>`, `optionButton_<id>_<i>`, `replyInput`, `replyButton`, `castRow_<chr id>`; welcome — `welcomeOpenBoard`, `welcomeNewStory`, `welcomeContexts`, `welcomeNewContext`, `welcomeReset`.

- [ ] **Step 1: UI tests**

```python
# tests/test_ui_story.py
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
```

- [ ] **Step 2: Run to verify failure**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_ui_story.py -q -x`
Expected: fails on `newStoryButton` not found.

- [ ] **Step 3: `qml/content/StoryBoard.qml`**

```qml
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// The board: stories by phase. Stories waiting on you are highlighted, say why, sort first, and are counted.
ContentBase {
    id: board
    readonly property var columns: [
        { phase: "backlog", title: "Backlog" }, { phase: "todo", title: "To do" },
        { phase: "planning", title: "Planning" }, { phase: "implementing", title: "Implementing" }, { phase: "done", title: "Done" }
    ]
    property var rows: app.stories.list()
    readonly property int needsYouCount: rows.filter(function (r) { return r.needsYou }).length
    Connections { target: app.stories; function onStoriesChanged() { board.rows = app.stories.list() } }
    function inPhase(phase) {
        return rows.filter(function (r) { return r.phase === phase })
                   .sort(function (a, b) { return (b.needsYou - a.needsYou) || (a.createdAt - b.createdAt) })
    }

    ColumnLayout {
        anchors.fill: parent; anchors.margins: 10; spacing: 8
        RowLayout {
            Label {
                objectName: "needsYouCount"
                text: board.needsYouCount > 0 ? board.needsYouCount + " need" + (board.needsYouCount === 1 ? "s" : "") + " you" : "nothing waits on you"
                color: board.needsYouCount > 0 ? "#f0a732" : app.theme.textMuted; font.bold: board.needsYouCount > 0
            }
            Item { Layout.fillWidth: true }
            Label {
                objectName: "newStoryButton"; text: "+ new story"; color: app.theme.accent
                TapHandler { onTapped: { var k = app.stories.create("New story", ""); if (k) app.layout.openContent("story", k, k) } }
            }
        }
        Flickable {
            id: flick
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentWidth: width; contentHeight: flow.height
            ScrollBar.vertical: ScrollBar {}
            Flow {
                id: flow; width: flick.width; spacing: 10
                Repeater {
                    model: board.columns
                    delegate: Rectangle {
                        id: column
                        required property var modelData
                        readonly property var cards: board.inPhase(modelData.phase)
                        width: 220; height: col.implicitHeight + 20; radius: 6; color: app.theme.panel; border.color: app.theme.border
                        ColumnLayout {
                            id: col; spacing: 6
                            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                            Label { text: column.modelData.title + "  " + column.cards.length; color: app.theme.textMuted; font.bold: true }
                            Repeater {
                                model: column.cards
                                delegate: Rectangle {
                                    id: card
                                    required property var modelData
                                    objectName: "card_" + modelData.key
                                    Layout.fillWidth: true; height: body.implicitHeight + 16
                                    radius: 4; color: app.theme.bg
                                    border.color: modelData.needsYou ? "#f0a732" : app.theme.border; border.width: modelData.needsYou ? 2 : 1
                                    ColumnLayout {
                                        id: body; spacing: 4
                                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                                        RowLayout {
                                            Label { text: card.modelData.key; color: app.theme.accent; font.pixelSize: 11; font.bold: true }
                                            Item { Layout.fillWidth: true }
                                            Label { text: card.modelData.priority; color: app.theme.textMuted; font.pixelSize: 10 }
                                        }
                                        Label { text: card.modelData.title; color: app.theme.text; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 12 }
                                        Label {
                                            objectName: "cardBadge_" + card.modelData.key
                                            visible: card.modelData.needsYou
                                            text: "needs you · " + card.modelData.flavor; color: "#f0a732"; font.pixelSize: 10; font.bold: true
                                        }
                                        RowLayout {
                                            visible: card.modelData.castCount > 0
                                            Rectangle { width: 7; height: 7; radius: 4; color: card.modelData.workingCount > 0 ? "#3574f0" : "#5fb865" }
                                            Label {
                                                text: card.modelData.castCount + " cast" + (card.modelData.workingCount > 0 ? " · working" : "")
                                                color: app.theme.textMuted; font.pixelSize: 10
                                            }
                                        }
                                    }
                                    TapHandler { onTapped: app.layout.openContent("story", card.modelData.key, card.modelData.key + " " + card.modelData.title) }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
```

- [ ] **Step 4: `qml/content/Story.qml`**

```qml
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// A story page. tabKey = story key. Description and Start until it begins; then phase, ball, the
// actions you have right now, the comments (choices as buttons), a composer, and the cast.
ContentBase {
    id: view
    property var story: app.stories.get(tabKey)
    property var comments: app.stories.comments(tabKey)
    property var cast: app.stories.cast(tabKey)
    readonly property bool found: !!(story && story.key)
    readonly property bool started: found && story.phase !== "backlog" && story.phase !== "todo"
    readonly property bool terminal: found && (story.phase === "done" || story.phase === "canceled")
    readonly property bool mine: found && story.ball === "author"
    function refresh() { story = app.stories.get(tabKey); comments = app.stories.comments(tabKey); cast = app.stories.cast(tabKey) }
    Connections { target: app.stories; function onStoriesChanged() { view.refresh() } }
    readonly property var statusColor: ({ starting: "#f0a732", working: "#3574f0", idle: "#5fb865", failed: "#e5534b", stopped: "#868a91", none: "#868a91" })

    Label {
        objectName: "storyMissing"; visible: !view.found
        anchors.centerIn: parent; width: parent.width - 40; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
        text: "Story " + tabKey + " not found — it may have been removed, or the tab is stale."; color: app.theme.textMuted
    }

    Flickable {
        visible: view.found
        anchors.fill: parent; contentHeight: body.implicitHeight + 32; clip: true
        ScrollBar.vertical: ScrollBar {}
        ColumnLayout {
            id: body
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 16 }
            spacing: 12

            // ---- header
            RowLayout {
                spacing: 10
                Label { text: tabKey; color: app.theme.accent; font.bold: true }
                Label { objectName: "storyTitle"; visible: view.started; text: view.story.title || ""; color: app.theme.text; font.pixelSize: 18; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                TextField {
                    objectName: "storyTitleEdit"; visible: !view.started; Layout.fillWidth: true
                    text: view.story.title || ""; font.pixelSize: 18; font.bold: true; color: app.theme.text
                    onEditingFinished: if (text !== view.story.title) app.stories.update(tabKey, text, descEdit.text)
                }
                Rectangle { visible: view.started; radius: 3; color: app.theme.accentSoft; height: 20; width: phaseLabel.implicitWidth + 12
                            Label { id: phaseLabel; objectName: "storyPhase"; anchors.centerIn: parent; text: view.story.phase || ""; color: app.theme.text; font.pixelSize: 11 } }
                Rectangle { visible: view.started && !view.terminal; radius: 3; color: view.mine ? "#f0a732" : app.theme.panel; height: 20; width: ballLabel.implicitWidth + 12; border.color: app.theme.border
                            Label { id: ballLabel; objectName: "storyBall"; anchors.centerIn: parent; text: view.story.ball || ""; color: view.mine ? "black" : app.theme.textMuted; font.pixelSize: 11 } }
            }
            Label { objectName: "storyDescription"; visible: view.started; text: view.story.description || "No description."; color: app.theme.textMuted; wrapMode: Text.Wrap; Layout.fillWidth: true; textFormat: Text.MarkdownText }
            TextArea {
                id: descEdit; objectName: "storyDescriptionEdit"; visible: !view.started
                Layout.fillWidth: true; Layout.preferredHeight: 90; wrapMode: TextEdit.Wrap; color: app.theme.text
                placeholderText: "Describe the work: what, why, how you will validate it."
                text: view.story.description || ""
                background: Rectangle { color: app.theme.bg; radius: 4; border.color: descEdit.activeFocus ? app.theme.accent : app.theme.border }
                onEditingFinished: if (text !== view.story.description) app.stories.update(tabKey, view.story.title, text)
            }

            // ---- Start (unstarted only)
            RowLayout {
                visible: !view.started && view.story.phase !== "canceled"; spacing: 8
                ComboBox { id: roleBox; objectName: "roleBox"; model: app.roles.names(); Layout.preferredWidth: 180
                           Component.onCompleted: currentIndex = Math.max(0, app.roles.names().indexOf("protagonist")) }
                TextField { id: startNote; objectName: "startNote"; Layout.fillWidth: true; placeholderText: "Opening note for the protagonist (optional)"; color: app.theme.text }
                Button { objectName: "startButton"; text: "Start"; onClicked: { if (app.stories.start(tabKey, startNote.text, roleBox.currentText)) startNote.text = "" } }
            }

            // ---- needs-you banner + action bar (started only)
            Rectangle {
                objectName: "needsYouBanner"; visible: view.mine
                Layout.fillWidth: true; height: 30; radius: 4; color: "#3a2e14"; border.color: "#f0a732"
                Label { anchors.verticalCenter: parent.verticalCenter; x: 10; text: "Waiting on you: " + view.story.flavor; color: "#f0a732"; font.bold: true }
            }
            RowLayout {
                visible: view.started; spacing: 8
                Button { objectName: "proceedButton"; visible: view.story.phase === "planning" && view.mine; text: "Proceed to implementing"; onClicked: app.stories.proceed(tabKey, "") }
                Button { objectName: "approveButton"; visible: view.story.phase === "implementing" && view.mine; text: "Approve"; onClicked: app.stories.approve(tabKey, "") }
                Button { objectName: "backButton"; visible: view.story.phase === "implementing" && view.mine; text: "Back to planning"; onClicked: app.stories.backToPlanning(tabKey, "") }
                Item { Layout.fillWidth: true }
                Button { objectName: "reopenButton"; visible: view.terminal; text: "Reopen"; onClicked: app.stories.reopen(tabKey, "reopened from the story page") }
                Button { objectName: "cancelButton"; visible: !view.terminal; text: "Cancel"; onClicked: app.stories.cancel(tabKey, "") }
            }

            // ---- comments
            Label { visible: view.started; text: "Main thread"; color: app.theme.text; font.bold: true; Layout.topMargin: 8 }
            Repeater {
                model: view.comments
                delegate: Rectangle {
                    id: row
                    required property int index
                    required property var modelData
                    readonly property var options: (modelData.structured && modelData.structured.options) ? modelData.structured.options : []
                    readonly property bool answerable: options.length > 0 && view.mine && index === view.comments.length - 1
                    objectName: "comment_" + modelData.id
                    Layout.fillWidth: true; height: ccol.implicitHeight + 16; radius: 4
                    color: modelData.author === "human" ? app.theme.accentSoft : (modelData.kind === "system" ? "transparent" : app.theme.panel)
                    border.color: modelData.kind === "system" ? "transparent" : app.theme.border
                    ColumnLayout {
                        id: ccol; spacing: 4
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                        RowLayout {
                            Label { text: row.modelData.authorName; color: app.theme.text; font.bold: true; font.pixelSize: 11 }
                            Label { text: row.modelData.kind; color: row.modelData.kind === "question" || row.modelData.kind === "handoff" ? "#f0a732" : app.theme.textMuted; font.pixelSize: 10 }
                            Item { Layout.fillWidth: true }
                            Label { visible: !!(row.modelData.structured && row.modelData.structured.transition); text: "→ " + (row.modelData.structured && row.modelData.structured.transition ? row.modelData.structured.transition.to.join("/") : ""); color: app.theme.textMuted; font.pixelSize: 10 }
                        }
                        Text { text: row.modelData.body; textFormat: Text.MarkdownText; wrapMode: Text.Wrap; Layout.fillWidth: true; color: row.modelData.kind === "system" ? app.theme.textMuted : app.theme.text; font.family: app.theme.fontFamily; font.pixelSize: app.theme.fontSize }
                        Flow {
                            visible: row.options.length > 0; Layout.fillWidth: true; spacing: 6
                            Repeater {
                                model: row.options
                                delegate: Button {
                                    required property int index
                                    required property var modelData
                                    objectName: "optionButton_" + row.modelData.id + "_" + index
                                    text: modelData; enabled: row.answerable
                                    onClicked: app.stories.comment(tabKey, modelData)
                                }
                            }
                        }
                    }
                }
            }

            // ---- composer
            RowLayout {
                visible: view.started && !view.terminal; spacing: 8
                TextArea {
                    id: reply; objectName: "replyInput"; Layout.fillWidth: true; Layout.preferredHeight: 70
                    placeholderText: view.mine ? "Reply to the protagonist  (Ctrl+Enter)" : "Comment for the protagonist — arrives between turns  (Ctrl+Enter)"
                    wrapMode: TextEdit.Wrap; color: app.theme.text
                    background: Rectangle { color: app.theme.bg; radius: 4; border.color: reply.activeFocus ? app.theme.accent : app.theme.border }
                    Keys.onPressed: (e) => { if ((e.key === Qt.Key_Return || e.key === Qt.Key_Enter) && (e.modifiers & Qt.ControlModifier)) { post(); e.accepted = true } }
                    function post() { if (text.trim().length) { app.stories.comment(tabKey, text); text = "" } }
                }
                Button { objectName: "replyButton"; text: view.mine ? "Reply" : "Comment"; enabled: reply.text.trim().length > 0; onClicked: reply.post() }
            }

            // ---- cast
            Label { visible: view.cast.length > 0; text: "Cast"; color: app.theme.text; font.bold: true; Layout.topMargin: 8 }
            Repeater {
                model: view.cast
                delegate: Rectangle {
                    required property var modelData
                    objectName: "castRow_" + modelData.id
                    Layout.fillWidth: true; height: 34; radius: 4; color: app.theme.panel; border.color: app.theme.border
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 8
                        Rectangle { width: 8; height: 8; radius: 4; color: view.statusColor[modelData.contextStatus] || "gray" }
                        Label { text: modelData.name + (modelData.id === view.story.protagonist ? "  · protagonist" : ""); color: app.theme.text; Layout.fillWidth: true }
                        Label { text: modelData.role; color: app.theme.textMuted; font.pixelSize: 11 }
                        Label { text: modelData.contextStatus; color: app.theme.textMuted; font.pixelSize: 11 }
                    }
                    TapHandler { onTapped: if (modelData.live_context) app.layout.openContent("context", modelData.live_context, tabKey + " · " + modelData.name) }
                }
            }
        }
    }
}
```

- [ ] **Step 5: Kinds, layout defaults, links**

`harness/content.py` KINDS:

```python
KINDS: dict[str, dict] = {
    "board":    {"title": "Board",    "qml": "content/StoryBoard.qml", "panel": True,  "icon": "☰"},
    "contexts": {"title": "Contexts", "qml": "content/Contexts.qml",   "panel": True,  "icon": "≡"},
    "files":    {"title": "Files",    "qml": "content/Files.qml",      "panel": True,  "icon": "▤"},
    "git":      {"title": "Git",      "qml": "content/Git.qml",        "panel": True,  "icon": "⎇"},
    "terminal": {"title": "Terminal", "qml": "content/Terminal.qml",   "panel": True,  "icon": ">_"},
    "welcome":  {"title": "Welcome",  "qml": "content/Welcome.qml",    "panel": False, "icon": "★"},
    "story":    {"title": "Story",    "qml": "content/Story.qml",      "panel": False, "icon": "☐"},
    "context":  {"title": "Context",  "qml": "content/Context.qml",    "panel": False, "icon": "💬"},
    "document": {"title": "Document", "qml": "content/Document.qml",   "panel": False, "icon": "▢"},
}
```

`harness/layout.py` default docks:

```python
            "left": {"panels": ["board", "files"], "active": "board", "mode": "docked", "size": 280},
            "right": {"panels": ["contexts"], "active": "contexts", "mode": "docked", "size": 320},
            "bottom": {"panels": ["terminal", "git"], "active": "terminal", "mode": "strip", "size": 220},
```

`qml/content/Context.qml`: `contextStoryLink` opens `("story", storyKey, storyKey)`. `qml/content/Welcome.qml`: `welcomeOpenBoard` → `showPanel("board")` text "Board"; `welcomeNewTask` → `welcomeNewStory` (`app.stories.create("New story", "")` then `openContent("story", k, k)`); second paragraph becomes "Work is a story. Open the board, write one, press Start, and answer the protagonist when the ball is yours."

Tests: `tests/test_layout.py` — `"tasks"` → `"board"`, `"task_details"` → `"contexts"` (lines 173-176 move `contexts` to the left), lines 260-264 use `"git"` on the bottom instead of `"contexts"` (`show_panel("git") == "bottom"`). `tests/test_ui_chrome.py` — `stripButton_tasks` → `stripButton_board`, `dockPanel_tasks` → `dockPanel_board`, `test_welcome_new_task_creates_and_opens_one` → `test_welcome_new_story_creates_and_opens_one` (`app.stories`, `tab_story_<key>`), `test_welcome_open_board_shows_the_task_board` expects `active: "board"`, contexts tests now look at `docks["right"]`. `tests/test_ui_context.py` — the story-link test expects `tab_story_ABC-1`; `open_context` spawns with `story_key=<a created story key>` (create one in the fixture: `ui.store.stories.create("ctx home", "")`). `tests/test_app.py:81-85` — `togglePanel("left", "board")`. `tests/test_ui_task.py` is deleted in Task 8; for now it will fail — **delete it in this task** (its `TaskView`/`TaskBoard` kinds no longer exist), and `test_agents.py::test_context_tab_renders_and_screenshot` opens `("story", key, key)` for a created story instead of `("task", "ABC-1", …)`.

- [ ] **Step 6: Run, screenshot, commit**

```bash
QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest tests/test_ui_story.py tests/test_ui_chrome.py tests/test_ui_context.py tests/test_layout.py tests/test_app.py -q
QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q
git add -A harness qml tests
git commit -m "UI: story board by phase with needs-you, story page with Start / action bar / comments / composer / cast

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Remove the task model

Nothing task-shaped survives: no `TaskStore`, no `status`, no `task.*` verbs, no `.harness/`. The smoke hook starts a story instead of dispatching a task.

**Files:**
- Delete: `harness/tasks.py`, `tests/test_tasks.py`, `qml/content/TaskBoard.qml`, `qml/content/TaskView.qml`, `qml/content/TaskDetails.qml`, the `.harness/` directory in the checkout (`rm -rf .harness`; it is gitignored and its contents are worthless per DESIGN.md §0)
- Modify: `harness/__main__.py`, `harness/store.py`, `harness/ipc.py`, `harness/cli.py`, `harness/shell.py:25-27`, `tests/test_ipc.py`, `tests/test_cli.py`, `tests/test_agents.py`, `tests/test_ui_chrome.py`

**Interfaces:**
- Consumes: everything from Tasks 4–7.
- Produces: `AppStore` without `tasks`; IPC without `task.*`; CLI without the `task` noun; `build()` without `TaskStore`; `HARNESS_SMOKE_PROMPT` creates a story titled "smoke", starts it with the prompt as the note (role `HARNESS_SMOKE_ROLE`, default `protagonist`), opens the protagonist's context tab, and exits when that context settles, printing `[smoke] …` lines as before.

- [ ] **Step 1: Delete the files and every reference**

```bash
git rm -q harness/tasks.py tests/test_tasks.py qml/content/TaskBoard.qml qml/content/TaskView.qml qml/content/TaskDetails.qml
rm -rf .harness
```

Then:

| File | Change |
|---|---|
| `harness/shell.py` | drop `"harness.tasks"` from `RELOADABLE` |
| `harness/store.py` | drop the `tasks` kwarg, `_tasks`, and the `tasks` property |
| `harness/__main__.py` | drop the `TaskStore` import/instance/wiring; smoke hook: `key = store.stories.create("smoke", "smoke test"); chr_id = store.stories.start(key, smoke_prompt, os.environ.get("HARNESS_SMOKE_ROLE", "protagonist")); cid = store.stories.character(chr_id)["live_context"]; store.layout.openContent("context", cid, key); context = store.contexts.get(cid)` and the existing `settled()` loop over `context` |
| `harness/ipc.py` | delete the `task.*` branches and the `tasks` unpack |
| `harness/cli.py` | delete the `task` subparser and its dispatch |
| `tests/test_ipc.py` | delete `FakeTasks` and every `task.*` test; `FakeAppStore` no longer has `tasks` |
| `tests/test_cli.py` | delete the `task …` tests |
| `tests/test_agents.py` | `test_roles_and_demo_tasks` → `test_roles_and_empty_board` (asserts `store.stories.model.count() == 0` on the fresh workspace and the role assertions); delete `test_task_dispatch_sets_in_progress_and_counts`; `test_cli_over_ipc` calls `story create --title T`, `story show <key>`, `context list --story <key>` instead of the task commands |
| `tests/test_ui_chrome.py` | nothing should reference tasks after Task 7; verify |

- [ ] **Step 2: Verify nothing task-shaped remains**

```bash
grep -rn -i "task" harness qml tests --include=*.py --include=*.qml
```
Expected: no output. (`docs/` keeps the vocabulary map; that is fine.)

- [ ] **Step 3: Full suite, real boot, commit**

```bash
QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q
HARNESS_EXIT_AFTER_MS=2500 HARNESS_SCREENSHOT=tests/_out/boot.png QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m harness
ls .zharn/workspace.toml .zharn/local/session.json tests/_out/boot.png
git status --short   # .zharn/ must NOT appear (gitignored)
git add -A harness qml tests
git commit -m "Remove the task model: TaskStore, task views, task.* verbs, .harness/

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: the boot prints `[hot] QML generation 1 in … ms`, exits 0, and `.zharn/workspace.toml` contains `prefix = "ZHAR"` and one `[[repos]]` with `path = "."`.

---

### Task 9: Docs and status

**Files:**
- Modify: `README.md` (Agents + Test sections), `docs/DESIGN.md` §8

- [ ] **Step 1: README**

Replace the whole `## Agents` section with:

```markdown
## Stories, characters, contexts

> **Experimental — no backward compatibility** (DESIGN.md §0): on-disk formats, module names,
> env vars and CLI verbs change without migration until further notice.

Work is a **story** ([docs/AGENT-MODEL.md](docs/AGENT-MODEL.md)); you are its author, agents are its
cast. Write a story on the board, press **Start**: the harness casts a **protagonist** from a role
(`harness/config_def.py: DEFAULT_ROLES`) on a fresh **context** (one `claude -p --output-format
stream-json` process) and hands it the brief. The story's state is `(phase, ball)`: phase moves only
through the actions on the story page (Proceed, Approve, Back to planning, Cancel, Reopen) and the
protagonist's `yield`/`proceed`; nobody sets a status. When the ball is yours the board says why.

Inside a character `HARNESS_CLI`, `HARNESS_CONTEXT_ID`, `HARNESS_STORY_KEY`, `HARNESS_CHARACTER_ID`,
`HARNESS_WORKSPACE` and `HARNESS_IPC` are set:

    $HARNESS_CLI story yield --question --body "pg or sqlite?" --options pg,sqlite   # ball → author
    $HARNESS_CLI story yield --handoff --body "what changed / how verified / where to look"
    $HARNESS_CLI story proceed | recap --body … | comment --body … | show

The current slice drives the main thread only. Friends, minions, sub-stories, inbox delivery,
auto-yield, recap/recast and repo checks are the next plan
([docs/superpowers/plans/](docs/superpowers/plans/)); the full mechanics are in the
[lifecycle spec](docs/superpowers/specs/2026-08-28-story-lifecycle-design.md).

**Where things live.** The checkout you run from is opened as a **workspace**
([spec](docs/superpowers/specs/2026-08-31-workspace-model-design.md)): `.zharn/workspace.toml`
(id, prefix, repos), `.zharn/stories/<key>/{story.json,threads.jsonl}` (the durable record), and
`.zharn/local/` (contexts, characters, session — machine-local). Set `HARNESS_WORKSPACE` to open a
different directory. Point `HARNESS_CLAUDE_CMD` at another CLI to substitute the provider
(`tests/fake_claude.py` speaks the protocol).
```

In `## Test`, update the count to the real number after Task 8 and the layer list:
`tests/test_<module>.py — unit tests per Python module (workspace, lifecycle, stories, contexts, roles, stream interpreter, models, IPC, CLI, watcher, layout, notifier, process wrapper)`; the UI line's examples become `startButton`, `card_ZHAR-3`, `stripButton_board`, `optionButton_<comment>_<i>`. Smoke-test line: `HARNESS_SMOKE_PROMPT="say pong"` *starts a story* on the checkout's workspace.

- [ ] **Step 2: DESIGN.md §8**

Prepend a status line: `Status 2026-08-31: foundation shipped per docs/superpowers/plans/2026-08-31-story-foundation.md — workspace storage (.zharn/), lifecycle state machine, stories/characters/contexts/roles stores, zharn story verbs, board + story + context UI over the main thread; the old task/thread/preset model is gone (§0).` Mark step 3 as **partly done (main thread; characters/delivery next)** and step 6 as **partly done (workspace storage; start screen, repos, worktrees next)**.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/DESIGN.md
git commit -m "Docs: stories/characters/contexts in the README, status in DESIGN §8

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
