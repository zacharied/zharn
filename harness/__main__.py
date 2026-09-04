"""Entry point. `python -m harness` (or `harness` once installed)."""
from __future__ import annotations

import importlib
import json
import os
import uuid
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
            '# DEFAULT_ROLES = DEFAULT_ROLES + [{"name": "mine", "provider": "claude-code", "model": "claude-opus-5", "reasoning": "high", "permission": "full"}]\n')


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
    from harness.environments import head_branch
    from harness.icons import app_icon
    from harness.ipc import IpcServer, make_handler
    from harness.notify import Notifier
    from harness.roles import RoleStore
    from harness.shell import QML_DIR, Reloader
    from harness.store import AppStore, LayoutStore, Session
    from harness.contexts import ContextStore
    from harness.stories import StoryStore
    from harness.workspace import Workspace
    from harness.workspace_store import WorkspaceStore

    app = QGuiApplication.instance() or QGuiApplication(argv or sys.argv)
    app.setApplicationName("zharn")
    app.setOrganizationName("zharn")
    app.setWindowIcon(app_icon())
    QQuickStyle.setStyle("Basic")

    ws_env = os.environ.get("HARNESS_WORKSPACE")
    if ws_env:   # an explicit workspace (tests, run.bat); a git repo opened as a workspace registers itself as "."
        ws_dir = Path(ws_env)
        workspace = Workspace.open_or_create(ws_dir)
        if not workspace.repos and (ws_dir / ".git").exists():
            workspace.add_repo(ws_dir, base=head_branch(ws_dir))   # a repo with no `base` has no target: the gate and Approve need one
    else:
        workspace = Workspace.scratch(ROOT)
    data_dir = workspace.local_dir
    session = Session(Path(os.environ.get("HARNESS_SESSION") or data_dir / "session.json"))
    layout_store = LayoutStore(session)
    content = ContentRegistry(QML_DIR)
    roles = RoleStore(data_dir)
    contexts = ContextStore(ROOT, data_dir / "contexts", roles, workspace_dir=workspace.dir)
    stories = StoryStore(workspace, contexts, roles)
    workspace_store = WorkspaceStore(workspace, stories)
    from harness.documents import DocumentsStore
    documents = DocumentsStore(workspace, layout_store)
    workspace_store.workspaceChanged.connect(documents.rescan)   # a repo registered or unregistered: rescan now
    notifier = Notifier()
    for s in (layout_store, roles, contexts, stories, workspace_store, documents):
        s.notifier = notifier  # @intent slots report here; the status bar shows it
    store = AppStore(session, layout_store, content, cfg.THEME, contexts=contexts, roles=roles,
                     stories=stories, workspace=workspace, workspace_store=workspace_store, notifier=notifier,
                     documents=documents)
    # Unique per app instance, not just per process: tests build several apps in one process, and a torn-down
    # QLocalServer unlinks its socket by name — it must never be the live one's.
    ipc = IpcServer(f"zharn-{os.getpid()}-{uuid.uuid4().hex[:6]}", make_handler(store), parent=store)
    store._ipc_path = ipc.path
    contexts.extra_env = lambda: {"HARNESS_IPC": ipc.path}
    documents.start(cfg.DOCS_RESCAN_MS)
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
        key = store.stories.create("smoke", "smoke test")
        chr_id = store.stories.start(key, smoke_prompt, os.environ.get("HARNESS_SMOKE_ROLE", "protagonist"))
        cid = store.stories.character(chr_id)["live_context"]
        store.layout.openContent("context", cid, key)
        context = store.contexts.get(cid)

        def settled():
            if context.status in ("idle", "failed", "stopped"):
                print("[smoke] " + json.dumps(context.summary()), flush=True)
                for row in context.transcript.rows():
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
    store.contexts.shutdown()
    reloader.shutdown()
    sys.exit(rc)


if __name__ == "__main__":
    main()
