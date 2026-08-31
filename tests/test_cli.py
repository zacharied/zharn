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
        cli.request("thread.show", {"id": "nope"})
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
    monkeypatch.delenv("HARNESS_TASK_KEY", raising=False)
    monkeypatch.delenv("HARNESS_THREAD_ID", raising=False)
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


def test_thread_spawn_defaults_task_and_parent_from_env(recorder, monkeypatch, capsys):
    monkeypatch.setenv("HARNESS_TASK_KEY", "ABC-1")
    monkeypatch.setenv("HARNESS_THREAD_ID", "parent1")
    recorder.replies["thread.spawn"] = {"id": "t9", "status": "working"}
    cli.main(["thread", "spawn", "--role", "p", "--prompt", "x"])
    assert recorder.calls == [("thread.spawn", {"task": "ABC-1", "role": "p", "prompt": "x", "parent": "parent1", "open": False})]
    assert capsys.readouterr().out == "t9\n"


def test_thread_spawn_no_parent_clears_parent(recorder, monkeypatch):
    monkeypatch.setenv("HARNESS_THREAD_ID", "parent1")
    recorder.replies["thread.spawn"] = {"id": "t9", "status": "working"}
    cli.main(["thread", "spawn", "--role", "p", "--prompt", "x", "--no-parent"])
    assert recorder.calls[0][1]["parent"] == ""


def test_thread_spawn_task_flag_overrides_env(recorder, monkeypatch):
    monkeypatch.setenv("HARNESS_TASK_KEY", "ABC-1")
    recorder.replies["thread.spawn"] = {"id": "t9", "status": "working"}
    cli.main(["thread", "spawn", "--role", "p", "--prompt", "x", "--task", "XYZ-2"])
    assert recorder.calls[0][1]["task"] == "XYZ-2"


def test_thread_spawn_without_env_sends_empty_task_and_parent(recorder):
    recorder.replies["thread.spawn"] = {"id": "t9", "status": "working"}
    cli.main(["thread", "spawn", "--role", "p", "--prompt", "x"])
    assert recorder.calls[0][1]["task"] == "" and recorder.calls[0][1]["parent"] == ""


def test_thread_spawn_open_flag_is_forwarded(recorder):
    recorder.replies["thread.spawn"] = {"id": "t9", "status": "working"}
    cli.main(["thread", "spawn", "--role", "p", "--prompt", "x", "--open"])
    assert recorder.calls[0][1]["open"] is True


def test_thread_spawn_wait_polls_show_until_settled_and_prints_last_text(recorder, fake_clock, capsys):
    recorder.replies["thread.spawn"] = {"id": "t9", "status": "working"}
    recorder.replies["thread.show"] = deque([{"id": "t9", "status": "working"},
                                             {"id": "t9", "status": "idle", "lastText": "all done"}])
    cli.main(["thread", "spawn", "--role", "p", "--prompt", "x", "--wait"])
    assert recorder.calls == [("thread.spawn", {"task": "", "role": "p", "prompt": "x", "parent": "", "open": False}),
                              ("thread.show", {"id": "t9"}), ("thread.show", {"id": "t9"})]
    assert capsys.readouterr().out == "all done\n"


def test_thread_spawn_wait_json_prints_full_summary(recorder, fake_clock, capsys):
    recorder.replies["thread.spawn"] = {"id": "t9", "status": "working"}
    recorder.replies["thread.show"] = deque([{"id": "t9", "status": "idle", "lastText": "done"}])
    cli.main(["--json", "thread", "spawn", "--role", "p", "--prompt", "x", "--wait"])
    assert json.loads(capsys.readouterr().out) == {"id": "t9", "status": "idle", "lastText": "done"}


def test_thread_wait_prints_status_when_settled_without_last_text(recorder, fake_clock, capsys):
    recorder.replies["thread.show"] = deque([{"id": "t1", "status": "failed"}])
    cli.main(["thread", "wait", "t1"])
    assert recorder.calls == [("thread.show", {"id": "t1"})]
    assert capsys.readouterr().out == "failed\n"


def test_thread_wait_times_out_with_system_exit(recorder, fake_clock):
    recorder.replies["thread.show"] = {"id": "t1", "status": "working"}  # never settles
    with pytest.raises(SystemExit) as e:
        cli.main(["thread", "wait", "t1", "--timeout", "2"])
    assert str(e.value) == "timeout waiting for t1"
    assert 1 <= len(recorder.calls) <= 5  # 2s / 0.5s polls, driven by the fake clock


def test_thread_list_forwards_task_filter(recorder):
    recorder.replies["thread.list"] = []
    cli.main(["thread", "list", "--task", "ABC-1"])
    assert recorder.calls == [("thread.list", {"task": "ABC-1"})]


def test_thread_list_without_task_sends_empty_filter(recorder):
    recorder.replies["thread.list"] = []
    cli.main(["thread", "list"])
    assert recorder.calls == [("thread.list", {"task": ""})]


def test_thread_show_forwards_transcript_flag(recorder):
    recorder.replies["thread.show"] = {"id": "t1"}
    cli.main(["thread", "show", "t1", "--transcript"])
    assert recorder.calls == [("thread.show", {"id": "t1", "transcript": True})]


def test_thread_show_without_flag_sends_transcript_false(recorder):
    recorder.replies["thread.show"] = {"id": "t1"}
    cli.main(["thread", "show", "t1"])
    assert recorder.calls == [("thread.show", {"id": "t1", "transcript": False})]


def test_thread_send_forwards_message_as_text(recorder):
    recorder.replies["thread.send"] = {"id": "t1"}
    cli.main(["thread", "send", "t1", "--message", "hello there"])
    assert recorder.calls == [("thread.send", {"id": "t1", "text": "hello there"})]


def test_thread_stop_requests_stop(recorder):
    recorder.replies["thread.stop"] = {"id": "t1"}
    cli.main(["thread", "stop", "t1"])
    assert recorder.calls == [("thread.stop", {"id": "t1"})]


def test_task_list_requests_task_list(recorder):
    recorder.replies["task.list"] = []
    cli.main(["task", "list"])
    assert recorder.calls == [("task.list", {})]


def test_task_show_forwards_key(recorder):
    recorder.replies["task.show"] = {"key": "ABC-1"}
    cli.main(["task", "show", "ABC-1"])
    assert recorder.calls == [("task.show", {"key": "ABC-1"})]


def test_task_status_forwards_key_and_status(recorder):
    recorder.replies["task.status"] = {"key": "ABC-1"}
    cli.main(["task", "status", "ABC-1", "done"])
    assert recorder.calls == [("task.status", {"key": "ABC-1", "status": "done"})]


def test_task_create_forwards_title_and_default_description(recorder):
    recorder.replies["task.create"] = {"key": "ABC-2"}
    cli.main(["task", "create", "--title", "T"])
    assert recorder.calls == [("task.create", {"title": "T", "description": ""})]


def test_task_create_forwards_description(recorder):
    recorder.replies["task.create"] = {"key": "ABC-2"}
    cli.main(["task", "create", "--title", "T", "--description", "D"])
    assert recorder.calls[0][1]["description"] == "D"


def test_missing_subcommand_is_a_usage_error(recorder):
    with pytest.raises(SystemExit) as e:
        cli.main(["thread"])
    assert e.value.code == 2
    assert recorder.calls == []
