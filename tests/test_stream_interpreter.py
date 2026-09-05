"""StreamInterpreter: hand-built claude stream-json events -> TranscriptModel rows.

No subprocess, no app. Event shapes mirror tests/fake_claude.py (captured from the real CLI).
"""
import json

import pytest

from harness import config as cfg
from harness.agents import StreamInterpreter, TranscriptModel, _block_text, claude_command, split_command


# --------------------------------------------------------------------------- event builders
def init_ev(session="sess-1", model="fake-model"):
    return {"type": "system", "subtype": "init", "session_id": session, "model": model, "tools": ["Bash"]}


def stream(event):
    return {"type": "stream_event", "event": event}


def block_start(content_block, index=0):
    return stream({"type": "content_block_start", "index": index, "content_block": content_block})


def text_delta(text, index=0):
    return stream({"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": text}})


def json_delta(partial, index=0):
    return stream({"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": partial}})


def thinking_delta(text, index=0):
    return stream({"type": "content_block_delta", "index": index, "delta": {"type": "thinking_delta", "thinking": text}})


def block_stop(index=0):
    return stream({"type": "content_block_stop", "index": index})


def assistant_ev(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks), "model": "fake-model"}}


def tool_result_ev(tool_use_id, content, is_error=False):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use_id, "content": content, "is_error": is_error}]}}


def result_ev(is_error=False, **kw):
    base = {"type": "result", "subtype": "error_during_execution" if is_error else "success", "is_error": is_error,
            "result": "done", "num_turns": 1, "total_cost_usd": 0.01, "duration_ms": 5, "session_id": "sess-1"}
    return {**base, **kw}


def summarize(model):
    """Row tuples without the wall-clock `ts` field."""
    return [tuple((k, r[k]) for k in sorted(r) if k != "ts") for r in model.rows()]


@pytest.fixture
def model():
    return TranscriptModel()


@pytest.fixture
def interp(model):
    return StreamInterpreter(model)


# --------------------------------------------------------------------------- system / init
def test_init_sets_session_and_model_and_returns_working(interp, model):
    assert interp.apply(init_ev(session="abc", model="claude-x")) == "working"
    assert interp.session_id == "abc"
    assert interp.model_name == "claude-x"
    assert model.count() == 0


# --------------------------------------------------------------------------- text streaming
def test_text_deltas_accumulate_while_streaming(interp, model):
    interp.apply(block_start({"type": "text", "text": ""}))
    assert model.count() == 1
    assert model.rows()[0]["streaming"] is True
    interp.apply(text_delta("hel"))
    interp.apply(text_delta("lo"))
    assert model.rows()[0]["text"] == "hello"
    assert model.rows()[0]["streaming"] is True


def test_block_stop_clears_streaming(interp, model):
    interp.apply(block_start({"type": "text", "text": ""}))
    interp.apply(text_delta("hi"))
    interp.apply(block_stop())
    assert model.rows()[0]["streaming"] is False
    assert model.rows()[0]["text"] == "hi"


def test_delta_without_open_block_is_ignored(interp, model):
    assert interp.apply(text_delta("orphan")) is None
    assert model.count() == 0


def test_assistant_finalizes_streamed_text_without_duplicate(interp, model):
    interp.apply(block_start({"type": "text", "text": ""}))
    interp.apply(text_delta("hel"))
    interp.apply(text_delta("lo"))
    # real CLI order: assistant message arrives before content_block_stop
    interp.apply(assistant_ev({"type": "text", "text": "hello"}))
    interp.apply(block_stop())
    assert model.count() == 1
    assert model.rows()[0] | {"ts": 0} == {"role": "assistant", "kind": "text", "text": "hello", "name": "", "input": "",
                                            "toolId": "", "isError": False, "streaming": False, "ts": 0, "meta": ""}


def test_assistant_text_block_without_stream_appends_row(interp, model):
    interp.apply(assistant_ev({"type": "text", "text": "plain answer"}))
    assert model.count() == 1
    r = model.rows()[0]
    assert (r["role"], r["kind"], r["text"], r["streaming"]) == ("assistant", "text", "plain answer", False)


def test_second_assistant_text_after_finalized_one_appends_new_row(interp, model):
    interp.apply(assistant_ev({"type": "text", "text": "first"}))
    interp.apply(assistant_ev({"type": "text", "text": "second"}))
    assert [r["text"] for r in model.rows()] == ["first", "second"]


def test_repeated_identical_assistant_text_is_deduplicated(interp, model):
    interp.apply(assistant_ev({"type": "text", "text": "same"}))
    interp.apply(assistant_ev({"type": "text", "text": "same"}))
    assert [r["text"] for r in model.rows()] == ["same"]


# --------------------------------------------------------------------------- tool_use
def test_tool_use_streams_partial_json_then_finalizes_pretty(interp, model):
    interp.apply(block_start({"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {}}))
    r = model.rows()[0]
    assert (r["kind"], r["name"], r["toolId"], r["input"], r["streaming"]) == ("tool_use", "Bash", "toolu_1", "", True)
    interp.apply(json_delta('{"command": '))
    interp.apply(json_delta('"echo hi"}'))
    assert model.rows()[0]["input"] == '{"command": "echo hi"}'
    interp.apply(assistant_ev({"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "echo hi"}}))
    interp.apply(block_stop())
    assert model.count() == 1
    assert model.rows()[0]["input"] == json.dumps({"command": "echo hi"}, indent=1)
    assert model.rows()[0]["streaming"] is False


def test_tool_use_without_stream_appends_with_pretty_input(interp, model):
    interp.apply(assistant_ev({"type": "tool_use", "id": "toolu_9", "name": "Read", "input": {"path": "x"}}))
    assert model.count() == 1
    r = model.rows()[0]
    assert (r["kind"], r["name"], r["toolId"]) == ("tool_use", "Read", "toolu_9")
    assert json.loads(r["input"]) == {"path": "x"}
    assert r["streaming"] is False


def test_tool_use_finalize_matches_by_tool_id(interp, model):
    interp.apply(block_start({"type": "tool_use", "id": "toolu_a", "name": "Bash", "input": {}}))
    interp.apply(block_stop())
    interp.apply(block_start({"type": "tool_use", "id": "toolu_b", "name": "Bash", "input": {}}))
    interp.apply(block_stop())
    interp.apply(assistant_ev({"type": "tool_use", "id": "toolu_a", "name": "Bash", "input": {"n": 1}}))
    assert model.count() == 2
    assert json.loads(model.rows()[0]["input"]) == {"n": 1}
    assert model.rows()[1]["input"] == ""


# --------------------------------------------------------------------------- tool_result
def test_tool_result_string_content(interp, model):
    assert interp.apply(tool_result_ev("toolu_1", "hello-from-tool")) is None
    r = model.rows()[0]
    assert (r["role"], r["kind"], r["toolId"], r["text"], r["isError"]) == ("tool", "tool_result", "toolu_1", "hello-from-tool", False)


def test_tool_result_list_of_blocks_content_joined(interp, model):
    interp.apply(tool_result_ev("toolu_1", [{"type": "text", "text": "line1"}, {"type": "text", "text": "line2"}]))
    assert model.rows()[0]["text"] == "line1\nline2"


def test_tool_result_is_error_flag(interp, model):
    interp.apply(tool_result_ev("toolu_1", "boom", is_error=True))
    assert model.rows()[0]["isError"] is True


def test_user_event_ignores_non_tool_result_blocks(interp, model):
    interp.apply({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]}})
    assert model.count() == 0


# --------------------------------------------------------------------------- thinking
def test_thinking_streams_and_finalizes(interp, model):
    interp.apply(block_start({"type": "thinking", "thinking": ""}))
    interp.apply(thinking_delta("let me "))
    interp.apply(thinking_delta("think"))
    r = model.rows()[0]
    assert (r["kind"], r["text"], r["streaming"]) == ("thinking", "let me think", True)
    interp.apply(assistant_ev({"type": "thinking", "thinking": "let me think", "signature": "sig"}))
    interp.apply(block_stop())
    assert model.count() == 1
    assert (model.rows()[0]["text"], model.rows()[0]["streaming"]) == ("let me think", False)


def test_thinking_finalize_keeps_streamed_text_when_block_empty(interp, model):
    interp.apply(block_start({"type": "thinking", "thinking": ""}))
    interp.apply(thinking_delta("streamed"))
    interp.apply(assistant_ev({"type": "thinking", "thinking": ""}))
    assert model.rows()[0]["text"] == "streamed"


def test_unknown_content_block_type_is_skipped(interp, model):
    interp.apply(block_start({"type": "redacted_thinking", "data": "x"}))
    interp.apply(text_delta("ignored"))
    assert model.count() == 0


# --------------------------------------------------------------------------- result
def test_result_success_accumulates_and_returns_idle(interp, model):
    assert interp.apply(result_ev(num_turns=2, total_cost_usd=0.01, session_id="s1")) == "idle"
    assert interp.apply(result_ev(num_turns=1, total_cost_usd=0.02, session_id="s2")) == "idle"
    assert interp.turns == 3
    assert abs(interp.cost_usd - 0.03) < 1e-9
    assert interp.session_id == "s2"
    assert model.count() == 0


def test_result_error_appends_error_row_and_returns_failed(interp, model):
    assert interp.apply(result_ev(is_error=True, result="simulated failure")) == "failed"
    r = model.rows()[-1]
    assert (r["role"], r["kind"], r["text"], r["isError"]) == ("system", "error", "simulated failure", True)


def test_result_error_without_text_uses_subtype(interp, model):
    interp.apply(result_ev(is_error=True, result="", subtype="error_max_turns"))
    assert model.rows()[-1]["text"] == "error_max_turns"


def test_result_resets_current_block(interp, model):
    interp.apply(block_start({"type": "text", "text": ""}))
    interp.apply(result_ev())
    interp.apply(text_delta("late"))
    assert model.rows()[0]["text"] == ""


def test_result_with_missing_numbers_is_tolerated(interp):
    interp.apply(result_ev(num_turns=None, total_cost_usd=None))
    assert (interp.turns, interp.cost_usd) == (0, 0.0)


# --------------------------------------------------------------------------- context usage (lifecycle spec §2.3)
def usage_ev(input_tokens, cache_read, cache_creation):
    ev = assistant_ev({"type": "text", "text": "hi"})
    ev["message"]["usage"] = {"input_tokens": input_tokens, "cache_read_input_tokens": cache_read,
                              "cache_creation_input_tokens": cache_creation, "output_tokens": 4}
    return ev


def test_assistant_usage_is_a_reading_not_a_sum(interp):
    assert interp.context_tokens == 0
    interp.apply(usage_ev(10, 13615, 8249))
    assert interp.context_tokens == 21874
    interp.apply(usage_ev(10, 13615, 8249))     # one API message → one assistant event per block, same usage each
    assert interp.context_tokens == 21874
    interp.apply(usage_ev(5, 30000, 0))
    assert interp.context_tokens == 30005


def test_assistant_without_usage_keeps_the_reading(interp):
    interp.apply(usage_ev(10, 1000, 0))
    interp.apply(assistant_ev({"type": "text", "text": "no usage here"}))
    assert interp.context_tokens == 1010


def test_result_model_usage_sets_the_window(interp):
    interp.apply(init_ev(model="claude-haiku-4-5"))
    assert interp.context_window == 0
    interp.apply(result_ev(modelUsage={"claude-haiku-4-5": {"contextWindow": 200000, "maxOutputTokens": 32000}}))
    assert interp.context_window == 200000
    interp.apply(result_ev())                  # a result without modelUsage keeps it
    assert interp.context_window == 200000


def test_result_window_prefers_the_sessions_model(interp):
    interp.apply(init_ev(model="claude-opus-5"))
    interp.apply(result_ev(modelUsage={"claude-haiku-4-5": {"contextWindow": 200000},
                                       "claude-opus-5": {"contextWindow": 1000000}}))
    assert interp.context_window == 1000000


def test_compact_boundary_is_a_visible_error(interp, model):
    ev = {"type": "system", "subtype": "compact_boundary", "compact_metadata": {"trigger": "auto", "pre_tokens": 150000}}
    assert interp.apply(ev) is None
    row = model.rows()[-1]
    assert row["role"] == "system" and row["kind"] == "error" and row["isError"] and "compacted" in row["text"]


# --------------------------------------------------------------------------- misc
@pytest.mark.parametrize("ev", [
    {"type": "system", "subtype": "status", "status": "requesting"},
    {"type": "rate_limit_event"},
    {"type": "bogus"},
    {},
    stream({"type": "message_start"}),
    stream({"type": "message_stop"}),
])
def test_unknown_events_return_none_and_add_nothing(interp, model, ev):
    assert interp.apply(ev) is None
    assert model.count() == 0


def test_replay_is_deterministic():
    events = [
        init_ev(),
        block_start({"type": "text", "text": ""}), text_delta("he"), text_delta("llo"),
        assistant_ev({"type": "text", "text": "hello"}), block_stop(),
        block_start({"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {}}),
        json_delta('{"command": "ls"}'),
        assistant_ev({"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "ls"}}), block_stop(),
        tool_result_ev("toolu_1", "a\nb"),
        block_start({"type": "text", "text": ""}), text_delta("done"),
        assistant_ev({"type": "text", "text": "done"}), block_stop(),
        result_ev(),
    ]
    m1, m2 = TranscriptModel(), TranscriptModel()
    s1 = [StreamInterpreter(m1).apply(e) for e in events]
    s2 = [StreamInterpreter(m2).apply(e) for e in events]
    assert s1 == s2
    assert summarize(m1) == summarize(m2)
    assert [(r["role"], r["kind"]) for r in m1.rows()] == [
        ("assistant", "text"), ("assistant", "tool_use"), ("tool", "tool_result"), ("assistant", "text")]


# --------------------------------------------------------------------------- _block_text
@pytest.mark.parametrize("content, expected", [
    ("plain", "plain"),
    ([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}], "a\nb"),
    ([{"type": "image"}], ""),
    (["raw", 3], "raw\n3"),
    ([], ""),
    (None, ""),
    (42, "42"),
])
def test_block_text(content, expected):
    assert _block_text(content) == expected


# --------------------------------------------------------------------------- claude_command
def test_claude_command_honors_env_override(monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", "/usr/bin/python3 /tmp/fake claude.py --flag")
    assert claude_command() == ["/usr/bin/python3", "/tmp/fake", "claude.py", "--flag"]


def test_claude_command_env_override_supports_quoting(monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", '"/path with space/claude" --x')
    assert claude_command() == ["/path with space/claude", "--x"]


def test_split_command_on_windows_drops_quotes_and_keeps_backslashes():
    """Windows has no POSIX quoting: shlex's non-POSIX mode keeps the quotes on a token, which would make the
    program name a path with literal quotes in it (never found). Backslashes are path separators, not escapes."""
    assert split_command(r'"C:\path with space\claude.exe" --x', nt=True) == [r"C:\path with space\claude.exe", "--x"]
    assert split_command(r"C:\Users\z\Scripts\python.exe fake.py --flag", nt=True) == [r"C:\Users\z\Scripts\python.exe", "fake.py", "--flag"]


def test_split_command_on_posix_honors_shell_quoting():
    assert split_command('"/path with space/claude" --x', nt=False) == ["/path with space/claude", "--x"]
    assert split_command(r"/usr/bin/python3 /tmp/fake\ claude.py", nt=False) == ["/usr/bin/python3", "/tmp/fake claude.py"]


def test_claude_command_falls_back_to_config(monkeypatch):
    monkeypatch.delenv("HARNESS_CLAUDE_CMD", raising=False)
    monkeypatch.setattr(cfg, "CLAUDE_CMD", ["my-claude", "--wrapped"])
    cmd = claude_command()
    assert cmd == ["my-claude", "--wrapped"]
    assert cmd is not cfg.CLAUDE_CMD, "must return a copy so callers can't mutate config"


def test_claude_command_ignores_empty_env_override(monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", "")
    monkeypatch.setattr(cfg, "CLAUDE_CMD", ["claude"])
    assert claude_command() == ["claude"]
