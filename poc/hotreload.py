"""
Hot-reload PoC for a PySide6 + QML app.

Proves two things:
  1. QML hot reload: edit any .qml under ./qml and the UI reloads in-place
     (QFileSystemWatcher -> engine.clearComponentCache() -> reload root).
  2. Python hot reload: edit backend.py and the logic reloads in-place
     (importlib.reload; the QObject singleton keeps its state, only code swaps).

State survives both kinds of reload because it lives in a long-lived
Python-side Store object, NOT in the QML tree.
"""
import importlib, os, sys, time
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, QUrl, Signal, Slot, Property
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

import backend  # user-editable logic

HERE = Path(__file__).parent
QML_DIR = HERE / "qml"
ROOT_QML = QML_DIR / "Main.qml"


class Store(QObject):
    """Long-lived app state. Survives QML and Python reloads."""
    changed = Signal()
    reloadsChanged = Signal()

    def __init__(self):
        super().__init__()
        self._counter = 0
        self._reloads = 0
        self._log = []

    @Property(int, notify=changed)
    def counter(self):
        return self._counter

    @Property(int, notify=reloadsChanged)
    def reloads(self):
        return self._reloads

    @Property(str, notify=changed)
    def log(self):
        return "\n".join(self._log[-8:])

    @Slot()
    def bump(self):
        # Delegates to the reloadable module so behaviour can change live.
        self._counter = backend.next_value(self._counter)
        self._log.append(backend.describe(self._counter))
        self.changed.emit()

    @Slot(str)
    def note(self, msg):
        self._log.append(msg)
        self.changed.emit()


class HotReloader(QObject):
    def __init__(self, engine: QQmlApplicationEngine, store: Store):
        super().__init__()
        self.engine, self.store = engine, store
        self.watcher = QFileSystemWatcher()
        self.watcher.fileChanged.connect(self._on_change)
        self.watcher.directoryChanged.connect(self._on_change)
        self._debounce = QTimer(singleShot=True, interval=80)
        self._debounce.timeout.connect(self._reload)
        self._pending = set()
        # Polling fallback: inotify is unavailable on WSL drvfs (/mnt/c) and some network FS.
        self._mtimes = {}
        self._poll = QTimer(interval=250)
        self._poll.timeout.connect(self._poll_tick)
        self.mode = "poll" if os.environ.get("HOT_POLL") else "inotify"
        if self.mode == "poll":
            self._poll.start()
        self._rewatch()

    def _watched_paths(self):
        return [str(p) for p in QML_DIR.rglob("*.qml")] + [str(QML_DIR), str(HERE / "backend.py")]

    def _rewatch(self):
        # Editors often replace files (rename), which drops the watch: re-add each time.
        paths = self._watched_paths()
        if self.mode == "poll":
            self._mtimes = {p: self._mtime(p) for p in paths}
            return
        new = [p for p in paths if p not in self.watcher.files() and p not in self.watcher.directories()]
        failed = self.watcher.addPaths(new) if new else []
        if failed:
            self.mode = "poll"
            self.watcher.removePaths(self.watcher.files() + self.watcher.directories())
            self._mtimes = {p: self._mtime(p) for p in paths}
            self._poll.start()
            print(f"[hot] inotify unavailable for {len(failed)} path(s); falling back to mtime polling every {self._poll.interval()} ms", flush=True)

    @staticmethod
    def _mtime(p):
        try:
            return os.stat(p).st_mtime_ns
        except OSError:
            return None

    def _poll_tick(self):
        for p in self._watched_paths():
            m = self._mtime(p)
            if self._mtimes.get(p) != m:
                self._mtimes[p] = m
                self._on_change(p)

    def _on_change(self, path):
        self._pending.add(path)
        self._debounce.start()

    def _reload(self):
        pending, self._pending = self._pending, set()
        t0 = time.perf_counter()
        if any(p.endswith(".py") for p in pending):
            try:
                importlib.reload(backend)
                self.store.note(f"[py] reloaded backend.py")
            except Exception as e:  # keep running on syntax errors
                self.store.note(f"[py] reload FAILED: {e}")
        if any(p.endswith(".qml") or p == str(QML_DIR) for p in pending):
            self._reload_qml()
        self.store._reloads += 1
        self.store.reloadsChanged.emit()
        self._rewatch()
        print(f"[hot] reloaded {sorted(os.path.basename(p) for p in pending)} in {1000*(time.perf_counter()-t0):.1f} ms", flush=True)

    def _reload_qml(self):
        old_roots = list(self.engine.rootObjects())
        self.engine.clearComponentCache()
        self.engine.load(QUrl.fromLocalFile(str(ROOT_QML)))
        new_roots = self.engine.rootObjects()
        if len(new_roots) > len(old_roots):
            for r in old_roots:
                r.deleteLater()  # tear down the old window only once the new one loaded
            self.store.note("[qml] reloaded Main.qml")
        else:
            self.store.note("[qml] reload FAILED (QML error) - kept old window")


def main():
    app = QGuiApplication(sys.argv)
    store = Store()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("store", store)
    engine.load(QUrl.fromLocalFile(str(ROOT_QML)))
    if not engine.rootObjects():
        sys.exit("initial QML load failed")
    reloader = HotReloader(engine, store)
    if os.environ.get("POC_SELFTEST"):
        selftest(app, store, reloader)
    sys.exit(app.exec())


def selftest(app, store, reloader):
    """Headless proof: mutate files on a timer and assert the running app picked them up."""
    failures = []
    orig_backend = (HERE / "backend.py").read_text()
    orig_qml = ROOT_QML.read_text()
    def guard(fn):
        def run():
            try:
                fn()
            except Exception as e:
                failures.append(f"{fn.__name__}: {e!r}")
                print(f"[test] FAIL {fn.__name__}: {e!r}", flush=True)
        return run
    def step1():
        store.bump(); store.bump()
        assert store.counter == 2, store.counter
        (HERE / "backend.py").write_text((HERE / "backend.py").read_text().replace("return current + 1", "return current + 10"))
        print("[test] edited backend.py (+1 -> +10)", flush=True)
    def step2():
        store.bump()
        assert store.counter == 12, f"python reload did not take effect: {store.counter}"
        print("[test] OK python hot reload: counter =", store.counter, "(state 2 survived, new logic applied)", flush=True)
        src = ROOT_QML.read_text()
        ROOT_QML.write_text(src.replace("title: \"harness poc\"", "title: \"harness poc RELOADED\""))
        print("[test] edited Main.qml (title)", flush=True)
    def step3():
        root = reloader.engine.rootObjects()[-1]
        assert root.property("title") == "harness poc RELOADED", root.property("title")
        assert store.counter == 12, "state lost across QML reload"
        print("[test] OK qml hot reload: title =", root.property("title"), "; counter still", store.counter, flush=True)
    def done():
        (HERE / "backend.py").write_text(orig_backend)
        ROOT_QML.write_text(orig_qml)
        if failures:
            print(f"[test] FAILED ({len(failures)}) watch-mode={reloader.mode} reloads={store.reloads}", flush=True)
            app.exit(1)
        else:
            print(f"[test] ALL PASSED watch-mode={reloader.mode} reloads={store.reloads}", flush=True)
            app.quit()
    for ms, fn in ((300, step1), (1500, step2), (3000, step3), (4200, done)):
        QTimer.singleShot(ms, guard(fn))


if __name__ == "__main__":
    main()
