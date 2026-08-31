"""Unit tests for harness.cli (pure stdlib): request() transport, out() formatting, main() arg parsing.
The end-to-end CLI-over-IPC path lives in test_agents.py::test_cli_over_ipc."""
import json
import os
import socket
import threading
import types
from collections import deque

import pytest

from harness import cli


# ---------------------------------------------------------------- request()

def test_request_exits_with_clear_message_when_ipc_unset(monkeypatch):
    monkeypatch.delenv("HARNESS_IPC", raising=False)
    with pytest.raises(SystemExit) as e:
        cli.request("ping", {})
    assert "HARNESS_IPC is not set" in str(e.value)


posix_only = pytest.mark.skipif(os.name == "nt", reason="AF_UNIX fake server")


@pytest.fixture
def fake_server(tmp_path, monkeypatch):
    """One-shot AF_UNIX server in a thread: reads one line, records it, replies with `reply`."""
    path = str(tmp_path / "ipc.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(1)
    srv.settimeout(5)
    state = {"received": None, "reply": None}

    def serve():
        conn, _ = srv.accept()
        with conn:
            data = b""
            while not data.endswith(b"\n"):
                data += conn.recv(65536)
            state["received"] = json.loads(data)
            conn.sendall((json.dumps(state["reply"]) + "\n").encode())

    t = threading.Thread(target=serve, daemon=True)
    monkeypatch.setenv("HARNESS_IPC", path)

    def start(reply):
        state["reply"] = reply
        t.start()
        return state

    yield start
    srv.close()
    t.join(timeout=5)


@posix_only
def test_request_sends_cmd_and_args_and_returns_result(fake_server):
    state = fake_server({"ok": True, "result": {"pid": 42}})
    assert cli.request("ping", {"a": 1}) == {"pid": 42}
    assert state["received"] == {"cmd": "ping", "args": {"a": 1}}


@posix_only
def test_request_exits_with_server_error_text_when_not_ok(fake_server):
    fake_server({"ok": False, "error": "KeyError: 'nope'"})
    with pytest.raises(SystemExit) as e:
        cli.request("context.show", {"id": "nope"})
    assert str(e.value) == "error: KeyError: 'nope'"


# ---------------------------------------------------------------- out()

def test_out_list_of_dicts_prints_known_columns_in_order(capsys):
    cli.out([{"status": "idle", "id": "t1", "title": "T", "extra": "hidden"},
             {"key": "ABC-1", "name": "n", "model": "m"}], as_json=False)
    assert capsys.readouterr().out == "id=t1  status=idle  title=T\nkey=ABC-1  name=n  model=m\n"


def test_out_list_of_scalars_prints_one_per_line(capsys):
    cli.out(["a", 2], as_json=False)
    assert capsys.readouterr().out == "a\n2\n"


def test_out_dict_prints_fields_then_transcript_rows(capsys):
    cli.out({"id": "t1", "status": "idle",
             "transcript": [{"role": "user", "kind": "text", "text": "hi"},
                            {"role": "assistant", "kind": "tool_use", "name": "Bash", "input": "ls"}]}, as_json=False)
    assert capsys.readouterr().out == "id: t1\nstatus: idle\n[user/text]  hi\n[assistant/tool_use] Bash ls\n"


def test_out_dict_without_transcript_prints_only_fields(capsys):
    cli.out({"pid": 7}, as_json=False)
    assert capsys.readouterr().out == "pid: 7\n"


def test_out_scalar_prints_value(capsys):
    cli.out("t1", as_json=False)
    assert capsys.readouterr().out == "t1\n"


def test_out_json_mode_dumps_indented_json(capsys):
    value = {"id": "t1", "transcript": [{"role": "user"}]}
    cli.out(value, as_json=True)
    text = capsys.readouterr().out
    assert json.loads(text) == value
    assert text == json.dumps(value, indent=1) + "\n"


# ---------------------------------------------------------------- main()

@pytest.fixture
def recorder(monkeypatch):
    """Replace cli.request with a recorder. `replies[cmd]` is a value, or a deque consumed one per call."""
    calls = []
    replies = {}

    def fake_request(cmd, args):
        calls.append((cmd, args))
        r = replies.get(cmd, {})
        if isinstance(r, deque):
            return r.popleft()
        return r

    monkeypatch.setattr(cli, "request", fake_request)
    monkeypatch.delenv("HARNESS_CHARACTER_ID", raising=False)
    monkeypatch.delenv("HARNESS_STORY_KEY", raising=False)
    return types.SimpleNamespace(calls=calls, replies=replies)


@pytest.fixture
def fake_clock(monkeypatch):
    """Replace cli.time so the wait loop never sleeps for real; sleep() advances the clock."""
    now = [1000.0]
    clock = types.SimpleNamespace(time=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s))
    monkeypatch.setattr(cli, "time", clock)
    return clock


def test_ping_requests_ping(recorder, capsys):
    recorder.replies["ping"] = {"pid": 5}
    cli.main(["ping"])
    assert recorder.calls == [("ping", {})]
    assert capsys.readouterr().out == "pid: 5\n"


def test_role_list_requests_role_list(recorder, capsys):
    recorder.replies["role.list"] = [{"name": "claude-fast", "model": "m"}]
    cli.main(["role", "list"])
    assert recorder.calls == [("role.list", {})]
    assert capsys.readouterr().out == "name=claude-fast  model=m\n"


def test_json_flag_switches_output_to_json(recorder, capsys):
    recorder.replies["ping"] = {"pid": 5}
    cli.main(["--json", "ping"])
    assert json.loads(capsys.readouterr().out) == {"pid": 5}


def test_context_new_forwards_role_prompt_and_title(recorder, capsys):
    recorder.replies["context.new"] = {"id": "t9", "status": "working"}
    cli.main(["context", "new", "--role", "p", "--prompt", "x"])
    assert recorder.calls == [("context.new", {"role": "p", "prompt": "x", "title": "", "open": False})]
    assert capsys.readouterr().out == "t9\n"


def test_context_new_without_prompt_sends_empty_prompt(recorder):
    recorder.replies["context.new"] = {"id": "t9", "status": "idle"}
    cli.main(["context", "new", "--role", "p"])
    assert recorder.calls == [("context.new", {"role": "p", "prompt": "", "title": "", "open": False})]


def test_context_new_title_flag_is_forwarded(recorder):
    recorder.replies["context.new"] = {"id": "t9", "status": "working"}
    cli.main(["context", "new", "--role", "p", "--prompt", "x", "--title", "T"])
    assert recorder.calls[0][1]["title"] == "T"


def test_context_new_open_flag_is_forwarded(recorder):
    recorder.replies["context.new"] = {"id": "t9", "status": "working"}
    cli.main(["context", "new", "--role", "p", "--prompt", "x", "--open"])
    assert recorder.calls[0][1]["open"] is True


def test_context_new_wait_polls_show_until_settled_and_prints_last_text(recorder, fake_clock, capsys):
    recorder.replies["context.new"] = {"id": "t9", "status": "working"}
    recorder.replies["context.show"] = deque([{"id": "t9", "status": "working"},
                                              {"id": "t9", "status": "idle", "lastText": "all done"}])
    cli.main(["context", "new", "--role", "p", "--prompt", "x", "--wait"])
    assert recorder.calls == [("context.new", {"role": "p", "prompt": "x", "title": "", "open": False}),
                              ("context.show", {"id": "t9"}), ("context.show", {"id": "t9"})]
    assert capsys.readouterr().out == "all done\n"


def test_context_new_wait_json_prints_full_summary(recorder, fake_clock, capsys):
    recorder.replies["context.new"] = {"id": "t9", "status": "working"}
    recorder.replies["context.show"] = deque([{"id": "t9", "status": "idle", "lastText": "done"}])
    cli.main(["--json", "context", "new", "--role", "p", "--prompt", "x", "--wait"])
    assert json.loads(capsys.readouterr().out) == {"id": "t9", "status": "idle", "lastText": "done"}


def test_context_wait_prints_status_when_settled_without_last_text(recorder, fake_clock, capsys):
    recorder.replies["context.show"] = deque([{"id": "t1", "status": "failed"}])
    cli.main(["context", "wait", "t1"])
    assert recorder.calls == [("context.show", {"id": "t1"})]
    assert capsys.readouterr().out == "failed\n"


def test_context_wait_times_out_with_system_exit(recorder, fake_clock):
    recorder.replies["context.show"] = {"id": "t1", "status": "working"}  # never settles
    with pytest.raises(SystemExit) as e:
        cli.main(["context", "wait", "t1", "--timeout", "2"])
    assert str(e.value) == "timeout waiting for t1"
    assert 1 <= len(recorder.calls) <= 5  # 2s / 0.5s polls, driven by the fake clock


def test_context_list_forwards_story_filter(recorder):
    recorder.replies["context.list"] = []
    cli.main(["context", "list", "--story", "ABC-1"])
    assert recorder.calls == [("context.list", {"story": "ABC-1"})]


def test_context_list_without_story_sends_empty_filter(recorder):
    recorder.replies["context.list"] = []
    cli.main(["context", "list"])
    assert recorder.calls == [("context.list", {"story": ""})]


def test_context_show_forwards_transcript_flag(recorder):
    recorder.replies["context.show"] = {"id": "t1"}
    cli.main(["context", "show", "t1", "--transcript"])
    assert recorder.calls == [("context.show", {"id": "t1", "transcript": True})]


def test_context_show_without_flag_sends_transcript_false(recorder):
    recorder.replies["context.show"] = {"id": "t1"}
    cli.main(["context", "show", "t1"])
    assert recorder.calls == [("context.show", {"id": "t1", "transcript": False})]


def test_context_send_forwards_message_as_text(recorder):
    recorder.replies["context.send"] = {"id": "t1"}
    cli.main(["context", "send", "t1", "--message", "hello there"])
    assert recorder.calls == [("context.send", {"id": "t1", "text": "hello there"})]


def test_context_stop_requests_stop(recorder):
    recorder.replies["context.stop"] = {"id": "t1"}
    cli.main(["context", "stop", "t1"])
    assert recorder.calls == [("context.stop", {"id": "t1"})]


def test_missing_subcommand_is_a_usage_error(recorder):
    with pytest.raises(SystemExit) as e:
        cli.main(["context"])
    assert e.value.code == 2
    assert recorder.calls == []


# ---------------------------------------------------------------- story


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


def test_story_resolve_inside_and_outside_a_character(recorder, monkeypatch):
    recorder.replies["story.resolve"] = {"id": "c1", "kind": "system"}
    cli.main(["story", "resolve", "ABC-1", "--thread", "t2", "--note", "n"])
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr1")
    cli.main(["story", "resolve", "--thread", "t2"])
    assert recorder.calls == [("story.resolve", {"key": "ABC-1", "thread": "t2", "note": "n"}),
                              ("story.resolve", {"character": "chr1", "thread": "t2", "note": ""})]
