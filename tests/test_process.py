"""ClaudeCodeProcess: the child process wrapper must never leave a thread hanging."""
import os
import stat
import sys
import time

import pytest

from PySide6.QtTest import QTest

from harness.agents import ClaudeCodeProcess, claude_command




def wait_until(cond, timeout_ms=3000, step=20):
    t0 = time.time()
    while time.time() - t0 < timeout_ms / 1000:
        QTest.qWait(step)
        if cond():
            return True
    return False


def test_missing_program_finishes_with_failure_naming_it(monkeypatch):
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", "/nonexistent/claude-nope")
    p = ClaudeCodeProcess(cwd=os.getcwd(), env={})
    done, errs = [], []
    p.finished.connect(lambda code, status: done.append((code, status)))
    p.stderrText.connect(errs.append)
    p.start()
    assert wait_until(lambda: bool(done)), "finished was never emitted"
    assert done[0][0] != 0
    assert any("claude-nope" in e for e in errs), errs
    assert not p.running()


def test_program_on_path_is_resolved_to_absolute(tmp_path, monkeypatch):
    if os.name == "nt":
        exe = tmp_path / "fakeclaude.bat"   # PATHEXT: `fakeclaude` resolves to it, as `claude` resolves to npm's claude.cmd
        exe.write_text("@exit /b 0\n")
    else:
        exe = tmp_path / "fakeclaude"
        exe.write_text("#!/bin/sh\nexit 0\n")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("HARNESS_CLAUDE_CMD", "fakeclaude --flag")
    assert claude_command() == ["fakeclaude", "--flag"]
    p = ClaudeCodeProcess(cwd=os.getcwd(), env={})
    assert os.path.normcase(p.program) == os.path.normcase(str(exe))   # Windows resolves via PATHEXT, which is upper-case
    assert p.args[0] == "--flag"


def test_child_harness_vars_come_only_from_env_not_inheritance(monkeypatch):
    # Spawning inside a character must not hand the child the *spawner's* identity: _env() is the
    # only source of a child's HARNESS_*, the way CLAUDECODE is dropped so claude can nest.
    monkeypatch.setenv("HARNESS_CHARACTER_ID", "chr_outer")
    monkeypatch.setenv("HARNESS_REPO", "outer-repo")
    p = ClaudeCodeProcess(cwd=os.getcwd(), env={"HARNESS_CONTEXT_ID": "ctx_inner"})
    penv = p.proc.processEnvironment()
    assert penv.value("HARNESS_CONTEXT_ID") == "ctx_inner", "what _env() passes must reach the child"
    assert not penv.contains("HARNESS_CHARACTER_ID"), "the spawner's character leaked into the child"
    assert not penv.contains("HARNESS_REPO"), "the spawner's repo leaked into the child"
    assert penv.contains("PATH"), "only HARNESS_* is dropped, not the whole environment"
