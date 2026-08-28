"""Entry point. `python -m harness` (or `harness` once installed)."""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ensure_user_config():
    """config_def.py is upstream's; config.py is yours (gitignored) and starts as an import-star
    of the defaults plus your overrides, so new upstream settings keep flowing through."""
    user = ROOT / "harness" / "config.py"
    if not user.exists():
        user.write_text(
            '"""Your config. Anything set here overrides harness/config_def.py (upstream defaults).\n'
            'This file is gitignored: your fork is your config, this is just the convenient part."""\n'
            "from harness.config_def import *  # noqa: F401,F403\n\n"
            "# Examples:\n"
            '# THEME = {**THEME, "accent": "#c678dd"}\n'
            '# DEFAULT_PRESETS = DEFAULT_PRESETS + [{"name": "mine", "provider": "claude-code", "model": "claude-opus-5", "reasoning": "high", "permission": "full"}]\n')


def load_theme() -> dict:
    import harness.config as cfg
    return dict(cfg.THEME)


def build(argv=None, force_poll=False):
    """Create app + stores + reloader (no exec). Used by main() and by tests."""
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuickControls2 import QQuickStyle

    ensure_user_config()
    sys.dont_write_bytecode = True  # hot reload must compile from source (stale .pyc has 1s mtime granularity)
    import harness.config as cfg
    from harness.content import ContentRegistry
    from harness.ipc import IpcServer, make_handler
    from harness.presets import PresetStore
    from harness.shell import QML_DIR, Reloader
    from harness.store import AppStore, LayoutStore, Session
    from harness.tasks import TaskStore
    from harness.threads import ThreadStore

    app = QGuiApplication.instance() or QGuiApplication(argv or sys.argv)
    app.setApplicationName("my-harness")
    app.setOrganizationName("my-harness")
    QQuickStyle.setStyle("Basic")

    data_dir = Path(os.environ.get("HARNESS_DATA_DIR") or ROOT / ".harness")
    session = Session(Path(os.environ.get("HARNESS_SESSION") or data_dir / "session.json"))
    layout_store = LayoutStore(session)
    content = ContentRegistry(QML_DIR)
    presets = PresetStore(data_dir)
    threads = ThreadStore(ROOT, data_dir, presets)
    tasks = TaskStore(data_dir, threads)
    store = AppStore(session, layout_store, content, cfg.THEME, threads=threads, presets=presets, tasks=tasks)
    ipc = IpcServer(f"my-harness-{os.getpid()}", make_handler(store), parent=store)
    store._ipc_path = ipc.path
    threads.extra_env = lambda: {"HARNESS_IPC": ipc.path}
    reloader = Reloader(store, load_theme, force_poll=force_poll or bool(os.environ.get("HOT_POLL")),
                        poll_ms=getattr(cfg, "WATCH_POLL_MS", 250))
    return app, store, reloader


def main():
    app, store, reloader = build()
    if not reloader.load():
        sys.exit("initial QML load failed:\n" + store.reloadError)
    smoke_prompt = os.environ.get("HARNESS_SMOKE_PROMPT")  # smoke-test hooks: real agent run, then exit
    if smoke_prompt:
        from PySide6.QtCore import QTimer
        task_key = store.tasks.list()[0]["key"]
        tid = store.tasks.dispatch(task_key, os.environ.get("HARNESS_SMOKE_PRESET", "claude-default"), smoke_prompt)
        store.layout.openContent("thread", tid, store.threads.get(tid).title)
        thread = store.threads.get(tid)

        def settled():
            if thread.status in ("idle", "failed", "stopped"):
                print("[smoke] " + json.dumps(thread.summary()), flush=True)
                for row in thread.transcript.rows():
                    print(f"[smoke] {row['role']}/{row['kind']}: {(row['text'] or row['input'])[:160]!r}", flush=True)
                QTimer.singleShot(800, finish)
            else:
                QTimer.singleShot(200, settled)
        QTimer.singleShot(200, settled)

    def finish():
        shot = os.environ.get("HARNESS_SCREENSHOT")
        if shot:
            reloader.engine.rootObjects()[-1].grabWindow().save(shot)
        app.quit()
    if os.environ.get("HARNESS_EXIT_AFTER_MS"):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(int(os.environ["HARNESS_EXIT_AFTER_MS"]), finish)
    rc = app.exec()
    store.threads.shutdown()
    reloader.shutdown()
    sys.exit(rc)


if __name__ == "__main__":
    main()
