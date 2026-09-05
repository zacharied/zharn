"""WorkspaceStore: the QML face of a Workspace (spec §2, §3) — identity, repos() with status, and the
register/unregister/relocate intents. Real temporary git repos via tests/gitfix.py; no network, no QML."""
import json
import shutil
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gitfix import make_repo  # noqa: E402

from harness.content import KINDS, ContentRegistry  # noqa: E402
from harness.environments import EnvError, register_repo  # noqa: E402
from harness.notify import Notifier  # noqa: E402
from harness.shell import QML_DIR, RELOADABLE  # noqa: E402
from harness.stories import StoryStore  # noqa: E402
from harness.store import AppStore, LayoutStore, Session  # noqa: E402
from harness.workspace import Workspace  # noqa: E402
from harness.workspace_store import WorkspaceStore  # noqa: E402


class StubContexts(QObject):
    contextsChanged = Signal()
    contextSettled = Signal(str)
    contextUsage = Signal(str)

    def get(self, cid): return None
    def all(self): return []
    def contexts_for(self, key): return []


class StubRoles:
    def get(self, name): return {}


@pytest.fixture
def ws(tmp_path):
    return Workspace.create(tmp_path / "ws", name="Zharn", prefix="ZH")


@pytest.fixture
def stories(ws):
    s = StoryStore(ws, StubContexts(), StubRoles())
    s.notifier = Notifier()
    return s


@pytest.fixture
def wss(ws, stories):
    s = WorkspaceStore(ws, stories)
    s.notifier = Notifier()
    return s


@pytest.fixture
def client(tmp_path, ws):
    """`client`, registered in `ws`, one commit on main."""
    p = make_repo(tmp_path / "ws" / "client")
    register_repo(ws, str(p))
    return p


def changes(wss) -> list:
    seen = []
    wss.workspaceChanged.connect(lambda: seen.append(1))
    return seen


# ---------------------------------------------------------------- identity

def test_identity_reads_through(wss, ws):
    assert wss.name == "Zharn" and wss.prefix == "ZH"
    assert wss.dir == str(ws.dir) and wss.id == ws.id


# ---------------------------------------------------------------- repos()

def test_repos_lists_records_with_status(wss, client, tmp_path):
    (rec,) = wss.repos()
    assert rec["name"] == "client" and rec["path"] == "client" and rec["base"] == "main" and rec["status"] == "ok"
    assert set(rec) == {"name", "path", "checks", "setup", "base", "status"}
    shutil.move(client, tmp_path / "elsewhere")
    assert wss.repos()[0]["status"] == "missing"


def test_repos_keeps_registration_order(wss, ws, tmp_path):
    for n in ("b", "a", "c"):
        register_repo(ws, str(make_repo(tmp_path / "ws" / n)))
    assert [r["name"] for r in wss.repos()] == ["b", "a", "c"]


# ---------------------------------------------------------------- register

def test_register_path_adds_a_repo(wss, ws, tmp_path):
    seen = changes(wss)
    p = make_repo(tmp_path / "ws" / "api")
    rec = wss.register(str(p), "", "npm test", "", "")
    assert rec["name"] == "api" and rec["path"] == "api" and rec["checks"] == "npm test" and rec["base"] == "main"
    assert [r["name"] for r in wss.repos()] == ["api"]
    assert seen == [1]
    assert [r["name"] for r in Workspace.open(ws.dir).repos] == ["api"]   # persisted


def test_register_non_git_path_is_refused(wss, tmp_path):
    seen = changes(wss)
    (tmp_path / "ws" / "plain").mkdir()
    with pytest.raises(EnvError, match="not a git repository"):
        wss.register(str(tmp_path / "ws" / "plain"), "", "", "", "")
    assert wss.notifier.lastError.startswith("register:") and "not a git repository" in wss.notifier.lastError
    assert wss.repos() == [] and seen == []


def test_register_url_clones_into_repos_dir(wss, ws, tmp_path):
    src = make_repo(tmp_path / "upstream")
    rec = wss.register(src.as_uri(), "", "", "", "")   # file:// URL
    assert rec["name"] == "upstream" and rec["path"] == "repos/upstream" and rec["base"] == "main"
    assert (ws.dir / "repos" / "upstream" / "README.md").read_text() == "hello\n"
    assert wss.repos()[0]["status"] == "ok"


def test_register_refreshes_story_rows(wss, stories, tmp_path):
    seen = []
    stories.storiesChanged.connect(lambda: seen.append(1))
    wss.register(str(make_repo(tmp_path / "ws" / "api")), "", "", "", "")
    assert seen == [1]
    assert [r["name"] for r in stories.repo_list()] == ["api"]


# ---------------------------------------------------------------- unregister

def test_unregister_removes_the_record_and_leaves_files(wss, ws, stories, client):
    key = stories.create("T", "")
    stories.environments.open(key, "client")                     # a managed worktree + a local record
    env_file = ws.local_dir / "environments.json"
    before = json.loads(env_file.read_text())
    seen = changes(wss)
    wss.unregister("client")
    assert wss.repos() == [] and seen == [1]
    assert Workspace.open(ws.dir).repos == []
    assert (client / "README.md").exists()
    assert (ws.local_dir / "worktrees" / "client" / key).is_dir()
    assert json.loads(env_file.read_text()) == before


def test_unregister_unknown_name_is_a_readable_error(wss, client):
    seen = changes(wss)
    with pytest.raises(Exception, match="no repo named 'nope'"):
        wss.unregister("nope")
    assert wss.notifier.lastError == "unregister: no repo named 'nope'"
    assert [r["name"] for r in wss.repos()] == ["client"] and seen == []


# ---------------------------------------------------------------- relocate

def test_relocate_rewrites_the_path(wss, ws, client, tmp_path):
    shutil.move(client, tmp_path / "moved")
    assert wss.repos()[0]["status"] == "missing"
    seen = changes(wss)
    rec = wss.relocate("client", str(tmp_path / "moved"))
    assert rec["path"] == str(tmp_path / "moved") and rec["name"] == "client"
    assert wss.repos()[0]["status"] == "ok" and wss.repos()[0]["path"] == str(tmp_path / "moved")
    assert seen == [1]
    assert Workspace.open(ws.dir).repo("client")["path"] == str(tmp_path / "moved")


def test_relocate_inside_the_workspace_stores_relative(wss, ws, client, tmp_path):
    shutil.move(client, tmp_path / "ws" / "renamed")
    assert wss.relocate("client", str(tmp_path / "ws" / "renamed"))["path"] == "renamed"


def test_relocate_refuses_a_path_without_git(wss, ws, client, tmp_path):
    shutil.move(client, tmp_path / "moved")
    (tmp_path / "plain").mkdir()
    seen = changes(wss)
    with pytest.raises(Exception, match="not a git repository"):
        wss.relocate("client", str(tmp_path / "plain"))
    with pytest.raises(Exception, match="not a git repository"):
        wss.relocate("client", str(tmp_path / "does-not-exist"))
    assert wss.notifier.lastError.startswith("relocate:")
    assert wss.repos()[0]["path"] == "client" and wss.repos()[0]["status"] == "missing" and seen == []


def test_relocate_unknown_name_is_a_readable_error(wss, client, tmp_path):
    with pytest.raises(Exception, match="no repo named 'nope'"):
        wss.relocate("nope", str(client))
    assert wss.notifier.lastError == "relocate: no repo named 'nope'"


def test_relocated_repo_serves_new_environments(wss, ws, stories, client, tmp_path):
    """EnvironmentStore reads the registration live: after Relocate, `env open` cuts from the new path."""
    shutil.move(client, tmp_path / "moved")
    key = stories.create("T", "")
    with pytest.raises(EnvError):
        stories.environments.open(key, "client")
    wss.relocate("client", str(tmp_path / "moved"))
    d = stories.environments.open(key, "client")
    assert (Path(d["path"]) / "README.md").exists()


# ---------------------------------------------------------------- one signal per mutation

def test_workspace_changed_fires_once_per_successful_mutation(wss, tmp_path):
    seen = changes(wss)
    p = make_repo(tmp_path / "ws" / "api")
    wss.register(str(p), "", "", "", "")
    shutil.move(p, tmp_path / "moved")
    wss.relocate("api", str(tmp_path / "moved"))
    wss.unregister("api")
    assert seen == [1, 1, 1]


# ---------------------------------------------------------------- wiring

def test_workspace_content_kind_resolves():
    assert ContentRegistry(QML_DIR).qmlFor("workspace").endswith("content/Workspace.qml")
    assert KINDS["workspace"] == {"title": "Workspace", "qml": "content/Workspace.qml", "panel": False, "icon": "folder-open"}
    assert "workspace" not in ContentRegistry(QML_DIR).panelKinds()


def test_app_store_exposes_the_workspace_store(wss, ws, tmp_path):
    session = Session(tmp_path / "session.json")
    app = AppStore(session, LayoutStore(session), ContentRegistry(QML_DIR), {}, workspace=ws, workspace_store=wss)
    assert app.workspace is wss and app.workspaceDir == str(ws.dir)


def test_workspace_store_is_hot_reloadable():
    assert "harness.workspace_store" in RELOADABLE
    assert RELOADABLE.index("harness.workspace_store") > RELOADABLE.index("harness.stories")
    assert RELOADABLE.index("harness.workspace_store") < RELOADABLE.index("harness.store")
