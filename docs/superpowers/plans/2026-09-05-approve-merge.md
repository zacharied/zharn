# Approve fast-forwards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Approve fast-forwards every environment of a story into its target branch, refuses when a branch is behind, records what landed in its system comment, and removes worktrees as the cast retires; an implementing handoff on main refuses a branch behind its target.

**Architecture:** `harness/environments.py` owns the git: `target`, `behind`, `integrate`, `remove`. The lifecycle reducer stays pure and records the merge results the store hands it (`Approve.merged`). `StoryStore` orders the steps — precondition, precheck, integrate, persist, sweep — for both the human `approve` intent and a character's `approve <key>`. The CLI gains the ancestry gate beside the tree gate, inside the character's turn. Specs are rewritten to the present tense last.

**Tech Stack:** Python 3.12, PySide6/QML, pytest (`~/.venvs/mh-conda/bin/python -m pytest -q`), real temporary git repos via `tests/gitfix.py`.

**Spec:** `docs/superpowers/proposals/2026-09-05-approve-merge.md` (then `docs/specs/workspace-model.md` §4.8 and `docs/specs/story-lifecycle.md` §2.1 once Task 9 rewrites them).

## Global Constraints

- No backward compatibility (DESIGN.md §0): no flags, aliases or migration shims; tests are rewritten to the new shape.
- Specs are present tense; proposals and plans are not updated after they land.
- No explanatory copy in the UI; labels, placeholders and tooltips only.
- Tests: `~/.venvs/mh-conda/bin/python -m pytest -q` from the repo root. Never `pip install -e .` from this worktree (mh-conda has one shared editable install pointing at the main checkout). UI tests hot-reload on writes; `find()` wants exactly one visible item.
- Git in the harness never prompts and never runs unbounded: every call goes through `environments.git()` (bounded by `GIT_TIMEOUT_S`).
- The harness process never waits on a test suite: Approve runs no checks.
- Fast-forward only. The harness never creates a merge commit.

---

## File structure

| File | Responsibility in this change |
|---|---|
| `harness/environments.py` | `target(rec)`, `behind(rec)`, `integrate(rec)`, `remove(rec)`, `_checkout_of()`; `describe` carries `target` and `repo_path`; `records()` skips removed environments; `open()` revives a removed one |
| `harness/lifecycle.py` | `Approve.merged`; the Approve comment's body lines and `structured.merged`; `merged_lines()` |
| `harness/stories.py` | `_approve()` ordering precondition → precheck → integrate → persist → sweep, used by `approve` and `cast_author`; `_sweep_environments()` at Approve and at turn end of a done story; `_env_rows` via `environments.target` |
| `harness/cli.py` | `behind_targets()` and the ancestry gate between the tree gate and the checks; `target` in `out()`'s column table |
| `harness/skills/skills/implementing-a-story/SKILL.md` | bring the branch up to date before the handoff |
| `tests/test_environments.py`, `tests/test_lifecycle.py`, `tests/test_stories.py`, `tests/test_cli.py`, `tests/test_ui_story.py` | one test per behaviour in the proposal §7 |
| `docs/specs/workspace-model.md`, `docs/specs/story-lifecycle.md`, `docs/DESIGN.md` | present-tense description |

---

### Task 1: `target`, `behind`, and a fuller `describe`

**Files:**
- Modify: `harness/environments.py` (class `EnvironmentStore`, after `describe` at `:108`)
- Test: `tests/test_environments.py`

**Interfaces:**
- Produces: `EnvironmentStore.target(rec: dict) -> str` — the parent environment's branch, else the repo's registered `base`; no git call, safe for a missing repo (returns `""` when the repo is unregistered). `EnvironmentStore.behind(rec) -> int` — commits on the target the branch lacks (`git rev-list --count <branch>..<target>` in the repo's main checkout); raises `EnvError` for a missing repo. `describe(rec)` gains `"target"` and `"repo_path"` (str).

- [ ] **Step 1: Write the failing tests** (append under the "sub-stories" section of `tests/test_environments.py`)

```python
# ---------------------------------------------------------------- target and behind (§4.8)

def test_target_is_base_at_the_root_and_the_parents_branch_below(ws, repo):
    es = store(ws, **{"ZH-1": None, "ZH-2": "ZH-1"})
    child = es.open("ZH-2", "client")
    assert es.target(es.get("ZH-1", "client")) == "main"
    assert es.target(es.get("ZH-2", "client")) == "zharn/ZH-1"
    assert child["target"] == "zharn/ZH-1" and child["repo_path"] == str(repo.resolve())


def test_behind_counts_target_commits_the_branch_lacks(ws, repo):
    es = store(ws, **{"ZH-1": None})
    es.open("ZH-1", "client")
    rec = es.get("ZH-1", "client")
    assert es.behind(rec) == 0
    commit_file(repo, "m1.txt"); commit_file(repo, "m2.txt")        # main moves on in the main checkout
    assert es.behind(rec) == 2
    run(Path(rec["path"]), "rebase", "-q", "main")
    assert es.behind(rec) == 0
    commit_file(Path(rec["path"]), "work.txt")                        # ahead is not behind
    assert es.behind(rec) == 0


def test_behind_on_a_missing_repo_is_the_missing_message(ws, repo):
    from gitfix import rmtree
    es = store(ws, **{"ZH-1": None})
    es.open("ZH-1", "client")
    rmtree(repo)
    with pytest.raises(EnvError, match="missing"):
        es.behind(es.get("ZH-1", "client"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `~/.venvs/mh-conda/bin/python -m pytest -q tests/test_environments.py -k "target_is_base or behind" -q`
Expected: FAIL with `AttributeError: 'EnvironmentStore' object has no attribute 'target'`

- [ ] **Step 3: Implement**

In `harness/environments.py`, replace `describe` and add the two methods:

```python
    def describe(self, rec: dict) -> dict:
        r = self.ws.repo(rec["repo"]) or {}
        return {**rec, "checks": r.get("checks", ""), "target": self.target(rec),
                "repo_path": str(self.ws.repo_path(r)) if r else ""}

    # ---------------------------------------------------------------- the target (§4.8)
    def target(self, rec: dict) -> str:
        """The branch this environment's branch lands in: the parent environment's branch, else the repo's `base`.
        No git call — this is read for every board row — and "" when the repo is no longer registered."""
        if rec.get("parent"):
            pk, prepo = rec["parent"].split(":", 1)
            prec = self.get(pk, prepo)
            return prec["branch"] if prec else f"zharn/{pk}"
        return (self.ws.repo(rec["repo"]) or {}).get("base", "")

    def behind(self, rec: dict) -> int:
        """Commits on the target that the branch lacks. 0 means up to date: the target's tip is an ancestor."""
        _, repo_path = self._repo(rec["repo"])
        return int(git(repo_path, "rev-list", "--count", f"{rec['branch']}..{self.target(rec)}") or 0)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `~/.venvs/mh-conda/bin/python -m pytest -q tests/test_environments.py tests/test_stories.py -q`
Expected: all PASS (`test_env_open_creates_the_worktree_records_it_on_the_character_and_the_story` compares `cast_env_list` against `describe` output on both sides, so it stays green).

- [ ] **Step 5: Commit**

```bash
git add harness/environments.py tests/test_environments.py
git commit -m "Environments: target and behind; describe carries the target and the repo path"
```

---

### Task 2: `integrate` — the fast-forward, where the target lives

**Files:**
- Modify: `harness/environments.py` (module-level helper after `head_branch`; method after `behind`)
- Test: `tests/test_environments.py`

**Interfaces:**
- Consumes: `target`, `behind` from Task 1; `git()`.
- Produces: `_checkout_of(repo_path: Path, branch: str) -> Path | None`; `EnvironmentStore.integrate(rec) -> dict` returning `{"repo", "branch", "target", "from", "to", "commits"}` (short hashes; `commits` is how many landed, 0 for a no-op). Raises `EnvError` when behind (message `"<branch> is N commit(s) behind <target> in <repo> — rebase onto <target> (or merge it in) and retry"`) or when git refuses.

- [ ] **Step 1: Write the failing tests**

```python
# ---------------------------------------------------------------- integrate (§4.8)

def test_integrate_fast_forwards_base_in_the_main_checkout(ws, repo):
    es = store(ws, **{"ZH-1": None})
    d = es.open("ZH-1", "client")
    commit_file(Path(d["path"]), "work.txt")
    m = es.integrate(es.get("ZH-1", "client"))
    assert (m["repo"], m["branch"], m["target"], m["commits"]) == ("client", "zharn/ZH-1", "main", 1)
    assert m["to"] == run(repo, "rev-parse", "--short", "zharn/ZH-1") and m["from"] != m["to"]
    assert run(repo, "rev-parse", "main") == run(repo, "rev-parse", "zharn/ZH-1")
    assert (repo / "work.txt").exists()                               # the checked-out tree moved with the ref


def test_integrate_moves_the_ref_when_base_is_checked_out_nowhere(ws, repo):
    run(repo, "checkout", "-q", "-b", "other")                        # main is no longer checked out anywhere
    es = store(ws, **{"ZH-1": None})
    d = es.open("ZH-1", "client")
    commit_file(Path(d["path"]), "work.txt")
    es.integrate(es.get("ZH-1", "client"))
    assert run(repo, "rev-parse", "main") == run(repo, "rev-parse", "zharn/ZH-1")
    assert branch_of(repo) == "other" and not (repo / "work.txt").exists()


def test_integrate_with_nothing_committed_is_a_no_op(ws, repo):
    es = store(ws, **{"ZH-1": None})
    es.open("ZH-1", "client")
    before = run(repo, "rev-parse", "main")
    m = es.integrate(es.get("ZH-1", "client"))
    assert m["commits"] == 0 and m["from"] == m["to"] and run(repo, "rev-parse", "main") == before


def test_integrate_refuses_a_branch_behind_its_target_and_moves_nothing(ws, repo):
    es = store(ws, **{"ZH-1": None})
    d = es.open("ZH-1", "client")
    commit_file(Path(d["path"]), "work.txt")
    commit_file(repo, "m.txt")
    before = run(repo, "rev-parse", "main")
    with pytest.raises(EnvError, match=r"zharn/ZH-1 is 1 commit behind main in client — rebase onto main"):
        es.integrate(es.get("ZH-1", "client"))
    assert run(repo, "rev-parse", "main") == before
    run(Path(d["path"]), "rebase", "-q", "main")
    assert es.integrate(es.get("ZH-1", "client"))["commits"] == 1 and (repo / "work.txt").exists()


def test_integrate_substory_fast_forwards_the_parents_worktree(ws, repo):
    es = store(ws, **{"ZH-1": None, "ZH-2": "ZH-1"})
    child = es.open("ZH-2", "client")
    parent = es.get("ZH-1", "client")
    (Path(parent["path"]) / "notes.txt").write_text("wip")           # the parent's cast is mid-work, on other files
    commit_file(Path(child["path"]), "part.txt")
    m = es.integrate(es.get("ZH-2", "client"))
    assert m["target"] == "zharn/ZH-1" and m["commits"] == 1
    assert (Path(parent["path"]) / "part.txt").exists() and (Path(parent["path"]) / "notes.txt").read_text() == "wip"
    assert run(repo, "rev-parse", "main") != run(repo, "rev-parse", "zharn/ZH-1")   # the root is untouched


def test_integrate_refuses_when_the_parents_dirty_file_would_be_overwritten(ws, repo):
    es = store(ws, **{"ZH-1": None, "ZH-2": "ZH-1"})
    child = es.open("ZH-2", "client")
    parent = es.get("ZH-1", "client")
    (Path(parent["path"]) / "shared.txt").write_text("theirs")
    commit_file(Path(child["path"]), "shared.txt", "mine\n")
    before = run(repo, "rev-parse", "zharn/ZH-1")
    with pytest.raises(EnvError, match="would be overwritten"):
        es.integrate(es.get("ZH-2", "client"))
    assert run(repo, "rev-parse", "zharn/ZH-1") == before and (Path(parent["path"]) / "shared.txt").read_text() == "theirs"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `~/.venvs/mh-conda/bin/python -m pytest -q tests/test_environments.py -k integrate -q`
Expected: FAIL with `AttributeError: ... 'integrate'`

- [ ] **Step 3: Implement**

Module-level, after `head_branch`:

```python
def _checkout_of(repo_path: Path, branch: str) -> Path | None:
    """The worktree that has `branch` checked out, or None when it is checked out nowhere."""
    wt = None
    for line in git(repo_path, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            wt = Path(line[len("worktree "):])
        elif line == f"branch refs/heads/{branch}":
            return wt
    return None
```

Method, after `behind`:

```python
    def integrate(self, rec: dict) -> dict:
        """§4.8: fast-forward the target onto the branch's tip — in the target's worktree when it is checked out, so
        its files move too; else the ref alone. Never a merge commit: what lands is what the checks ran on."""
        _, repo_path = self._repo(rec["repo"])
        tgt, br = self.target(rec), rec["branch"]
        n_behind = self.behind(rec)
        if n_behind:
            s = "" if n_behind == 1 else "s"
            raise EnvError(f"{br} is {n_behind} commit{s} behind {tgt} in {rec['repo']} — rebase onto {tgt} (or merge it in) and retry")
        frm, to = git(repo_path, "rev-parse", "--short", tgt), git(repo_path, "rev-parse", "--short", br)
        n = int(git(repo_path, "rev-list", "--count", f"{tgt}..{br}") or 0)
        if n:
            wt = _checkout_of(repo_path, tgt)
            if wt is not None:
                git(wt, "merge", "--ff-only", "-q", br)
            else:
                git(repo_path, "branch", "-f", tgt, br)
        return {"repo": rec["repo"], "branch": br, "target": tgt, "from": frm, "to": to, "commits": n}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `~/.venvs/mh-conda/bin/python -m pytest -q tests/test_environments.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add harness/environments.py tests/test_environments.py
git commit -m "Environments: integrate fast-forwards the target in its worktree or by ref; refuses a branch behind"
```

---

### Task 3: `remove`, and a removed environment is revived by `open`

**Files:**
- Modify: `harness/environments.py` (`records`, `open`, new `remove`)
- Test: `tests/test_environments.py`

**Interfaces:**
- Produces: `EnvironmentStore.remove(rec) -> None` — `git worktree remove --force`, stamps `rec["removed"] = time.time()`, keeps the branch and the record. `records(story)` returns only records without `removed`; `get()` still returns everything. `open()` on a removed record prunes, re-adds on the kept branch, drops `removed`, and runs `setup` again.

- [ ] **Step 1: Write the failing tests**

```python
# ---------------------------------------------------------------- remove (§4.8 cleanup)

def test_remove_deletes_the_worktree_and_keeps_the_branch_and_record(ws, repo):
    es = store(ws, **{"ZH-1": None})
    d = es.open("ZH-1", "client")
    commit_file(Path(d["path"]), "work.txt")
    es.remove(es.get("ZH-1", "client"))
    assert not Path(d["path"]).exists()
    assert "zharn/ZH-1" in run(repo, "branch", "--list", "zharn/ZH-1")
    assert es.records("ZH-1") == [] and es.get("ZH-1", "client")["removed"] > 0
    assert json.loads((ws.local_dir / "environments.json").read_text())[env_key("ZH-1", "client")]["removed"] > 0
    assert "zharn/ZH-1" not in run(repo, "worktree", "list")


def test_open_revives_a_removed_environment_on_its_branch_and_reruns_setup(ws, tmp_path):
    p = make_repo(tmp_path / "ws" / "api")
    marker = tmp_path / "setups"
    register_repo(ws, str(p), setup=f"echo run >> {marker}")
    es = store(ws, **{"ZH-1": None})
    d = es.open("ZH-1", "api")
    commit_file(Path(d["path"]), "work.txt")
    es.remove(es.get("ZH-1", "api"))
    d2 = es.open("ZH-1", "api")
    assert d2["path"] == d["path"] and Path(d2["path"]).is_dir() and branch_of(Path(d2["path"])) == "zharn/ZH-1"
    assert (Path(d2["path"]) / "work.txt").exists() and "removed" not in d2
    assert marker.read_text().count("run") == 2 and es.records("ZH-1") == [es.get("ZH-1", "api")]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `~/.venvs/mh-conda/bin/python -m pytest -q tests/test_environments.py -k "remove or revives" -q`
Expected: FAIL with `AttributeError: ... 'remove'`

- [ ] **Step 3: Implement**

```python
    def records(self, story: str) -> list[dict]:
        return [r for r in self._records.values() if r["story"] == story and not r.get("removed")]
```

In `open`, change the revive branch to cover removal as well:

```python
        elif rec.get("removed") or not Path(rec["path"]).is_dir():
            _, repo_path = self._repo(repo)   # removed after Approve, or deleted by hand: prune, re-add on the kept branch
            git(repo_path, "worktree", "prune")
            Path(rec["path"]).parent.mkdir(parents=True, exist_ok=True)
            git(repo_path, "worktree", "add", "-q", rec["path"], rec["branch"])
            rec.pop("removed", None)
            rec["setup_done"] = False   # a fresh tree: §3.1 setup runs once in every new worktree, including a re-added one
            self._save()
```

New method after `integrate`:

```python
    def remove(self, rec: dict) -> None:
        """§4.8 cleanup: the worktree goes; the branch (the story's history) and the record stay, stamped `removed`.
        `open` brings it back on the same branch."""
        _, repo_path = self._repo(rec["repo"])
        if Path(rec["path"]).is_dir():
            git(repo_path, "worktree", "remove", "--force", rec["path"])
        else:
            git(repo_path, "worktree", "prune")
        rec["removed"] = time.time()
        self._save()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `~/.venvs/mh-conda/bin/python -m pytest -q tests/test_environments.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add harness/environments.py tests/test_environments.py
git commit -m "Environments: remove a worktree after Approve, keep the branch; open revives it"
```

---

### Task 4: The reducer records what landed

**Files:**
- Modify: `harness/lifecycle.py:104-107` (Approve dataclass), the Approve branch of `step` (`:374-386`), a `merged_lines()` helper beside `question_lines`
- Test: `tests/test_lifecycle.py`

**Interfaces:**
- Produces: `Approve(note="", by="human", merged: list[dict] = [])`; `merged_lines(merged) -> list[str]` — `"merged <branch> → <target> in <repo> (<from>..<to>, N commit(s))"` or `"merged <branch> → <target> in <repo> (no changes)"`; the Approve comment's body is `"approved"` (with the note as `_with_note` renders it) followed by one merged line per entry, and `structured.merged` is the list verbatim (absent when empty).

- [ ] **Step 1: Write the failing tests** (under the "Approve / Back to planning" section)

```python
def test_approve_records_what_landed_in_body_and_structured():
    s = at("implementing", "author")
    merged = [{"repo": "zharn", "branch": "zharn/ZH-1", "target": "main", "from": "a1b2c3d", "to": "e4f5a6b", "commits": 4},
              {"repo": "client", "branch": "zharn/ZH-1", "target": "main", "from": "0000000", "to": "0000000", "commits": 0}]
    s, c = run(s, Approve(note="ship it", merged=merged))
    assert c["body"].splitlines() == ["approved — ship it",
                                      "merged zharn/ZH-1 → main in zharn (a1b2c3d..e4f5a6b, 4 commits)",
                                      "merged zharn/ZH-1 → main in client (no changes)"]
    assert c["structured"]["merged"] == merged and c["structured"]["transition"]["to"] == ["done", None]


def test_approve_without_environments_has_no_merged_key():
    s, c = run(at("implementing", "author"), Approve())
    assert c["body"] == "approved" and "merged" not in c["structured"]


def test_merged_lines_singular_commit():
    assert merged_lines([{"repo": "r", "branch": "zharn/K-1", "target": "zharn/K-0", "from": "aaa", "to": "bbb", "commits": 1}]) == \
        ["merged zharn/K-1 → zharn/K-0 in r (aaa..bbb, 1 commit)"]
```

Add `merged_lines` to the file's `from harness.lifecycle import ...` line.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `~/.venvs/mh-conda/bin/python -m pytest -q tests/test_lifecycle.py -k "records_what_landed or no_merged_key or merged_lines" -q`
Expected: FAIL with `ImportError: cannot import name 'merged_lines'`

- [ ] **Step 3: Implement**

Dataclass (`field` is already imported for `Yield.questions`; add it to the `dataclasses` import if not):

```python
@dataclass
class Approve:
    note: str = ""
    by: str = "human"
    merged: list = field(default_factory=list)   # workspace spec §4.8: what the store fast-forwarded, one record per environment
```

Helper beside `question_lines`:

```python
def merged_lines(merged: list[dict]) -> list[str]:
    """One line per environment for the Approve comment: `merged <branch> → <target> in <repo> (<range>, N commits)`."""
    out = []
    for m in merged:
        n = m.get("commits", 0)
        what = f"{m['from']}..{m['to']}, {n} commit{'' if n == 1 else 's'}" if n else "no changes"
        out.append(f"merged {m['branch']} → {m['target']} in {m['repo']} ({what})")
    return out
```

In `step`, the Approve/BackToPlanning branch:

```python
    elif isinstance(action, (Approve, BackToPlanning)):
        if action.by != s.author:
            raise Rejected(f"only the author ({s.author}) can do that")
        if (s.phase, s.ball) != ("implementing", "author"):
            raise Rejected(f"requires (implementing, author); {s.key} is ({s.phase}, {s.ball})")
        m = s.main
        structured = None
        if isinstance(action, Approve):
            for t in s.threads:  # terminal sweep: every open thread resolves, main included
                t.turn, t.pending_yield = "resolved", None
            s.phase = "done"
            body = "\n".join([_with_note("approved", action.note), *merged_lines(action.merged)])
            if action.merged:
                structured = {"merged": [dict(x) for x in action.merged]}
        else:
            m.turn, m.pending_yield = "cast", None
            s.phase, body = "planning", _with_note("back to planning", action.note)
        c = _comment(s, comment_id, now, thread_id=m.id, author=action.by, kind="system", body=body, structured=structured)
```

`step` deep-copies the story on entry (`lifecycle.py:259`) and sets `c["structured"]["transition"] = ...` by key after the branch (`:419`), so the `structured` dict passed here keeps `merged` alongside `transition`, and the store's probe call in Task 5 mutates nothing.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `~/.venvs/mh-conda/bin/python -m pytest -q tests/test_lifecycle.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add harness/lifecycle.py tests/test_lifecycle.py
git commit -m "Lifecycle: Approve carries what landed — merged lines in the body, structured.merged"
```

---

### Task 5: The store orders Approve, and sweeps worktrees as the cast retires

**Files:**
- Modify: `harness/stories.py` — `_env_rows` (`:198-210`), `_on_turn_end` (`:486-500`), `approve` (`:667`), `cast_author` (`:932-937`), new `_approve` and `_sweep_environments`
- Test: `tests/test_stories.py`

**Interfaces:**
- Consumes: `environments.target/behind/integrate/remove/records` (Tasks 1–3); `lc.Approve(merged=)` (Task 4).
- Produces: `StoryStore._approve(key, by, note) -> dict` (the comment); `StoryStore._sweep_environments(key)`; `approve(key, note)` and `cast_author(ch, "approve", key)` both go through `_approve`. Rejection text for a branch behind: `"cannot approve: <branch> is N commit(s) behind <target> in <repo> — reply and have the cast rebase, then approve again"` (`lc.Rejected`); a missing repo or a git refusal surfaces as `EnvError` with its own message.

- [ ] **Step 1: Write the failing tests** (append at the end of the environments section; extend the gitfix import at the top of `tests/test_stories.py` to `from gitfix import make_repo, branch_of, commit_file, run`)

```python
# ---------------------------------------------------------------- Approve fast-forwards (workspace spec §4.8)

def implementing_with_work(store, contexts, repo_name="client"):
    """A started story, in implementing, one commit in its worktree, handed off: the ball is the author's."""
    key, chr_id = started(store)
    d = store.cast_env_open(chr_id, repo_name)
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    commit_file(_Path(d["path"]), "work.txt")
    store.cast_yield(chr_id, "handoff", "done")
    return key, chr_id, d


def test_approve_fast_forwards_base_records_it_and_removes_the_worktree(store, contexts, repo, ws):
    key, chr_id, d = implementing_with_work(store, contexts)
    contexts.get(store.character(chr_id)["live_context"]).status = "idle"
    c = store.approve(key, "nice")
    assert store.story(key).phase == "done"
    assert run(repo, "rev-parse", "main") == run(repo, "rev-parse", f"zharn/{key}") and (repo / "work.txt").exists()
    last = store.comments(key)[-1]
    assert last["body"].splitlines()[0] == "approved — nice"
    assert last["body"].splitlines()[1].startswith(f"merged zharn/{key} → main in client (") and last["body"].endswith("1 commit)")
    assert last["structured"]["merged"][0] == {**last["structured"]["merged"][0], "repo": "client", "target": "main", "commits": 1}
    assert not _Path(d["path"]).exists() and store.get(key)["environments"] == []      # idle cast: swept now
    assert f"zharn/{key}" in run(repo, "branch", "--list", f"zharn/{key}")             # the branch stays


def test_approve_refuses_a_branch_behind_and_leaves_the_story_implementing(store, contexts, repo):
    key, chr_id, d = implementing_with_work(store, contexts)
    commit_file(repo, "m.txt")                                                          # main moved after the handoff
    with pytest.raises(Rejected, match=f"cannot approve: zharn/{key} is 1 commit behind main in client"):
        store.approve(key)
    assert (store.story(key).phase, store.story(key).ball) == ("implementing", "author")
    assert not (repo / "work.txt").exists() and _Path(d["path"]).is_dir()
    run(_Path(d["path"]), "rebase", "-q", "main")
    store.approve(key)
    assert store.story(key).phase == "done" and (repo / "work.txt").exists() and (repo / "m.txt").exists()


def test_approve_with_one_repo_behind_moves_nothing(store, contexts, repo, ws, tmp_path):
    api = make_repo(tmp_path / "ws" / "api"); register_repo(ws, str(api))
    key, chr_id, d = implementing_with_work(store, contexts)
    d2 = store.cast_env_open(chr_id, "api"); commit_file(_Path(d2["path"]), "api.txt")
    commit_file(api, "moved.txt")
    before = run(repo, "rev-parse", "main")
    with pytest.raises(Rejected, match="behind main in api"):
        store.approve(key)
    assert run(repo, "rev-parse", "main") == before and store.story(key).phase == "implementing"


def test_approve_partial_failure_is_retried_to_completion(store, contexts, repo, ws, tmp_path):
    api = make_repo(tmp_path / "ws" / "api"); register_repo(ws, str(api))
    key, chr_id, d = implementing_with_work(store, contexts)
    d2 = store.cast_env_open(chr_id, "api"); commit_file(_Path(d2["path"]), "api.txt")
    (api / "api.txt").write_text("dirty")                     # api's main checkout would be overwritten: git refuses
    with pytest.raises(EnvError, match="would be overwritten"):
        store.approve(key)
    assert (repo / "work.txt").exists() and store.story(key).phase == "implementing"   # client landed, api did not
    (api / "api.txt").unlink()
    store.approve(key)
    body = store.comments(key)[-1]["body"]
    assert f"merged zharn/{key} → main in client (no changes)" in body and "in api (" in body and (api / "api.txt").exists()


def test_approve_on_a_missing_repo_is_refused_with_the_missing_message(store, contexts, repo):
    from gitfix import rmtree
    key, chr_id, d = implementing_with_work(store, contexts)
    rmtree(repo)
    with pytest.raises(EnvError, match="missing"):
        store.approve(key)
    assert store.story(key).phase == "implementing"


def test_worktree_is_swept_when_the_last_working_character_settles(store, contexts, repo):
    key, chr_id = started(store)
    d = store.cast_env_open(chr_id, "client")
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    r = store.cast_call(chr_id, "claude-fast", "build")        # the friend's context is working
    store._apply(key, Yield(thread_id=r["thread"], by=r["character"], kind="handoff", body="built"))
    commit_file(_Path(d["path"]), "work.txt")
    store.cast_yield(chr_id, "handoff", "done")
    contexts.get(store.character(chr_id)["live_context"]).status = "idle"
    store.approve(key)
    assert store.story(key).phase == "done" and _Path(d["path"]).is_dir()          # a turn is still finishing there
    settle(store, contexts, r["character"])
    assert not _Path(d["path"]).exists() and store.get(key)["environments"] == []


def test_reopen_after_approve_revives_the_worktree_behind_its_target(store, contexts, repo):
    key, chr_id, d = implementing_with_work(store, contexts)
    contexts.get(store.character(chr_id)["live_context"]).status = "idle"
    store.approve(key)
    commit_file(repo, "later.txt")
    store.reopen(key, "one more thing")
    d2 = store.cast_env_open(chr_id, "client")
    assert d2["path"] == d["path"] and _Path(d2["path"]).is_dir() and branch_of(_Path(d2["path"])) == f"zharn/{key}"
    assert store.get(key)["environments"][0]["into"] == "main"
    assert store.environments.behind(store.environments.get(key, "client")) == 1


def test_character_approves_its_substory_into_its_own_worktree(store, contexts, repo):
    key, chr_id = started(store)
    d = store.cast_env_open(chr_id, "client")
    store.cast_yield(chr_id, "handoff", "outline"); store.proceed(key)
    live = contexts.get(store.character(chr_id)["live_context"]); live.status = "idle"
    sub = store.cast_create(chr_id, "part", start=True, role="claude-fast")
    lead = store.story(sub).protagonist
    ds = store.cast_env_open(lead, "client")
    assert branch_of(_Path(ds["path"])) == f"zharn/{sub}" and store.get(sub)["environments"][0]["into"] == f"zharn/{key}"
    commit_file(_Path(ds["path"]), "part.txt")
    store.cast_yield(lead, "handoff", "outline"); store.cast_author(chr_id, "proceed", sub)
    store.cast_yield(lead, "handoff", "built")
    contexts.get(store.character(lead)["live_context"]).status = "idle"
    c = store.cast_author(chr_id, "approve", sub)
    assert f"merged zharn/{sub} → zharn/{key} in client (" in c["body"]
    assert (_Path(d["path"]) / "part.txt").exists() and not (repo / "part.txt").exists()
    assert not _Path(ds["path"]).exists() and store.story(sub).phase == "done"
```

`register_repo` and `EnvError` must be imported in `tests/test_stories.py` (`from harness.environments import EnvError, register_repo`); `_Path` is the file's existing alias for `pathlib.Path`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `~/.venvs/mh-conda/bin/python -m pytest -q tests/test_stories.py -k "approve_fast_forwards or approve_refuses or one_repo_behind or partial_failure or missing_repo or swept or revives or approves_its_substory" -q`
Expected: FAIL — the first asserts on `run(repo, "rev-parse", "main")` equality (nothing merged) and the worktree still existing.

- [ ] **Step 3: Implement**

`_env_rows` becomes:

```python
    def _env_rows(self, key: str) -> list[dict]:
        """One row per live environment; `into` is the branch this story's branch lands in (workspace spec §4.8)."""
        return [{"repo": r["repo"], "path": r["path"], "branch": r["branch"], "parent": r["parent"],
                 "into": self.environments.target(r)} for r in self.environments.records(key)]
```

In `_on_turn_end`, replace the early return:

```python
        if s.phase in lc.TERMINAL:
            self._sweep_environments(key)   # §4.8: a done story's worktrees go once nobody is still finishing a turn there
            return
```

Replace `approve`:

```python
    @Slot(str, str)
    @intent
    def approve(self, key, note=""):
        self._approve(self._key(key), self._on_behalf(key), note)
```

New methods next to `_author_action`:

```python
    def _approve(self, key: str, by: str, note: str) -> dict:
        """§2.1 Approve in the store's order (workspace spec §4.8): the lifecycle precondition, every environment
        prechecked, each fast-forwarded, then the reducer's comment carrying what landed, then the sweep. A story is
        never done with unmerged work; a failure partway leaves the story implementing and the retry finishes."""
        lc.step(self._stories[key], lc.Approve(by=by, note=note), comment_id="probe", now=0.0)   # rejection only: pure
        recs = self.environments.records(key)
        behind = []
        for r in recs:
            n = self.environments.behind(r)
            if n:
                behind.append(f"{r['branch']} is {n} commit{'' if n == 1 else 's'} behind {self.environments.target(r)} in {r['repo']}")
        if behind:
            raise lc.Rejected("cannot approve: " + "; ".join(behind) + " — reply and have the cast rebase, then approve again")
        merged = [self.environments.integrate(r) for r in recs]
        c = self._author_action(key, lc.Approve(by=by, note=note, merged=merged), resume=False)
        self._sweep_environments(key)
        return c

    def _sweep_environments(self, key: str) -> None:
        """Workspace spec §4.8 cleanup: once a done story has no character mid-turn, its worktrees are removed."""
        if self._stories[key].phase != "done":
            return
        for ch in self._characters.values():
            if ch["story_key"] == key and ch.get("live_context"):
                ctx = self._contexts.get(ch["live_context"])
                if ctx is not None and ctx.status in WORKING:
                    return
        for rec in self.environments.records(key):
            try:
                self.environments.remove(rec)
            except EnvError as e:
                if self.notifier is not None:
                    self.notifier.error(f"{key}: {e}")
        self._refresh()
```

In `cast_author`, before the `actions = {...}` dict:

```python
        if verb == "approve":
            c = self._approve(key, by, note)
            self._refresh()
            return c
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `~/.venvs/mh-conda/bin/python -m pytest -q tests/test_stories.py tests/test_ipc.py tests/test_lifecycle.py -q`
Expected: all PASS. `test_approve_lets_a_working_friend_finish_and_delivers_nothing_after` still passes: no environments, so nothing to integrate or sweep.

- [ ] **Step 5: Commit**

```bash
git add harness/stories.py tests/test_stories.py
git commit -m "Store: Approve prechecks and fast-forwards every environment, records what landed, sweeps worktrees as the cast retires"
```

---

### Task 6: The ancestry gate in the CLI, and `target` in `env list`

**Files:**
- Modify: `harness/cli.py` — `out()` column table (`:74`), new `behind_targets()` beside `dirty_trees` (`:92`), the handoff branch of `main` (`:255-262`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `env.checks` environments now carry `target` and `repo_path` (Task 1's `describe`).
- Produces: `cli.behind_targets(envs) -> list[dict]` with `{"repo", "branch", "target", "behind"}`; the refusal `"handoff refused: <branch> is N commit(s) behind <target> in <repo> — rebase onto <target> (or merge it in) and retry"` after the tree gate and before the checks; `env list` prints `target=<branch>`.

- [ ] **Step 1: Write the failing tests** (beside `test_dirty_trees_reports_status_per_repo`)

```python
def _behind_setup(tmp_path):
    """A repo whose `zharn/X-1` worktree is one commit behind main; returns (repo, worktree)."""
    repo = _git_repo(tmp_path / "api")
    wt = tmp_path / "wt"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "zharn/X-1", str(wt), "main"], cwd=repo, check=True)
    (repo / "m.txt").write_text("m")
    subprocess.run(["git", "add", "m.txt"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "m"], cwd=repo, check=True)
    return repo, wt


def test_behind_targets_counts_per_environment_and_skips_unknown_targets(tmp_path):
    repo, wt = _behind_setup(tmp_path)
    env = {"repo": "api", "path": str(wt), "branch": "zharn/X-1", "target": "main", "repo_path": str(repo)}
    assert cli.behind_targets([env]) == [{"repo": "api", "branch": "zharn/X-1", "target": "main", "behind": 1}]
    assert cli.behind_targets([{**env, "target": ""}]) == []                      # no registered target: nothing to gate
    import shutil; shutil.rmtree(wt)                                              # a branch check: the worktree may be gone
    assert cli.behind_targets([env])[0]["behind"] == 1


def test_handoff_refuses_a_branch_behind_its_target_before_running_checks(fake_ipc, tmp_path, capsys):
    repo, wt = _behind_setup(tmp_path)
    st = fake_ipc({"run": True, "policy": "gate", "limit": 100, "timeout": 30,
                   "environments": [{"repo": "api", "checks": "false", "path": str(wt), "branch": "zharn/X-1",
                                     "target": "main", "repo_path": str(repo)}]})
    with pytest.raises(SystemExit) as e:
        cli.main(["story", "yield", "--handoff", "--body", "done", "--despite-checks"])
    assert str(e.value) == "handoff refused: zharn/X-1 is 1 commit behind main in api — rebase onto main (or merge it in) and retry"
    assert [r["cmd"] for r in st["received"]] == ["env.checks"]                   # no flag past it; the checks never ran


def test_env_list_prints_the_target(fake_ipc, capsys):
    fake_ipc([{"repo": "api", "path": "/wt/api", "branch": "zharn/X-1", "target": "main", "checks": ""}])
    cli.main(["env", "list"])
    assert "branch=zharn/X-1  target=main" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `~/.venvs/mh-conda/bin/python -m pytest -q tests/test_cli.py -k "behind or env_list_prints" -q`
Expected: FAIL with `AttributeError: module 'harness.cli' has no attribute 'behind_targets'`

- [ ] **Step 3: Implement**

`out()` column tuple: insert `"target"` after `"branch"`:

```python
                print("  ".join(f"{k}={row[k]}" for k in ("id", "key", "name", "phase", "ball", "status", "title", "storyKey", "owner", "kind", "model", "repo", "path", "branch", "target", "checks") if k in row))
```

After `dirty_trees`:

```python
def behind_targets(envs: list[dict]) -> list[dict]:
    """Workspace spec §4.6, the ancestry gate: environments whose branch lacks commits of its target. A check on
    branches, not trees — it runs in the repo, so a worktree deleted by hand is still gated."""
    out = []
    for e in envs:
        if not e.get("target") or not os.path.isdir(e.get("repo_path", "")):
            continue
        r = subprocess.run(["git", "rev-list", "--count", f"{e['branch']}..{e['target']}"], cwd=e["repo_path"],
                           capture_output=True, text=True)
        n = int(r.stdout.strip() or 0) if r.returncode == 0 else 0
        if n:
            out.append({"repo": e["repo"], "branch": e["branch"], "target": e["target"], "behind": n})
    return out
```

In `main`, after the dirty-tree `sys.exit` and before `try: checks = run_checks(...)`:

```python
            behind = behind_targets(plan["environments"]) if plan["run"] else []
            if behind:
                sys.exit("handoff refused: " + "; ".join(
                    f"{b['branch']} is {b['behind']} commit{'' if b['behind'] == 1 else 's'} behind {b['target']} in {b['repo']}"
                    for b in behind) + f" — rebase onto {behind[0]['target']} (or merge it in) and retry")
```

Update the comment above the gates to read `# §4.6: the gates run here, in your turn — the tree, then the target, then each repo's checks — before the handoff posts`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `~/.venvs/mh-conda/bin/python -m pytest -q tests/test_cli.py tests/test_environments.py -q`
Expected: all PASS, including `test_handoff_over_the_cli_carries_the_checks` (its branch is not behind).

- [ ] **Step 5: Commit**

```bash
git add harness/cli.py tests/test_cli.py
git commit -m "CLI: the ancestry gate — a handoff on a branch behind its target is refused before the checks; env list names the target"
```

---

### Task 7: The story page after Approve

**Files:**
- Modify: `tests/test_ui_story.py` (extend `test_story_page_shows_environments_and_folds_passing_checks`, `:274-304`)
- Modify only if the test demands it: `qml/content/Story.qml`

**Interfaces:**
- Consumes: `_env_rows` filtering removed environments (Task 5); the Approve comment body (Task 4).

- [ ] **Step 1: Extend the test** — replace its last three lines (`ui.store.stories.approve(key)` onward) with:

```python
    ui.store.stories.approve(key)
    QTest.qWait(80)
    assert not ui.visible(ui.find("checksFailingChip"))          # the chip belongs to the handoff that waits on you
    last = ui.store.stories.comments(key)[-1]
    assert last["body"].splitlines()[1] == f"merged zharn/{key} → main in api (no changes)"
    assert ui.find(f"comment_{last['id']}")                      # the stage direction renders with its merged line
    assert wait_until(lambda: not ui.has("storyEnv_api"))         # swept once the protagonist's turn ended (§4.8)
```

- [ ] **Step 2: Run the test**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q tests/test_ui_story.py -k environments -q`
Expected: PASS without QML changes — the system comment already renders its body, and the environments `Repeater` follows `story.environments`. If the multi-line body renders as one line, it is still the same `Text` with `wrapMode: Text.Wrap`; no change needed. If `storyEnv_api` stays visible, the model row did not refresh: confirm `_sweep_environments` ends with `self._refresh()`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ui_story.py
git commit -m "UI test: the Approve comment names what landed and the swept environment leaves the story page"
```

---

### Task 8: The implementing skill brings the branch up to date

**Files:**
- Modify: `harness/skills/skills/implementing-a-story/SKILL.md` (step 6 at `:31`, the handoff paragraph at `:43`, the rationalization table, the checklist at `:67-72`)
- Test: `tests/test_skills.py` (existing structure checks only; run it)

- [ ] **Step 1: Edit step 6 of "Shape of the work"**

```markdown
6. Before the handoff: `zharn:verification-before-completion`, then commit in your environment and bring your branch up to date with its target (`$HARNESS_CLI env list` names it as `target`): rebase onto it, or merge it in if the rebase fights you. Run the repo's checks yourself first; a refused handoff is a wasted turn.
```

- [ ] **Step 2: Edit the handoff paragraph**

```markdown
The tree is clean: a handoff with uncommitted changes is refused, and there is no flag past it. A branch behind its target is refused the same way, with no flag either — Approve only fast-forwards. The handoff names the commit. Checks attach mechanically. Open sub-stories block the handoff: finish or cancel them first.
```

- [ ] **Step 3: Add one rationalization row** after the "I'll leave committing to the author" row

```markdown
| "I'll leave the rebase to the author" | Approve only fast-forwards. A branch behind its target cannot be approved; the author's only move is to send it back to you. Rebase now. |
```

- [ ] **Step 4: Add to the checklist** after "Committed in your environment; the handoff names the commit"

```markdown
- [ ] Branch up to date with its target (`env list`); rebased or merged, and the checks re-run after
```

- [ ] **Step 5: Run the skill tests**

Run: `~/.venvs/mh-conda/bin/python -m pytest -q tests/test_skills.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add harness/skills/skills/implementing-a-story/SKILL.md
git commit -m "Skill: bring the branch up to date with its target before the handoff; Approve only fast-forwards"
```

---

### Task 9: Specs in the present tense, full suite

**Files:**
- Modify: `docs/specs/workspace-model.md` (§4 preamble, §4.2 last paragraph, §4.6, new §4.8, §8, §9, §10), `docs/specs/story-lifecycle.md` (§2.1 Approve row, §2.2 `yield --handoff` row, §7, §8), `docs/DESIGN.md` (§8 items 6 and 8)

- [ ] **Step 1: `docs/specs/workspace-model.md`**

§4 preamble, replace the last sentence of the italic paragraph with: *"A story's work reaches its author only through a handoff and Approve, which fast-forwards the story's branch into its parent environment's — that is what makes the handoff mean something."*

§4.2, replace the paragraph beginning "Approve is out of scope (§10)" with:

```markdown
The parent environment's branch is the story's **target** — the repo's `base` for a root story,
`zharn/<parent-key>` for a sub-story — and Approve fast-forwards the target onto the story's
branch (§4.8).
```

§4.6, retitle to **"The gates at a handoff: the tree, the target, then the checks"** and insert after the tree paragraph:

```markdown
**Then the target.** The story's branch must contain its target's tip (`git merge-base
--is-ancestor <target> <branch>`): the cast rebases onto the target, or merges it in, before
handing off. A branch behind is refused with the target and the count named — "handoff refused:
zharn/SCR-3 is 2 commits behind main in zharn — rebase onto main (or merge it in) and retry" —
and there is no flag past it either: Approve only fast-forwards (§4.8), so a branch behind
cannot land. It is a check on branches, so it runs in the repo's main checkout whether or not
the worktree still exists. It runs before the checks because a rebase changes what they measure.
```

New §4.8 after §4.7:

```markdown
### 4.8 Approve

Approve fast-forwards every environment of the story into its target and is refused when any
cannot: a story is never done with unmerged work. The commit that lands is the commit the checks
ran on; the harness never creates a merge commit and never runs checks itself.

In order, in the harness process (bounded by `GIT_TIMEOUT_S`):

1. The lifecycle precondition `(implementing, author)`.
2. Every environment prechecked: the repo present (§3.3), the branch up to date with its target.
   One failing environment refuses the whole Approve; nothing has moved.
3. Each environment fast-forwarded, in registration order. When the target branch is checked out
   in a worktree of the repo, the fast-forward runs there so its files update; otherwise the ref
   alone moves. A target already at the branch's tip is a no-op.
4. The Approve system comment carries the result — `approved`, then one line per environment,
   `merged zharn/SCR-3 → main in zharn (a1b2c3d..e4f5a6b, 4 commits)` or `(no changes)` — and
   `structured.merged = [{repo, branch, target, from, to, commits}]`.

A refusal partway (git refuses to overwrite dirty files in the target's tree; a timeout) is the
Approve's refusal with git's message; the story stays `implementing`, repos already
fast-forwarded stay so, and the next Approve finds them up to date and finishes. A story with no
environments approves with no git at all.

**The two kinds of target.** A root story's target is `base`, usually checked out in the main
checkout — the author's own tree and, for zharn in Scratch, the tree the harness runs from; the
fast-forward updates it and the reloader takes it from there. A sub-story's target is
`zharn/<parent-key>` in the parent's worktree, where the parent's cast may be mid-work: the
actor is the parent character running `approve <key>`, and git's own rule applies — a
fast-forward that would overwrite its uncommitted files is refused, one that touches other
files goes through.

**Cleanup.** At Approve, and at every turn end of a done story, once no character of the story
has a live working context, each environment's worktree is removed (`git worktree remove
--force`); the record stays, stamped `removed`, and the branch stays — it is the story's history.
Reopen changes nothing here: `env open` re-adds the worktree on the kept branch and runs `setup`
again (§4.4); the branch is behind by whatever landed since, and the ancestry gate makes the cast
rebase before its next handoff. Cancel leaves environments as they are.
```

§4.3, add after the record shape: *"`removed` is set when the worktree was removed after Approve (§4.8); such records are not environments of the story until `env open` revives them."*

§8, add `target` to the `env list` line: `zharn env list [--json]               # this story's environments, each with its repo's checks and its target`.

§9, add to `tests/test_environments.py`: *"`target` and `behind`; `integrate` into a checked-out base and into one checked out nowhere, into a parent's worktree clean, dirty elsewhere, and dirty on the same file; a no-op; refused when behind; `remove` keeps the branch and record, `open` revives."* Add to `tests/test_stories.py`: *"Approve fast-forwards and records, refuses a branch behind, moves nothing when one repo is behind, finishes on retry after a partial refusal, refuses a missing repo, sweeps at Approve or at the last working character's turn end, Reopen revives behind its target, a character approves its sub-story into its own worktree."* Add to `tests/test_cli.py`: *"the ancestry gate before the checks; `env list` names the target."*

§10, replace the first sentence with: *"Pull requests and pushes; a prune verb for canceled stories' worktrees; squashing on landing."*

- [ ] **Step 2: `docs/specs/story-lifecycle.md`**

§2.1 Approve row:

```markdown
| Approve `[note]` | `(implementing, author)`, and every environment of the story fast-forwards into its target ([workspace spec](workspace-model.md) §4.8) | Each environment's target is moved onto the story branch's tip; system comment carrying what landed (`structured.merged`); every open thread of the story resolves, main included; every character retires at its next turn boundary (§2.3); worktrees are removed as the cast retires. → `(done)`. |
```

§2.2 `yield --handoff` row, precondition: replace "every environment of the story has a clean tree (no flag past it), then each repo's `checks` run" with "every environment of the story has a clean tree and a branch up to date with its target (no flag past either), then each repo's `checks` run".

§7, in the `test_stories.py` line add "Approve fast-forwards its environments (workspace spec §4.8)"; in `test_lifecycle.py` add "the Approve comment's merged lines and `structured.merged`".

§8, replace "Approve's effect on the environment (merge/PR/worktree);" with "pull requests;".

- [ ] **Step 3: `docs/DESIGN.md` §8**

Item 6: replace "What Approve does to a story's environments (merge/PR/cleanup) gets its own spec;" with "Approve fast-forwards each environment into its target and sweeps worktrees (spec §4.8, **shipped 2026-09-05**, plan `docs/superpowers/plans/2026-09-05-approve-merge.md`);".

Item 8: append " The loop is closed: a story's branch lands in the running checkout through Approve (§3c, spec §4.8)."

- [ ] **Step 4: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen ~/.venvs/mh-conda/bin/python -m pytest -q`
Expected: all PASS. Paste the final count line into the commit message.

- [ ] **Step 5: Commit**

```bash
git add docs/specs/workspace-model.md docs/specs/story-lifecycle.md docs/DESIGN.md
git commit -m "Specs: Approve fast-forwards each environment into its target (§4.8); the ancestry gate at handoff; worktrees swept as the cast retires"
```

---

## Self-review

- **Spec coverage.** Proposal §1 vocabulary → Task 1 `target`. §2 ancestry gate → Task 6. §3 Approve order, evidence, partial retry, no-environments → Tasks 4–5. §3.1 root vs sub-story targets → Task 2 tests, Task 5 sub-story test. §3.2 cleanup, Reopen, Cancel untouched → Tasks 3, 5. §4 skill → Task 8. §5 CLI/UI → Tasks 6, 7 (the `approve <key>` verb already prints the returned comment's `body`, which now carries the merged lines). §6 file placement → as listed. §7 tests → one test per bullet. §8 out of scope → not built.
- **Types.** `integrate` returns `{repo, branch, target, from, to, commits}`; `merged_lines` and the reducer read exactly those keys; `describe` adds `target`/`repo_path` and `behind_targets` reads exactly those; `records()` excludes `removed`, `get()` does not, and `open()` checks `removed` first.
- **Nothing hidden.** No flag past either gate. No config knob. No Cancel cleanup.
