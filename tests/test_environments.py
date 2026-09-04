"""Environments (workspace spec §4): records, the parent chain, lazy worktrees, setup, checks plumbing.
Real temporary git repos via tests/gitfix.py; no network."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gitfix import make_repo, commit_file, branch_of, run  # noqa: E402

from harness import config as cfg  # noqa: E402
from harness import environments as env_mod  # noqa: E402
from harness.environments import EnvError, EnvironmentStore, env_key, git, head_branch, register_repo  # noqa: E402
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


def store(ws, **parents):
    """parents: story key → parent story key (or None for a root story)."""
    return EnvironmentStore(ws, lambda key: parents[key])


# ---------------------------------------------------------------- git helpers / registration (§3.1, §3.2)

def test_head_branch_and_detached(tmp_path):
    p = make_repo(tmp_path / "r", branch="trunk")
    assert head_branch(p) == "trunk"
    run(p, "checkout", "-q", "--detach")
    assert head_branch(p) == run(p, "rev-parse", "--short", "HEAD")


def test_git_suppresses_prompts_and_is_bounded(tmp_path, monkeypatch):
    """C1: a git call must never sit waiting for credentials, and must not run unbounded."""
    p = make_repo(tmp_path / "r")
    calls = []
    real_run = subprocess.run

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(env_mod.subprocess, "run", spy)
    git(p, "rev-parse", "HEAD")
    assert calls, "git() should shell out via subprocess.run"
    kw = calls[-1]
    assert kw["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kw["env"]["GIT_ASKPASS"] == "/bin/echo" and kw["env"]["SSH_ASKPASS"] == "/bin/echo"
    assert kw["env"]["GIT_SSH_COMMAND"] == "ssh -oBatchMode=yes"
    assert kw["timeout"] == getattr(cfg, "GIT_TIMEOUT_S", 600)


def test_git_times_out_raises_env_error(tmp_path, monkeypatch):
    p = make_repo(tmp_path / "r")
    monkeypatch.setattr(cfg, "GIT_TIMEOUT_S", 0.05, raising=False)

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 0.05))

    monkeypatch.setattr(env_mod.subprocess, "run", slow)
    with pytest.raises(EnvError, match="timed out after 0.05s"):
        git(p, "rev-parse", "HEAD")


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
    es = store(ws, **{"ZH-1": None})
    d = es.open("ZH-1", "client")
    path = ws.local_dir / "worktrees" / "client" / "ZH-1"
    assert d["path"] == str(path) and d["branch"] == "zharn/ZH-1" and d["parent"] is None and d["story"] == "ZH-1"
    assert path.is_dir() and branch_of(path) == "zharn/ZH-1" and (path / "README.md").exists()
    assert run(repo, "rev-parse", "zharn/ZH-1") == run(repo, "rev-parse", "main")
    saved = json.loads((ws.local_dir / "environments.json").read_text())
    assert saved[env_key("ZH-1", "client")]["path"] == str(path) and saved[env_key("ZH-1", "client")]["setup_done"] is True


def test_open_is_idempotent_per_pair(ws, repo):
    es = store(ws, **{"ZH-1": None})
    a, b = es.open("ZH-1", "client"), es.open("ZH-1", "client")
    assert a == b and len(es.records("ZH-1")) == 1
    assert run(repo, "worktree", "list").count("zharn/ZH-1") == 1


def test_open_uses_the_registered_base(ws, tmp_path):
    p = make_repo(tmp_path / "ws" / "api", branch="develop")
    run(p, "checkout", "-q", "-b", "feature")
    commit_file(p, "f.txt")
    register_repo(ws, str(p), base="develop")
    es = store(ws, **{"ZH-1": None})
    d = es.open("ZH-1", "api")
    assert not (Path(d["path"]) / "f.txt").exists()   # cut from develop, not the checked-out feature branch


def test_open_recreates_a_deleted_worktree_on_its_branch(ws, repo):
    import shutil
    es = store(ws, **{"ZH-1": None})
    d = es.open("ZH-1", "client")
    commit_file(Path(d["path"]), "work.txt")
    shutil.rmtree(d["path"])
    d2 = es.open("ZH-1", "client")
    assert d2["path"] == d["path"] and (Path(d2["path"]) / "work.txt").exists() and branch_of(Path(d2["path"])) == "zharn/ZH-1"


def test_open_unknown_or_missing_repo_creates_nothing(ws, repo, tmp_path):
    es = store(ws, **{"ZH-1": None})
    with pytest.raises(EnvError, match="unknown repo"):
        es.open("ZH-1", "nope")
    ws.relocate("client", tmp_path / "gone")
    with pytest.raises(EnvError, match="missing"):
        es.open("ZH-1", "client")
    assert es.records("ZH-1") == [] and not (ws.local_dir / "worktrees").exists()


# ---------------------------------------------------------------- setup (§3.1, §4.4)

def test_setup_runs_once_in_the_worktree_and_is_retried_after_failure(ws, tmp_path):
    p = make_repo(tmp_path / "ws" / "api")
    marker = tmp_path / "gate"
    register_repo(ws, str(p), setup=f"test -f {marker} && echo ran >> setup.log")
    es = store(ws, **{"ZH-1": None})
    with pytest.raises(EnvError, match="setup failed"):
        es.open("ZH-1", "api")
    path = ws.local_dir / "worktrees" / "api" / "ZH-1"
    assert path.is_dir() and es.get("ZH-1", "api")["setup_done"] is False   # worktree stays
    marker.write_text("")
    es.open("ZH-1", "api")
    es.open("ZH-1", "api")
    assert (path / "setup.log").read_text() == "ran\n" and es.get("ZH-1", "api")["setup_done"] is True


def test_setup_times_out_raises_env_error_and_leaves_worktree(ws, tmp_path, monkeypatch):
    """C1: a hung setup command must not block the app forever."""
    p = make_repo(tmp_path / "ws" / "api")
    register_repo(ws, str(p), setup="sleep 5")
    monkeypatch.setattr(cfg, "SETUP_TIMEOUT_S", 0.2, raising=False)
    es = store(ws, **{"ZH-1": None})
    with pytest.raises(EnvError, match="timed out"):
        es.open("ZH-1", "api")
    path = ws.local_dir / "worktrees" / "api" / "ZH-1"
    assert path.is_dir() and es.get("ZH-1", "api")["setup_done"] is False


def test_open_recreates_a_deleted_worktree_runs_setup_again(ws, tmp_path):
    """I3: a re-added worktree is a new worktree — setup runs again in it (spec §3.1, §4.4)."""
    import shutil
    p = make_repo(tmp_path / "ws" / "api")
    log = tmp_path / "setup.log"
    register_repo(ws, str(p), setup=f"echo ran >> {log}")
    es = store(ws, **{"ZH-1": None})
    d = es.open("ZH-1", "api")
    assert log.read_text().splitlines() == ["ran"]
    shutil.rmtree(d["path"])
    es.open("ZH-1", "api")
    assert log.read_text().splitlines() == ["ran", "ran"]
    assert es.get("ZH-1", "api")["setup_done"] is True


def test_describe_carries_the_repos_checks(ws, tmp_path):
    p = make_repo(tmp_path / "ws" / "api")
    register_repo(ws, str(p), checks="make test")
    es = store(ws, **{"ZH-1": None})
    assert es.open("ZH-1", "api")["checks"] == "make test"


# ---------------------------------------------------------------- sub-stories: the parent chain (§4.2)

def test_substory_branches_from_the_parents_branch(ws, repo):
    es = store(ws, **{"ZH-1": None, "ZH-2": "ZH-1"})
    parent = es.open("ZH-1", "client")
    commit_file(Path(parent["path"]), "parent.txt")          # parent's committed work
    sub = es.open("ZH-2", "client")
    assert sub["branch"] == "zharn/ZH-2" and sub["parent"] == "ZH-1:client"
    assert sub["path"] == str(ws.local_dir / "worktrees" / "client" / "ZH-2")
    assert (Path(sub["path"]) / "parent.txt").exists()        # cut from zharn/ZH-1, not from main
    assert run(repo, "rev-parse", "zharn/ZH-2") == run(repo, "rev-parse", "zharn/ZH-1")
    assert sub["path"] != parent["path"]                      # never the parent's tree


def test_substory_creates_the_parents_environment_on_demand(ws, repo):
    es = store(ws, **{"ZH-1": None, "ZH-2": "ZH-1"})
    sub = es.open("ZH-2", "client")
    assert es.get("ZH-1", "client") is not None and es.get("ZH-1", "client")["parent"] is None
    assert (ws.local_dir / "worktrees" / "client" / "ZH-1").is_dir() and sub["parent"] == "ZH-1:client"
    assert run(repo, "rev-parse", "zharn/ZH-1") == run(repo, "rev-parse", "main")


def test_grandchild_branches_from_its_parent_not_the_root(ws, repo):
    es = store(ws, **{"ZH-1": None, "ZH-2": "ZH-1", "ZH-3": "ZH-2"})
    root = es.open("ZH-1", "client")
    commit_file(Path(root["path"]), "root.txt")
    child = es.open("ZH-2", "client")
    commit_file(Path(child["path"]), "child.txt")
    g = es.open("ZH-3", "client")
    assert g["parent"] == "ZH-2:client"
    assert (Path(g["path"]) / "root.txt").exists() and (Path(g["path"]) / "child.txt").exists()
    assert run(repo, "rev-parse", "zharn/ZH-3") == run(repo, "rev-parse", "zharn/ZH-2")


def test_parents_later_commits_do_not_move_the_substory(ws, repo):
    es = store(ws, **{"ZH-1": None, "ZH-2": "ZH-1"})
    parent = es.open("ZH-1", "client")
    sub = es.open("ZH-2", "client")
    commit_file(Path(parent["path"]), "later.txt")
    assert not (Path(sub["path"]) / "later.txt").exists()     # plain git: a branch, not a view


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
    assert d["path"] in [r["text"] for r in ctx.transcript.rows() if r["role"] == "user"][-1]


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
