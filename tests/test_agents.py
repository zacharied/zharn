"""Threads, roles, tasks, IPC/CLI and the thread UI — against the fake claude CLI."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtTest import QTest

from harness.__main__ import ROOT, build

OUT = ROOT / "tests" / "_out"
DATA = OUT / "agents-data"


def wait_until(cond, timeout_ms=8000, step=25):
    t0 = time.time()
    while time.time() - t0 < timeout_ms / 1000:
        QTest.qWait(step)
        if cond():
            return True
    return False


@pytest.fixture(scope="module")
def harness():
    shutil.rmtree(DATA, ignore_errors=True)
    os.environ["HARNESS_DATA_DIR"] = str(DATA)
    os.environ["HARNESS_SESSION"] = str(OUT / "agents-session.json")
    os.environ["HARNESS_CLAUDE_CMD"] = f"{sys.executable} {ROOT / 'tests' / 'fake_claude.py'}"
    (OUT / "agents-session.json").unlink(missing_ok=True)
    app, store, reloader = build(force_poll=True)
    assert reloader.load(), store.reloadError
    QTest.qWait(100)
    yield app, store, reloader
    store.threads.shutdown()
    reloader.shutdown()
    QTest.qWait(50)


def rows(thread):
    return thread.transcript.rows()


def test_roles_and_demo_tasks(harness):
    app, store, _ = harness
    names = store.roles.names()
    assert "claude-fast" in names and "codex-review" in names
    assert store.roles.get("claude-deep")["model"] == "claude-opus-5"
    assert store.tasks.model.count() >= 5
    assert store.tasks.get("ABC-1")["title"].startswith("Hot reload")
    with pytest.raises(ValueError):
        store.threads.spawn("ABC-1", "codex-review", "x")


def test_spawn_streams_and_settles(harness):
    app, store, _ = harness
    tid = store.threads.spawn("ABC-1", "claude-fast", "hello agent")
    t = store.threads.get(tid)
    assert t.status in ("starting", "working")
    assert wait_until(lambda: t.status == "idle"), (t.status, t.lastError)
    kinds = [(r["role"], r["kind"]) for r in rows(t)]
    assert kinds == [("user", "text"), ("assistant", "text")]
    assert rows(t)[1]["text"] == "echo: hello agent" and not rows(t)[1]["streaming"]
    assert t.sessionId == "fake-session-1" and t.model == "fake-model"
    assert abs(t.costUsd - 0.0123) < 1e-6 and t.turns == 1
    # child process got the harness env
    records = [json.loads(l) for l in (DATA / "threads" / f"{tid}.jsonl").read_text().splitlines()]
    assert [r["type"] for r in records[:3]] == ["harness.meta", "harness.user", "system"]
    init = records[2]
    assert init["harness_env"]["HARNESS_THREAD_ID"] == tid
    assert init["harness_env"]["HARNESS_TASK_KEY"] == "ABC-1"
    assert init["harness_env"]["HARNESS_IPC"] == store.ipcPath != ""
    # summary row in the list model
    assert any(r["id"] == tid and r["status"] == "idle" for r in store.threads.model.rows())


def test_follow_up_reuses_process_and_tools_render(harness):
    app, store, _ = harness
    t = store.threads.get(store.threads.model.rows()[0]["id"])
    proc = t._proc
    t.send("please use a tool")
    assert t.status == "working"
    assert wait_until(lambda: t.status == "idle")
    assert t._proc is proc, "follow-up should go over stdin to the same process"
    kinds = [(r["role"], r["kind"]) for r in rows(t)]
    assert kinds[-4:] == [("user", "text"), ("assistant", "tool_use"), ("tool", "tool_result"), ("assistant", "text")]
    tool = rows(t)[-3]
    assert tool["name"] == "Bash" and json.loads(tool["input"])["command"] == "echo hello-from-tool"
    assert rows(t)[-2]["text"] == "hello-from-tool"
    assert abs(t.costUsd - 0.0246) < 1e-6


def test_failure_is_surfaced(harness):
    app, store, _ = harness
    tid = store.threads.spawn("ABC-2", "claude-fast", "please fail")
    t = store.threads.get(tid)
    assert wait_until(lambda: t.status == "failed")
    assert rows(t)[-1]["kind"] == "error" and "simulated failure" in rows(t)[-1]["text"]


def test_task_dispatch_sets_in_progress_and_counts(harness):
    app, store, _ = harness
    assert store.tasks.get("ABC-3")["status"] == "todo"
    tid = store.tasks.dispatch("ABC-3", "claude-fast", "do the thing")
    t = store.threads.get(tid)
    assert store.tasks.get("ABC-3")["status"] == "in_progress"
    assert t.title == "do the thing"
    assert rows(t)[0]["text"].startswith("# Task ABC-3") and "Report-back contract" in rows(t)[0]["text"]
    assert wait_until(lambda: t.status == "idle")
    assert store.tasks.get("ABC-3")["threadCount"] == 1 and store.tasks.get("ABC-3")["workingCount"] == 0


def test_cli_over_ipc(harness):
    app, store, _ = harness
    env = {**os.environ, "HARNESS_IPC": store.ipcPath}
    def cli(*args):
        # Popen + pump the Qt loop: the IPC server lives in this process and needs the event loop running
        p = subprocess.Popen([sys.executable, "-m", "harness.cli", "--json", *args], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=env, cwd=ROOT)
        assert wait_until(lambda: p.poll() is not None, timeout_ms=30000), "cli did not finish"
        out, err = p.communicate()
        p.returncode = p.returncode
        return subprocess.CompletedProcess(p.args, p.returncode, out, err)
    r = cli("ping")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["pid"] == os.getpid()
    r = cli("role", "list")
    assert "claude-fast" in [p["name"] for p in json.loads(r.stdout)]
    r = cli("task", "show", "ABC-3")
    assert json.loads(r.stdout)["threads"][0]["status"] == "idle"
    r = cli("thread", "list", "--task", "ABC-3")
    assert len(json.loads(r.stdout)) == 1


def test_agent_spawns_child_on_same_task_and_parent_is_notified(harness):
    """The fake agent shells out to $HARNESS_CLI to spawn+wait a sibling — the real delegation path."""
    app, store, _ = harness
    tid = store.tasks.dispatch("ABC-4", "claude-deep", "spawn-child then report")
    parent = store.threads.get(tid)
    assert wait_until(lambda: len(store.threads.threads_for("ABC-4")) == 2, timeout_ms=15000)
    child = [x for x in store.threads.threads_for("ABC-4") if x.id != tid][0]
    assert child.parentId == tid and child.taskKey == "ABC-4" and child.roleName == "claude-fast"
    assert wait_until(lambda: child.status == "idle", timeout_ms=15000)
    # the parent's tool_result contains the child's last reply (via `thread spawn --wait`)
    assert wait_until(lambda: parent.status == "idle" and any(r["kind"] == "tool_result" for r in rows(parent)), timeout_ms=15000)
    tool_result = [r for r in rows(parent) if r["kind"] == "tool_result"][0]
    assert "echo: child says hi" in tool_result["text"], tool_result
    # the parent transcript got the lifecycle note; no follow-up turn because the parent was busy (--wait)
    assert wait_until(lambda: any(r["kind"] == "note" and child.id in r["text"] for r in rows(parent)))
    assert wait_until(lambda: parent.status == "idle" and rows(parent)[-1]["role"] == "assistant", timeout_ms=15000)
    assert not any(r["role"] == "user" and r["text"].startswith("[harness] child thread") for r in rows(parent))
    # fire-and-forget child while the parent is idle → parent is re-prompted with the child's outcome
    cid = store.threads.spawn("ABC-4", "claude-fast", "background helper", tid)
    child2 = store.threads.get(cid)
    assert wait_until(lambda: child2.status == "idle")
    assert wait_until(lambda: any(r["role"] == "user" and r["text"].startswith("[harness] child thread " + cid) for r in rows(parent)))
    assert wait_until(lambda: parent.status == "idle" and rows(parent)[-1]["role"] == "assistant")
    assert rows(parent)[-1]["text"].startswith("echo: [harness] child thread")


def test_transcripts_persist_and_replay(harness):
    app, store, _ = harness
    from harness.threads import ThreadStore
    fresh = ThreadStore(ROOT, DATA, store.roles)
    ids = {t.id for t in store.threads.all()}
    assert {t.id for t in fresh.all()} == ids
    for t in fresh.all():
        live = store.threads.get(t.id)
        assert [(r["role"], r["kind"], r["text"]) for r in rows(t)] == [(r["role"], r["kind"], r["text"]) for r in rows(live)]
        assert t.status in ("idle", "failed") and t.costUsd == live.costUsd


def test_thread_tab_renders_and_screenshot(harness):
    app, store, reloader = harness
    from test_app import find_all, root
    t = store.threads.get(store.threads.model.rows()[0]["id"])
    store.layout.openContent("task", "ABC-1", "ABC-1")
    store.layout.openContent("thread", t.id, t.title)
    QTest.qWait(300)
    win = root(reloader)
    win.setWidth(1400); win.setHeight(900)
    lists = find_all(win, "transcript")
    assert lists and lists[0].property("count") == t.transcript.count()
    QTest.qWait(300)
    img = win.grabWindow()
    assert img.save(str(OUT / "thread.png"))
    # send from the UI path
    t.send("from the ui")
    assert wait_until(lambda: t.status == "idle")
    assert rows(t)[-1]["text"] == "echo: from the ui"
    assert wait_until(lambda: lists[0].property("count") == t.transcript.count())
