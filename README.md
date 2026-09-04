# zharn

A native (Qt / PySide6 + QML), self-modifying coding-agent harness. bb's model, no web stack,
your fork is your config.

* [docs/DESIGN.md](docs/DESIGN.md) — stack decision, architecture, window model, task model, licensing
* [poc/](poc/README.md) — the original hot-reload proof of concept

## Run

```sh
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .            # editable: PySide6-Essentials 6.11+, Python 3.10+
python -m harness           # or just `zharn`
```

Windows shortcut: double-click or run `run.bat` — it creates `.venv` and installs on first use, then
launches the app (arguments are passed through to `python -m harness`).

Always install **editable** (`-e`): the app runs from your checkout (`qml/`, `harness/config.py`,
transcripts in `.zharn/local/`) — that is the whole point. A plain `pip install .` would copy
`harness/` into site-packages, away from `qml/`.

Windows: works natively (PySide6 wheels, no WSL needed). For real agents the `claude` CLI must be
on PATH for the *same* OS the harness runs on; set `CLAUDE_CMD` in `harness/config.py` if it lives
elsewhere (e.g. `["wsl", "claude"]` to drive the WSL install from a Windows harness).

The UI follows JetBrains' New UI conventions (DESIGN.md §3a): tool windows on icon strips, editor
tabs in the middle, a Stories tree on the left, the Cast of the focused story on the right, Contexts
at the bottom. Tokens are in `harness/config_def.py: THEME`; reusable pieces in `qml/ui/`.

Edit anything under `qml/` or `harness/` while it runs: QML re-renders as a new generation
(state lives in Python, so tabs/docks/layout survive); Python method bodies are swapped into the
live classes. Adding a `Signal`/`Property` to a live class shows a "restart" button in the status
bar (one click, session persists). Errors show in the status bar; a broken root keeps the previous
generation running.

`harness/config.py` is generated on first run as `from harness.config_def import *` plus your
overrides; it is gitignored, so `git pull` never touches it and new upstream settings still flow
through. Everything else is yours too — fork it.

## Stories, characters, contexts

> **Experimental — no backward compatibility** (DESIGN.md §0): on-disk formats, module names,
> env vars and CLI verbs change without migration until further notice.

Work is a **story** ([docs/AGENT-MODEL.md](docs/AGENT-MODEL.md)); you are its author, agents are its
cast. Write a story on the board, press **Start**: the harness casts a **protagonist** from a role
(`harness/config_def.py: DEFAULT_ROLES`) on a fresh **context** (one `claude -p --output-format
stream-json` process) and hands it the brief. The story's state is `(phase, ball)`: phase moves only
through the actions on the story page (Proceed, Approve, Back to planning, Cancel, Reopen) and the
protagonist's `yield`/`proceed`; nobody sets a status. When the ball is yours the board says why.

Inside a character `HARNESS_CLI`, `HARNESS_CONTEXT_ID`, `HARNESS_STORY_KEY`, `HARNESS_CHARACTER_ID`,
`HARNESS_WORKSPACE` and `HARNESS_IPC` are set:

    $HARNESS_CLI story yield --question --body "pg or sqlite?" --options pg,sqlite   # ball → author
    $HARNESS_CLI story yield --handoff --body "what changed / how verified / where to look"
    $HARNESS_CLI story proceed | recap --body … | comment --body … | show

Every character's system prompt is stable for the life of its context: identity, the iron laws of
`harness/skills/skills/being-a-character/SKILL.md`, the CLI contract, its role. Everything that moves — phase, the
attended thread, what it owes and awaits, where it stands — arrives as a `[situation]` line on top of every message,
and the skill for the current phase rides the message whenever the phase changes. `harness/skills/` is a Claude Code
plugin (`--plugin-dir` at every spawn; `HARNESS_SKILLS_DIR` overrides it): four zharn skills and five discipline
skills vendored from superpowers (`harness/skills/VENDORED.md`). Edit a skill and the next spawn has it. The full
mechanics are in the [lifecycle spec](docs/specs/story-lifecycle.md); harness-spawned minions are still Claude's native
`Agent` tool.

**Where things live.** The checkout you run from is opened as a **workspace**
([spec](docs/specs/workspace-model.md)): `.zharn/workspace.toml`
(id, prefix, repos), `.zharn/stories/<key>/{story.json,threads.jsonl}` (the durable record), and
`.zharn/local/` (contexts, characters, session — machine-local). Click the workspace name in the
toolbar for the **workspace page**: the registered repos, each with its worktrees, Relocate when a
path has moved, Unregister, and a form to register another by path. Set `HARNESS_WORKSPACE` to open a
different directory. Point `HARNESS_CLAUDE_CMD` at another CLI to substitute the provider
(`tests/fake_claude.py` speaks the protocol).

## Test

```sh
pip install -e .[dev]
QT_QPA_PLATFORM=offscreen python -m pytest      # ~600 tests, ~30 s, no display needed
```

Three layers, all offscreen:

* `tests/test_<module>.py` — unit tests per Python module (workspace, lifecycle, stories, contexts, roles, stream interpreter, models, IPC, CLI, watcher, layout, notifier, process wrapper).
* `tests/test_ui_*.py` — **drive the real QML** through `tests/ui.py`: find a control by `objectName`,
  click it, type into it, assert the store changed. Every interactive control in `qml/` has a stable
  `objectName` (`startButton`, `card_ZHAR-3`, `stripButton_board`, `optionButton_<comment>_<i>` …) — keep
  that up when you add one, it is how the tests (and agents editing the UI) reach it.
* `tests/test_app.py`, `tests/test_agents.py` — end-to-end: hot reload, fake-agent conversations, IPC.
* `tests/skills/` — the paid layer: three scenarios against real `claude -p`, each run with and without the skill under
  test; assertions read `verbs_log`. Skipped unless `HARNESS_PAID_TESTS=1`; the last run's `baseline.json` and
  `skilled.json` sit beside each scenario.

Anything a QML button calls is an `@intent` (`harness/notify.py`): if it raises, the message shows in
the status bar (`app.notify.lastError`) instead of silently doing nothing.

Smoke-test a real window: `HARNESS_EXIT_AFTER_MS=3000 HARNESS_SCREENSHOT=shot.png python -m harness`;
add `HARNESS_SMOKE_PROMPT="say pong"` to start a story on the checkout's workspace and exit when it settles.
On WSL without WSLg, run it from a Windows Python (see docs/DESIGN.md §7).
