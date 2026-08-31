"""Thread lifecycle without the UI: a thread must always settle, and say why."""
import shutil
import sys
import time

import pytest

from PySide6.QtTest import QTest

from harness.__main__ import ROOT
from harness.roles import RoleStore
from harness.threads import ThreadStore


OUT = ROOT / "tests" / "_out"


def wait_until(cond, timeout_ms=5000, step=20):
    t0 = time.time()
    while time.time() - t0 < timeout_ms / 1000:
        QTest.qWait(step)
        if cond():
            return True
    return False


@pytest.fixture
def store(tmp_path):
    s = ThreadStore(ROOT, tmp_path, RoleStore(tmp_path))
    yield s
    s.shutdown()


def test_unstartable_cli_fails_the_thread_with_a_visible_reason(store, monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", "/nonexistent/claude-nope")
    tid = store.spawn("ABC-1", "claude-fast", "hello")
    t = store.get(tid)
    assert wait_until(lambda: t.status == "failed"), t.status
    assert "claude-nope" in t.lastError
    last = t.transcript.rows()[-1]
    assert last["kind"] == "error" and "claude-nope" in last["text"]
    assert store.model.rows()[-1]["status"] == "failed"


def test_send_on_a_failed_thread_retries_by_spawning_again(store, monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", "/nonexistent/claude-nope")
    tid = store.spawn("ABC-1", "claude-fast", "hello")
    t = store.get(tid)
    assert wait_until(lambda: t.status == "failed")
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", f"{sys.executable} {ROOT / 'tests' / 'fake_claude.py'}")
    t.send("again")
    assert wait_until(lambda: t.status == "idle"), (t.status, t.lastError)
    assert t.transcript.rows()[-1]["text"] == "echo: again"
    assert t.lastError == ""
