# tests/test_contexts_unit.py
"""Context lifecycle without the UI: a context must always settle and say why; bare contexts; env."""
import json
import os
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QTest

from harness import config as cfg
from harness.__main__ import ROOT
from harness.contexts import ContextStore, new_context_id
from harness.casting import CastStore

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
    s = ContextStore(ROOT, tmp_path / "contexts", CastStore(tmp_path), workspace_dir=tmp_path)
    yield s
    s.shutdown()


def test_ids_have_ctx_prefix():
    assert new_context_id().startswith("ctx_") and len(new_context_id()) == 14


def test_create_is_a_record_without_a_process(store, tmp_path):
    cid = store.create("friend", story_key="ZH-1", owner="chr1", title="hello", env={"HARNESS_CHARACTER_ID": "chr1"})
    c = store.get(cid)
    assert c.status == "idle" and c._proc is None and c.owner == "chr1" and c.storyKey == "ZH-1" and c.position == "friend"
    assert json.loads((tmp_path / "contexts" / "index.json").read_text())[0]["id"] == cid
    assert store.contexts_for("ZH-1") == [c] and store.contexts_for("ZH-2") == []
    assert store.model.rows()[0] == {**store.model.rows()[0], "id": cid, "owner": "chr1", "storyKey": "ZH-1", "status": "idle"}


def test_spawn_sends_env_and_settles(store, tmp_path):
    cid = store.spawn("friend", "hello agent", story_key="ZH-1", owner="chr1", env={"HARNESS_CHARACTER_ID": "chr1"})
    c = store.get(cid)
    assert wait_until(lambda: c.status == "idle"), (c.status, c.lastError)
    records = [json.loads(l) for l in (tmp_path / "contexts" / f"{cid}.jsonl").read_text().splitlines()]
    init = next(r for r in records if r.get("subtype") == "init")
    assert init["harness_env"] == {"HARNESS_CONTEXT_ID": cid, "HARNESS_STORY_KEY": "ZH-1", "HARNESS_CHARACTER_ID": "chr1",
                                   "HARNESS_WORKSPACE": str(tmp_path)}
    assert c.transcript.rows()[-1]["text"] == "echo: hello agent"


def test_create_stores_the_position_and_the_cast_it_resolved(store, tmp_path):
    cid = store.create("protagonist", model="claude-opus-5", effort="low", preset="builder")
    meta = store.get(cid).meta
    assert meta["position"] == "protagonist"
    assert meta["cast"] == CastStore(tmp_path).resolve("protagonist", "claude-opus-5", "low", "builder")
    assert "role" not in meta and "roleConfig" not in meta


def test_create_falls_back_to_the_positions_own_picks(store):
    cast = store.get(store.create("friend")).meta["cast"]
    pos = cfg.CAST_POSITIONS["friend"]
    assert (cast["model"], cast["effort"], cast["preset"]) == (pos["model"], pos["effort"], pos["preset"])


def test_the_model_property_falls_back_to_the_casts_model(store):
    assert store.get(store.create("friend", model="claude-opus-5")).model == "claude-opus-5"


def test_a_spawn_carries_the_casts_model_effort_and_plugin_dir(store, tmp_path):
    cid = store.spawn("friend", "hello", model="claude-opus-5", effort="xhigh", preset="builder")
    assert wait_until(lambda: store.get(cid).status == "idle")
    argv = inits(tmp_path, cid)[0]["argv"]
    assert argv[argv.index("--model") + 1] == "claude-opus-5"
    assert argv[argv.index("--effort") + 1] == "xhigh"
    plugin = Path(argv[argv.index("--plugin-dir") + 1])
    assert plugin == store.skills_cache / "builder"
    # The preset's own skills, plus the injected set every tree carries whatever the preset names (spec §5.1).
    from harness import skills
    assert sorted(d.name for d in (plugin / "skills").iterdir()) == sorted(
        set(cfg.DEFAULT_PRESETS[1]["skills"]) | skills.always_on())


def test_a_whole_tree_preset_spawns_on_the_source_skills_tree(store, tmp_path):
    from harness import skills
    cid = store.spawn("friend", "hello", preset="full")
    assert wait_until(lambda: store.get(cid).status == "idle")
    argv = inits(tmp_path, cid)[0]["argv"]
    assert Path(argv[argv.index("--plugin-dir") + 1]) == skills.skills_dir()
    assert "--effort" in argv and argv[argv.index("--effort") + 1] == cfg.CAST_POSITIONS["friend"]["effort"]


def test_the_skills_cache_sits_beside_the_contexts_dir(store, tmp_path):
    assert store.skills_cache == tmp_path / "skills"


def test_env_prepends_root_to_an_inherited_pythonpath(store, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/somewhere/else")
    c = store.get(store.create("friend"))
    pp = c._env()["PYTHONPATH"]
    assert pp.startswith(str(ROOT)) and pp.endswith("/somewhere/else") and pp == os.pathsep.join([str(ROOT), "/somewhere/else"])


def test_env_pythonpath_is_just_root_when_none_was_inherited(store, monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    c = store.get(store.create("friend"))
    assert c._env()["PYTHONPATH"] == str(ROOT)


def test_env_carries_the_character_shell_pin(store, monkeypatch):
    """On Windows the character's Claude Code is pinned to the harness's bash with the PowerShell tool off; the
    pin comes from procs.claude_shell_env so one function decides it for the checks and for the character."""
    import harness.contexts as contexts_mod
    pin = {"CLAUDE_CODE_GIT_BASH_PATH": r"X:\Git\bin\bash.exe", "CLAUDE_CODE_USE_POWERSHELL_TOOL": "0"}
    monkeypatch.setattr(contexts_mod, "claude_shell_env", lambda: dict(pin))
    c = store.get(store.create("friend"))
    env = c._env()
    assert {k: env.get(k) for k in pin} == pin


def test_new_bare_has_human_owner_and_no_story(store):
    cid = store.newBare("bare")
    c = store.get(cid)
    assert c.owner == "human" and c.storyKey == "" and c.title == "New context" and c.status == "idle"
    c.send("first message")
    assert wait_until(lambda: c.status == "idle")
    assert c.transcript.rows()[-1]["text"] == "echo: first message"


def test_new_bare_defaults_to_the_bare_position(store):
    cid = store.newBare("")
    assert store.get(cid).position == cfg.DEFAULT_BARE_POSITION


def test_new_bare_takes_the_three_picks(store):
    c = store.get(store.newBare("", "claude-opus-5", "low", "builder"))
    assert (c.meta["cast"]["model"], c.meta["cast"]["effort"], c.meta["cast"]["preset"]) == ("claude-opus-5", "low", "builder")


def test_unknown_position_and_unimplemented_provider_raise(store):
    with pytest.raises(ValueError, match="unknown position"):
        store.create("nope")
    with pytest.raises(ValueError, match="provider"):
        store.create("friend", model="gpt-5.6-sol")


def test_unstartable_cli_fails_the_context_with_a_visible_reason(store, monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", "/nonexistent/claude-nope")
    cid = store.spawn("friend", "hello")
    c = store.get(cid)
    assert wait_until(lambda: c.status == "failed"), c.status
    assert "claude-nope" in c.lastError and c.transcript.rows()[-1]["kind"] == "error"
    assert store.model.rows()[-1]["status"] == "failed"


def test_a_cli_that_fails_to_start_synchronously_still_fails_the_context(store, monkeypatch):
    """On Windows QProcess reports FailedToStart from inside start(), so finished() has already run — and dropped
    the process — before send() gets to write the prompt. Linux delivers it later; the outcome must be the same."""
    from PySide6.QtCore import QProcess
    from harness.agents import ClaudeCodeProcess
    monkeypatch.setattr(ClaudeCodeProcess, "start", lambda self: self._on_error(QProcess.ProcessError.FailedToStart))
    cid = store.spawn("friend", "hello")
    c = store.get(cid)
    assert c.status == "failed" and "failed to start" in c.lastError, (c.status, c.lastError)
    assert c.transcript.rows()[-1]["kind"] == "error"


def test_send_on_a_failed_context_retries_by_spawning_again(store, monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", "/nonexistent/claude-nope")
    cid = store.spawn("friend", "hello")
    c = store.get(cid)
    assert wait_until(lambda: c.status == "failed")
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", FAKE)
    c.send("again")
    assert wait_until(lambda: c.status == "idle"), (c.status, c.lastError)
    assert c.transcript.rows()[-1]["text"] == "echo: again" and c.lastError == ""


def test_settled_signal_fires_once_per_settle(store):
    seen = []
    store.contextSettled.connect(seen.append)
    cid = store.spawn("friend", "hi")
    assert wait_until(lambda: seen == [cid])
    store.get(cid).send("more")
    assert wait_until(lambda: seen == [cid, cid])


def test_transcripts_persist_and_replay(store, tmp_path):
    cid = store.spawn("friend", "persist me", story_key="ZH-3", owner="chr9")
    assert wait_until(lambda: store.get(cid).status == "idle")
    fresh = ContextStore(ROOT, tmp_path / "contexts", CastStore(tmp_path), workspace_dir=tmp_path)
    c = fresh.get(cid)
    assert c.owner == "chr9" and c.storyKey == "ZH-3" and c.status == "idle"
    assert [(r["role"], r["text"]) for r in c.transcript.rows()] == [("user", "persist me"), ("assistant", "echo: persist me")]


def inits(tmp_path, cid):
    return [json.loads(l) for l in (tmp_path / "contexts" / f"{cid}.jsonl").read_text().splitlines() if '"init"' in l]


def test_fork_resumes_the_source_once_then_runs_on_its_own_session(store, tmp_path):
    src = store.get(store.spawn("friend", "hello", story_key="ZH-1", owner="chr1", env={"HARNESS_CHARACTER_ID": "chr1"}))
    assert wait_until(lambda: src.status == "idle") and src.sessionId == "fake-session-1"
    fid = store.fork(src.id, position="bare", title="aside", system_prompt="you are an aside",
                     about={"story_key": "ZH-1", "comment_id": "cmt_1"})
    f = store.get(fid)
    assert (f.meta["forkedFrom"], f.meta["forkSession"], f.owner, f.storyKey, f.position) == (src.id, "fake-session-1", "human", "", "bare")
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
    src = store.get(store.spawn("friend", "hello"))
    assert wait_until(lambda: src.status == "idle")
    fid = store.fork(src.id, position="bare")
    store.get(fid).send("first")
    assert wait_until(lambda: store.get(fid).status == "idle")
    store.shutdown()
    again = ContextStore(ROOT, tmp_path / "contexts", CastStore(tmp_path), workspace_dir=tmp_path)
    f = again.get(fid)
    assert f.sessionId == "fork-of-fake-session-1" and f.meta["forkedFrom"] == src.id
    f.send("second")
    assert wait_until(lambda: f.status == "idle")
    assert "--fork-session" not in inits(tmp_path, fid)[-1]["argv"]
    again.shutdown()


def test_fork_rejects_a_source_that_never_ran_or_is_working(store):
    never = store.create("friend")
    with pytest.raises(ValueError, match="never run"):
        store.fork(never, position="bare")
    busy = store.get(store.spawn("friend", "slow reply"))
    assert wait_until(lambda: busy.status == "working")
    with pytest.raises(ValueError, match="working"):
        store.fork(busy.id, position="bare")
    with pytest.raises(KeyError):
        store.fork("ctx_nope", position="bare")


def test_a_result_is_not_a_turn_end_while_a_pushed_message_is_unechoed(store):
    settled = []
    store.contextSettled.connect(settled.append)
    c = store.get(store.spawn("friend", "slow one"))
    assert wait_until(lambda: c.status == "working")
    c.send("two")                                  # pushed mid-turn; the fake echoes it only when it reads it
    assert c._unacked in (1, 2)                     # "slow one" may or may not be echoed yet
    assert wait_until(lambda: c.turns == 2 and c.status == "idle", timeout_ms=8000), (c.turns, c.status)
    assert settled == [c.id]                       # one settle for two results: the first was not a turn end
    assert [r["text"] for r in c.transcript.rows() if r["role"] == "user"] == ["slow one", "two"]   # no double rows
    assert c._unacked == 0


def test_a_stop_settles_regardless_of_unechoed_pushes(store):
    c = store.get(store.spawn("friend", "slow one"))
    assert wait_until(lambda: c.status == "working")
    c.send("never echoed")
    c.stop()
    assert wait_until(lambda: c.status == "stopped") and c._unacked == 0


def test_placement_decides_cwd_and_extra_env_at_every_spawn(store, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    target = {"cwd": str(a)}
    store.placement = lambda c: (target["cwd"], {"HARNESS_REPO": "r", "HARNESS_ENV": target["cwd"]})
    cid = store.spawn("friend", "hello")
    c = store.get(cid)
    assert wait_until(lambda: c.status == "idle"), c.lastError
    assert c.proc_cwd == str(a)
    init = next(r for r in (json.loads(l) for l in (store.data_dir / f"{cid}.jsonl").read_text().splitlines()) if r.get("subtype") == "init")
    assert Path(init["cwd"]).resolve() == a.resolve() and init["harness_env"]["HARNESS_REPO"] == "r" and init["harness_env"]["HARNESS_ENV"] == str(a)
    target["cwd"] = str(b)
    c.send("again")                      # same process: cwd unchanged until recycled
    assert wait_until(lambda: c.status == "idle")
    assert c.proc_cwd == str(a)
    c.recycle()
    assert c.proc_cwd is None and c.status == "idle"
    c.send("after recycle")
    assert wait_until(lambda: c.status == "idle")
    assert c.proc_cwd == str(b)
    inits = [r for r in (json.loads(l) for l in (store.data_dir / f"{cid}.jsonl").read_text().splitlines()) if r.get("subtype") == "init"]
    assert len(inits) == 2 and Path(inits[-1]["cwd"]).resolve() == b.resolve()
    assert "--resume" in inits[-1]["argv"]   # the session carried over


def test_recycle_is_a_no_op_while_working(store):
    cid = store.spawn("friend", "slow please")
    c = store.get(cid)
    assert c.status in ("starting", "working")
    proc = c._proc
    c.recycle()
    assert c._proc is proc
    assert wait_until(lambda: c.status == "idle")


def test_recycle_releases_the_old_process_without_blocking(store):
    cid = store.spawn("friend", "hello")
    c = store.get(cid)
    assert wait_until(lambda: c.status == "idle")
    t0 = time.monotonic()
    c.recycle()
    assert time.monotonic() - t0 < 0.5
    assert len(c._retired) == 1
    assert wait_until(lambda: not any(p.running() for p in c._retired), timeout_ms=5000)
    assert wait_until(lambda: c._retired == [])


class _FakeDeadProc(QObject):
    """A process double that has already exited: `running()` is False and `finished` never fires again."""
    event = Signal(object)
    stderrText = Signal(str)
    finished = Signal(int, str)

    def running(self):
        return False

    def release(self):
        pass


def test_recycle_does_not_retire_a_process_that_already_finished(store):
    """M1: only a still-running process needs to be kept referenced until its `finished` fires — a dead one
    (finished already fired, or never fires again) must not be appended, or it would sit in _retired forever."""
    cid = store.create("friend", title="t")
    c = store.get(cid)
    c._status = "idle"
    fake = _FakeDeadProc()
    fake.event.connect(c._on_event)
    fake.stderrText.connect(c._on_stderr)
    fake.finished.connect(c._on_finished)
    c._proc = fake
    c.recycle()
    assert c._proc is None and c._retired == []


def test_spawn_passes_the_skills_plugin_and_the_fake_echoes_the_prompt(store, tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_SKILLS_DIR", str(tmp_path / "plug"))
    cid = store.spawn("friend", "hello", preset="full", story_key="ZH-1", owner="chr1")
    c = store.get(cid)
    assert wait_until(lambda: c.status == "idle"), (c.status, c.lastError)
    init = inits(tmp_path, cid)[-1]
    assert init["argv"][init["argv"].index("--plugin-dir") + 1] == str(tmp_path / "plug")
    assert init["system_prompt"].startswith("You are a bare context")     # no StoryStore here: the hook returns None


def test_system_prompt_hook_replaces_the_stored_prompt_at_spawn(store, tmp_path):
    store.system_prompt = lambda c: "COMPOSED for " + c.id
    cid = store.spawn("friend", "hello", system_prompt="stored")
    c = store.get(cid)
    assert wait_until(lambda: c.status == "idle"), (c.status, c.lastError)
    assert inits(tmp_path, cid)[-1]["system_prompt"] == "COMPOSED for " + cid


# --------------------------------------------------------------------------- context usage (lifecycle spec §2.3)
def test_every_spawn_turns_the_clis_auto_compaction_off(store, tmp_path):
    cid = store.spawn("friend", "hello")
    assert wait_until(lambda: store.get(cid).status == "idle")
    assert inits(tmp_path, cid)[0]["auto_compact_disabled"] is True
    bare = store.get(store.newBare("bare"))
    assert bare._env()["DISABLE_AUTO_COMPACT"] == "1"


def test_usage_reaches_the_context_its_row_and_a_signal(store):
    seen = []
    store.contextUsage.connect(seen.append)
    cid = store.spawn("friend", "hello tokens=4321")
    c = store.get(cid)
    assert wait_until(lambda: c.status == "idle"), (c.status, c.lastError)
    assert c.contextTokens == 4331 and c.contextWindow == 1000000      # 10 input + 4321 cached
    assert cid in seen
    row = next(r for r in store.model.rows() if r["id"] == cid)
    assert row["contextTokens"] == 4331 and row["contextWindow"] == 1000000
    assert c.summary()["contextTokens"] == 4331
    assert (row["contextWarn"], row["contextMax"]) == (c.contextWarn, c.contextMax) == (300_000, 500_000)   # the meter's frame


def test_the_warn_and_max_lines_scale_to_a_smaller_window():
    from harness.contexts import context_lines
    assert context_lines(1_000_000) == (300_000, 500_000)
    assert context_lines(200_000) == (60_000, 100_000)
    assert context_lines(0) == (300_000, 500_000)          # unknown window: the 1M lines
    assert context_lines(2_000_000) == (300_000, 500_000)  # a bigger window does not move them


def test_usage_survives_a_restart_through_replay(store, tmp_path):
    cid = store.spawn("friend", "hello tokens=4321")
    assert wait_until(lambda: store.get(cid).status == "idle")
    fresh = ContextStore(ROOT, tmp_path / "contexts", CastStore(tmp_path), workspace_dir=tmp_path)
    assert fresh.get(cid).contextTokens == 4331 and fresh.get(cid).contextWindow == 1000000


def test_a_fork_starts_with_its_sources_reading_and_keeps_it_across_a_restart(store, tmp_path):
    src = store.get(store.spawn("friend", "hello tokens=4321"))
    assert wait_until(lambda: src.status == "idle")
    fid = store.fork(src.id, position="bare")
    f = store.get(fid)
    assert f.contextTokens == 4331 and f.contextWindow == 1000000 and f._proc is None
    fresh = ContextStore(ROOT, tmp_path / "contexts", CastStore(tmp_path), workspace_dir=tmp_path)
    assert fresh.get(fid).contextTokens == 4331
    f.send("what was said?")                  # its own first call replaces the seed with a real reading
    assert wait_until(lambda: f.status == "idle"), (f.status, f.lastError)
    assert f.contextTokens == 1010


def test_a_recast_successor_starts_at_zero(store):
    cid = store.create("friend", predecessor="ctx_old")
    assert store.get(cid).contextTokens == 0 and store.get(cid).contextWindow == 0
