# Repos and Environments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A character can register a repo and ask for a place to work in it — a managed worktree cut from its parent environment, or, for a sub-story, the parent's environment itself — and an implementing handoff carries that repo's check results. A root story never works on the main checkout.

**Architecture:** A new `harness/environments.py` owns git and the `(story, repo)` records in `local/environments.json`: `EnvironmentStore.open` resolves the parent chain (sub-story → parent story → main checkout) and creates worktrees lazily; `register_repo` handles paths and URL clones. `StoryStore` wires it in: the story's `env_mode` (`shared` is sub-story only; root stories are always `worktree`), the character's `environment`, inheritance on call/fork/recast, and a `placement` hook that `ContextStore` calls at every spawn to pick the working directory. Checks run in the CLI inside the character's turn (`env.checks` → run → `story.yield --handoff` with results), governed by `config.HANDOFF_CHECKS`. Scratch becomes the default workspace, created under appdata.

**Tech Stack:** Python ≥3.10, PySide6 6.11, git ≥2.20 (`git worktree`), pytest, `tests/fake_claude.py`.

**Spec:** `docs/superpowers/specs/2026-08-31-workspace-model-design.md` — §2.2 (Scratch), §3 (repos), §4 (environments, all of it), §6 (storage), §8 (CLI), §10 (tests). Read §4 before every task; it is two pages.

## Global Constraints

- **No backward compatibility** (DESIGN.md §0): no migration of `story.json` or `characters.json`; new keys read with `.get()` defaults. `config.CHECK_CMD` does not exist and is not added.
- **Nobody sets status.** Phases and turns change only through `lifecycle.step`.
- Every QML-facing mutation is an `@intent`; every cast verb goes through `harness/ipc.py` and is logged to `verbs_log` by the wrapper in `make_handler.h`.
- The harness process never blocks on a test suite: checks run in `harness/cli.py`, inside the character's turn. `git worktree add`, `git clone`, and `setup` do run in-process (they are short; a clone is the character's own choice).
- Character records gain one key: `environment` (repo name or `None`). Story records gain `env_mode` (`"worktree"` | `"shared"`; `shared` only on a sub-story — a root story never works on the main checkout, spec §4.2) and `repos` (list of repo names, derived from environments, persisted for the board).
- Environment records (`local/environments.json`, keyed `"<story>:<repo>"`): `{story, repo, kind, path, branch, parent, created, setup_done}`. `path`/`branch` are `""` for `shared`; the resolved view (`EnvironmentStore.describe`) fills them in. **Never store a resolved path for a shared record** — Relocate must keep working.
- Tests run with `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q`. Git tests use real temporary repos created by the `make_repo` helper below; no network (URL clones use `file://`). Full suite green at the end of every task.
- Commit after every task, message style `Component: what changed`, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **Out of scope:** story move (§5.3), start screen and workspace page QML (UI thread — briefed at the end), Approve's effect on environments (§11), Windows path handling beyond what `pathlib` gives for free.

## File map

| File | Change |
|---|---|
| `harness/workspace.py` | `_store_path`, `unregister`, `relocate`, `appdata_dir`, `Workspace.scratch`. |
| `harness/environments.py` | **New.** `git`, `head_branch`, `register_repo`, `EnvError`, `EnvironmentStore`. |
| `harness/lifecycle.py` | `Story.env_mode`, `Story.repos`. |
| `harness/stories.py` | `EnvironmentStore` wiring; `create(env_mode)`; `cast_create(shared)`; `cast_env_open/list`, `cast_repo_add`, `repo_list`, `env_checks`; `_placement`; environment inheritance in `_cast`/`openThread`; recycle at turn end; rows; system prompt line. |
| `harness/contexts.py` | `ContextStore.placement`; `Context._spawn` uses it; `Context.recycle`, `proc_cwd`. |
| `harness/config_def.py` | `HANDOFF_CHECKS`, `CHECKS_OUTPUT_LIMIT`, `CHECKS_TIMEOUT_S`; `CHARACTER_SYSTEM_PROMPT` `{environment}` + verbs. |
| `harness/ipc.py`, `harness/cli.py` | `repo add/list`, `env open/list`, `env.checks`, `story create --shared`, `story yield --despite-checks` + `run_checks`. |
| `harness/__main__.py` | Scratch as the default workspace. |
| `run.bat` | Pin `HARNESS_WORKSPACE` to the checkout until the start screen exists. |
| `tests/fake_claude.py` | `HARNESS_REPO`/`HARNESS_ENV` in `harness_env`; `yield-handoff` behaviour. |
| `tests/test_workspace.py`, `tests/test_environments.py` (new), `tests/test_stories.py`, `tests/test_contexts_unit.py`, `tests/test_ipc.py`, `tests/test_cli.py` | Per task. |
| `docs/DESIGN.md` §8 | Status. |

## Shared test helper

Both `tests/test_environments.py` and the additions to `tests/test_workspace.py` need real git repos. Put this in **`tests/gitfix.py`** (Task 2 creates it; Task 1 does not need git):

```python
"""Real temporary git repositories for environment tests. No network, no user config needed."""
import subprocess
from pathlib import Path

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false"]


def run(cwd: Path, *args: str) -> str:
    r = subprocess.run(GIT + list(args), cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, f"git {' '.join(args)} failed: {r.stderr}"
    return r.stdout.strip()


def make_repo(path: Path, branch: str = "main") -> Path:
    """A repo at `path` with one commit on `branch` containing README.md."""
    path.mkdir(parents=True, exist_ok=True)
    run(path, "init", "-b", branch)
    (path / "README.md").write_text("hello\n")
    run(path, "add", "README.md")
    run(path, "commit", "-q", "-m", "init")
    return path


def commit_file(path: Path, name: str, text: str = "x\n") -> None:
    (path / name).write_text(text)
    run(path, "add", name)
    run(path, "commit", "-q", "-m", f"add {name}")


def branch_of(path: Path) -> str:
    return run(path, "rev-parse", "--abbrev-ref", "HEAD")
```

---

### Task 1: Workspace — unregister, relocate, appdata, Scratch

**Files:**
- Modify: `harness/workspace.py`
- Modify: `harness/__main__.py` (the `ws_dir = …` block in `build`)
- Modify: `run.bat`
- Test: `tests/test_workspace.py`

**Interfaces:**
- Produces:
  ```python
  def appdata_dir() -> Path                      # ZHARN_APPDATA, else %APPDATA%/zharn or $XDG_DATA_HOME|~/.local/share /zharn
  class Workspace:
      def _store_path(self, path: Path) -> str   # relative posix if inside the workspace dir, else absolute
      def unregister(self, name: str) -> None    # KeyError if unknown; never touches files
      def relocate(self, name: str, path: Path) -> dict
      @classmethod
      def scratch(cls, zharn_root: Path) -> "Workspace"   # <appdata>/scratch, name Scratch, prefix SCR, repo "zharn" registered
  ```

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_workspace.py`:

```python
# ---------------------------------------------------------------- unregister / relocate (spec §3.2, §3.3)

def test_unregister_removes_the_record_and_leaves_files(tmp_path):
    ws = Workspace.create(tmp_path / "ws")
    (tmp_path / "ws" / "client").mkdir()
    ws.add_repo(tmp_path / "ws" / "client")
    ws.unregister("client")
    assert ws.repos == [] and (tmp_path / "ws" / "client").is_dir()
    assert Workspace.open(tmp_path / "ws").repos == []
    with pytest.raises(KeyError):
        ws.unregister("client")


def test_relocate_rewrites_the_path_and_status_recovers(tmp_path):
    ws = Workspace.create(tmp_path / "ws")
    ws.add_repo(tmp_path / "elsewhere", name="lib")   # does not exist yet
    assert ws.repo_status("lib") == "missing"
    (tmp_path / "ws" / "lib").mkdir()
    rec = ws.relocate("lib", tmp_path / "ws" / "lib")
    assert rec["path"] == "lib" and ws.repo_status("lib") == "ok"
    assert Workspace.open(tmp_path / "ws").repo("lib")["path"] == "lib"


# ---------------------------------------------------------------- appdata + Scratch (spec §2.2)

def test_appdata_dir_honours_override(monkeypatch, tmp_path):
    from harness.workspace import appdata_dir
    monkeypatch.setenv("ZHARN_APPDATA", str(tmp_path / "ad"))
    assert appdata_dir() == tmp_path / "ad"
    monkeypatch.delenv("ZHARN_APPDATA")
    assert appdata_dir().name == "zharn"


def test_scratch_is_created_once_with_zharn_registered(monkeypatch, tmp_path):
    monkeypatch.setenv("ZHARN_APPDATA", str(tmp_path / "ad"))
    root = tmp_path / "zharn-src"
    root.mkdir()
    ws = Workspace.scratch(root)
    assert ws.dir == (tmp_path / "ad" / "scratch").resolve()
    assert ws.name == "Scratch" and ws.prefix == "SCR"
    assert [r["name"] for r in ws.repos] == ["zharn"] and ws.repo_path(ws.repo("zharn")) == root.resolve()
    again = Workspace.scratch(root)
    assert again.id == ws.id and [r["name"] for r in again.repos] == ["zharn"]


def test_scratch_is_never_special_cased():
    """§2.2: no code may test for Scratch. Only its creation (workspace.py) and the call into it may say the word."""
    import re
    from pathlib import Path
    harness = Path(__file__).resolve().parent.parent / "harness"
    for f in harness.glob("*.py"):
        if f.name in ("workspace.py", "config_def.py"):   # creation; prose in prompts ("scratch conversation")
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if re.search(r"scratch", line, re.I):
                assert "Workspace.scratch(" in line, f"{f.name}: {line.strip()}"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_workspace.py -q -k "unregister or relocate or appdata or scratch"`
Expected: FAIL — `AttributeError: 'Workspace' object has no attribute 'unregister'`, `ImportError: cannot import name 'appdata_dir'`.

- [ ] **Step 3: Implement**

In `harness/workspace.py`, add `import os` to the imports, then:

```python
def appdata_dir() -> Path:
    """<appdata>/zharn (spec §2.2). ZHARN_APPDATA overrides — tests keep it in a temp dir."""
    override = os.environ.get("ZHARN_APPDATA")
    if override:
        return Path(override)
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "zharn"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "zharn"
```

Replace the body of `add_repo` so it uses a shared `_store_path`, and add the new methods after `repo_status`:

```python
    def _store_path(self, path: Path) -> str:
        path = Path(path).resolve()
        try:
            return path.relative_to(self.dir).as_posix() or "."
        except ValueError:
            return str(path)

    def add_repo(self, path: Path, name: str = "", checks: str = "", setup: str = "", base: str = "") -> dict:
        path = Path(path).resolve()
        name = name or path.name
        if self.repo(name) is not None:
            raise ValueError(f"repo {name!r} is already registered")
        record = {"name": name, "path": self._store_path(path), "checks": checks, "setup": setup, "base": base}
        self._data["repos"].append(record)
        self.save()
        return dict(record)

    def unregister(self, name: str) -> None:
        """§3.2: author-only; never deletes files — worktrees stay and work again once re-registered."""
        if self.repo(name) is None:
            raise KeyError(name)
        self._data["repos"] = [r for r in self._data["repos"] if r["name"] != name]
        self.save()

    def relocate(self, name: str, path: Path) -> dict:
        """§3.3 Relocate: rewrite a missing repo's path. Nothing else changes."""
        for r in self._data["repos"]:
            if r["name"] == name:
                r["path"] = self._store_path(path)
                self.save()
                return dict(r)
        raise KeyError(name)

    # ---------------------------------------------------------------- Scratch (spec §2.2)
    @classmethod
    def scratch(cls, zharn_root: Path) -> "Workspace":
        """The workspace zharn opens when none is given: <appdata>/zharn/scratch, with zharn's own checkout
        registered as `zharn`. Ordinary in every other way — nothing may test for it."""
        d = appdata_dir() / "scratch"
        ws = cls.open(d) if cls.exists(d) else cls.create(d, name="Scratch", prefix="SCR")
        if ws.repo("zharn") is None:
            ws.add_repo(Path(zharn_root), name="zharn")
        return ws
```

In `harness/__main__.py`, replace

```python
    ws_dir = Path(os.environ.get("HARNESS_WORKSPACE") or ROOT)
    workspace = Workspace.open_or_create(ws_dir)
    if not workspace.repos and (ws_dir / ".git").exists():
        workspace.add_repo(ws_dir)
```

with

```python
    ws_env = os.environ.get("HARNESS_WORKSPACE")
    if ws_env:   # an explicit workspace (tests, run.bat); a git repo opened as a workspace registers itself as "."
        ws_dir = Path(ws_env)
        workspace = Workspace.open_or_create(ws_dir)
        if not workspace.repos and (ws_dir / ".git").exists():
            workspace.add_repo(ws_dir)
    else:
        workspace = Workspace.scratch(ROOT)
```

In `run.bat`, after `cd /d "%~dp0"` add:

```bat
rem Until the start screen exists, open this checkout as the workspace (unset to get Scratch).
if not defined HARNESS_WORKSPACE set "HARNESS_WORKSPACE=%~dp0."
```

- [ ] **Step 4: Run the tests, then the full suite**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_workspace.py -q` then the full suite.
Expected: PASS. (The full suite still sets `HARNESS_WORKSPACE` in `test_agents.py` and `tests/ui.py`, so nothing opens Scratch.)

- [ ] **Step 5: Commit**

```bash
git add harness/workspace.py harness/__main__.py run.bat tests/test_workspace.py
git commit -m "Workspace: unregister, relocate, appdata dir; Scratch is the default workspace with zharn registered

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: environments.py — git helpers, register_repo, root environments

**Files:**
- Create: `harness/environments.py`
- Create: `tests/gitfix.py` (the helper above)
- Create: `tests/test_environments.py`

**Interfaces:**
- Produces:
  ```python
  class EnvError(Exception): ...
  def git(cwd: Path, *args: str) -> str                     # stdout stripped; EnvError with stderr on failure
  def head_branch(path: Path) -> str                         # current branch; short sha when detached
  def register_repo(ws, spec: str, name="", checks="", setup="", base="") -> dict   # path or URL; base defaults to head_branch
  def env_key(story: str, repo: str) -> str                  # "ZH-1:client"
  class EnvironmentStore:
      def __init__(self, workspace, story_info: Callable[[str], tuple[str | None, str]])  # key → (parent_story, env_mode)
      def get(self, story, repo) -> dict | None              # the stored record
      def records(self, story) -> list[dict]
      def path(self, rec) -> Path                            # resolved through the parent chain
      def effective_branch(self, rec) -> str
      def describe(self, rec) -> dict                        # {**rec, path, branch resolved, checks}
      def open(self, story, repo) -> dict                    # describe() of the (created) record; EnvError "a root story cannot be shared"
  ```

- [ ] **Step 1: Write the failing tests**

`tests/test_environments.py`:

```python
"""Environments (workspace spec §4): records, the parent chain, lazy worktrees, setup, checks plumbing.
Real temporary git repos via tests/gitfix.py; no network."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gitfix import make_repo, commit_file, branch_of, run  # noqa: E402

from harness.environments import EnvError, EnvironmentStore, env_key, head_branch, register_repo  # noqa: E402
from harness.workspace import Workspace  # noqa: E402


@pytest.fixture
def ws(tmp_path):
    return Workspace.create(tmp_path / "ws", prefix="ZH")


@pytest.fixture
def repo(tmp_path, ws):
    """`client`, registered in `ws`, one commit on main."""
    p = make_repo(tmp_path / "ws" / "client")
    register_repo(ws, str(p))
    return p


class Stories:
    """story_info stand-in: key → (parent_story, env_mode)."""
    def __init__(self, **stories):
        self.stories = stories   # key → (parent, mode)

    def __call__(self, key):
        return self.stories[key]


def store(ws, **stories):
    return EnvironmentStore(ws, Stories(**stories))


# ---------------------------------------------------------------- git helpers / registration (§3.1, §3.2)

def test_head_branch_and_detached(tmp_path):
    p = make_repo(tmp_path / "r", branch="trunk")
    assert head_branch(p) == "trunk"
    run(p, "checkout", "-q", "--detach")
    assert head_branch(p) == run(p, "rev-parse", "--short", "HEAD")


def test_register_path_defaults_base_to_head_branch(tmp_path, ws):
    p = make_repo(tmp_path / "ws" / "api", branch="develop")
    rec = register_repo(ws, str(p), checks="pytest -q")
    assert rec == {"name": "api", "path": "api", "checks": "pytest -q", "setup": "", "base": "develop"}
    assert register_repo(ws, str(make_repo(tmp_path / "other")), base="main")["path"] == str(tmp_path / "other")


def test_register_rejects_non_repos(tmp_path, ws):
    (tmp_path / "ws" / "plain").mkdir()
    with pytest.raises(EnvError, match="not a git repository"):
        register_repo(ws, str(tmp_path / "ws" / "plain"))


def test_register_url_clones_into_repos_dir(tmp_path, ws):
    src = make_repo(tmp_path / "upstream")
    rec = register_repo(ws, src.as_uri())   # file:// URL
    assert rec["name"] == "upstream" and rec["path"] == "repos/upstream" and rec["base"] == "main"
    assert (tmp_path / "ws" / "repos" / "upstream" / "README.md").read_text() == "hello\n"
    with pytest.raises(EnvError, match="exists"):
        register_repo(ws, src.as_uri())


# ---------------------------------------------------------------- root story: worktree (§4.1, §4.4)

def test_open_creates_a_worktree_on_zharn_branch_from_base(ws, repo):
    es = store(ws, **{"ZH-1": (None, "worktree")})
    d = es.open("ZH-1", "client")
    path = ws.local_dir / "worktrees" / "client" / "ZH-1"
    assert d["kind"] == "worktree" and d["path"] == str(path) and d["branch"] == "zharn/ZH-1" and d["parent"] is None
    assert path.is_dir() and branch_of(path) == "zharn/ZH-1" and (path / "README.md").exists()
    assert run(repo, "rev-parse", "zharn/ZH-1") == run(repo, "rev-parse", "main")
    saved = json.loads((ws.local_dir / "environments.json").read_text())
    assert saved[env_key("ZH-1", "client")]["path"] == str(path) and saved[env_key("ZH-1", "client")]["setup_done"] is True


def test_open_is_idempotent_per_pair(ws, repo):
    es = store(ws, **{"ZH-1": (None, "worktree")})
    a, b = es.open("ZH-1", "client"), es.open("ZH-1", "client")
    assert a == b and len(es.records("ZH-1")) == 1
    assert run(repo, "worktree", "list").count("zharn/ZH-1") == 1


def test_open_uses_the_registered_base(ws, tmp_path):
    p = make_repo(tmp_path / "ws" / "api", branch="develop")
    run(p, "checkout", "-q", "-b", "feature")
    commit_file(p, "f.txt")
    register_repo(ws, str(p), base="develop")
    es = store(ws, **{"ZH-1": (None, "worktree")})
    d = es.open("ZH-1", "api")
    assert not (Path(d["path"]) / "f.txt").exists()   # cut from develop, not the checked-out feature branch


def test_open_recreates_a_deleted_worktree_on_its_branch(ws, repo):
    import shutil
    es = store(ws, **{"ZH-1": (None, "worktree")})
    d = es.open("ZH-1", "client")
    commit_file(Path(d["path"]), "work.txt")
    shutil.rmtree(d["path"])
    d2 = es.open("ZH-1", "client")
    assert d2["path"] == d["path"] and (Path(d2["path"]) / "work.txt").exists() and branch_of(Path(d2["path"])) == "zharn/ZH-1"


def test_open_unknown_or_missing_repo_creates_nothing(ws, repo, tmp_path):
    es = store(ws, **{"ZH-1": (None, "worktree")})
    with pytest.raises(EnvError, match="unknown repo"):
        es.open("ZH-1", "nope")
    ws.relocate("client", tmp_path / "gone")
    with pytest.raises(EnvError, match="missing"):
        es.open("ZH-1", "client")
    assert es.records("ZH-1") == [] and not (ws.local_dir / "worktrees").exists()


# ---------------------------------------------------------------- root story: never shared (§4.2)

def test_a_root_story_cannot_be_shared(ws, repo):
    es = store(ws, **{"ZH-1": (None, "shared")})   # a corrupt or hand-edited story.json; the store must still refuse
    with pytest.raises(EnvError, match="a root story cannot be shared"):
        es.open("ZH-1", "client")
    assert es.records("ZH-1") == [] and not (ws.local_dir / "worktrees").exists()
    assert run(repo, "branch", "--list", "zharn/*") == ""


# ---------------------------------------------------------------- setup (§3.1, §4.4)

def test_setup_runs_once_in_the_worktree_and_is_retried_after_failure(ws, tmp_path):
    p = make_repo(tmp_path / "ws" / "api")
    marker = tmp_path / "gate"
    register_repo(ws, str(p), setup=f"test -f {marker} && echo ran >> setup.log")
    es = store(ws, **{"ZH-1": (None, "worktree")})
    with pytest.raises(EnvError, match="setup failed"):
        es.open("ZH-1", "api")
    path = ws.local_dir / "worktrees" / "api" / "ZH-1"
    assert path.is_dir() and es.get("ZH-1", "api")["setup_done"] is False   # worktree stays
    marker.write_text("")
    es.open("ZH-1", "api")
    es.open("ZH-1", "api")
    assert (path / "setup.log").read_text() == "ran\n" and es.get("ZH-1", "api")["setup_done"] is True


def test_describe_carries_the_repos_checks(ws, tmp_path):
    p = make_repo(tmp_path / "ws" / "api")
    register_repo(ws, str(p), checks="make test")
    es = store(ws, **{"ZH-1": (None, "worktree")})
    assert es.open("ZH-1", "api")["checks"] == "make test"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_environments.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'harness.environments'`.

- [ ] **Step 3: Implement**

`harness/environments.py`:

```python
"""Environments: where a context stands (workspace spec §4). One record per (story, repo) — a managed worktree
on `zharn/<key>` cut from the parent environment's effective branch, or `shared`: standing in the parent
environment itself. The parent environment of a root story is the repo's main checkout. Records live in
`local/environments.json`; a shared record stores no path — it resolves through the chain at use time."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Callable

from harness.fsutil import write_text_atomic


class EnvError(Exception):
    """A refused or failed environment operation; the message is what the character reads."""


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    if r.returncode != 0:
        raise EnvError(f"git {' '.join(args)} failed in {cwd}: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def head_branch(path: Path) -> str:
    """The checked-out branch, or the short commit when detached."""
    try:
        return git(path, "symbolic-ref", "--short", "HEAD")
    except EnvError:
        return git(path, "rev-parse", "--short", "HEAD")


def _is_url(spec: str) -> bool:
    return "://" in spec or spec.startswith("git@")


def register_repo(ws, spec: str, name: str = "", checks: str = "", setup: str = "", base: str = "") -> dict:
    """§3.2: a path is registered as is (absolute, or relative to the workspace dir); a URL is cloned into
    <workspace>/repos/<name>/ and registered relative. `base` defaults to the HEAD branch at registration."""
    if _is_url(spec):
        name = name or spec.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        dest = ws.dir / "repos" / name
        if dest.exists():
            raise EnvError(f"{dest} exists")
        dest.parent.mkdir(parents=True, exist_ok=True)
        git(ws.dir, "clone", "-q", spec, str(dest))
        path = dest
    else:
        path = Path(spec)
        if not path.is_absolute():
            path = ws.dir / path
    path = path.resolve()
    if not (path / ".git").exists():
        raise EnvError(f"{path} is not a git repository")
    return ws.add_repo(path, name=name, checks=checks, setup=setup, base=base or head_branch(path))


def env_key(story: str, repo: str) -> str:
    return f"{story}:{repo}"


class EnvironmentStore:
    def __init__(self, workspace, story_info: Callable[[str], tuple[str | None, str]]):
        """`story_info(key)` → (parent story key or None, env mode "worktree" | "shared")."""
        self.ws = workspace
        self.story_info = story_info
        self._file = workspace.local_dir / "environments.json"
        try:
            self._records: dict[str, dict] = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._records = {}

    def _save(self) -> None:
        write_text_atomic(self._file, json.dumps(self._records, indent=1))

    # ---------------------------------------------------------------- queries
    def get(self, story: str, repo: str) -> dict | None:
        return self._records.get(env_key(story, repo))

    def records(self, story: str) -> list[dict]:
        return [r for r in self._records.values() if r["story"] == story]

    def _repo(self, name: str) -> tuple[dict, Path]:
        r = self.ws.repo(name)
        if r is None:
            raise EnvError(f"unknown repo {name!r}; `repo list` shows what is registered")
        p = self.ws.repo_path(r)
        if not p.is_dir():
            raise EnvError(f"repo {name!r} is missing at {p}; relocate it from the workspace page")
        return r, p

    def _parent(self, rec: dict) -> dict | None:
        return self._records.get(rec["parent"]) if rec.get("parent") else None

    def path(self, rec: dict) -> Path:
        """Resolved through the chain: a shared record stands where its parent stands. The chain always ends at a
        worktree (a root story is never shared); the main-checkout fallback only guards a hand-edited record."""
        if rec["kind"] == "worktree":
            return Path(rec["path"])
        parent = self._parent(rec)
        return self.path(parent) if parent is not None else self._repo(rec["repo"])[1]

    def _base(self, repo: str) -> str:
        r, p = self._repo(repo)
        return r.get("base") or head_branch(p)

    def effective_branch(self, rec: dict) -> str:
        """§4.2: walk up to the first worktree (its branch) or the main checkout (the repo's base)."""
        if rec["kind"] == "worktree":
            return rec["branch"]
        parent = self._parent(rec)
        return self.effective_branch(parent) if parent is not None else self._base(rec["repo"])

    def describe(self, rec: dict) -> dict:
        r = self.ws.repo(rec["repo"]) or {}
        return {**rec, "path": str(self.path(rec)), "branch": self.effective_branch(rec), "checks": r.get("checks", "")}

    # ---------------------------------------------------------------- open (§4.4)
    def open(self, story: str, repo: str) -> dict:
        """Idempotent per (story, repo). First use resolves the parent chain — creating the parent story's
        environment on demand — then creates this story's in its mode. Returns the resolved view."""
        rec = self.get(story, repo)
        if rec is None:
            _, repo_path = self._repo(repo)
            parent_key, mode = self.story_info(story)
            if mode == "shared" and not parent_key:
                raise EnvError(f"a root story cannot be shared: {story} must work on its own branch (spec §4.2)")
            parent_rec = self.open(parent_key, repo) if parent_key else None   # the parent's resolved view
            rec = {"story": story, "repo": repo, "kind": mode, "path": "", "branch": "",
                   "parent": env_key(parent_key, repo) if parent_key else None, "created": time.time(), "setup_done": mode == "shared"}
            if mode == "worktree":
                rec["path"] = str(self.ws.local_dir / "worktrees" / repo / story)
                rec["branch"] = f"zharn/{story}"
                base = parent_rec["branch"] if parent_rec is not None else self._base(repo)   # the parent's effective branch, or the repo's base
                Path(rec["path"]).parent.mkdir(parents=True, exist_ok=True)
                git(repo_path, "worktree", "add", "-q", "-b", rec["branch"], rec["path"], base)
            self._records[env_key(story, repo)] = rec
            self._save()
        elif rec["kind"] == "worktree" and not Path(rec["path"]).is_dir():
            _, repo_path = self._repo(repo)   # deleted by hand: prune the stale entry, re-add on the existing branch
            git(repo_path, "worktree", "prune")
            Path(rec["path"]).parent.mkdir(parents=True, exist_ok=True)
            git(repo_path, "worktree", "add", "-q", rec["path"], rec["branch"])
        if not rec["setup_done"]:
            self._setup(rec)
        return self.describe(rec)

    def _setup(self, rec: dict) -> None:
        r, _ = self._repo(rec["repo"])
        cmd = r.get("setup", "")
        if cmd:
            res = subprocess.run(cmd, shell=True, cwd=rec["path"], capture_output=True, text=True)
            if res.returncode != 0:
                raise EnvError(f"setup failed in {rec['path']} (exit {res.returncode}): {(res.stderr or res.stdout).strip()[-2000:]}")
        rec["setup_done"] = True
        self._save()
```

- [ ] **Step 4: Run the tests, then the full suite**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_environments.py -q` then the full suite.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add harness/environments.py tests/gitfix.py tests/test_environments.py
git commit -m "Environments: register_repo (path or URL clone, base from HEAD), EnvironmentStore with lazy worktrees, setup once, recreate after delete; a root story is never shared

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: The parent chain — sub-stories in both modes

**Files:**
- Modify: `harness/environments.py` (no new API; this task pins the recursion with tests and fixes what they find)
- Test: `tests/test_environments.py`

**Interfaces:** consumes Task 2's `EnvironmentStore`. No new names.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_environments.py`:

```python
# ---------------------------------------------------------------- sub-stories: the parent chain (§4.2)

def test_substory_worktree_branches_from_the_parents_branch(ws, repo):
    es = store(ws, **{"ZH-1": (None, "worktree"), "ZH-2": ("ZH-1", "worktree")})
    parent = es.open("ZH-1", "client")
    commit_file(Path(parent["path"]), "parent.txt")          # parent's committed work
    sub = es.open("ZH-2", "client")
    assert sub["kind"] == "worktree" and sub["branch"] == "zharn/ZH-2" and sub["parent"] == "ZH-1:client"
    assert sub["path"] == str(ws.local_dir / "worktrees" / "client" / "ZH-2")
    assert (Path(sub["path"]) / "parent.txt").exists()        # cut from zharn/ZH-1, not from main
    assert run(repo, "rev-parse", "zharn/ZH-2") == run(repo, "rev-parse", "zharn/ZH-1")


def test_substory_creates_the_parents_environment_on_demand(ws, repo):
    es = store(ws, **{"ZH-1": (None, "worktree"), "ZH-2": ("ZH-1", "worktree")})
    sub = es.open("ZH-2", "client")
    assert es.get("ZH-1", "client") is not None and es.get("ZH-1", "client")["kind"] == "worktree"
    assert (ws.local_dir / "worktrees" / "client" / "ZH-1").is_dir() and sub["parent"] == "ZH-1:client"


def test_substory_shared_stands_in_the_parents_worktree(ws, repo):
    es = store(ws, **{"ZH-1": (None, "worktree"), "ZH-2": ("ZH-1", "shared")})
    parent = es.open("ZH-1", "client")
    sub = es.open("ZH-2", "client")
    assert sub["kind"] == "shared" and sub["path"] == parent["path"] and sub["branch"] == "zharn/ZH-1"
    assert es.get("ZH-2", "client")["path"] == ""
    assert "zharn/ZH-2" not in run(repo, "branch", "--list", "zharn/*")


def test_effective_branch_walks_through_shared_records(ws, repo):
    """root worktree → shared child → worktree grandchild: the grandchild branches from the root's branch."""
    es = store(ws, **{"ZH-1": (None, "worktree"), "ZH-2": ("ZH-1", "shared"), "ZH-3": ("ZH-2", "worktree")})
    root = es.open("ZH-1", "client")
    commit_file(Path(root["path"]), "root.txt")
    g = es.open("ZH-3", "client")
    assert g["parent"] == "ZH-2:client" and es.get("ZH-2", "client")["kind"] == "shared"
    assert (Path(g["path"]) / "root.txt").exists() and run(repo, "rev-parse", "zharn/ZH-3") == run(repo, "rev-parse", "zharn/ZH-1")


def test_shared_substory_under_a_shared_substory_reaches_the_root_worktree(ws, repo):
    es = store(ws, **{"ZH-1": (None, "worktree"), "ZH-2": ("ZH-1", "shared"), "ZH-3": ("ZH-2", "shared")})
    root = es.open("ZH-1", "client")
    assert es.open("ZH-3", "client")["path"] == root["path"]
    assert [r["kind"] for r in es.records("ZH-2") + es.records("ZH-3")] == ["shared", "shared"]
```

- [ ] **Step 2: Run them to verify they pass or fail**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_environments.py -q -k "substory or effective or reaches_the_root"`
Expected: all PASS if Task 2's recursion is right. If any fails, fix `EnvironmentStore.open`/`effective_branch`/`path` — do not weaken the tests. The likely trap: `open` must call `self._repo(repo)` **before** recursing so a missing repo creates no parent record.

- [ ] **Step 3: Run the full suite** — PASS.

- [ ] **Step 4: Commit**

```bash
git add harness/environments.py tests/test_environments.py
git commit -m "Environments: the parent chain pinned — sub-stories branch from the parent's branch or stand in its worktree; parents created on demand

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: StoryStore — env mode, repos, env verbs, environment inheritance

**Files:**
- Modify: `harness/lifecycle.py` (`Story` dataclass)
- Modify: `harness/stories.py` (`__init__`, `_row`, `cast`, `create`, `cast_create`, `_cast`, `_start`, `openThread`, `cast_call`, `_system_prompt`; new methods)
- Modify: `harness/config_def.py` (`CHARACTER_SYSTEM_PROMPT`)
- Test: `tests/test_stories.py`, `tests/test_lifecycle.py`

**Interfaces:**
- Produces:
  ```python
  # lifecycle
  @dataclass
  class Story: ...; env_mode: str = "worktree"; repos: list[str] = field(default_factory=list)
  # stories
  StoryStore.environments: EnvironmentStore
  # create(title, description) is unchanged: a human's story is a root story and is always "worktree"
  def cast_create(self, character_id, title, description="", start=False, role="", shared=False) -> str   # shared: sub-story only (always the case here)
  def cast_env_open(self, character_id, repo) -> dict                       # describe(); sets ch["environment"]; appends story.repos
  def cast_env_list(self, character_id) -> list[dict]
  def cast_repo_add(self, character_id, spec, name="", checks="", setup="", base="") -> dict   # + system Note in the attended thread
  def repo_list(self) -> list[dict]                                         # [{**record, "status": ok|missing}]
  def env_checks(self, character_id, thread_id="") -> dict                  # {"run", "environments", "policy", "limit", "timeout"}
  def environment_line(self, ch) -> str                                     # for the system prompt
  ```
  Character record: `environment: str | None` (repo name). `_row` gains `envMode`, `repos`, `environments: [{repo, kind, path, branch}]`. `cast()` rows gain `environment`.
  Rejections: `"unknown repo"` / `"missing"` come from `EnvError` (Task 2); `"env open needs a repo name"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lifecycle.py`:

```python
def test_story_env_mode_and_repos_round_trip():
    from harness.lifecycle import Story
    s = Story(key="ZH-1", title="t", env_mode="shared", repos=["client"])
    d = s.to_dict()
    assert d["env_mode"] == "shared" and d["repos"] == ["client"]
    assert Story.from_dict({"key": "ZH-2", "title": "u"}).env_mode == "worktree"
    assert Story.from_dict(d).repos == ["client"]
```

Append to `tests/test_stories.py` (the module already imports `json`, `pytest`, `Workspace`, `StoryStore`; add `import sys, pathlib` lines shown):

```python
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


def test_root_stories_are_worktree_and_substories_may_be_shared(store, ws):
    a = store.create("A")
    assert json.loads((ws.stories_dir / a / "story.json").read_text())["env_mode"] == "worktree"
    assert store.get(a)["envMode"] == "worktree" and store.get(a)["repos"] == []
    key, chr_id = started(store)
    b = store.cast_create(chr_id, "B", shared=True)
    assert json.loads((ws.stories_dir / b / "story.json").read_text())["env_mode"] == "shared" and store.get(b)["envMode"] == "shared"
    assert store.get(store.cast_create(chr_id, "C"))["envMode"] == "worktree"


def test_env_open_creates_the_worktree_records_it_on_the_character_and_the_story(store, ws, repo, contexts):
    key, chr_id = started(store)
    d = store.cast_env_open(chr_id, "client")
    assert d["kind"] == "worktree" and branch_of(_Path(d["path"])) == f"zharn/{key}" and d["checks"] == "echo ok"
    assert store.character(chr_id)["environment"] == "client"
    assert store.get(key)["repos"] == ["client"] and json.loads((ws.stories_dir / key / "story.json").read_text())["repos"] == ["client"]
    assert store.get(key)["environments"] == [{"repo": "client", "kind": "worktree", "path": d["path"], "branch": f"zharn/{key}"}]
    assert store.cast(key)[0]["environment"] == "client"
    assert store.cast_env_list(chr_id) == [d]
    assert store.cast_env_open(chr_id, "client") == d and store.get(key)["repos"] == ["client"]


def test_env_open_errors_are_the_repos_message(store, repo):
    key, chr_id = started(store)
    from harness.environments import EnvError
    with pytest.raises(EnvError, match="unknown repo 'nope'"):
        store.cast_env_open(chr_id, "nope")
    with pytest.raises(EnvError, match="env open needs a repo name"):
        store.cast_env_open(chr_id, "")
    assert store.character(chr_id)["environment"] is None and store.get(key)["repos"] == []


def test_substory_shared_flag_sets_its_mode_and_opens_in_the_parents_worktree(store, repo):
    key, chr_id = started(store)
    parent_env = store.cast_env_open(chr_id, "client")
    sub = store.cast_create(chr_id, "Contained", shared=True, start=True, role="claude-fast")
    assert store.get(sub)["envMode"] == "shared"
    sub_chr = store.get(sub)["protagonist"]
    d = store.cast_env_open(sub_chr, "client")
    assert d["kind"] == "shared" and d["path"] == parent_env["path"] and d["branch"] == f"zharn/{key}"
    own = store.cast_create(chr_id, "Own branch", start=True, role="claude-fast")
    d2 = store.cast_env_open(store.get(own)["protagonist"], "client")
    assert d2["kind"] == "worktree" and d2["branch"] == f"zharn/{own}" and d2["parent"] == f"{key}:client"


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


def test_system_prompt_names_the_environment(store, repo):
    key, chr_id = started(store)
    ch = store.character(chr_id)
    assert "workspace dir" in store.environment_line(ch) and "env open" in store.environment_line(ch)
    d = store.cast_env_open(chr_id, "client")
    line = store.environment_line(store.character(chr_id))
    assert d["path"] in line and "client" in line and "worktree" in line and f"zharn/{key}" in line
    ctx = store._contexts.get(store.character(chr_id)["live_context"])
    store.comment(key, "reply")        # any delivery rebuilds the system prompt
    assert d["path"] in ctx.meta["systemPrompt"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_lifecycle.py tests/test_stories.py -q -k "env or repo or environment or recast_keeps or friends_inherit or substory_shared"`
Expected: FAIL — `TypeError: Story.__init__() got an unexpected keyword argument 'env_mode'`, `AttributeError: 'StoryStore' object has no attribute 'cast_env_open'`.

- [ ] **Step 3: Implement**

`harness/lifecycle.py`, in `Story` after `parent_story`:

```python
    env_mode: str = "worktree"       # "worktree" | "shared" (workspace spec §4.2), fixed at creation
    repos: list[str] = field(default_factory=list)   # derived from environments, persisted for the board
```

`harness/stories.py`:

Imports: add `from harness.environments import EnvError, EnvironmentStore, register_repo`.

In `__init__`, after `self._load()`:

```python
        self.environments = EnvironmentStore(workspace, self._story_info)
        contexts.placement = self._placement   # Task 5 makes ContextStore call it at every spawn
```

New methods (put them after `_key`):

```python
    def _story_info(self, key: str) -> tuple[str | None, str]:
        s = self._stories[key]
        return s.parent_story, s.env_mode

    def _env_rows(self, key: str) -> list[dict]:
        out = []
        for rec in self.environments.records(key):
            try:
                d = self.environments.describe(rec)
                out.append({"repo": d["repo"], "kind": d["kind"], "path": d["path"], "branch": d["branch"]})
            except EnvError as e:   # a missing repo: show the record, say why it has no path
                out.append({"repo": rec["repo"], "kind": rec["kind"], "path": "", "branch": "", "error": str(e)})
        return out

    def _placement(self, ctx) -> tuple[str, dict]:
        """§4.5: a character's context runs in its environment's path, else where its meta says (the workspace dir)."""
        ch = self._characters.get(ctx.meta.get("owner", ""))
        repo = ch.get("environment") if ch else None
        if repo:
            rec = self.environments.get(ch["story_key"], repo)
            if rec is not None:
                try:
                    path = str(self.environments.path(rec))
                    return path, {"HARNESS_REPO": repo, "HARNESS_ENV": path}
                except EnvError:
                    pass   # missing repo: fall back to the workspace dir; env open will say so
        return ctx.meta.get("cwd") or str(self.workspace.dir), {}

    def environment_line(self, ch: dict) -> str:
        repo = ch.get("environment")
        if repo:
            rec = self.environments.get(ch["story_key"], repo)
            if rec is not None:
                try:
                    d = self.environments.describe(rec)
                    return f"{d['path']} (repo {repo}, {d['kind']} environment on branch {d['branch']})"
                except EnvError as e:
                    return f"repo {repo} is unavailable: {e}"
        mode = self._stories[ch["story_key"]].env_mode
        return (f"the workspace dir ({self.workspace.dir}); run `env open <repo>` before touching a repo "
                f"(this story's environments are {mode})")
```

`_row`: add three keys to the returned dict:

```python
                "envMode": s.env_mode, "repos": list(s.repos), "environments": self._env_rows(key),
```

`cast()`: add `"environment": ch.get("environment") or ""` to each row.

`create`: unchanged — a human's story is a root story and `Story.env_mode` defaults to `"worktree"`.

`cast_create`: add `shared=False` parameter and `env_mode="shared" if shared else "worktree"` to the `lc.Story(...)` call. Every story created here has a parent (the character's story), so `shared` is always legal.

`_cast`: add a parameter `environment: str | None = None` and put `"environment": environment` in the `ch = {...}` record. Callers:
- `_start`: unchanged (no environment → `None`).
- `cast_call`: pass `environment=ch.get("environment")`.
- `openThread`: `/fork @Name` passes `environment=source.get("environment")`; `/call` passes nothing. In the `if m_call or m_fork` branch, set `environment = None` in the `m_call` arm and `environment = source.get("environment")` in the `m_fork` arm, then pass `environment=environment` to `self._cast(...)`.
- `_recast_now`: does not touch `ch["environment"]` — nothing to do; the test pins it.

`_system_prompt`: add `environment=self.environment_line(ch)` to the `.format(...)` call.

Cast verbs (after `cast_wait`):

```python
    # ---------------------------------------------------------------- repos and environments (workspace spec §3.2, §4)
    def cast_repo_add(self, character_id, spec, name="", checks="", setup="", base="") -> dict:
        key, ch = self._char(character_id)
        rec = register_repo(self.workspace, spec, name=name, checks=checks, setup=setup, base=base)
        tid = ch.get("attention") or self._stories[key].main_thread
        self._apply(key, lc.Note(thread_id=tid, body=f"Registered repo `{rec['name']}` at `{rec['path']}`"))
        self._refresh()
        return rec

    def repo_list(self) -> list[dict]:
        return [{**r, "status": self.workspace.repo_status(r["name"])} for r in self.workspace.repos]

    def cast_env_open(self, character_id, repo) -> dict:
        key, ch = self._char(character_id)
        if not repo:
            raise EnvError("env open needs a repo name; `repo list` shows what is registered")
        d = self.environments.open(key, repo)
        ch["environment"] = repo
        self._save_characters()
        s = self._stories[key]
        if repo not in s.repos:
            s.repos.append(repo)
            self._save_story(key)
        self._refresh()
        return d

    def cast_env_list(self, character_id) -> list[dict]:
        key, _ = self._char(character_id)
        return [self.environments.describe(r) for r in self.environments.records(key)]

    def env_checks(self, character_id, thread_id="") -> dict:
        """§4.6: what the CLI must run before posting a handoff — only on the main thread of an implementing story."""
        key, ch = self._char(character_id)
        s = self._stories[key]
        tid = thread_id or ch.get("attention") or s.main_thread
        run = s.phase == "implementing" and tid == s.main_thread
        envs = [d for d in self.cast_env_list(character_id) if d["checks"]] if run else []
        return {"run": run, "environments": envs, "policy": getattr(cfg, "HANDOFF_CHECKS", "gate"),
                "limit": getattr(cfg, "CHECKS_OUTPUT_LIMIT", 4000), "timeout": getattr(cfg, "CHECKS_TIMEOUT_S", 1800)}
```

`harness/config_def.py` — after `RECAP_STALE_TURNS`:

```python
# ---- environments (workspace spec §4) ---------------------------------------------------------
# What a failing repo check does at an implementing handoff (§4.6). "gate": the handoff is refused until the
# character fixes it or passes --despite-checks. "attach": it posts anyway with the red results attached.
# The trade is token burn against red handoffs.
HANDOFF_CHECKS = "gate"
CHECKS_OUTPUT_LIMIT = 4000   # characters of check output kept per repo
CHECKS_TIMEOUT_S = 1800      # per repo
```

`CHARACTER_SYSTEM_PROMPT`: after the `You are attending thread …` line add

```
You stand in {environment}.
```

and after the `story show · cast · inbox` line add

```
  $HARNESS_CLI env open <repo>                                                  # where to work: prints the path (your story's worktree, or the shared tree); cd there
  $HARNESS_CLI env list · repo list                                             # this story's environments; registered repos
  $HARNESS_CLI repo add <path|url> [--name N] [--checks C] [--setup S] [--base B]   # register a repo (URLs are cloned); checks run at your handoffs
```

- [ ] **Step 4: Run the tests, then the full suite**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_lifecycle.py tests/test_stories.py -q` then the full suite.
Expected: PASS. Watch `tests/test_stories.py::test_system_prompt_*` and any test comparing the whole system prompt — update expectations for the new line rather than removing it.

- [ ] **Step 5: Commit**

```bash
git add harness/lifecycle.py harness/stories.py harness/config_def.py tests/test_lifecycle.py tests/test_stories.py
git commit -m "Stories: sub-stories may be shared, env open/list, repo add with a system note, environment inherited by friends and forks, the environment line in the system prompt

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Context placement at spawn, recycle at turn end

**Files:**
- Modify: `harness/contexts.py` (`ContextStore.__init__`, `Context._env`, `Context._spawn`; new `Context.recycle`, `proc_cwd`)
- Modify: `harness/stories.py` (`_on_turn_end`)
- Modify: `tests/fake_claude.py` (`harness_env` keys)
- Test: `tests/test_contexts_unit.py`, `tests/test_environments.py` (end-to-end section)

**Interfaces:**
- Produces:
  ```python
  ContextStore.placement: Callable[[Context], tuple[str, dict]]   # default: (meta cwd or workspace dir, {})
  Context.proc_cwd -> str | None                                  # cwd of the live process, None when none
  def Context.recycle(self) -> None                               # drop an idle process; the next send resumes in a fresh one
  ```

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_contexts_unit.py` (read its top first: it has a `store` fixture built with `HARNESS_CLAUDE_CMD` = the fake and a `wait_until`; reuse them, mirroring the existing spawn test's shape):

```python
def test_placement_decides_cwd_and_extra_env_at_every_spawn(store, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    target = {"cwd": str(a)}
    store.placement = lambda c: (target["cwd"], {"HARNESS_REPO": "r", "HARNESS_ENV": target["cwd"]})
    cid = store.spawn("claude-fast", "hello")
    c = store.get(cid)
    assert wait_until(lambda: c.status == "idle"), c.lastError
    assert c.proc_cwd == str(a)
    init = next(r for r in (json.loads(l) for l in (store.data_dir / f"{cid}.jsonl").read_text().splitlines()) if r.get("subtype") == "init")
    assert Path(init["cwd"]).resolve() == a.resolve() and init["harness_env"]["HARNESS_REPO"] == "r" and init["harness_env"]["HARNESS_ENV"] == str(a)
    target["cwd"] = str(b)
    c.send("again")                      # same process: cwd unchanged until recycled
    assert wait_until(lambda: c.status == "idle")
    assert c.proc_cwd == str(a)
    c.recycle()
    assert c.proc_cwd is None and c.status == "idle"
    c.send("after recycle")
    assert wait_until(lambda: c.status == "idle")
    assert c.proc_cwd == str(b)
    inits = [r for r in (json.loads(l) for l in (store.data_dir / f"{cid}.jsonl").read_text().splitlines()) if r.get("subtype") == "init"]
    assert len(inits) == 2 and Path(inits[-1]["cwd"]).resolve() == b.resolve()
    assert "--resume" in inits[-1]["argv"]   # the session carried over


def test_recycle_is_a_no_op_while_working(store):
    cid = store.spawn("claude-fast", "slow please")
    c = store.get(cid)
    assert c.status in ("starting", "working")
    proc = c._proc
    c.recycle()
    assert c._proc is proc
    assert wait_until(lambda: c.status == "idle")
```

Append to `tests/test_environments.py` an end-to-end section that builds the real app against the fake claude (mirrors `tests/test_agents.py::harness`; module-scoped, own workspace dir):

```python
# ---------------------------------------------------------------- end to end: cwd at spawn (§4.5)
import os
import shutil
from PySide6.QtTest import QTest
from harness.__main__ import ROOT, build

OUT = ROOT / "tests" / "_out"
WS = OUT / "env-ws"


def wait_until(cond, timeout_ms=8000, step=25):
    import time
    t0 = time.time()
    while time.time() - t0 < timeout_ms / 1000:
        QTest.qWait(step)
        if cond():
            return True
    return False


@pytest.fixture(scope="module")
def app_store():
    shutil.rmtree(WS, ignore_errors=True)
    os.environ["HARNESS_WORKSPACE"] = str(WS)
    os.environ["HARNESS_SESSION"] = str(OUT / "env-session.json")
    os.environ["HARNESS_CLAUDE_CMD"] = f"{sys.executable} {ROOT / 'tests' / 'fake_claude.py'}"
    (OUT / "env-session.json").unlink(missing_ok=True)
    app, store, reloader = build(force_poll=True)
    assert reloader.load(), store.reloadError
    make_repo(WS / "client")
    register_repo(store.stories.workspace, str(WS / "client"), checks="test -f ok.txt")
    QTest.qWait(50)
    yield store
    store.contexts.shutdown()
    reloader.shutdown()
    QTest.qWait(50)


def _inits(store, cid):
    return [json.loads(l) for l in (store.contexts.data_dir / f"{cid}.jsonl").read_text().splitlines() if '"init"' in l]


def test_character_moves_into_its_worktree_at_the_next_turn(app_store):
    st = app_store.stories
    key = st.create("E2E", "")
    chr_id = st.start(key, "go", "protagonist")
    ctx = app_store.contexts.get(st.character(chr_id)["live_context"])
    assert wait_until(lambda: ctx.status == "idle"), ctx.lastError
    assert Path(_inits(app_store, ctx.id)[0]["cwd"]).resolve() == WS.resolve()
    # the first turn ended with the harness yielding for the protagonist (it owed the main thread): ball is the author's,
    # so each comment below is a Reply that resumes it.
    assert st.get(key)["ball"] == "author"
    d = st.cast_env_open(chr_id, "client")
    st.comment(key, "now in the worktree?")          # delivery → turn → turn end recycles the stale process
    assert wait_until(lambda: ctx.status == "idle")
    assert wait_until(lambda: ctx.proc_cwd is None)  # recycled at turn end because placement changed
    st.comment(key, "and now?")
    assert wait_until(lambda: ctx.status == "idle")
    init = _inits(app_store, ctx.id)[-1]
    assert Path(init["cwd"]).resolve() == Path(d["path"]).resolve()
    assert init["harness_env"]["HARNESS_REPO"] == "client" and init["harness_env"]["HARNESS_ENV"] == d["path"]
    assert d["path"] in ctx.meta["systemPrompt"]
```

In `tests/fake_claude.py`, extend the `harness_env` key tuple:

```python
"harness_env": {k: os.environ[k] for k in ("HARNESS_CONTEXT_ID", "HARNESS_STORY_KEY", "HARNESS_CHARACTER_ID", "HARNESS_WORKSPACE", "HARNESS_REPO", "HARNESS_ENV") if k in os.environ}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_contexts_unit.py tests/test_environments.py -q -k "placement or recycle or moves_into"`
Expected: FAIL — `AttributeError: ... 'proc_cwd'`.

- [ ] **Step 3: Implement**

`harness/contexts.py`:

In `ContextStore.__init__`, after `self.extra_env = lambda: {}`:

```python
        self.placement = lambda c: (c.meta.get("cwd") or str(self.workspace_dir), {})   # StoryStore overrides (spec §4.5)
```

In `Context.__init__`, after `self._proc = None`: `self._proc_cwd: str | None = None`.

Add a property next to `notifier`:

```python
    @property
    def proc_cwd(self) -> str | None:
        return self._proc_cwd if self._proc is not None else None
```

Change `_env` to take extras and `_spawn` to use placement:

```python
    def _env(self, extra: dict | None = None) -> dict:
        env = {"HARNESS_CONTEXT_ID": self.id, "HARNESS_STORY_KEY": self.storyKey, "HARNESS_ROOT": str(self._store.root),
               "HARNESS_WORKSPACE": str(self._store.workspace_dir), "HARNESS_CLI": f"{sys.executable} -m harness.cli"}
        env.update(self.meta.get("env") or {})
        env.update(extra or {})
        env.update(self._store.extra_env())
        return env

    def _spawn(self, resume: str = ""):
        role = self.meta.get("roleConfig", {})
        extra = list(getattr(cfg, "EFFORT_FLAGS", {}).get(role.get("reasoning", ""), []))
        if not resume and self.meta.get("forkSession"):
            resume, extra = self.meta["forkSession"], extra + ["--fork-session"]  # first turn of a fork only
        cwd, place_env = self._store.placement(self)   # decided at every spawn, not at creation (workspace spec §4.5)
        self._proc_cwd = cwd
        self._proc = ClaudeCodeProcess(cwd=cwd, env=self._env(place_env),
                                       model=role.get("model", ""), permission=role.get("permission", "auto"),
                                       resume=resume, system_prompt=self._system_prompt(), extra_args=extra)
        ...  # connects + start unchanged
```

Add after `stop`:

```python
    def recycle(self):
        """Drop an idle process so the next send resumes the session in a fresh one — the way a character
        changes working directory between turns. A working process is left alone."""
        if self._proc is None or self._status in ("starting", "working"):
            return
        old, self._proc = self._proc, None
        for sig, slot in ((old.event, self._on_event), (old.stderrText, self._on_stderr), (old.finished, self._on_finished)):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        old.shutdown()
        self.changed.emit()
```

`harness/stories.py`, `_on_turn_end`: right after the `if ch is None: return` line:

```python
        ctx = self._contexts.get(context_id)
        if ctx is not None and getattr(ctx, "proc_cwd", None) not in (None, self._placement(ctx)[0]):
            ctx.recycle()   # its environment changed this turn: the next turn spawns there (§4.5)
```

and delete the later `ctx = self._contexts.get(context_id)` line (it is now assigned above).

- [ ] **Step 4: Run the tests, then the full suite**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_contexts_unit.py tests/test_environments.py tests/test_agents.py -q` then the full suite.
Expected: PASS. `test_agents.py::test_spawn_streams_and_settles` still sees `HARNESS_WORKSPACE`; the stub in `test_stories.py` never spawns, so `placement` is only set there.

- [ ] **Step 5: Commit**

```bash
git add harness/contexts.py harness/stories.py tests/fake_claude.py tests/test_contexts_unit.py tests/test_environments.py
git commit -m "Contexts: placement decides cwd and HARNESS_REPO/HARNESS_ENV at every spawn; a character whose environment changed is recycled at turn end

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: IPC and CLI — repo/env verbs, create --shared, checks at handoff

**Files:**
- Modify: `harness/ipc.py` (`make_handler`)
- Modify: `harness/cli.py` (parsers, dispatch, `out` columns, new `run_checks`)
- Modify: `tests/fake_claude.py` (`yield-handoff` behaviour)
- Test: `tests/test_ipc.py`, `tests/test_cli.py`, `tests/test_environments.py` (end-to-end)

**Interfaces:**
- IPC commands: `repo.add {character, spec, name, checks, setup, base}`, `repo.list {}`, `env.open {character, repo}`, `env.list {character}`, `env.checks {character, thread}`; `story.create` gains `shared`; `story.yield` gains `checks: [{repo, cmd, exit, output}]`.
- CLI: `zharn repo add <spec> [--name --checks --setup --base]`, `zharn repo list`, `zharn env open <repo>` (prints the path), `zharn env list`, `zharn story create --shared`, `zharn story yield --handoff --despite-checks`.
- Produces: `cli.run_checks(envs: list[dict], limit: int, timeout: float) -> list[dict]`.
- Exit text (tests match on it): `"handoff refused: checks failed in <repos> — fix and retry, or pass --despite-checks"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ipc.py` (its `FakeStories` fake lives near the top of the file — extend it with recording methods; read the file's existing `FakeStories`/`make_handler` tests and follow their shape):

```python
class FakeEnvStories:
    """Records the env/repo calls the handler makes; `verbs` mirrors log_verb."""
    def __init__(self):
        self.calls, self.verbs = [], []

    def cast_repo_add(self, ch, spec, name, checks, setup, base):
        self.calls.append(("repo_add", ch, spec, name, checks, setup, base)); return {"name": name or "r"}

    def repo_list(self):
        self.calls.append(("repo_list",)); return [{"name": "r", "status": "ok"}]

    def cast_env_open(self, ch, repo):
        self.calls.append(("env_open", ch, repo)); return {"repo": repo, "path": "/p"}

    def cast_env_list(self, ch):
        self.calls.append(("env_list", ch)); return []

    def env_checks(self, ch, thread):
        self.calls.append(("env_checks", ch, thread)); return {"run": False, "environments": [], "policy": "gate", "limit": 10, "timeout": 5}

    def cast_yield(self, ch, kind, body, options, thread, checks=()):
        self.calls.append(("yield", ch, kind, body, list(options), thread, list(checks))); return {"id": "c"}

    def cast_create(self, ch, title, description, start, role, shared=False):
        self.calls.append(("create", ch, title, description, start, role, shared)); return "ZH-9"

    def log_verb(self, ch, verb, args, ok, error=""):
        self.verbs.append((ch, verb, args, ok, error))


class FakeEnvApp:
    def __init__(self, stories):
        self.stories, self.contexts, self.roles, self.layout = stories, FakeContexts(), None, None


def test_repo_and_env_commands_route_and_log():
    st = FakeEnvStories()
    h = make_handler(FakeEnvApp(st))
    assert h("repo.add", {"character": "chr_1", "spec": "/r", "name": "", "checks": "c", "setup": "", "base": ""}) == {"name": "r"}
    assert h("repo.list", {}) == [{"name": "r", "status": "ok"}]
    assert h("env.open", {"character": "chr_1", "repo": "r"}) == {"repo": "r", "path": "/p"}
    assert h("env.list", {"character": "chr_1"}) == []
    assert h("env.checks", {"character": "chr_1", "thread": "t"})["policy"] == "gate"
    assert [c[0] for c in st.calls] == ["repo_add", "repo_list", "env_open", "env_list", "env_checks"]
    assert [(v[1], v[3]) for v in st.verbs] == [("repo.add", True), ("env.open", True), ("env.list", True), ("env.checks", True)]
    with pytest.raises(KeyError):
        h("env.open", {"character": "chr_1"})
    assert st.verbs[-1][1] == "env.open" and st.verbs[-1][3] is False


def test_yield_passes_checks_and_create_passes_shared():
    st = FakeEnvStories()
    h = make_handler(FakeEnvApp(st))
    checks = [{"repo": "r", "cmd": "c", "exit": 0, "output": ""}]
    h("story.yield", {"character": "chr_1", "kind": "handoff", "body": "b", "checks": checks})
    assert st.calls[-1] == ("yield", "chr_1", "handoff", "b", [], "", checks)
    h("story.create", {"character": "chr_1", "title": "T", "shared": True, "start": True, "role": "claude-fast"})
    assert st.calls[-1] == ("create", "chr_1", "T", "", True, "claude-fast", True)
```

Append to `tests/test_cli.py` — a multi-request fake server (the existing `fake_server` is one-shot) and the parsing/flow tests:

```python
@pytest.fixture
def fake_ipc(tmp_path, monkeypatch):
    """Serves `replies` in order, one connection each; records every request."""
    path = str(tmp_path / "ipc2.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path); srv.listen(8); srv.settimeout(10)
    state = {"received": [], "replies": deque()}

    def serve():
        while state["replies"]:
            conn, _ = srv.accept()
            with conn:
                data = b""
                while not data.endswith(b"\n"):
                    data += conn.recv(65536)
                state["received"].append(json.loads(data))
                conn.sendall((json.dumps(state["replies"].popleft()) + "\n").encode())

    t = threading.Thread(target=serve, daemon=True)
    monkeypatch.setenv("HARNESS_IPC", path)
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr_1")

    def start(*replies):
        state["replies"].extend({"ok": True, "result": r} for r in replies)
        t.start()
        return state
    yield start
    srv.close(); t.join(timeout=5)


@posix_only
def test_repo_and_env_verbs(fake_ipc, capsys, tmp_path):
    st = fake_ipc({"name": "api"}, [{"name": "api", "status": "ok"}], {"repo": "api", "path": "/wt/api"}, [])
    cli.main(["repo", "add", str(tmp_path / "api"), "--checks", "pytest -q"])
    cli.main(["repo", "list"])
    cli.main(["env", "open", "api"])
    cli.main(["env", "list"])
    cmds = [(r["cmd"], r["args"]) for r in st["received"]]
    assert cmds[0] == ("repo.add", {"character": "chr_1", "spec": str(tmp_path / "api"), "name": "", "checks": "pytest -q", "setup": "", "base": ""})
    assert cmds[1] == ("repo.list", {})
    assert cmds[2] == ("env.open", {"character": "chr_1", "repo": "api"}) and cmds[3] == ("env.list", {"character": "chr_1"})
    out = capsys.readouterr().out
    assert "/wt/api\n" in out and "name=api  status=ok" in out


@posix_only
def test_repo_add_keeps_urls_and_absolutises_paths(fake_ipc, monkeypatch, tmp_path):
    st = fake_ipc({"name": "a"}, {"name": "b"})
    monkeypatch.chdir(tmp_path)
    cli.main(["repo", "add", "https://example.com/x/a.git"])
    cli.main(["repo", "add", "sub/b"])
    assert st["received"][0]["args"]["spec"] == "https://example.com/x/a.git"
    assert st["received"][1]["args"]["spec"] == str(tmp_path / "sub" / "b")


@posix_only
def test_story_create_shared_flag(fake_ipc):
    st = fake_ipc({"key": "ZH-3"})
    cli.main(["story", "create", "--title", "T", "--shared", "--start"])
    assert st["received"][0]["args"] == {"title": "T", "description": "", "character": "chr_1", "start": True, "role": "", "shared": True}


def test_run_checks_runs_each_env_and_truncates(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "ok.txt").write_text("")
    res = cli.run_checks([{"repo": "a", "checks": "test -f ok.txt && echo fine", "path": str(a)},
                          {"repo": "b", "checks": "echo 0123456789; test -f ok.txt", "path": str(b)}], limit=6, timeout=30)
    assert res == [{"repo": "a", "cmd": "test -f ok.txt && echo fine", "exit": 0, "output": "fine\n"[-6:]},
                   {"repo": "b", "cmd": "echo 0123456789; test -f ok.txt", "exit": 1, "output": "56789\n"}]


def test_run_checks_times_out(tmp_path):
    res = cli.run_checks([{"repo": "s", "checks": "sleep 5", "path": str(tmp_path)}], limit=100, timeout=0.2)
    assert res[0]["exit"] == -1 and "timed out" in res[0]["output"]


@posix_only
def test_handoff_runs_checks_and_gates_on_failure(fake_ipc, tmp_path, capsys):
    plan = {"run": True, "policy": "gate", "limit": 100, "timeout": 30,
            "environments": [{"repo": "api", "checks": "test -f ok.txt", "path": str(tmp_path)}]}
    st = fake_ipc(plan)
    with pytest.raises(SystemExit) as e:
        cli.main(["story", "yield", "--handoff", "--body", "done"])
    assert "handoff refused: checks failed in api" in str(e.value) and "--despite-checks" in str(e.value)
    assert len(st["received"]) == 1 and st["received"][0]["cmd"] == "env.checks"
    assert "[api] test -f ok.txt" in capsys.readouterr().err


@posix_only
def test_handoff_posts_with_checks_when_they_pass_or_despite_or_attach(fake_ipc, tmp_path):
    (tmp_path / "ok.txt").write_text("")
    env = {"repo": "api", "checks": "test -f ok.txt", "path": str(tmp_path)}
    st = fake_ipc({"run": True, "policy": "gate", "limit": 100, "timeout": 30, "environments": [env]}, {"id": "c1"},
                  {"run": True, "policy": "attach", "limit": 100, "timeout": 30, "environments": [{**env, "checks": "false"}]}, {"id": "c2"},
                  {"run": True, "policy": "gate", "limit": 100, "timeout": 30, "environments": [{**env, "checks": "false"}]}, {"id": "c3"},
                  {"run": False, "policy": "gate", "limit": 100, "timeout": 30, "environments": []}, {"id": "c4"})
    cli.main(["story", "yield", "--handoff", "--body", "green"])
    cli.main(["story", "yield", "--handoff", "--body", "red but attach"])
    cli.main(["story", "yield", "--handoff", "--body", "red despite", "--despite-checks"])
    cli.main(["story", "yield", "--handoff", "--body", "not implementing"])
    yields = [r["args"] for r in st["received"] if r["cmd"] == "story.yield"]
    assert yields[0]["checks"] == [{"repo": "api", "cmd": "test -f ok.txt", "exit": 0, "output": ""}]
    assert yields[1]["checks"][0]["exit"] == 1 and yields[2]["checks"][0]["exit"] == 1 and yields[3]["checks"] == []
    assert all(y["kind"] == "handoff" for y in yields)
```

Append to `tests/test_environments.py` (end-to-end section, uses `app_store` from Task 5 — the repo there has `checks="test -f ok.txt"`):

```python
def test_handoff_over_the_cli_carries_the_checks(app_store):
    """fake claude's `yield-handoff` runs `$HARNESS_CLI story yield --handoff` from inside the character."""
    st = app_store.stories
    key = st.create("Checks", "")
    chr_id = st.start(key, "go", "claude-fast")   # no outline required
    ctx = app_store.contexts.get(st.character(chr_id)["live_context"])
    assert wait_until(lambda: ctx.status == "idle"), ctx.lastError
    assert st.get(key)["ball"] == "author"           # the harness yielded for it at turn end
    d = st.cast_env_open(chr_id, "client")
    st.proceed(key)                                  # planning → implementing; resumes the protagonist
    assert wait_until(lambda: ctx.status == "idle" and st.get(key)["ball"] == "author", timeout_ms=15000)
    (Path(d["path"]) / "ok.txt").write_text("")
    st.comment(key, "yield-handoff")                 # the fake runs `story yield --handoff` from inside the character

    def posted():
        return any(c["kind"] == "handoff" and "checks" in c.get("structured", {}) for c in st.comments(key))
    assert wait_until(posted, timeout_ms=15000), [(c["author"], c["kind"], c["body"][:60]) for c in st.comments(key)]
    handoff = [c for c in st.comments(key) if c["kind"] == "handoff" and "checks" in c.get("structured", {})][-1]
    assert handoff["author"] == chr_id
    assert handoff["structured"]["checks"] == [{"repo": "client", "cmd": "test -f ok.txt", "exit": 0, "output": ""}]
```

In `tests/fake_claude.py`, next to the `yield-question` branch:

```python
        elif "yield-handoff" in prompt:
            cli = os.environ["HARNESS_CLI"].split() + ["story", "yield", "--handoff", "--body", "done"]
            r = subprocess.run(cli, capture_output=True, text=True, env=os.environ)
            tool_turn("Bash", {"command": "zharn story yield --handoff …"}, (r.stdout + r.stderr).strip(), is_error=r.returncode != 0)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_ipc.py tests/test_cli.py -q -k "repo or env or shared or checks or handoff"`
Expected: FAIL — `ValueError: unknown command 'repo.add'`, `argparse` errors on `repo`, `AttributeError: module 'harness.cli' has no attribute 'run_checks'`.

- [ ] **Step 3: Implement**

`harness/ipc.py`, inside `story_cmd` — rename nothing; add at the top of the function, before `verb = …`:

```python
        if cmd == "repo.add":
            return stories.cast_repo_add(ch_of(a), a["spec"], a.get("name", ""), a.get("checks", ""), a.get("setup", ""), a.get("base", ""))
        if cmd == "repo.list":
            return stories.repo_list()
        if cmd == "env.open":
            return stories.cast_env_open(ch_of(a), a["repo"])
        if cmd == "env.list":
            return stories.cast_env_list(ch_of(a))
        if cmd == "env.checks":
            return stories.env_checks(ch_of(a), a.get("thread", ""))
```

with, above `story_cmd`:

```python
    def ch_of(a: dict) -> str:
        if not a.get("character"):
            raise KeyError("character")
        return a["character"]
```

Change the `create` and `yield` branches:

```python
        if verb == "create":
            if ch:
                return stories.cast_create(ch, a["title"], a.get("description", ""), bool(a.get("start")), a.get("role", ""),
                                           bool(a.get("shared")))
            return stories.get(stories.create(a["title"], a.get("description", "")))
        ...
        if verb == "yield":
            return stories.cast_yield(ch, a["kind"], a["body"], a.get("options") or [], a.get("thread", ""), a.get("checks") or [])
```

In `h`, widen the logged prefix: replace `if cmd.startswith("story."):` with `if cmd.startswith(("story.", "repo.", "env.")):` and log the verb as `cmd.split(".", 1)[1] if cmd.startswith("story.") else cmd` (both places).

`harness/cli.py`:

Add `import subprocess` to the imports. Add the parsers before `sub.add_parser("ping")`:

```python
    rp = sub.add_parser("repo").add_subparsers(dest="verb", required=True)
    ra = rp.add_parser("add", help="Register a git repo (a URL is cloned into the workspace)")
    ra.add_argument("spec", help="path or URL"); ra.add_argument("--name", default=""); ra.add_argument("--checks", default="", help="run in your environment at every implementing handoff")
    ra.add_argument("--setup", default="", help="run once in every new worktree"); ra.add_argument("--base", default="", help="branch worktrees are cut from (default: HEAD at registration)")
    rp.add_parser("list")
    en = sub.add_parser("env").add_subparsers(dest="verb", required=True)
    en.add_parser("open", help="Where to work in a repo: prints the path; creates it on first use").add_argument("repo")
    en.add_parser("list", help="This story's environments")
```

Add flags: `c.add_argument("--shared", action="store_true", help="the sub-story works in your environment instead of its own worktree")` on `create`, and `y.add_argument("--despite-checks", action="store_true", help="post a handoff even though checks failed")` on `yield`.

Extend `out`'s column tuple with `"repo", "kind", "path", "branch"` — the final tuple is `("id", "key", "name", "phase", "ball", "status", "title", "storyKey", "owner", "kind", "model", "repo", "path", "branch")` (keep `kind` where it is).

Add above `main`:

```python
def run_checks(envs: list[dict], limit: int, timeout: float) -> list[dict]:
    """Workspace spec §4.6: each repo's `checks` in that environment; output truncated to `limit` characters."""
    results = []
    for e in envs:
        try:
            r = subprocess.run(e["checks"], shell=True, cwd=e["path"], capture_output=True, text=True, timeout=timeout)
            code, output = r.returncode, r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            code, output = -1, f"timed out after {timeout}s"
        results.append({"repo": e["repo"], "cmd": e["checks"], "exit": code, "output": output[-limit:]})
    return results
```

Dispatch — add branches after `elif a.noun == "role":`:

```python
    elif a.noun == "repo":
        if a.verb == "add":
            spec = a.spec if ("://" in a.spec or a.spec.startswith("git@")) else os.path.abspath(a.spec)
            out(request("repo.add", {"character": character(), "spec": spec, "name": a.name, "checks": a.checks,
                                     "setup": a.setup, "base": a.base}), a.json)
        else:
            out(request("repo.list", {}), a.json)
    elif a.noun == "env":
        if a.verb == "open":
            r = request("env.open", {"character": character(), "repo": a.repo})
            out(r if a.json else r["path"], a.json)
        else:
            out(request("env.list", {"character": character()}), a.json)
```

Replace the `create` args and the `yield` branch:

```python
        elif a.verb == "create":
            args = {"title": a.title, "description": a.description}
            if ch:
                args.update(character=ch, start=a.start, role=a.role, shared=a.shared)
            out(request("story.create", args), a.json)
        ...
        elif a.verb == "yield":
            if a.question == a.handoff:
                sys.exit("yield needs exactly one of --question / --handoff")
            opts = [o.strip() for o in a.options.split(",") if o.strip()]
            checks = []
            if a.handoff:   # §4.6: checks run here, in your turn, before the handoff posts
                plan = request("env.checks", {"character": character(), "thread": a.thread})
                checks = run_checks(plan["environments"], plan["limit"], plan["timeout"])
                failed = [c for c in checks if c["exit"] != 0]
                if failed and plan["policy"] == "gate" and not a.despite_checks:
                    for c in failed:
                        print(f"[{c['repo']}] {c['cmd']} → exit {c['exit']}\n{c['output']}", file=sys.stderr)
                    sys.exit("handoff refused: checks failed in " + ", ".join(c["repo"] for c in failed)
                             + " — fix and retry, or pass --despite-checks")
            out(request("story.yield", {"character": character(), "kind": "question" if a.question else "handoff",
                                        "body": a.body, "options": opts, "thread": a.thread, "checks": checks}), a.json)
```

- [ ] **Step 4: Run the tests, then the full suite**

Run: `~/.venvs/mh-conda/bin/python -m pytest tests/test_ipc.py tests/test_cli.py tests/test_environments.py -q` then the full suite.
Expected: PASS. The end-to-end handoff test needs `fake_claude` to find `HARNESS_CLI` — it does, via `Context._env`.

- [ ] **Step 5: Commit**

```bash
git add harness/ipc.py harness/cli.py tests/fake_claude.py tests/test_ipc.py tests/test_cli.py tests/test_environments.py
git commit -m "CLI/IPC: repo add/list, env open/list, story create --shared; checks run in the CLI at an implementing handoff, gated by HANDOFF_CHECKS

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: DESIGN status, brief the UI thread

**Files:**
- Modify: `docs/DESIGN.md` §8 item 6

- [ ] **Step 1: Update the status**

In `docs/DESIGN.md` §8, item 6, replace the trailing `**Partly done (workspace storage; start screen, repos, worktrees next).**` with:

```
**Harness side shipped 2026-09-03** (plan `docs/superpowers/plans/2026-09-03-environments.md`, spec §4 revised the same day):
   repo registration (`zharn repo add`, paths or URL clones), environments — every story on its own worktree
   cut from its parent environment, sub-stories optionally sharing the parent's — lazy managed worktrees,
   context placement at spawn, checks at implementing handoffs run by the CLI (`HANDOFF_CHECKS` gate/attach),
   Scratch under appdata as the default workspace. **Next:** start screen, workspace page (Relocate/Unregister),
   story move (§5.3), environments on the story page and cast panel (UI thread).
```

- [ ] **Step 2: Run the full suite** — PASS. Commit:

```bash
git add docs/DESIGN.md
git commit -m "DESIGN: environments status

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 3: Brief the UI thread**

Send the UI thread (`thr_h2eg7mfy7u`) this, with `bb thread message thr_h2eg7mfy7u "<text>"` (check `bb guide thread` for the exact verb first):

> Environments landed on `bb/thr_w5px42mt28` (workspace spec §4, revised 2026-09-03). What the QML can read now:
> - `stories.create(title, description)` is unchanged; a root story is always on its own worktree. Only sub-stories can be `shared` (a character's choice at `story create --shared`), so the creation form needs no toggle.
> - `_row`: `envMode`, `repos` (names), `environments: [{repo, kind, path, branch, error?}]` — show each environment's kind and branch on the story page; a `shared` sub-story stands in its parent's worktree.
> - `cast(key)` rows: `environment` (repo name or `""`).
> - `stories.repo_list()` → `[{name, path, checks, setup, base, status: ok|missing}]`; store methods `workspace.unregister(name)`, `workspace.relocate(name, path)` for the workspace page. `Workspace.scratch(root)` + `appdata_dir()` exist for the start screen; recents are not built.
> - Handoff comments carry `structured.checks: [{repo, cmd, exit, output}]` — the per-cell action bar can render exit≠0 in `danger`.
> - System notes `Registered repo …` appear in threads like the existing recast notes.

---

## Self-review

**Spec coverage.** §2.2 Scratch/appdata → Task 1. §3.1 record fields (`base` default) → Task 2 `register_repo`. §3.2 `repo add` path/URL + system comment → Tasks 2, 4, 6; unregister store method → Task 1. §3.3 missing + relocate → Tasks 1, 2 (`_repo` error), 4 (`_env_rows` error field). §4.1 kinds → Task 2. §4.2 mode at creation, parent chain, effective branch, `--shared` (sub-story only; a root story is refused by `EnvironmentStore.open` and has no UI path to it) → Tasks 2, 3, 4, 6. §4.3 records, never-store-resolved, derived `repos` → Tasks 2, 4. §4.4 idempotent, prune/recreate, setup retry, missing repo, git errors as-is → Task 2. §4.5 placement at every spawn, minions (process cwd), friends/forks inherit, recast keeps, protagonist in workspace dir, `HARNESS_REPO`/`HARNESS_ENV` → Tasks 4, 5. §4.6 checks in the CLI, main thread + implementing only, truncation, gate/attach knob, `--despite-checks` → Tasks 4, 6. §6 storage keys → Tasks 2, 4. §8 CLI → Task 6. §10 tests → each task; `test_story_move.py` and `test_ui_start.py` are explicitly out of scope.

**Type consistency.** `EnvironmentStore.open/describe` return the resolved dict everywhere (`path`, `branch`, `checks` present); `get`/`records` return stored records. `story_info(key) -> (parent, mode)` is what `StoryStore._story_info` returns. `placement(ctx) -> (cwd, env)` in Tasks 4 and 5. `cast_yield(..., checks)` already exists with that name; `env_checks` returns `run/environments/policy/limit/timeout`, which `cli.main` reads by those keys.

**Known trap for executors.** `tests/test_stories.py` imports `gitfix` via `sys.path`; keep the `_sys`/`_Path` aliases so the module's existing names are untouched.
