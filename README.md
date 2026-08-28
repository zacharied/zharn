# my-harness

A native (Qt / PySide6 + QML), self-modifying coding-agent harness. bb's model, no web stack,
your fork is your config.

* [docs/DESIGN.md](docs/DESIGN.md) — stack decision, architecture, window model, task model, licensing
* [poc/](poc/README.md) — the original hot-reload proof of concept

## Run

```sh
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .            # editable: PySide6-Essentials 6.11+, Python 3.10+
python -m harness           # or just `harness`
```

Always install **editable** (`-e`): the app runs from your checkout (`qml/`, `harness/config.py`,
transcripts in `.harness/`) — that is the whole point. A plain `pip install .` would copy
`harness/` into site-packages, away from `qml/`.

Windows: works natively (PySide6 wheels, no WSL needed). For real agents the `claude` CLI must be
on PATH for the *same* OS the harness runs on; set `CLAUDE_CMD` in `harness/config.py` if it lives
elsewhere (e.g. `["wsl", "claude"]` to drive the WSL install from a Windows harness).

Edit anything under `qml/` or `harness/` while it runs: QML re-renders as a new generation
(state lives in Python, so tabs/docks/layout survive); Python method bodies are swapped into the
live classes. Adding a `Signal`/`Property` to a live class shows a "restart" button in the status
bar (one click, session persists). Errors show in the status bar; a broken root keeps the previous
generation running.

`harness/config.py` is generated on first run as `from harness.config_def import *` plus your
overrides; it is gitignored, so `git pull` never touches it and new upstream settings still flow
through. Everything else is yours too — fork it.

## Agents

Threads run `claude -p --output-format stream-json --input-format stream-json` as a child process
(one process per thread, follow-ups over stdin, `--resume` after a restart). Every thread belongs to
a task; dispatch from a task tab with a preset (`harness/config_def.py: DEFAULT_PRESETS`).

Agents get `HARNESS_THREAD_ID`, `HARNESS_TASK_KEY`, `HARNESS_IPC` and `HARNESS_CLI` and can drive
the harness over a local socket — bb's `BB_CLI` idea:

```sh
$HARNESS_CLI thread spawn --preset claude-fast --prompt "write the tests" --wait   # sibling on the same task
$HARNESS_CLI thread list --task ABC-12 | preset list | task status ABC-12 in_review
```

Child threads are parented to the caller; when a child settles, the parent transcript gets a note
and, if the parent is idle, a follow-up turn with the child's outcome.

Point `HARNESS_CLAUDE_CMD` at another CLI to substitute the provider (the tests use
`tests/fake_claude.py`, which speaks the same protocol).

## Test

```sh
pip install -e .[dev]
QT_QPA_PLATFORM=offscreen python -m pytest      # layout unit tests + offscreen end-to-end + hot-reload tests
```

Smoke-test a real window: `HARNESS_EXIT_AFTER_MS=3000 HARNESS_SCREENSHOT=shot.png python -m harness`;
add `HARNESS_SMOKE_PROMPT="say pong"` to dispatch a real agent on the first task and exit when it settles.
On WSL without WSLg, run it from a Windows Python (see docs/DESIGN.md §7).
