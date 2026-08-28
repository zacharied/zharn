"""Entry point. `python -m harness` (or `harness` once installed)."""
from __future__ import annotations

import importlib
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ensure_user_config():
    """config.def.py is upstream's; config.py is yours. Same for qml/Theme.def.qml."""
    for d, u in ((ROOT / "harness/config.def.py", ROOT / "harness/config.py"),):
        if not u.exists():
            shutil.copy(d, u)


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
    from harness.shell import QML_DIR, Reloader
    from harness.store import AppStore, LayoutStore, Session

    app = QGuiApplication.instance() or QGuiApplication(argv or sys.argv)
    app.setApplicationName("my-harness")
    app.setOrganizationName("my-harness")
    QQuickStyle.setStyle("Basic")

    session = Session(Path(os.environ.get("HARNESS_SESSION") or ROOT / ".harness-session.json"))
    layout_store = LayoutStore(session)
    content = ContentRegistry(QML_DIR)
    store = AppStore(session, layout_store, content, cfg.THEME)
    reloader = Reloader(store, load_theme, force_poll=force_poll or bool(os.environ.get("HOT_POLL")),
                        poll_ms=getattr(cfg, "WATCH_POLL_MS", 250))
    return app, store, reloader


def main():
    app, store, reloader = build()
    if not reloader.load():
        sys.exit("initial QML load failed:\n" + store.reloadError)
    if os.environ.get("HARNESS_EXIT_AFTER_MS"):  # smoke-test hooks
        from PySide6.QtCore import QTimer

        def finish():
            shot = os.environ.get("HARNESS_SCREENSHOT")
            if shot:
                reloader.engine.rootObjects()[-1].grabWindow().save(shot)
            app.quit()
        QTimer.singleShot(int(os.environ["HARNESS_EXIT_AFTER_MS"]), finish)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
