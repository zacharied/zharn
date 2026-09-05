"""Unit tests for harness.cli (pure stdlib): request() transport, out() formatting, main() arg parsing.
The end-to-end CLI-over-IPC path lives in test_agents.py::test_cli_over_ipc."""
import io
import json
from pathlib import Path
import sys
import os
import socket
import subprocess
import threading
import time
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


@pytest.fixture
def fake_server(tmp_path, monkeypatch):
    """One-shot AF_UNIX server in a thread: reads one line, records it, replies with `reply`."""
    if os.name == "nt":
        pytest.skip("AF_UNIX fake server; the Windows named-pipe client is covered by test_agents.py")
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


def test_request_sends_cmd_and_args_and_returns_result(fake_server):
    state = fake_server({"ok": True, "result": {"pid": 42}})
    assert cli.request("ping", {"a": 1}) == {"pid": 42}
    assert state["received"] == {"cmd": "ping", "args": {"a": 1}}


def test_request_exits_with_server_error_text_when_not_ok(fake_server):
    fake_server({"ok": False, "error": "KeyError: 'nope'"})
    with pytest.raises(SystemExit) as e:
        cli.request("context.show", {"id": "nope"})
    assert str(e.value) == "error: KeyError: 'nope'"


@pytest.mark.skipif(os.name == "nt", reason="AF_UNIX fake server")
def test_request_exits_with_clear_message_when_the_harness_never_replies(tmp_path, monkeypatch):
    """C2: a clone/worktree/setup on the harness side can run far longer than a short socket timeout; the CLI
    must say plainly that it gave up waiting, not crash with a raw socket.timeout traceback."""
    path = str(tmp_path / "ipc.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(1)
    srv.settimeout(5)

    def serve():
        conn, _ = srv.accept()
        with conn:
            data = b""
            while not data.endswith(b"\n"):
                data += conn.recv(65536)
            time.sleep(2)   # outlive the client's request timeout without ever replying

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    monkeypatch.setenv("HARNESS_IPC", path)
    try:
        with pytest.raises(SystemExit) as e:
            cli.request("ping", {}, timeout=0.2)
        assert str(e.value) == "error: no reply from the harness within 0.2s for ping"
    finally:
        srv.close()
        t.join(timeout=5)


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
    kwargs_seen = []
    replies = {}

    def fake_request(cmd, args, **kwargs):
        calls.append((cmd, args))
        kwargs_seen.append((cmd, kwargs))
        r = replies.get(cmd, {})
        if isinstance(r, deque):
            return r.popleft()
        return r

    monkeypatch.setattr(cli, "request", fake_request)
    monkeypatch.delenv("HARNESS_CHARACTER_ID", raising=False)
    monkeypatch.delenv("HARNESS_STORY_KEY", raising=False)
    return types.SimpleNamespace(calls=calls, replies=replies, kwargs_seen=kwargs_seen)


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


def _git_repo(path):
    """A committed repo at `path` (a clean tree for the handoff's tree gate)."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text("hello\n")
    for args in (["init", "-q", "-b", "main"], ["add", "README.md"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)
    return path


def test_story_yield_question_reads_a_document_from_stdin(recorder, monkeypatch):
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr1")
    recorder.replies["story.yield"] = {"id": "c1", "kind": "question"}
    doc = {"body": "Two things.", "questions": [{"text": "a or b?", "options": ["a", "b"], "default": "a"}, {"text": "why?"}]}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(doc)))
    cli.main(["story", "yield", "--question", "--thread", "main"])
    assert recorder.calls == [("story.yield", {"character": "chr1", "kind": "question", "body": "Two things.",
                                               "questions": doc["questions"], "thread": "main", "checks": []})]
    recorder.replies["env.checks"] = {"run": False, "environments": [], "policy": "gate", "limit": 100, "timeout": 30}
    cli.main(["story", "yield", "--handoff", "--body", "done"])
    assert recorder.calls[-1][1]["kind"] == "handoff" and recorder.calls[-1][1]["questions"] == [] and recorder.calls[-1][1]["body"] == "done"


def test_story_yield_question_refuses_body_and_bad_json(recorder, monkeypatch):
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr1")
    with pytest.raises(SystemExit, match="--body belongs to --handoff"):
        cli.main(["story", "yield", "--question", "--body", "which?"])
    monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))
    with pytest.raises(SystemExit, match="not JSON"):
        cli.main(["story", "yield", "--question"])
    monkeypatch.setattr("sys.stdin", io.StringIO("[]"))
    with pytest.raises(SystemExit, match="JSON object"):
        cli.main(["story", "yield", "--question"])
    with pytest.raises(SystemExit, match="a handoff needs --body"):
        cli.main(["story", "yield", "--handoff"])
    assert recorder.calls == []


def test_dirty_trees_reports_status_per_repo(tmp_path):
    clean, dirty = _git_repo(tmp_path / "clean"), _git_repo(tmp_path / "dirty")
    (dirty / "new.py").write_text("x")
    assert cli.dirty_trees([{"repo": "a", "path": str(clean)}, {"repo": "b", "path": str(dirty)}]) == [{"repo": "b", "path": str(dirty), "status": "?? new.py"}]
    assert cli.dirty_trees([{"repo": "c", "path": str(tmp_path / "missing")}]) == []


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


def test_story_yield_requires_exactly_one_kind_and_a_character(recorder, monkeypatch):
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr1")
    with pytest.raises(SystemExit):
        cli.main(["story", "yield", "--body", "x"])
    with pytest.raises(SystemExit):
        cli.main(["story", "yield", "--question", "--handoff", "--body", "x"])
    monkeypatch.delenv("HARNESS_CHARACTER_ID")
    with pytest.raises(SystemExit) as e:
        cli.main(["story", "yield", "--handoff", "--body", "x"])
    assert "HARNESS_CHARACTER_ID" in str(e.value)
    assert recorder.calls == []


def test_story_proceed_recap_comment_inside_a_character(recorder, monkeypatch):
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr1")
    for cmd in ("story.proceed", "story.recap", "story.comment"):
        recorder.replies[cmd] = {"id": "c"}
    cli.main(["story", "proceed", "--note", "bounded"]); cli.main(["story", "recap", "--body", "r"]); cli.main(["story", "comment", "--body", "c"])
    assert recorder.calls == [("story.proceed", {"character": "chr1", "note": "bounded"}), ("story.recap", {"character": "chr1", "body": "r", "thread": ""}),
                              ("story.comment", {"character": "chr1", "body": "c", "thread": "", "to": []})]


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


def test_story_call_wait_inbox_cast_recap_comment_args(recorder, monkeypatch):
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr1")
    recorder.replies["story.call"] = {"thread": "thr_x", "character": "chr2", "name": "Impl"}
    recorder.replies["story.wait"] = {"awaits": [], "message": "end your turn"}
    cli.main(["story", "call", "--role", "claude-fast", "--as", "Impl", "--fork", "--note", "build it"])
    cli.main(["story", "wait"])
    cli.main(["story", "inbox"])
    cli.main(["story", "cast"])
    cli.main(["story", "recap", "--body", "r", "--thread", "thr_x"])
    cli.main(["story", "comment", "--body", "b", "--to", "@Impl", "--to", "@Rev"])
    assert recorder.calls == [
        ("story.call", {"character": "chr1", "role": "claude-fast", "note": "build it", "as": "Impl", "fork": True}),
        ("story.wait", {"character": "chr1"}),
        ("story.inbox", {"character": "chr1"}),
        ("story.cast", {"key": "", "character": "chr1"}),
        ("story.recap", {"character": "chr1", "body": "r", "thread": "thr_x"}),
        ("story.comment", {"character": "chr1", "body": "b", "thread": "", "to": ["@Impl", "@Rev"]}),
    ]


def test_story_create_and_author_verbs_inside_a_character(recorder, monkeypatch):
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr1")
    recorder.replies["story.create"] = "SUB-1"
    cli.main(["story", "create", "--title", "t", "--start", "--role", "claude-fast"])
    cli.main(["story", "approve", "SUB-1", "--note", "ok"])
    cli.main(["story", "reply", "SUB-1", "--thread", "t", "--body", "b"])
    assert recorder.calls == [
        ("story.create", {"character": "chr1", "title": "t", "description": "", "start": True, "role": "claude-fast"}),
        ("story.approve", {"character": "chr1", "key": "SUB-1", "note": "ok"}),
        ("story.reply", {"character": "chr1", "key": "SUB-1", "thread": "t", "body": "b"}),
    ]


@pytest.fixture
def fake_ipc(tmp_path, monkeypatch):
    """Serves `replies` in order, one connection each; records every request."""
    if os.name == "nt":
        pytest.skip("AF_UNIX fake server; the Windows named-pipe client is covered by test_agents.py")
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


def test_repo_add_and_env_open_use_a_long_request_timeout(recorder, monkeypatch, tmp_path):
    """C2: repo.add (clone) and env.open (worktree add + setup) can run far longer than the default 30s
    socket timeout, which is meant for ordinary requests; they must ask for the bounded-but-generous timeout."""
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr_1")
    recorder.replies["repo.add"] = {"name": "api"}
    recorder.replies["env.open"] = {"repo": "api", "path": "/wt/api"}
    cli.main(["repo", "add", str(tmp_path / "api")])
    cli.main(["env", "open", "api"])
    timeouts = dict(recorder.kwargs_seen)
    assert timeouts["repo.add"]["timeout"] == cli.LONG_REQUEST_TIMEOUT_S
    assert timeouts["env.open"]["timeout"] == cli.LONG_REQUEST_TIMEOUT_S


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


def test_repo_add_keeps_urls_and_absolutises_paths(fake_ipc, monkeypatch, tmp_path):
    st = fake_ipc({"name": "a"}, {"name": "b"})
    monkeypatch.chdir(tmp_path)
    cli.main(["repo", "add", "https://example.com/x/a.git"])
    cli.main(["repo", "add", "sub/b"])
    assert st["received"][0]["args"]["spec"] == "https://example.com/x/a.git"
    assert st["received"][1]["args"]["spec"] == str(tmp_path / "sub" / "b")


def test_run_checks_runs_each_env_and_truncates(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "ok.txt").write_text("")
    ok, missing = "test -f ok.txt && echo fine", "echo 0123456789; test -f ok.txt"
    res = cli.run_checks([{"repo": "a", "checks": ok, "path": str(a)},
                          {"repo": "b", "checks": missing, "path": str(b)}], limit=6, timeout=30)
    assert res == [{"repo": "a", "cmd": ok, "exit": 0, "output": "fine\n"[-6:]},
                   {"repo": "b", "cmd": missing, "exit": 1, "output": "56789\n"}]


def test_run_checks_times_out(tmp_path):
    t0 = time.time()
    res = cli.run_checks([{"repo": "s", "checks": "sleep 5", "path": str(tmp_path)}], limit=100, timeout=0.2)
    assert res[0]["exit"] == -1 and "timed out" in res[0]["output"]
    assert time.time() - t0 < 3, "the whole process tree must die at the timeout, not just the shell"


def test_run_checks_output_is_empty_when_limit_is_zero(tmp_path):
    """M3: `output[-limit:]` with limit=0 slices to the whole string (Python quirk); it must mean "keep none"."""
    res = cli.run_checks([{"repo": "a", "checks": "echo hi", "path": str(tmp_path)}], limit=0, timeout=30)
    assert res[0]["exit"] == 0 and res[0]["output"] == ""


def test_run_checks_kills_the_whole_process_group_on_timeout(tmp_path):
    """M4: a timed-out check must not leave grandchildren (spawned by the shell it ran in) running — the whole
    process group started for the check has to die, not just the immediate shell."""
    marker = tmp_path / "child-ran"
    cmd = f"bash -c 'sleep 3; touch {marker}' & wait"
    res = cli.run_checks([{"repo": "s", "checks": cmd, "path": str(tmp_path)}], limit=100, timeout=0.3)
    assert res[0]["exit"] == -1
    time.sleep(1)   # the backgrounded child's sleep would have finished by now if it survived the timeout
    assert not marker.exists()


def test_handoff_refuses_a_dirty_tree_before_running_checks(fake_ipc, tmp_path, capsys):
    repo = _git_repo(tmp_path / "api"); (repo / "hello.py").write_text("changed")
    st = fake_ipc({"run": True, "policy": "gate", "limit": 100, "timeout": 30,
                   "environments": [{"repo": "api", "checks": "false", "path": str(repo)}]})
    with pytest.raises(SystemExit) as e:
        cli.main(["story", "yield", "--handoff", "--body", "done", "--despite-checks"])
    assert "handoff refused: uncommitted changes in api" in str(e.value) and "commit them and retry" in str(e.value)
    assert "?? hello.py" in capsys.readouterr().err
    assert [r["cmd"] for r in st["received"]] == ["env.checks"]     # the checks never ran, nothing posted


def test_handoff_skips_repos_without_checks(fake_ipc, tmp_path):
    repo = _git_repo(tmp_path / "plain")
    st = fake_ipc({"run": True, "policy": "gate", "limit": 100, "timeout": 30,
                   "environments": [{"repo": "plain", "checks": "", "path": str(repo)}]}, {"id": "c1"})
    cli.main(["story", "yield", "--handoff", "--body", "done"])
    assert [r["args"]["checks"] for r in st["received"] if r["cmd"] == "story.yield"] == [[]]


def test_handoff_runs_checks_and_gates_on_failure(fake_ipc, tmp_path, capsys):
    tmp_path = _git_repo(tmp_path / "api")
    plan = {"run": True, "policy": "gate", "limit": 100, "timeout": 30,
            "environments": [{"repo": "api", "checks": "test -f ok.txt", "path": str(tmp_path)}]}
    st = fake_ipc(plan)
    with pytest.raises(SystemExit) as e:
        cli.main(["story", "yield", "--handoff", "--body", "done"])
    assert "handoff refused: checks failed in api" in str(e.value) and "--despite-checks" in str(e.value)
    assert len(st["received"]) == 1 and st["received"][0]["cmd"] == "env.checks"
    assert "[api] test -f ok.txt" in capsys.readouterr().err


def test_handoff_posts_with_checks_when_they_pass_or_despite_or_attach(fake_ipc, tmp_path):
    tmp_path = _git_repo(tmp_path / "api")
    (tmp_path / "ok.txt").write_text("")
    subprocess.run(["git", "add", "ok.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "ok"], cwd=tmp_path, check=True)
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


def test_handoff_without_bash_is_refused_naming_the_install(fake_ipc, tmp_path, monkeypatch):
    """No bash to run the checks in is a refused handoff whose message says what to install — not a traceback."""
    from harness import procs
    repo = _git_repo(tmp_path / "api")
    st = fake_ipc({"run": True, "policy": "gate", "limit": 100, "timeout": 30,
                   "environments": [{"repo": "api", "checks": "pytest -q", "path": str(repo)}]})

    def missing():
        raise procs.NoBash("Git Bash not found: install Git for Windows")
    monkeypatch.setattr(procs, "bash_path", missing)
    with pytest.raises(SystemExit) as e:
        cli.main(["story", "yield", "--handoff", "--body", "done"])
    assert str(e.value).startswith("handoff refused:") and "Git for Windows" in str(e.value)
    assert [r["cmd"] for r in st["received"]] == ["env.checks"]     # nothing posted


def test_story_proceed_prints_the_skill_after_the_comment(recorder, monkeypatch, capsys):
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr1")
    recorder.replies["story.proceed"] = {"id": "cmt_1", "kind": "system", "skill": "# Implementing\n\nBuild."}
    cli.main(["story", "proceed"])
    assert capsys.readouterr().out == "id: cmt_1\nkind: system\n\n# Implementing\n\nBuild.\n"
    cli.main(["--json", "story", "proceed"])
    assert json.loads(capsys.readouterr().out)["skill"] == "# Implementing\n\nBuild."


# ---------------------------------------------------------------- encoding

def test_cli_stdio_is_utf8_whatever_the_console_says(tmp_path):
    """Piped under Claude Code on Windows the streams default to the ANSI code page; a story body with a check mark
    then kills `story show`. The CLI owns its encoding: bash hands it UTF-8 bytes and gets UTF-8 back."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8",)}
    env["PYTHONIOENCODING"] = "cp1252"   # the worst console, on every platform
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
    r = subprocess.run([sys.executable, "-c", "import harness.cli, sys; print(sys.stdin.encoding, sys.stdout.encoding, sys.stderr.encoding); print('\u2713')"],
                       capture_output=True, env=env, timeout=30)
    assert r.returncode == 0, r.stderr
    assert r.stdout.decode("utf-8").splitlines()[:2] == ["utf-8 utf-8 utf-8", "\u2713"]
