# Hot-reload proof of concept (PySide6 + QML)

Answers the question "does Qt have hot reload good enough for a self-modifying harness?"
**Yes** — measured here, without any third-party tool:

| Layer            | Mechanism                                                     | Cost (measured)        | State survives? |
|------------------|---------------------------------------------------------------|------------------------|-----------------|
| QML/JS UI        | `engine.clearComponentCache()` + reload root, delete old root | 9–40 ms                | yes*            |
| Python logic     | `importlib.reload(backend)`                                   | 1–16 ms                | yes             |
| C++ core         | **don't** (Qt sets `PreventUnloadHint`; moc/QMetaType assume stable addresses) | rebuild + fast restart | via persisted session |

\* State survives because it lives in a long-lived Python `Store` QObject exposed to QML, not in the QML tree.
The QML tree is disposable; the store is not. Design everything that way.

## Run

```sh
# WSL, headless self-test (uses conda env because pip wheel needs system libs we can't install w/o sudo)
QT_QPA_PLATFORM=offscreen POC_SELFTEST=1 ~/.venvs/mh-conda/bin/python hotreload.py

# Windows, real window (env vars must go through cmd.exe; WSL interop doesn't forward them)
cmd.exe /c "C:\Users\zachd\.venvs\my-harness-win\Scripts\python.exe -u C:\Users\zachd\Code\my-harness\poc\hotreload.py"
# ...then edit qml/Main.qml, qml/Panel.qml or backend.py and watch it reload in place.
```

Self-test edits `backend.py` (+1 → +10) and `qml/Main.qml` (title) on a timer, asserts the running
app picked both up and kept `counter == 12`, then restores the files. Exit code 1 on failure.

## Caveats found on this machine

- inotify is broken in this WSL instance (`ENOSPC` on every path, even ext4, with a 524k limit) → the
  reloader auto-falls back to a 250 ms mtime poller (`HOT_POLL=1` forces it). Qt's own internal 1 s
  poller did **not** catch edits on `/mnt/c` (9p/drvfs); our own poller does.
- `.wslconfig` has `guiApplications=false`, so no WSLg display; run the GUI from Windows Python or flip that flag.
- Editors that save via rename drop inotify watches; `_rewatch()` re-adds after every reload.
