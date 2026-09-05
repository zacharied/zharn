# One shell everywhere Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A repo's `checks` and `setup` are bash lines run by one resolved `bash` on every platform (Git Bash on Windows); the character's Claude Code is pinned to that same bash with the PowerShell tool off; the CLI's stdio is UTF-8; the spec and README say so.

**Architecture:** `harness/procs.py` owns shell resolution (`bash_path()`) and execution (`run_shell()`); `environments.py` and `cli.py` keep calling `run_shell` and only learn to report a missing bash. `contexts.py` asks `procs` for the two Claude Code variables when on Windows. `cli.py` reconfigures its own streams at import. `tests/shellx.py` is deleted and the POSIX strings return.

**Tech Stack:** Python 3.10+, PySide6, pytest (`~/.venvs/mh-conda/bin/python -m pytest` in WSL; on Windows `C:\Users\zachd\.venvs\My-harness-win\Scripts\python.exe -m pytest` from a clone under `/mnt/c`, `PYTHONPATH=%CD%`, `QT_QPA_PLATFORM=offscreen`).

**Spec:** `docs/superpowers/proposals/2026-09-04-windows-bash.md` (then `docs/specs/workspace-model.md` §3.1 and the README once Task 5 rewrites them).

## Global Constraints

- Builds on the commit from thread `thr_zjy37ijsqz` (procs.py with `run_shell`/`kill_tree`, `split_command`, the FailedToStart guard). Do not start before it lands.
- No backward compatibility: the "platform shell" rule is deleted from the spec, not footnoted; `shellx.py` is deleted, not deprecated.
- `cli.py` stays free of Qt; it may import `harness.procs` (stdlib only).
- Never resolve `bash` from PATH on Windows: System32's `bash.exe` is WSL.

---

## File structure

| File | Responsibility in this change |
|---|---|
| `harness/procs.py` | `bash_path(nt, env, which)`, `NoBash`, `run_shell` runs `[bash, "-c", cmd]`, `claude_shell_env(nt)` |
| `harness/config_def.py` | `BASH_PATH = ""` beside `CLAUDE_CMD` |
| `harness/environments.py` | `_setup` turns `NoBash` into `EnvError` |
| `harness/cli.py` | UTF-8 stdio at import; `run_checks` lets `NoBash` refuse the handoff with its message |
| `harness/contexts.py` | `_env` merges `claude_shell_env()` |
| `tests/test_procs.py` (new), `tests/test_cli.py`, `tests/test_environments.py`, `tests/test_contexts_unit.py` | new tests; POSIX strings back; `shellx.py` deleted |
| `docs/specs/workspace-model.md` §3.1, `README.md` | present-tense description |

---

### Task 1: `procs.py` — resolve bash, run through it

**Files:** Modify `harness/procs.py`, `harness/config_def.py`; Create `tests/test_procs.py`

**Interfaces:**
- `class NoBash(RuntimeError)` — message names what to install.
- `bash_path(nt: bool = os.name == "nt", env: Mapping = os.environ, which=shutil.which) -> str`: `config.BASH_PATH` if set; POSIX → `which("bash")`; Windows → `env["CLAUDE_CODE_GIT_BASH_PATH"]` if set, else walk up from `which("git")` looking for `bin/bash.exe` (Git for Windows: `cmd/git.exe` → `../bin/bash.exe`; `mingw64/bin/git.exe` → `../../bin/bash.exe`), else `%ProgramFiles%\Git\bin\bash.exe` if it exists. Raise `NoBash` otherwise.
- `run_shell(cmd, cwd, timeout)` unchanged contract, runs `[bash_path(), "-c", cmd]` with `shell=False`.
- `claude_shell_env(nt: bool = os.name == "nt") -> dict`: `{}` on POSIX; on Windows `{"CLAUDE_CODE_GIT_BASH_PATH": bash_path(), "CLAUDE_CODE_USE_POWERSHELL_TOOL": "0"}`; `{}` again if `NoBash` (the spawn must not fail; the check/setup path reports it).

- [ ] **Step 1: Failing tests** in `tests/test_procs.py`: config override wins; POSIX uses `which("bash")`; Windows ignores PATH's `bash` and derives from a fake git tree in `tmp_path` (`Git/cmd/git.exe`, `Git/bin/bash.exe`); env var wins over derivation; nothing found → `NoBash` mentioning "Git for Windows"; `run_shell("test -f ok.txt && echo fine", ...)` → `(0, "fine\n")` on every platform; `run_shell("sleep 5", ..., timeout=0.2)` → `(None, "")` within 3 s; `claude_shell_env(nt=False) == {}` and `claude_shell_env(nt=True)` carries both keys.
- [ ] **Step 2: Implement**; run `tests/test_procs.py` green on WSL.
- [ ] **Step 3: Windows run** of `tests/test_procs.py` in the `/mnt/c` clone.

### Task 2: `environments.py` and `cli.py` report a missing bash

- [ ] `_setup`: `except NoBash as e: raise EnvError(str(e))`. Test: monkeypatch `procs.bash_path` to raise; `es.open` raises `EnvError` with the message; `setup_done` stays False.
- [ ] `run_checks`: a `NoBash` propagates; `main()`'s handoff branch catches it and `sys.exit("handoff refused: " + str(e))`. Test in `test_cli.py` with a recorder: exit message contains the bash text; no `story.yield` was sent.

### Task 3: `cli.py` owns its encoding

- [ ] At import, after `sys.dont_write_bytecode`: `for s in (sys.stdin, sys.stdout, sys.stderr): s.reconfigure(encoding="utf-8", errors="replace")` guarded by `hasattr(s, "reconfigure")`.
- [ ] Test: run `[sys.executable, "-c", "import harness.cli, sys; print(sys.stdout.encoding); print('\u2713')"]` with `PYTHONIOENCODING` removed and stdout captured → exit 0, first line `utf-8`, second decodes to `✓`. (On Linux the first assertion is the meaningful one; on Windows both.)

### Task 4: the character's shell is pinned

- [ ] `contexts.py` `_env`: `env.update(claude_shell_env())` before `self.meta["env"]` overrides.
- [ ] Test in `test_contexts_unit.py`: monkeypatch `harness.contexts.claude_shell_env` to return a marker dict; the spawned process env carries it (reuse the existing `_inits` / recorded-env pattern).

### Task 5: tests revert to one dialect; the record

- [ ] Delete `tests/shellx.py`; in `test_cli.py` and `test_environments.py` restore `test -f …`, `sleep 5`, `echo ran >> …`, `"ran\n"` assertions; drop the `sys.path.insert` for `shellx`.
- [ ] `docs/specs/workspace-model.md` §3.1: replace the "platform shell" paragraph with: "`checks` and `setup` are bash lines: the harness runs them as `bash -c` in the environment directory — the system bash on POSIX, Git Bash on Windows (`config.BASH_PATH` overrides where it is found). A multi-command line uses bash syntax (`&&`, `;`, …)."
- [ ] README: "Windows: works natively" paragraph → Git for Windows is required (Claude Code's Bash tool and the harness's `checks`/`setup` run in its bash; the harness pins Claude Code to it); delete the `["wsl", "claude"]` sentence; name `BASH_PATH` beside `CLAUDE_CMD`.
- [ ] Full suite green on WSL; full suite on Windows in the clone, expect only skips for AF_UNIX fixtures and the socket-file test.
