"""One bash for a repo's `checks` / `setup` line on every platform (workspace spec §3.1), run under a hard timeout
that takes the whole process tree down. Killing only the shell leaves its children holding the output pipe, and the
`communicate()` after it then waits on them — forever, for a hung test runner. POSIX has process groups for this;
Windows has `taskkill /T`.

Stdlib only: `harness.cli` imports this from inside a character."""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Callable, Mapping


class NoBash(RuntimeError):
    """No bash to run a line in; the message names what to install or set."""


def _config():
    try:
        from harness import config
    except ImportError:   # the user's config.py is written on the app's first run; the CLI may run before it exists
        return None
    return config


def bash_path(nt: bool | None = None, env: Mapping[str, str] | None = None,
              which: Callable[[str], str | None] = shutil.which) -> str:
    """`config.BASH_PATH` if set. POSIX: `bash` on PATH. Windows: `CLAUDE_CODE_GIT_BASH_PATH`, else Git for Windows'
    `bin\\bash.exe` beside the `git` on PATH (`cmd\\git.exe` or `mingw64\\bin\\git.exe`), else under %ProgramFiles%.
    Never `bash` on the Windows PATH: System32's bash.exe is WSL, where the pipe and the Windows Python are unreachable."""
    nt = os.name == "nt" if nt is None else nt
    env = os.environ if env is None else env
    override = getattr(_config(), "BASH_PATH", "")
    if override:
        return override
    if not nt:
        found = which("bash")
        if found:
            return found
        raise NoBash("bash not found on PATH; a repo's checks and setup are bash lines (config.BASH_PATH points at one)")
    pinned = env.get("CLAUDE_CODE_GIT_BASH_PATH")
    if pinned:
        return pinned
    git = which("git")
    if git:
        for install in list(Path(git).parents)[:3]:
            candidate = install / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
    candidate = Path(env.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
    if candidate.is_file():
        return str(candidate)
    raise NoBash("Git Bash not found: install Git for Windows — a repo's checks and setup are bash lines "
                 "(CLAUDE_CODE_GIT_BASH_PATH or config.BASH_PATH points at bash.exe)")


def claude_shell_env(nt: bool | None = None) -> dict:
    """What pins a Windows character's Claude Code to the same bash the harness uses, with the PowerShell tool off
    so the model is never offered a second dialect. Empty on POSIX, and when there is no bash: the spawn must not
    fail for that — the checks/setup path is where a missing bash is reported."""
    nt = os.name == "nt" if nt is None else nt
    if not nt:
        return {}
    try:
        return {"CLAUDE_CODE_GIT_BASH_PATH": bash_path(), "CLAUDE_CODE_USE_POWERSHELL_TOOL": "0"}
    except NoBash:
        return {}


def run_shell(cmd: str, cwd: str, timeout: float) -> tuple[int | None, str]:
    """(exit code, combined stdout+stderr); the exit code is None when it timed out and the tree was killed.
    Raises NoBash when there is nothing to run the line in."""
    kwargs = {"start_new_session": True} if os.name != "nt" else {}
    p = subprocess.Popen([bash_path(), "-c", cmd], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kwargs)
    try:
        output, _ = p.communicate(timeout=timeout)
        return p.returncode, output
    except subprocess.TimeoutExpired:
        kill_tree(p)
        p.communicate()
        return None, ""


def kill_tree(p: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        return
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
