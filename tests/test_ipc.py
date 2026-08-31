"""Unit tests for harness.ipc: the command table (make_handler) against plain-Python fakes, and the
IpcServer wire protocol round-tripped in-process over a QLocalSocket."""
import itertools
import json
import os

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtTest import QTest

from harness.ipc import IpcServer, make_handler

# A QGuiApplication *is* a QCoreApplication; creating the GUI flavour keeps the full suite happy, since
# test_agents/test_app build the real app (QML needs QGuiApplication) after this module is imported.
if QCoreApplication.instance() is None:
    from PySide6.QtGui import QGuiApplication
    _app = QGuiApplication([])


# ---------------------------------------------------------------- fakes (no Qt)

class FakeTranscript:
    def __init__(self, rows):
        self._rows = rows

    def rows(self):
        return self._rows


class FakeContext:
    def __init__(self, id, title="", status="idle", storyKey="", owner="human", rows=()):
        self.id, self.title, self.status, self.storyKey, self.owner = id, title, status, storyKey, owner
        self.transcript = FakeTranscript(list(rows))

    def summary(self):
        return {"id": self.id, "title": self.title, "status": self.status, "storyKey": self.storyKey, "owner": self.owner}


class FakeContexts:
    def __init__(self, *contexts):
        self._by_id = {c.id: c for c in contexts}
        self.calls = []
        self._ids = itertools.count(1)

    def summaries(self):
        return [c.summary() for c in self._by_id.values()]

    def get(self, cid):
        return self._by_id.get(cid)

    def create(self, role, title=""):
        self.calls.append(("create", role, title))
        cid = f"new{next(self._ids)}"
        self._by_id[cid] = FakeContext(cid, title=title, status="idle")
        return cid

    def spawn(self, role, prompt, **kw):
        self.calls.append(("spawn", role, prompt, kw))
        cid = f"new{next(self._ids)}"
        title = kw.get("title") or prompt
        self._by_id[cid] = FakeContext(cid, title=title, status="working", storyKey=kw.get("story_key", ""))
        return cid

    def send(self, cid, text):
        self.calls.append(("send", cid, text))
        self._by_id[cid].status = "working"

    def stop(self, cid):
        self.calls.append(("stop", cid))
        self._by_id[cid].status = "stopped"


class FakeTasks:
    def __init__(self, contexts, tasks=()):
        self._contexts = contexts
        self._tasks = {t["key"]: dict(t) for t in tasks}
        self.calls = []
        self._keys = itertools.count(100)

    def dispatch(self, task, role, prompt):
        self.calls.append(("dispatch", task, role, prompt))
        return self._contexts.spawn(role, prompt, story_key=task, owner="human", title="dispatched")

    def list(self):
        return list(self._tasks.values())

    def get(self, key):
        t = self._tasks.get(key)
        return dict(t) if t else None

    def contextsFor(self, key):
        return [s for s in self._contexts.summaries() if s["storyKey"] == key]

    def setStatus(self, key, status):
        self.calls.append(("setStatus", key, status))
        self._tasks[key]["status"] = status

    def create(self, title, description=""):
        self.calls.append(("create", title, description))
        key = f"T-{next(self._keys)}"
        self._tasks[key] = {"key": key, "title": title, "description": description, "status": "todo"}
        return key


class FakeRoles:
    def __init__(self, *names):
        self.roles = [{"name": n, "model": "m"} for n in names]


class FakeLayout:
    def __init__(self):
        self.opened = []

    def openContent(self, kind, key, title):
        self.opened.append((kind, key, title))


class FakeAppStore:
    def __init__(self):
        self.contexts = FakeContexts(
            FakeContext("t1", title="first", status="idle", storyKey="ABC-1", owner="human",
                        rows=[{"role": "user", "kind": "text", "text": "hi"},
                              {"role": "assistant", "kind": "text", "text": "hello"}]),
            FakeContext("t2", title="second", status="working", storyKey="ABC-2", owner="human"),
        )
        self.tasks = FakeTasks(self.contexts, [
            {"key": "ABC-1", "title": "one", "status": "todo"},
            {"key": "ABC-2", "title": "two", "status": "in-progress"},
        ])
        self.roles = FakeRoles("claude-fast", "claude-deep")
        self.layout = FakeLayout()


@pytest.fixture
def store():
    return FakeAppStore()


@pytest.fixture
def h(store):
    return make_handler(store)


# ---------------------------------------------------------------- make_handler

def test_ping_returns_own_pid(h):
    assert h("ping", {}) == {"pid": os.getpid()}


def test_role_list_returns_roles(h, store):
    assert h("role.list", {}) == store.roles.roles


def test_context_list_without_filter_returns_all_summaries(h):
    assert [s["id"] for s in h("context.list", {})] == ["t1", "t2"]


def test_context_list_with_story_filter_keeps_only_that_story(h):
    assert [s["id"] for s in h("context.list", {"story": "ABC-2"})] == ["t2"]


def test_context_list_with_empty_story_is_unfiltered(h):
    assert len(h("context.list", {"story": ""})) == 2


def test_context_show_returns_summary_without_transcript(h):
    s = h("context.show", {"id": "t1"})
    assert s == {"id": "t1", "title": "first", "status": "idle", "storyKey": "ABC-1", "owner": "human"}
    assert "transcript" not in s


def test_context_show_with_transcript_attaches_row_copies(h, store):
    s = h("context.show", {"id": "t1", "transcript": True})
    assert [r["text"] for r in s["transcript"]] == ["hi", "hello"]
    assert s["transcript"][0] is not store.contexts.get("t1").transcript.rows()[0]


def test_context_show_unknown_id_raises_keyerror(h):
    with pytest.raises(KeyError):
        h("context.show", {"id": "nope"})


def test_context_new_with_prompt_goes_through_contexts_spawn_with_title(h, store):
    s = h("context.new", {"role": "claude-deep", "prompt": "p", "title": "titled"})
    assert store.contexts.calls == [("spawn", "claude-deep", "p", {"title": "titled"})]
    assert s["title"] == "titled"


def test_context_new_without_prompt_goes_through_contexts_create(h, store):
    s = h("context.new", {"role": "claude-fast", "title": "bare one"})
    assert store.contexts.calls == [("create", "claude-fast", "bare one")]
    assert s["title"] == "bare one"


def test_context_new_without_prompt_or_title_defaults_title_to_new_context(h, store):
    h("context.new", {"role": "claude-fast"})
    assert store.contexts.calls == [("create", "claude-fast", "New context")]


def test_context_new_open_opens_context_tab_in_layout(h, store):
    s = h("context.new", {"role": "claude-fast", "prompt": "p", "title": "tab", "open": True})
    assert store.layout.opened == [("context", s["id"], "tab")]


def test_context_new_without_open_does_not_touch_layout(h, store):
    h("context.new", {"role": "claude-fast", "prompt": "p"})
    assert store.layout.opened == []


def test_context_send_forwards_text_and_returns_summary(h, store):
    s = h("context.send", {"id": "t1", "text": "more"})
    assert store.contexts.calls == [("send", "t1", "more")]
    assert s["id"] == "t1" and s["status"] == "working"


def test_context_stop_stops_and_returns_summary(h, store):
    s = h("context.stop", {"id": "t2"})
    assert store.contexts.calls == [("stop", "t2")]
    assert s["id"] == "t2" and s["status"] == "stopped"


def test_task_list_returns_all_tasks(h):
    assert [t["key"] for t in h("task.list", {})] == ["ABC-1", "ABC-2"]


def test_task_show_attaches_contexts_for_task(h):
    t = h("task.show", {"key": "ABC-1"})
    assert t["title"] == "one"
    assert [s["id"] for s in t["contexts"]] == ["t1"]


def test_task_show_unknown_key_raises_keyerror(h):
    with pytest.raises(KeyError):
        h("task.show", {"key": "ZZZ-9"})


def test_task_status_sets_status_and_returns_task(h, store):
    t = h("task.status", {"key": "ABC-1", "status": "done"})
    assert store.tasks.calls == [("setStatus", "ABC-1", "done")]
    assert t["key"] == "ABC-1" and t["status"] == "done"


def test_task_create_returns_created_task(h, store):
    t = h("task.create", {"title": "new one", "description": "desc"})
    assert store.tasks.calls == [("create", "new one", "desc")]
    assert t["title"] == "new one" and t["description"] == "desc" and t["key"].startswith("T-")


def test_task_create_description_defaults_to_empty(h, store):
    h("task.create", {"title": "bare"})
    assert store.tasks.calls == [("create", "bare", "")]


def test_layout_open_forwards_kind_key_title(h, store):
    assert h("layout.open", {"kind": "task", "key": "ABC-1", "title": "one"}) is True
    assert store.layout.opened == [("task", "ABC-1", "one")]


def test_layout_open_key_and_title_default_to_empty(h, store):
    h("layout.open", {"kind": "tasks"})
    assert store.layout.opened == [("tasks", "", "")]


def test_unknown_command_raises_valueerror(h):
    with pytest.raises(ValueError, match="unknown command 'bogus'"):
        h("bogus", {})


# ---------------------------------------------------------------- IpcServer round-trip

_names = itertools.count()


def unique_name():
    return f"mh-test-ipc-{os.getpid()}-{next(_names)}"


def pump_until(cond, timeout_ms=5000, step=10):
    for _ in range(timeout_ms // step):
        if cond():
            return True
        QTest.qWait(step)
    return cond()


def connect(server: IpcServer) -> QLocalSocket:
    sock = QLocalSocket()
    sock.connectToServer(server.server.serverName())
    assert sock.waitForConnected(2000), sock.errorString()
    return sock


def reply_of(sock: QLocalSocket) -> dict:
    buf = b""
    def got_line():
        nonlocal buf
        buf += bytes(sock.readAll())
        return b"\n" in buf
    assert pump_until(got_line), f"no reply; got {buf!r}"
    return json.loads(buf.split(b"\n", 1)[0])


def roundtrip(server: IpcServer, cmd: str, args: dict | None = None) -> dict:
    sock = connect(server)
    sock.write((json.dumps({"cmd": cmd, "args": args or {}}) + "\n").encode())
    sock.flush()
    try:
        return reply_of(sock)
    finally:
        sock.close()


@pytest.fixture
def recording_server():
    calls = []
    def handler(cmd, args):
        calls.append((cmd, args))
        if cmd == "boom":
            raise ValueError("kaboom")
        return {"echo": cmd, "args": args}
    server = IpcServer(unique_name(), handler)
    yield server, calls
    server.server.close()


def test_server_replies_ok_with_handler_result(recording_server):
    server, calls = recording_server
    assert roundtrip(server, "hello", {"x": 1}) == {"ok": True, "result": {"echo": "hello", "args": {"x": 1}}}
    assert calls == [("hello", {"x": 1})]


def test_server_path_is_the_listening_socket_name(recording_server):
    server, _ = recording_server
    assert server.path == server.server.fullServerName()
    if os.name != "nt":
        assert os.path.exists(server.path)


def test_missing_args_defaults_to_empty_dict(recording_server):
    server, calls = recording_server
    sock = connect(server)
    sock.write(b'{"cmd": "noargs", "args": null}\n')
    sock.flush()
    assert reply_of(sock)["result"]["args"] == {}
    assert calls == [("noargs", {})]


def test_handler_exception_becomes_error_reply_and_server_keeps_serving(recording_server):
    server, _ = recording_server
    assert roundtrip(server, "boom") == {"ok": False, "error": "ValueError: kaboom"}
    assert roundtrip(server, "after") == {"ok": True, "result": {"echo": "after", "args": {}}}


def test_malformed_json_is_reported_not_fatal(recording_server):
    server, _ = recording_server
    sock = connect(server)
    sock.write(b"not json\n")
    sock.flush()
    r = reply_of(sock)
    assert r["ok"] is False and r["error"].startswith("JSONDecodeError")
    assert roundtrip(server, "still-alive")["ok"] is True


def test_request_split_across_two_writes_is_buffered(recording_server):
    server, calls = recording_server
    sock = connect(server)
    payload = json.dumps({"cmd": "split", "args": {"n": 2}}).encode()
    sock.write(payload[:7])
    sock.flush()
    QTest.qWait(50)  # let the server read the partial line and park it in its buffer
    assert calls == []
    sock.write(payload[7:] + b"\n")
    sock.flush()
    assert reply_of(sock) == {"ok": True, "result": {"echo": "split", "args": {"n": 2}}}
    assert calls == [("split", {"n": 2})]


def test_server_closes_connection_after_one_reply(recording_server):
    server, _ = recording_server
    sock = connect(server)
    sock.write(b'{"cmd": "one"}\n')
    sock.flush()
    assert reply_of(sock)["ok"] is True
    assert pump_until(lambda: sock.state() == QLocalSocket.LocalSocketState.UnconnectedState)


def test_new_server_replaces_stale_server_of_same_name():
    name = unique_name()
    stale = IpcServer(name, lambda c, a: "stale")
    fresh = IpcServer(name, lambda c, a: "fresh")  # must not raise "address in use"
    try:
        assert fresh.server.isListening()
        assert roundtrip(fresh, "who")["result"] == "fresh"
    finally:
        fresh.server.close()
        stale.server.close()
