"""harness.procs: one resolved bash for `checks`/`setup` on every platform (workspace spec §3.1), and the two
Claude Code variables that pin a Windows character to the same bash."""
import sys

import pytest

from harness import config as cfg
from harness import procs
from harness.procs import NoBash, bash_path, claude_shell_env, run_shell


def _which(table):
    return lambda name: table.get(name)


# ---------------------------------------------------------------- bash_path()

def test_config_override_wins_everywhere(monkeypatch):
    monkeypatch.setattr(cfg, "BASH_PATH", "/opt/mybash", raising=False)
    assert bash_path(nt=False, env={}, which=_which({})) == "/opt/mybash"
    assert bash_path(nt=True, env={}, which=_which({})) == "/opt/mybash"


def test_posix_uses_bash_on_path(monkeypatch):
    monkeypatch.setattr(cfg, "BASH_PATH", "", raising=False)
    assert bash_path(nt=False, env={}, which=_which({"bash": "/usr/bin/bash"})) == "/usr/bin/bash"


def test_posix_without_bash_raises(monkeypatch):
    monkeypatch.setattr(cfg, "BASH_PATH", "", raising=False)
    with pytest.raises(NoBash, match="bash"):
        bash_path(nt=False, env={}, which=_which({}))


def test_windows_ignores_bash_on_path_and_finds_git_bash_beside_git(tmp_path, monkeypatch):
    """System32's bash.exe is WSL: inside it the pipe and the Windows Python are unreachable. Git for Windows puts
    `cmd\\git.exe` and `bin\\bash.exe` under one install dir."""
    monkeypatch.setattr(cfg, "BASH_PATH", "", raising=False)
    git_exe = tmp_path / "Git" / "cmd" / "git.exe"
    git_bash = tmp_path / "Git" / "bin" / "bash.exe"
    for f in (git_exe, git_bash):
        f.parent.mkdir(parents=True, exist_ok=True); f.write_text("")
    which = _which({"git": str(git_exe), "bash": r"C:\Windows\System32\bash.exe"})
    assert bash_path(nt=True, env={}, which=which) == str(git_bash)


def test_windows_finds_git_bash_from_a_mingw_git_too(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "BASH_PATH", "", raising=False)
    git_exe = tmp_path / "Git" / "mingw64" / "bin" / "git.exe"
    git_bash = tmp_path / "Git" / "bin" / "bash.exe"
    for f in (git_exe, git_bash):
        f.parent.mkdir(parents=True, exist_ok=True); f.write_text("")
    assert bash_path(nt=True, env={}, which=_which({"git": str(git_exe)})) == str(git_bash)


def test_windows_env_var_wins_over_derivation(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "BASH_PATH", "", raising=False)
    env = {"CLAUDE_CODE_GIT_BASH_PATH": r"D:\tools\Git\bin\bash.exe"}
    assert bash_path(nt=True, env=env, which=_which({"git": str(tmp_path / "x" / "git.exe")})) == r"D:\tools\Git\bin\bash.exe"


def test_windows_falls_back_to_program_files(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "BASH_PATH", "", raising=False)
    git_bash = tmp_path / "Git" / "bin" / "bash.exe"
    git_bash.parent.mkdir(parents=True); git_bash.write_text("")
    assert bash_path(nt=True, env={"ProgramFiles": str(tmp_path)}, which=_which({})) == str(git_bash)


def test_windows_without_git_names_what_to_install(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "BASH_PATH", "", raising=False)
    with pytest.raises(NoBash, match="Git for Windows"):
        bash_path(nt=True, env={"ProgramFiles": str(tmp_path)}, which=_which({"bash": r"C:\Windows\System32\bash.exe"}))


# ---------------------------------------------------------------- run_shell()

def test_run_shell_runs_the_line_through_bash_path(tmp_path, monkeypatch):
    """Not `shell=True` (cmd.exe on Windows): the resolved interpreter, `-c`, the line."""
    monkeypatch.setattr(procs, "bash_path", lambda: sys.executable)
    assert run_shell("import sys; sys.stdout.write('fine')", str(tmp_path), 30) == (0, "fine")


def test_run_shell_speaks_bash_not_sh(tmp_path):
    (tmp_path / "ok.txt").write_text("")
    assert run_shell("[[ -f ok.txt ]] && echo fine", str(tmp_path), 30) == (0, "fine\n")


def test_run_shell_reports_no_bash(tmp_path, monkeypatch):
    def missing():
        raise NoBash("no bash: install Git for Windows")
    monkeypatch.setattr(procs, "bash_path", missing)
    with pytest.raises(NoBash):
        run_shell("echo hi", str(tmp_path), 30)


# ---------------------------------------------------------------- claude_shell_env()

def test_posix_character_gets_no_shell_pin():
    assert claude_shell_env(nt=False) == {}


def test_windows_character_is_pinned_to_git_bash_with_powershell_off(monkeypatch):
    monkeypatch.setattr(procs, "bash_path", lambda: r"C:\Program Files\Git\bin\bash.exe")
    assert claude_shell_env(nt=True) == {"CLAUDE_CODE_GIT_BASH_PATH": r"C:\Program Files\Git\bin\bash.exe",
                                         "CLAUDE_CODE_USE_POWERSHELL_TOOL": "0"}


def test_windows_character_still_spawns_without_bash(monkeypatch):
    """The spawn must not fail on a missing bash; the checks/setup path is where it is reported."""
    def missing():
        raise NoBash("no bash")
    monkeypatch.setattr(procs, "bash_path", missing)
    assert claude_shell_env(nt=True) == {}
