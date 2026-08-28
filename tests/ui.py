"""Drive the real QML UI: find controls by objectName, click them, type into them.

Every interactive control in qml/ carries a stable objectName so tests (and agents editing
the UI) can target it. Clicks and keys go through QTest on the window, so handlers, enabled
states and visibility all matter — exactly like a user's mouse.

Item access goes through tests/probe.qml (JS inside the app's engine) and comes back as plain
values: Python never keeps wrappers for QML-created items. Holding such wrappers across a
generation teardown made shiboken return the wrong object for a reused address (flaky suite)."""
from __future__ import annotations

import os
import re
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, QPoint, Qt, Q_ARG
from PySide6.QtGui import QKeyEvent
from PySide6.QtQml import QJSValue, QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from harness.__main__ import ROOT, build

OUT = ROOT / "tests" / "_out"
PROBE = ROOT / "tests" / "probe.qml"
FAKE_CLAUDE = f"{sys.executable} {ROOT / 'tests' / 'fake_claude.py'}"


def wait_until(cond, timeout_ms=8000, step=25):
    t0 = time.time()
    while time.time() - t0 < timeout_ms / 1000:
        QTest.qWait(step)
        if cond():
            return True
    return False


class Ref:
    """A named item. Every call re-resolves by name (preferring the visible one), so a Ref
    stays valid across re-renders as long as something with that objectName exists."""

    def __init__(self, harness: "Harness", name: str):
        self.h, self.name = harness, name
        self._pat = re.escape(name)

    def _pick(self) -> int:
        infos = self.h._match(self._pat)
        assert infos, f"{self.name!r} is gone"
        if len(infos) > 1:
            vis = [i for i, x in enumerate(infos) if x["visible"]]
            if vis:
                return vis[0]
        return 0

    def _info(self) -> dict:
        return self.h._match(self._pat)[self._pick()]

    def objectName(self):
        return self.name

    def property(self, key: str):
        return self.h._call("prop", self._pat, self._pick(), key)

    def setProperty(self, key: str, value):
        return self.h._call("set", self._pat, self._pick(), key, value)

    def isVisible(self) -> bool:
        return bool(self._info()["visible"])

    def forceActiveFocus(self):
        self.h._call("focus", self._pat, self._pick())

    def center(self) -> QPoint:
        i = self._info()
        return QPoint(int(i["x"] + i["w"] / 2), int(i["y"] + i["h"] / 2))

    def width(self):
        return self._info()["w"]

    def height(self):
        return self._info()["h"]

    def __repr__(self):
        return f"<Ref {self.name}>"


class Harness:
    def __init__(self, app, store, reloader):
        self.app, self.store, self.reloader = app, store, reloader
        self._win, self._probe, self._gen = None, None, -1

    @property
    def win(self):
        self._ensure()
        return self._win

    def _ensure(self):
        """One window wrapper + one probe per QML generation."""
        if self._gen == self.store.generation:
            return
        self._win = self.reloader.engine.rootObjects()[-1]
        comp = QQmlComponent(self.reloader.engine, str(PROBE))
        assert not comp.isError(), comp.errorString()
        self._probe = comp.createWithInitialProperties({"win": self._win})
        assert self._probe is not None, comp.errorString()
        # parentless + JS ownership = the QML GC deletes it under us; pin it to the window
        QQmlEngine.setObjectOwnership(self._probe, QQmlEngine.ObjectOwnership.CppOwnership)
        self._probe.setParent(self._win)
        self._comp = comp
        self._gen = self.store.generation

    def _call(self, fn: str, *args):
        self._ensure()
        ok = QMetaObject.invokeMethod(self._probe, fn, Qt.ConnectionType.DirectConnection,
                                      *[Q_ARG("QVariant", a) for a in args])
        assert ok, f"probe.{fn}{args} failed"
        v = self._probe.property("result")
        return v.toVariant() if isinstance(v, QJSValue) else v

    def _match(self, pattern: str) -> list[dict]:
        return list(self._call("match", pattern) or [])

    # ---------------------------------------------------------------- finding
    def find_all(self, pattern: str) -> list[Ref]:
        return [Ref(self, i["name"]) for i in self._match(pattern)]

    def find(self, pattern: str) -> Ref:
        """The one item a user could see with that name (hidden delegates don't count)."""
        infos = self._match(pattern)
        if len(infos) > 1:
            infos = [i for i in infos if i["visible"]]
        assert len(infos) == 1, f"expected exactly one visible {pattern!r}, found {len(infos)}"
        return Ref(self, infos[0]["name"])

    def has(self, pattern: str) -> bool:
        return bool(self._match(pattern))

    def visible(self, item: Ref) -> bool:
        return item.isVisible()

    # ---------------------------------------------------------------- acting
    def click(self, item: Ref, button=Qt.MouseButton.LeftButton, modifier=Qt.KeyboardModifier.NoModifier):
        assert item.isVisible(), f"{item.name!r} is not visible/clickable"
        center = item.center()
        assert 0 <= center.x() < self.win.width() and 0 <= center.y() < self.win.height(), \
            f"{item.name!r} is outside the window at {center}"
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

    def focus_and_type(self, item: Ref, text: str):
        item.forceActiveFocus()
        QTest.qWait(10)
        self.type(text)

    def choose(self, combo: Ref, text: str):
        """Pick an entry in a ComboBox the way a user would end up: index set + activated."""
        self._call("choose", combo._pat, combo._pick(), text)
        QTest.qWait(30)

    def screenshot(self, name: str):
        img = self.win.grabWindow()
        path = OUT / name
        assert img.save(str(path))
        return path

    def shutdown(self):
        self._probe, self._win = None, None
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
