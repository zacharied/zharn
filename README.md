# my-harness

A native (Qt / PySide6 + QML), self-modifying coding-agent harness. bb's model, no web stack,
your fork is your config.

* [docs/DESIGN.md](docs/DESIGN.md) — stack decision, architecture, window model, task model, licensing
* [poc/](poc/README.md) — the original hot-reload proof of concept

## Run

```sh
pip install -e .            # PySide6-Essentials 6.11+, Python 3.10+
python -m harness           # or just `harness`
```

Edit anything under `qml/` or `harness/` while it runs: QML re-renders as a new generation
(state lives in Python, so tabs/docks/layout survive); Python method bodies are swapped into the
live classes. Adding a `Signal`/`Property` to a live class shows a "restart" button in the status
bar (one click, session persists). Errors show in the status bar; a broken root keeps the previous
generation running.

`harness/config.def.py` → copied to `harness/config.py` on first run. That copy is yours
(gitignored). Everything else is yours too — fork it.

## Test

```sh
pip install -e .[dev]
QT_QPA_PLATFORM=offscreen python -m pytest      # layout unit tests + offscreen end-to-end + hot-reload tests
```

Smoke-test a real window: `HARNESS_EXIT_AFTER_MS=3000 HARNESS_SCREENSHOT=shot.png python -m harness`.
On WSL without WSLg, run it from a Windows Python (see docs/DESIGN.md §7).
