"""The shell: the only code that is never hot-reloaded. Keep it tiny.

- Watcher:  file changes under harness/ and qml/ (inotify, or mtime polling where inotify is broken)
- Reloader: generation model for QML (new engine per reload, swap only on success) and
            in-place code swap for Python (methods/slots patched onto the live classes;
            signal/property shape changes flag "restart required").
"""
from __future__ import annotations

import importlib
import inspect
import os
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import (QCoreApplication, QEvent, QFileSystemWatcher, QObject, QProcess, QTimer, QUrl,
                            QtMsgType, Signal, Slot, qInstallMessageHandler)
from PySide6.QtQml import QQmlApplicationEngine

ROOT = Path(__file__).resolve().parent.parent
QML_DIR = ROOT / "qml"
PKG_DIR = ROOT / "harness"
RELOADABLE = ["harness.config_def", "harness.config", "harness.notify", "harness.icons", "harness.layout", "harness.content", "harness.qmodels",
              "harness.fsutil", "harness.workspace", "harness.lifecycle", "harness.agents", "harness.roles", "harness.contexts",
              "harness.stories", "harness.ipc", "harness.store"]  # dependency order
WATCH_EXT = {".py", ".qml", ".js", ".mjs"}


class Watcher(QObject):
    changed = Signal(list)  # absolute paths

    def __init__(self, roots, poll_ms=250, force_poll=False):
        super().__init__()
        self.roots = [Path(r) for r in roots]
        self.mode = "poll" if force_poll else "native"
        self._fsw = QFileSystemWatcher()
        self._fsw.fileChanged.connect(self._on_change)
        self._fsw.directoryChanged.connect(self._on_change)
        self._pending = set()
        self._debounce = QTimer(singleShot=True, interval=80)
        self._debounce.timeout.connect(self._flush)
        self._poll = QTimer(interval=poll_ms)
        self._poll.timeout.connect(self._poll_tick)
        self._mtimes = {}
        self._known_files = {p for p in self.paths() if not os.path.isdir(p)}
        self.rewatch()
        if self.mode == "poll":
            self._poll.start()

    def paths(self):
        out = []
        for root in self.roots:
            for p in root.rglob("*"):
                if p.suffix in WATCH_EXT and "__pycache__" not in p.parts:
                    out.append(str(p))
            out += [str(d) for d in root.rglob("*") if d.is_dir() and "__pycache__" not in d.parts]
            out.append(str(root))
        return out

    def rewatch(self):
        paths = self.paths()
        if self.mode == "poll":
            self._mtimes = {p: self._mtime(p) for p in paths}
            return
        known = set(self._fsw.files()) | set(self._fsw.directories())
        new = [p for p in paths if p not in known]
        failed = self._fsw.addPaths(new) if new else []
        if failed:
            self.mode = "poll"
            allp = self._fsw.files() + self._fsw.directories()
            if allp:
                self._fsw.removePaths(allp)
            self._mtimes = {p: self._mtime(p) for p in paths}
            self._poll.start()

    @staticmethod
    def _mtime(p):
        try:
            return os.stat(p).st_mtime_ns
        except OSError:
            return None

    def _poll_tick(self):
        for p in self.paths():
            m = self._mtime(p)
            if self._mtimes.get(p) != m:
                self._mtimes[p] = m
                self._on_change(p)

    def _on_change(self, path):
        if os.path.isdir(path):
            # directory mtime changes for any child (e.g. __pycache__, editor temp files):
            # only meaningful if the set of watched source files actually changed
            current = {p for p in self.paths() if not os.path.isdir(p)}
            if current == self._known_files:
                return
            self._known_files = current
        self._pending.add(path)
        self._debounce.start()

    def _flush(self):
        pending, self._pending = self._pending, set()
        self.changed.emit(sorted(pending))


def _swap_code(old_fn, new_fn) -> bool:
    """Put new code into the OLD function object (identity preserved: shiboken caches Python
    overrides of C++ virtuals by object, and bound methods/handlers may hold references)."""
    if old_fn.__code__.co_freevars != new_fn.__code__.co_freevars:
        return False
    old_fn.__code__ = new_fn.__code__
    old_fn.__defaults__ = new_fn.__defaults__
    old_fn.__kwdefaults__ = new_fn.__kwdefaults__
    old_fn.__doc__ = new_fn.__doc__
    for k, v in vars(new_fn).items():  # Slot() metadata etc.
        setattr(old_fn, k, v)
    return True


def _unwrap(fn):
    return fn.__func__ if isinstance(fn, (staticmethod, classmethod)) else fn


def _patch_classes(old_ns: dict, new_module) -> tuple[bool, list]:
    """Update the OLD class objects in place from the reloaded module (live instances keep
    pointing at them). Returns (shape_changed, notes)."""
    from PySide6.QtCore import Signal as _Signal, Property as _Property
    shape_changed, notes = False, []
    for name, old_cls in old_ns.items():
        if not inspect.isclass(old_cls) or old_cls.__module__ != new_module.__name__:
            continue
        new_cls = getattr(new_module, name, None)
        if not inspect.isclass(new_cls) or new_cls is old_cls:
            continue
        for attr, val in list(new_cls.__dict__.items()):
            if attr in ("__dict__", "__weakref__", "__module__", "__doc__", "__qualname__"):
                continue
            old_val = old_cls.__dict__.get(attr)
            if isinstance(val, _Signal) or isinstance(old_val, _Signal):
                if type(old_val) is not type(val):
                    shape_changed = True; notes.append(f"{name}.{attr}: signal added/removed")
                continue
            if isinstance(val, _Property) or isinstance(old_val, _Property):
                if type(old_val) is not type(val):
                    shape_changed = True; notes.append(f"{name}.{attr}: property added/removed")
                    continue
                for f in ("fget", "fset", "freset"):
                    old_fn, new_fn = getattr(old_val, f, None), getattr(val, f, None)
                    if old_fn is None and new_fn is None:
                        continue
                    if old_fn is None or new_fn is None or not _swap_code(old_fn, new_fn):
                        shape_changed = True; notes.append(f"{name}.{attr}.{f}: accessor changed shape")
                continue
            if inspect.isfunction(_unwrap(val)) and inspect.isfunction(_unwrap(old_val)) and type(val) is type(old_val):
                if not _swap_code(_unwrap(old_val), _unwrap(val)):
                    setattr(old_cls, attr, val)
                continue
            setattr(old_cls, attr, val)  # new methods, plain data, changed descriptor kinds
        for attr in list(old_cls.__dict__):
            if attr not in new_cls.__dict__ and not attr.startswith("__"):
                if isinstance(old_cls.__dict__[attr], (_Signal, _Property)):
                    shape_changed = True; notes.append(f"{name}.{attr}: removed")
                else:
                    delattr(old_cls, attr)
        new_module.__dict__[name] = old_cls  # module attr points at the live class again
    return shape_changed, notes


class Reloader(QObject):
    generationChanged = Signal()

    def __init__(self, app_store, theme_provider, force_poll=False, poll_ms=250):
        super().__init__()
        self.app_store = app_store
        self.theme_provider = theme_provider
        self.engine = None
        self.generation = 0
        self.watcher = Watcher([PKG_DIR, QML_DIR], poll_ms=poll_ms, force_poll=force_poll)
        self.watcher.changed.connect(self.on_changed)
        app_store.set_hot(watch_mode=self.watcher.mode)
        app_store.requestRestart.connect(self.restart)
        # QML runtime errors (lazily loaded components, binding errors) do not all flow through
        # QQmlEngine.warnings — a message handler is the only complete channel.
        self._suppress_messages = False
        self._load_messages = None  # list while a generation is loading, else None
        qInstallMessageHandler(self._on_message)

    def _on_message(self, mode, context, message):
        sys.stderr.write(message + "\n")
        if self._suppress_messages or mode not in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg):
            return
        category = context.category or ""
        if "file://" in message or category.startswith(("qml", "qt.qml", "qt.quick")):
            if self._load_messages is not None:  # surfaced once the generation settles
                self._load_messages.append(message)
                return
            try:
                self.app_store.set_hot(error=message)
            except RuntimeError:  # store already gone during shutdown
                pass

    # ---------------------------------------------------------------- QML generations
    def load(self) -> bool:
        t0 = time.perf_counter()
        engine = QQmlApplicationEngine()
        engine.addImportPath(str(QML_DIR))
        from harness.icons import IconProvider  # reloadable; a fresh provider (and cache) per generation
        engine.addImageProvider("icon", IconProvider())
        engine.rootContext().setContextProperty("app", self.app_store)
        engine.setOutputWarningsToStandardError(True)
        warnings = []
        # Warnings arrive both during load (root errors) and later (lazily loaded content).
        # Later ones are surfaced in the status bar but keep the generation: a broken panel
        # shows its error in place instead of blocking every other edit.
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        self._load_messages = []
        engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
        load_messages, self._load_messages = self._load_messages, None
        if not engine.rootObjects():
            engine.deleteLater()
            err = "\n".join(warnings) or "Main.qml produced no root object"
            self.app_store.set_hot(error=err)
            print(f"[hot] QML generation FAILED, keeping generation {self.generation}:\n{err}", flush=True)
            return False
        old = self.engine
        self.engine = engine
        self.generation += 1
        if old is not None:  # tear the old generation down now, muting its dying-binding chatter
            self._suppress_messages = True
            for r in old.rootObjects():
                r.deleteLater()
            old.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self._suppress_messages = False
        self.app_store.set_hot(generation=self.generation, error="\n".join(load_messages))
        self.generationChanged.emit()
        print(f"[hot] QML generation {self.generation} in {1000 * (time.perf_counter() - t0):.1f} ms", flush=True)
        return True

    # ---------------------------------------------------------------- Python code swap
    def reload_python(self, changed_files) -> bool:
        t0 = time.perf_counter()
        changed_mods = set()
        for f in changed_files:
            try:
                rel = Path(f).resolve().relative_to(PKG_DIR)
            except ValueError:
                continue
            mod = "harness." + ".".join(rel.with_suffix("").parts)
            changed_mods.add(mod)
        if not changed_mods:
            return True
        # reload in dependency order, plus everything after the first changed module
        order = [m for m in RELOADABLE if m in sys.modules]
        first = min((order.index(m) for m in changed_mods if m in order), default=None)
        to_reload = order[first:] if first is not None else []
        to_reload += [m for m in changed_mods if m not in order and m in sys.modules]
        shape_changed, notes = False, []
        for mod_name in to_reload:
            module = sys.modules[mod_name]
            old_ns = dict(module.__dict__)
            try:
                importlib.reload(module)
            except Exception:
                err = traceback.format_exc()
                self.app_store.set_hot(error=err)
                print(f"[hot] python reload FAILED for {mod_name}:\n{err}", flush=True)
                return False
            sc, n = _patch_classes(old_ns, module)
            shape_changed |= sc
            notes += n
        if "harness.config" in to_reload or "harness.config_def" in to_reload:
            self.app_store.set_theme(self.theme_provider())
        self.app_store.set_hot(error="", restart_required=shape_changed or self.app_store.restartRequired)
        print(f"[hot] python swapped {sorted(to_reload)} in {1000 * (time.perf_counter() - t0):.1f} ms"
              + (f"; RESTART REQUIRED: {notes}" if shape_changed else ""), flush=True)
        return True

    @Slot(list)
    def on_changed(self, files):
        py = [f for f in files if f.endswith(".py")]
        qml = [f for f in files if f.endswith((".qml", ".js", ".mjs"))] or [f for f in files if os.path.isdir(f)]
        ok = True
        if py:
            ok = self.reload_python(py)
        if ok and (qml or py):
            # python changes can alter what QML renders (content registry, theme) → new generation too
            self.load()
        self.watcher.rewatch()

    def shutdown(self):
        """Delete the QML generation before Python tears down the stores it binds to (else every
        binding re-evaluates against null and floods the log at exit). Stays muted afterwards."""
        self._suppress_messages = True
        if self.engine is not None:
            for r in self.engine.rootObjects():
                r.deleteLater()
            self.engine.deleteLater()
            self.engine = None
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    @Slot()
    def restart(self):
        from PySide6.QtGui import QGuiApplication
        QProcess.startDetached(sys.executable, ["-m", "harness"] + sys.argv[1:], str(ROOT))
        QGuiApplication.quit()
