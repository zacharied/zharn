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


def store(ws, **parents):
    """parents: story key → parent story key (or None for a root story)."""
    return EnvironmentStore(ws, lambda key: parents[key])


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
