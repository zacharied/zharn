"""Contexts, roles, tasks, IPC/CLI and the context UI — against the fake claude CLI."""
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
WS = OUT / "agents-ws"


def wait_until(cond, timeout_ms=8000, step=25):
    t0 = time.time()
    while time.time() - t0 < timeout_ms / 1000:
        QTest.qWait(step)
        if cond():
            return True
    return False


@pytest.fixture(scope="module")
def harness():
    shutil.rmtree(WS, ignore_errors=True)
    os.environ["HARNESS_WORKSPACE"] = str(WS)
    os.environ["HARNESS_SESSION"] = str(OUT / "agents-session.json")
    os.environ["HARNESS_CLAUDE_CMD"] = f"{sys.executable} {ROOT / 'tests' / 'fake_claude.py'}"
    (OUT / "agents-session.json").unlink(missing_ok=True)
    app, store, reloader = build(force_poll=True)
    assert reloader.load(), store.reloadError
    QTest.qWait(100)
    yield app, store, reloader
    store.contexts.shutdown()
    reloader.shutdown()
    QTest.qWait(50)


def rows(context):
    return context.transcript.rows()


def test_roles_and_demo_tasks(harness):
    app, store, _ = harness
    names = store.roles.names()
    assert "claude-fast" in names and "codex-review" in names
    assert store.roles.get("claude-deep")["model"] == "claude-opus-5"
    assert store.tasks.model.count() >= 5
    assert store.tasks.get("ABC-1")["title"].startswith("Hot reload")
    with pytest.raises(ValueError):
        store.contexts.spawn("codex-review", "x", story_key="ABC-1")


def test_spawn_streams_and_settles(harness):
    app, store, _ = harness
    cid = store.contexts.spawn("claude-fast", "hello agent", story_key="ABC-1")
    c = store.contexts.get(cid)
    assert c.status in ("starting", "working")
    assert wait_until(lambda: c.status == "idle"), (c.status, c.lastError)
    kinds = [(r["role"], r["kind"]) for r in rows(c)]
    assert kinds == [("user", "text"), ("assistant", "text")]
    assert rows(c)[1]["text"] == "echo: hello agent" and not rows(c)[1]["streaming"]
    assert c.sessionId == "fake-session-1" and c.model == "fake-model"
    assert abs(c.costUsd - 0.0123) < 1e-6 and c.turns == 1
    # child process got the harness env
    records = [json.loads(l) for l in (store.contexts.data_dir / f"{cid}.jsonl").read_text().splitlines()]
    assert [r["type"] for r in records[:3]] == ["harness.meta", "harness.user", "system"]
    init = records[2]
    assert init["harness_env"]["HARNESS_CONTEXT_ID"] == cid
    assert init["harness_env"]["HARNESS_STORY_KEY"] == "ABC-1"
    assert init["harness_env"]["HARNESS_WORKSPACE"] == store.workspaceDir
    # summary row in the list model
    assert any(r["id"] == cid and r["status"] == "idle" for r in store.contexts.model.rows())


def test_follow_up_reuses_process_and_tools_render(harness):
    app, store, _ = harness
    c = store.contexts.get(store.contexts.model.rows()[0]["id"])
    proc = c._proc
    c.send("please use a tool")
    assert c.status == "working"
    assert wait_until(lambda: c.status == "idle")
    assert c._proc is proc, "follow-up should go over stdin to the same process"
    kinds = [(r["role"], r["kind"]) for r in rows(c)]
    assert kinds[-4:] == [("user", "text"), ("assistant", "tool_use"), ("tool", "tool_result"), ("assistant", "text")]
    tool = rows(c)[-3]
    assert tool["name"] == "Bash" and json.loads(tool["input"])["command"] == "echo hello-from-tool"
    assert rows(c)[-2]["text"] == "hello-from-tool"
    assert abs(c.costUsd - 0.0246) < 1e-6


def test_failure_is_surfaced(harness):
    app, store, _ = harness
    cid = store.contexts.spawn("claude-fast", "please fail", story_key="ABC-2")
    c = store.contexts.get(cid)
    assert wait_until(lambda: c.status == "failed")
    assert rows(c)[-1]["kind"] == "error" and "simulated failure" in rows(c)[-1]["text"]


def test_task_dispatch_sets_in_progress_and_counts(harness):
    app, store, _ = harness
    assert store.tasks.get("ABC-3")["status"] == "todo"
    cid = store.tasks.dispatch("ABC-3", "claude-fast", "do the thing")
    c = store.contexts.get(cid)
    assert store.tasks.get("ABC-3")["status"] == "in_progress"
    assert c.title == "do the thing"
    assert rows(c)[0]["text"].startswith("# Task ABC-3") and "Report-back contract" in rows(c)[0]["text"]
    assert wait_until(lambda: c.status == "idle")
    assert store.tasks.get("ABC-3")["contextCount"] == 1 and store.tasks.get("ABC-3")["workingCount"] == 0


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
    assert json.loads(r.stdout)["contexts"][0]["status"] == "idle"
    r = cli("context", "list", "--story", "ABC-3")
    assert len(json.loads(r.stdout)) == 1


def test_transcripts_persist_and_replay(harness):
    app, store, _ = harness
    from harness.contexts import ContextStore
    fresh = ContextStore(ROOT, store.contexts.data_dir, store.roles, workspace_dir=store.contexts.workspace_dir)
    ids = {c.id for c in store.contexts.all()}
    assert {c.id for c in fresh.all()} == ids
    for c in fresh.all():
        live = store.contexts.get(c.id)
        assert [(r["role"], r["kind"], r["text"]) for r in rows(c)] == [(r["role"], r["kind"], r["text"]) for r in rows(live)]
        assert c.status in ("idle", "failed") and c.costUsd == live.costUsd


def test_context_tab_renders_and_screenshot(harness):
    app, store, reloader = harness
    from test_app import find_all, root
    c = store.contexts.get(store.contexts.model.rows()[0]["id"])
    store.layout.openContent("task", "ABC-1", "ABC-1")
    store.layout.openContent("context", c.id, c.title)
    QTest.qWait(300)
    win = root(reloader)
    win.setWidth(1400); win.setHeight(900)
    lists = find_all(win, "transcript")
    assert lists and lists[0].property("count") == c.transcript.count()
    QTest.qWait(300)
    img = win.grabWindow()
    assert img.save(str(OUT / "context.png"))
    # send from the UI path
    c.send("from the ui")
    assert wait_until(lambda: c.status == "idle")
    assert rows(c)[-1]["text"] == "echo: from the ui"
    assert wait_until(lambda: lists[0].property("count") == c.transcript.count())


def test_story_start_yield_over_cli_and_reply(harness):
    app, store, _ = harness
    key = store.stories.create("E2E", "end to end")
    chr_id = store.stories.start(key, "yield-question", "protagonist")
    ch = store.stories.character(chr_id)
    ctx = store.contexts.get(ch["live_context"])
    assert ctx.owner == chr_id and ctx.storyKey == key
    assert wait_until(lambda: store.stories.get(key)["ball"] == "author", timeout_ms=15000), store.stories.get(key)
    q = store.stories.comments(key)[-1]
    assert q["kind"] == "question" and q["structured"]["options"] == ["a", "b"] and q["authorName"] == "protagonist"
    assert store.stories.get(key)["flavor"] == "question" and store.notify.status == f"{key} needs you: question"
    assert store.stories.character(chr_id)["verbs_log"][-1]["verb"] == "yield"
    assert wait_until(lambda: ctx.status == "idle", timeout_ms=15000)
    store.stories.comment(key, "a")
    assert store.stories.get(key)["ball"] == "cast"
    assert wait_until(lambda: ctx.status == "idle" and rows(ctx)[-1]["role"] == "assistant", timeout_ms=15000)
    assert rows(ctx)[-1]["text"].startswith("echo: ")
    assert "[you] reply in #thr_" in rows(ctx)[-2]["text"]


def test_cli_story_show_over_ipc(harness):
    app, store, _ = harness
    key = store.stories.list()[-1]["key"]
    env = {**os.environ, "HARNESS_IPC": store.ipcPath}
    p = subprocess.Popen([sys.executable, "-m", "harness.cli", "--json", "story", "show", key], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, env=env, cwd=ROOT)
    assert wait_until(lambda: p.poll() is not None, timeout_ms=30000)
    out, err = p.communicate()
    assert p.returncode == 0, err
    data = json.loads(out)
    assert data["key"] == key and data["comments"] and data["cast"][0]["name"] == "protagonist" and data["contexts"]
