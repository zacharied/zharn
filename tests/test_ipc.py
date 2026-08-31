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


class FakeRoles:
    def __init__(self, *names):
        self.roles = [{"name": n, "model": "m"} for n in names]


class FakeLayout:
    def __init__(self):
        self.opened = []

    def openContent(self, kind, key, title):
        self.opened.append((kind, key, title))


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
    def resolve(self, key, thread_id, note=""): self.calls.append(("resolve", key, thread_id, note)); return {"id": "c10", "kind": "system"}
    def cast_resolve(self, character_id, thread_id, note=""): self.calls.append(("cast_resolve", character_id, thread_id, note)); return {"id": "c11", "kind": "system"}
    def log_verb(self, character_id, verb, args, ok, error=""): self.verbs.append((character_id, verb, dict(args), ok, error))


class FakeAppStore:
    def __init__(self):
        self.contexts = FakeContexts(
            FakeContext("t1", title="first", status="idle", storyKey="ABC-1", owner="human",
                        rows=[{"role": "user", "kind": "text", "text": "hi"},
                              {"role": "assistant", "kind": "text", "text": "hello"}]),
            FakeContext("t2", title="second", status="working", storyKey="ABC-2", owner="human"),
        )
        self.roles = FakeRoles("claude-fast", "claude-deep")
        self.layout = FakeLayout()
        self.stories = FakeStories()


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


def test_layout_open_forwards_kind_key_title(h, store):
    assert h("layout.open", {"kind": "context", "key": "ABC-1", "title": "one"}) is True
    assert store.layout.opened == [("context", "ABC-1", "one")]


def test_layout_open_key_and_title_default_to_empty(h, store):
    h("layout.open", {"kind": "board"})
    assert store.layout.opened == [("board", "", "")]


def test_unknown_command_raises_valueerror(h):
    with pytest.raises(ValueError, match="unknown command 'bogus'"):
        h("bogus", {})


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


def test_story_resolve_forwards_author_and_cast_forms(h, store):
    r = h("story.resolve", {"key": "ABC-1", "thread": "t2", "note": "n"})
    assert r["kind"] == "system"
    h("story.resolve", {"character": "chr1", "thread": "t2", "note": "n2"})
    assert store.stories.calls == [("resolve", "ABC-1", "t2", "n"), ("cast_resolve", "chr1", "t2", "n2")]
    assert [(v[1], v[3]) for v in store.stories.verbs] == [("resolve", True)]  # only the cast form is a character verb


def test_story_cast_rejection_is_logged_and_raised(h, store):
    with pytest.raises(Exception, match="already waits"):
        h("story.yield", {"character": "chr1", "kind": "question", "body": "boom"})
    assert store.stories.verbs[-1][3] is False and "already waits" in store.stories.verbs[-1][4]


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
