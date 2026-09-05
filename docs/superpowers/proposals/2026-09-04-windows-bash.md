# One shell everywhere: Git Bash on Windows

*Proposal, 2026-09-04. Expires when it lands; the standing text goes into
`docs/specs/workspace-model.md` (§3.1) and the README's Windows and environment paragraphs.*

Native Windows was verified on 2026-09-04 (commit b12f85c): the UI launches, `claude.exe`
spawns, the CLI reaches the harness over its named pipe, and the skills' heredoc question yield
works from Git Bash. Three bugs from that run (a synchronous FailedToStart, quoted
`HARNESS_CLAUDE_CMD` paths, `/bin/echo` as askpass) are fixed separately. What remains is not a
bug but a choice the project has not made: which shell a character, and the harness on its behalf,
speaks on Windows.

Claude Code has already half-made it. With Git for Windows installed it runs the Bash tool in Git
Bash; without it, a PowerShell tool; on claude.ai accounts the PowerShell tool is on *alongside*
Bash. The skills, the system prompt's verb table and `fake_claude.py` are written in bash. So
the only open question is whether the harness's own shell use — a repo's `checks` and `setup` —
follows suit or stays with "the platform shell", which the workspace spec today names as `sh` on
POSIX and `cmd.exe` on Windows.

## Positions taken without a ruling

| # | Question | Position |
|---|---|---|
| 1 | PowerShell skills as a second dialect? | No. Two copies of every skill, the verb table, the fake and the tests, for a dialect the model is weaker in, to gain nothing Git Bash does not already give. |
| 2 | cmd.exe for `checks`/`setup`? | No. No heredoc, no single quotes, a hostile quoting model. Its only role was the spec's "platform shell", and that rule goes. |
| 3 | `bash` on POSIX too, or `sh`? | `bash`, so a check string is one string everywhere. `sh` on Linux is dash; `[[ ]]` and `set -o pipefail` in a check would work in Git Bash and fail in CI. |
| 4 | Is the WSL `bash.exe` in System32 ever acceptable? | Never. Inside it the named pipe and the Windows Python are unreachable. Resolution goes by git's location, not by PATH. |
| 5 | Encoding: `PYTHONUTF8=1` in the character's env, or the CLI fixes itself? | The CLI. Setting `PYTHONUTF8` on the character leaks into every tool the character runs; the CLI reconfiguring its own stdio is contained and testable. |
| 6 | Is Git for Windows optional? | No. The README lists it as a requirement on native Windows, as `git` already is everywhere. |

## 1. One `bash` for `checks` and `setup`

**What the run showed.** The tests' check strings (`test -f ok.txt && echo fine`, `sleep 5`)
fail under cmd.exe, and the first fix reached for was a dual-dialect helper that writes every
test string twice. A repo's real check string would face the same fork: `workspace.toml` is
committable, so `checks = "QT_QPA_PLATFORM=offscreen pytest -q"` written on Linux must run on a
Windows checkout of the same workspace.

**The change.** `checks` and `setup` are bash lines, run as `bash -c <line>` in the environment
directory, on every platform. One function finds the interpreter:

```
harness/procs.py
  bash_path() -> str          # config.BASH_PATH if set; else `bash` on PATH on POSIX;
                              # on Windows: CLAUDE_CODE_GIT_BASH_PATH, else <git install>/bin/bash.exe
                              # found by walking up from shutil.which("git"); never System32's
  run_shell(cmd, cwd, timeout) -> (exit | None, output)     # unchanged contract; runs [bash, "-c", cmd]
```

No bash is an `EnvError` naming what is missing ("Git for Windows"), raised where the check would
have run — the character reads it in the refused handoff, the author on the workspace page.

`tests/shellx.py` goes; the tests' POSIX strings come back.

## 2. The character's shell is pinned

**The change.** On Windows the character's environment carries
`CLAUDE_CODE_GIT_BASH_PATH=<bash_path()>` and `CLAUDE_CODE_USE_POWERSHELL_TOOL=0`, so Claude Code
uses the same bash the harness does and never offers the model a second dialect. On POSIX neither
is set.

## 3. The CLI owns its encoding

**What the run showed.** Piped, the CLI's stdout is cp1252 on Windows; a story body with `✓`
kills `story show` with `UnicodeEncodeError`. The question document arrives on stdin as UTF-8
bytes from bash and would be decoded as cp1252.

**The change.** `harness/cli.py` reconfigures `stdin`, `stdout` and `stderr` to UTF-8 at
import, before any I/O. Output that a terminal cannot show is replaced, never fatal.

## 4. The record

- `docs/specs/workspace-model.md` §3.1: "`checks` and `setup` are bash lines, run by `bash -c`
  in the environment — the system bash on POSIX, Git Bash on Windows." The "platform shell"
  sentence goes.
- README: Git for Windows is required on native Windows; the `["wsl", "claude"]` hybrid note
  goes (the pipe and the Python path are unreachable from WSL); `config.BASH_PATH` is named beside
  `CLAUDE_CMD`.

## Known limit, left alone

`$HARNESS_CLI` is word-split by bash, so a venv whose path contains a space breaks every verb.
This is true on Linux today and is not made worse here; the fix, if wanted, is a launcher without
spaces, not quoting in forty skill lines.
