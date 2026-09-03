# tests/test_contexts_unit.py
"""Context lifecycle without the UI: a context must always settle and say why; bare contexts; env."""
import json
import sys
import time

import pytest
from PySide6.QtTest import QTest

from harness.__main__ import ROOT
from harness.contexts import ContextStore, new_context_id
from harness.roles import RoleStore

FAKE = f"{sys.executable} {ROOT / 'tests' / 'fake_claude.py'}"


def wait_until(cond, timeout_ms=5000, step=20):
    t0 = time.time()
    while time.time() - t0 < timeout_ms / 1000:
        QTest.qWait(step)
        if cond():
            return True
    return False


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", FAKE)
    s = ContextStore(ROOT, tmp_path / "contexts", RoleStore(tmp_path), workspace_dir=tmp_path)
    yield s
    s.shutdown()


def test_ids_have_ctx_prefix():
    assert new_context_id().startswith("ctx_") and len(new_context_id()) == 14


def test_create_is_a_record_without_a_process(store, tmp_path):
    cid = store.create("claude-fast", story_key="ZH-1", owner="chr1", title="hello", env={"HARNESS_CHARACTER_ID": "chr1"})
    c = store.get(cid)
    assert c.status == "idle" and c._proc is None and c.owner == "chr1" and c.storyKey == "ZH-1" and c.roleName == "claude-fast"
    assert json.loads((tmp_path / "contexts" / "index.json").read_text())[0]["id"] == cid
    assert store.contexts_for("ZH-1") == [c] and store.contexts_for("ZH-2") == []
    assert store.model.rows()[0] == {**store.model.rows()[0], "id": cid, "owner": "chr1", "storyKey": "ZH-1", "status": "idle"}


def test_spawn_sends_env_and_settles(store, tmp_path):
    cid = store.spawn("claude-fast", "hello agent", story_key="ZH-1", owner="chr1", env={"HARNESS_CHARACTER_ID": "chr1"})
    c = store.get(cid)
    assert wait_until(lambda: c.status == "idle"), (c.status, c.lastError)
    records = [json.loads(l) for l in (tmp_path / "contexts" / f"{cid}.jsonl").read_text().splitlines()]
    init = next(r for r in records if r.get("subtype") == "init")
    assert init["harness_env"] == {"HARNESS_CONTEXT_ID": cid, "HARNESS_STORY_KEY": "ZH-1", "HARNESS_CHARACTER_ID": "chr1",
                                   "HARNESS_WORKSPACE": str(tmp_path)}
    assert c.transcript.rows()[-1]["text"] == "echo: hello agent"


def test_new_bare_has_human_owner_and_no_story(store):
    cid = store.newBare("claude-default")
    c = store.get(cid)
    assert c.owner == "human" and c.storyKey == "" and c.title == "New context" and c.status == "idle"
    c.send("first message")
    assert wait_until(lambda: c.status == "idle")
    assert c.transcript.rows()[-1]["text"] == "echo: first message"


def test_new_bare_default_role_is_the_bare_role(store):
    cid = store.newBare("")
    assert store.get(cid).roleName == "claude-default"


def test_unknown_role_and_unimplemented_provider_raise(store):
    with pytest.raises(ValueError, match="unknown role"):
        store.create("nope")
    with pytest.raises(ValueError, match="provider"):
        store.create("codex-review")


def test_unstartable_cli_fails_the_context_with_a_visible_reason(store, monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", "/nonexistent/claude-nope")
    cid = store.spawn("claude-fast", "hello")
    c = store.get(cid)
    assert wait_until(lambda: c.status == "failed"), c.status
    assert "claude-nope" in c.lastError and c.transcript.rows()[-1]["kind"] == "error"
    assert store.model.rows()[-1]["status"] == "failed"


def test_send_on_a_failed_context_retries_by_spawning_again(store, monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", "/nonexistent/claude-nope")
    cid = store.spawn("claude-fast", "hello")
    c = store.get(cid)
    assert wait_until(lambda: c.status == "failed")
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", FAKE)
    c.send("again")
    assert wait_until(lambda: c.status == "idle"), (c.status, c.lastError)
    assert c.transcript.rows()[-1]["text"] == "echo: again" and c.lastError == ""


def test_settled_signal_fires_once_per_settle(store):
    seen = []
    store.contextSettled.connect(seen.append)
    cid = store.spawn("claude-fast", "hi")
    assert wait_until(lambda: seen == [cid])
    store.get(cid).send("more")
    assert wait_until(lambda: seen == [cid, cid])


def test_transcripts_persist_and_replay(store, tmp_path):
    cid = store.spawn("claude-fast", "persist me", story_key="ZH-3", owner="chr9")
    assert wait_until(lambda: store.get(cid).status == "idle")
    fresh = ContextStore(ROOT, tmp_path / "contexts", RoleStore(tmp_path), workspace_dir=tmp_path)
    c = fresh.get(cid)
    assert c.owner == "chr9" and c.storyKey == "ZH-3" and c.status == "idle"
    assert [(r["role"], r["text"]) for r in c.transcript.rows()] == [("user", "persist me"), ("assistant", "echo: persist me")]


def inits(tmp_path, cid):
    return [json.loads(l) for l in (tmp_path / "contexts" / f"{cid}.jsonl").read_text().splitlines() if '"init"' in l]


def test_fork_resumes_the_source_once_then_runs_on_its_own_session(store, tmp_path):
    src = store.get(store.spawn("claude-fast", "hello", story_key="ZH-1", owner="chr1", env={"HARNESS_CHARACTER_ID": "chr1"}))
    assert wait_until(lambda: src.status == "idle") and src.sessionId == "fake-session-1"
    fid = store.fork(src.id, role_name="claude-default", title="aside", system_prompt="you are an aside",
                     about={"story_key": "ZH-1", "comment_id": "cmt_1"})
    f = store.get(fid)
    assert (f.meta["forkedFrom"], f.meta["forkSession"], f.owner, f.storyKey, f.roleName) == (src.id, "fake-session-1", "human", "", "claude-default")
    assert f.summary()["about"] == {"story_key": "ZH-1", "comment_id": "cmt_1"} and f.status == "idle" and f._proc is None
    f.send("what was said?")
    assert wait_until(lambda: f.status == "idle"), (f.status, f.lastError)
    first = inits(tmp_path, fid)[0]
    assert first["argv"][first["argv"].index("--resume") + 1] == "fake-session-1" and "--fork-session" in first["argv"]
    assert "HARNESS_CHARACTER_ID" not in first["harness_env"] and not first["harness_env"].get("HARNESS_STORY_KEY")
    assert f.sessionId == "fork-of-fake-session-1" and src.sessionId == "fake-session-1"
    f.stop()
    assert wait_until(lambda: f._proc is None)
    f.send("again")
    assert wait_until(lambda: f.status == "idle"), (f.status, f.lastError)
    second = inits(tmp_path, fid)[1]
    assert second["argv"][second["argv"].index("--resume") + 1] == "fork-of-fake-session-1" and "--fork-session" not in second["argv"]


def test_fork_survives_a_restart_on_its_own_session(store, tmp_path):
    src = store.get(store.spawn("claude-fast", "hello"))
    assert wait_until(lambda: src.status == "idle")
    fid = store.fork(src.id, role_name="claude-default")
    store.get(fid).send("first")
    assert wait_until(lambda: store.get(fid).status == "idle")
    store.shutdown()
    again = ContextStore(ROOT, tmp_path / "contexts", RoleStore(tmp_path), workspace_dir=tmp_path)
    f = again.get(fid)
    assert f.sessionId == "fork-of-fake-session-1" and f.meta["forkedFrom"] == src.id
    f.send("second")
    assert wait_until(lambda: f.status == "idle")
    assert "--fork-session" not in inits(tmp_path, fid)[-1]["argv"]
    again.shutdown()


def test_fork_rejects_a_source_that_never_ran_or_is_working(store):
    never = store.create("claude-fast")
    with pytest.raises(ValueError, match="never run"):
        store.fork(never, role_name="claude-default")
    busy = store.get(store.spawn("claude-fast", "slow reply"))
    assert wait_until(lambda: busy.status == "working")
    with pytest.raises(ValueError, match="working"):
        store.fork(busy.id, role_name="claude-default")
    with pytest.raises(KeyError):
        store.fork("ctx_nope", role_name="claude-default")
