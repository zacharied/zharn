"""Drive the real QML UI: find controls by objectName, click them, type into them.

Every interactive control in qml/ carries a stable objectName so tests (and agents editing
the UI) can target it. Clicks go through QTest on the window, so handlers, enabled states
and visibility all matter — exactly like a user's mouse."""
from __future__ import annotations

import os
import re
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, QPointF, Qt, Q_ARG
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest

from harness.__main__ import ROOT, build

OUT = ROOT / "tests" / "_out"
FAKE_CLAUDE = f"{sys.executable} {ROOT / 'tests' / 'fake_claude.py'}"


def wait_until(cond, timeout_ms=8000, step=25):
    t0 = time.time()
    while time.time() - t0 < timeout_ms / 1000:
        QTest.qWait(step)
        if cond():
            return True
    return False


class Harness:
    def __init__(self, app, store, reloader):
        self.app, self.store, self.reloader = app, store, reloader
        self._win, self._win_gen = None, -1

    @property
    def win(self):
        # Keep ONE wrapper per generation alive: a temporary window wrapper takes the
        # contentItem wrapper down with it when it is collected (shiboken parent tracking).
        if self._win_gen != self.store.generation:
            self._win = self.reloader.engine.rootObjects()[-1]
            self._win_gen = self.store.generation
        return self._win

    # ---------------------------------------------------------------- finding
    def find_all(self, pattern: str):
        """Visual-tree walk (Repeater/Loader items have no QObject parent chain)."""
        rx = re.compile(pattern)
        out, stack = [], [self.win.contentItem()]
        while stack:
            it = stack.pop()
            try:
                name = it.objectName() or ""
                children = it.childItems()
            except RuntimeError:  # wrapper outlived its C++ item (mid-teardown Loader)
                continue
            if rx.fullmatch(name):
                out.append(it)
            stack.extend(children)
        return out

    def find(self, pattern: str):
        """The one item a user could see with that name (hidden delegates don't count)."""
        items = self.find_all(pattern)
        if len(items) > 1:
            items = [i for i in items if self.visible(i)]
        assert len(items) == 1, f"expected exactly one visible {pattern!r}, found {len(items)}"
        return items[0]

    def has(self, pattern: str) -> bool:
        return bool(self.find_all(pattern))

    def visible(self, item) -> bool:
        return item.isVisible() and item.width() > 0 and item.height() > 0

    # ---------------------------------------------------------------- acting
    def click(self, item, button=Qt.MouseButton.LeftButton, modifier=Qt.KeyboardModifier.NoModifier):
        assert self.visible(item), f"{item.objectName()!r} is not visible/clickable"
        center = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        assert 0 <= center.x() < self.win.width() and 0 <= center.y() < self.win.height(), \
            f"{item.objectName()!r} is outside the window at {center}"
        QTest.mouseClick(self.win, button, modifier, center)
        QTest.qWait(30)

    def type(self, text: str):
        """Type into whatever has focus, with the exact characters (QTest.keyClick would upper-case)."""
        for ch in text:
            key = ord(ch.upper()) if ch.isalpha() else ord(ch)
            for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                QCoreApplication.sendEvent(self.win, QKeyEvent(kind, key, Qt.KeyboardModifier.NoModifier, ch))
        QTest.qWait(10)

    def key(self, key: Qt.Key, modifier=Qt.KeyboardModifier.NoModifier):
        QTest.keyClick(self.win, key, modifier)
        QTest.qWait(30)

    def focus_and_type(self, item, text: str):
        item.forceActiveFocus()
        QTest.qWait(10)
        self.type(text)

    def choose(self, combo, text: str):
        """Pick an entry in a ComboBox the way a user would end up: index set + activated."""
        model = combo.property("model")
        entries = list(model) if not hasattr(model, "rowCount") else [model.index(i, 0).data() for i in range(model.rowCount())]
        i = entries.index(text)
        combo.setProperty("currentIndex", i)
        QMetaObject.invokeMethod(combo, "activated", Q_ARG(int, i))
        QTest.qWait(30)

    def screenshot(self, name: str):
        img = self.win.grabWindow()
        path = OUT / name
        assert img.save(str(path))
        return path

    def shutdown(self):
        self.store.threads.shutdown()
        self.reloader.shutdown()
        QTest.qWait(50)


def start(name: str, claude_cmd: str = FAKE_CLAUDE, width=1400, height=900) -> Harness:
    """A fresh app over an empty data dir, rendered offscreen."""
    data = OUT / f"{name}-data"
    shutil.rmtree(data, ignore_errors=True)
    os.environ["HARNESS_DATA_DIR"] = str(data)
    os.environ["HARNESS_SESSION"] = str(OUT / f"{name}-session.json")
    os.environ["HARNESS_CLAUDE_CMD"] = claude_cmd
    Path(os.environ["HARNESS_SESSION"]).unlink(missing_ok=True)
    app, store, reloader = build(force_poll=True)
    assert reloader.load(), store.reloadError
    h = Harness(app, store, reloader)
    h.win.setWidth(width)
    h.win.setHeight(height)
    QTest.qWait(150)
    return h
