"""Offscreen end-to-end: render, intents, hot reload (QML + Python), screenshot."""
import re
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QObject
from PySide6.QtTest import QTest

from harness.__main__ import build, ROOT

OUT = ROOT / "tests" / "_out"


def wait_until(cond, timeout_ms=4000, step=30):
    t0 = time.time()
    while time.time() - t0 < timeout_ms / 1000:
        QTest.qWait(step)
        if cond():
            return True
    return False


@pytest.fixture(scope="module")
def harness():
    (OUT / "session.json").unlink(missing_ok=True)
    app, store, reloader = build(force_poll=True)
    assert reloader.load(), store.reloadError
    QTest.qWait(200)
    yield app, store, reloader
    for r in reloader.engine.rootObjects():
        r.deleteLater()
    QTest.qWait(50)


def root(reloader):
    return reloader.engine.rootObjects()[-1]


def find_all(win, pattern: str):
    """Walk the visual item tree (Repeater/Loader items have no QObject parent chain)."""
    rx = re.compile(pattern)
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if rx.fullmatch(it.objectName() or ""):
            out.append(it)
        stack.extend(it.childItems())
    return out


def test_initial_render(harness):
    app, store, reloader = harness
    win = root(reloader)
    assert win.objectName() == "mainWindow"
    groups = find_all(win, r"group_g\d+")
    assert len(groups) == 1
    assert len(find_all(win, r"tab_welcome_welcome")) == 1
    assert find_all(win, r"dock_left") and find_all(win, r"dock_right")
    assert store.watchMode == "poll"
    assert store.reloadError == ""


def test_intents_rerender(harness):
    app, store, reloader = harness
    layout = store.layout
    win = root(reloader)
    gid = layout.activeGroup
    layout.openContent("context", "ctx_1", "Context 1")
    QTest.qWait(50)
    assert len(find_all(win, r"tab_context_ctx_1")) == 1
    layout.splitGroup(gid, "horizontal")
    QTest.qWait(50)
    assert len(find_all(win, r"group_g\d+")) == 2
    assert len(find_all(win, r"split_s\d+")) == 1
    new_gid = layout.activeGroup
    assert new_gid != gid
    layout.closeTab(new_gid, 0)
    QTest.qWait(50)
    assert len(find_all(win, r"group_g\d+")) == 1
    layout.togglePanel("left", "board")   # collapse left dock to strip
    QTest.qWait(50)
    docks = find_all(win, r"dock_left")
    assert docks and not docks[0].property("visible")
    layout.togglePanel("left", "board")
    layout.togglePanel("bottom", "terminal")  # open bottom dock
    QTest.qWait(50)
    assert find_all(win, r"dock_bottom")[0].property("visible")


def test_screenshot(harness):
    app, store, reloader = harness
    win = root(reloader)
    win.setWidth(1400); win.setHeight(900)
    QTest.qWait(300)
    img = win.grabWindow()
    assert not img.isNull() and img.width() > 0
    path = OUT / "main.png"
    assert img.save(str(path))
    assert path.stat().st_size > 1000


def test_qml_hot_reload_new_generation(harness):
    app, store, reloader = harness
    f = ROOT / "qml" / "content" / "Welcome.qml"
    src = f.read_text()
    store.layout.openContent("context", "ctx_1", "Context 1")
    QTest.qWait(50)
    gen = store.generation
    try:
        f.write_text(src.replace("Welcome to zharn", "Welcome to zharn (reloaded)"))
        assert wait_until(lambda: store.generation == gen + 1), f"no new generation; err={store.reloadError}"
        assert store.reloadError == ""
        win = root(reloader)
        assert win.objectName() == "mainWindow"
        # state survived: the context tab opened in the earlier test is still there
        assert len(find_all(win, r"tab_context_ctx_1")) == 1
        # a broken *content* file still swaps the generation (root loads) but surfaces the error
        store.layout.openContent("welcome", "welcome", "Welcome")  # make its Loader active
        QTest.qWait(50)
        f.write_text(src + "\nthis is not qml {")
        assert wait_until(lambda: store.reloadError != "" and store.generation == gen + 2)
        assert "Welcome.qml" in store.reloadError
        # a broken *root* keeps the previous generation
        main_qml = ROOT / "qml" / "Main.qml"
        main_src = main_qml.read_text()
        main_qml.write_text(main_src + "\nbroken {")
        assert wait_until(lambda: "Main.qml" in store.reloadError)
        assert store.generation == gen + 2
        main_qml.write_text(main_src)
        assert wait_until(lambda: store.generation == gen + 3)
    finally:
        f.write_text(src)
        wait_until(lambda: store.reloadError == "" and store.generation == gen + 4)
    assert store.reloadError == ""


def test_python_hot_reload_swaps_code_in_place(harness):
    app, store, reloader = harness
    f = ROOT / "harness" / "content.py"
    src = f.read_text()
    gen = store.generation
    try:
        assert store.content.titleFor("welcome") == "Welcome"
        f.write_text(src.replace('"title": "Welcome",', '"title": "Welcome!",'))
        assert wait_until(lambda: store.content.titleFor("welcome") == "Welcome!"), store.reloadError
        assert not store.restartRequired
        assert wait_until(lambda: store.generation == gen + 1)  # python change → re-render
    finally:
        f.write_text(src)
        wait_until(lambda: store.content.titleFor("welcome") == "Welcome")


def test_shape_change_flags_restart(tmp_path, monkeypatch):
    """Adding a Signal to a live QObject class can't be hot-swapped → restart required."""
    import importlib, sys
    from harness.shell import _patch_classes
    mod_file = tmp_path / "shapemod.py"
    mod_file.write_text(
        "from PySide6.QtCore import QObject, Signal, Slot\n"
        "class Thing(QObject):\n"
        "    ping = Signal()\n"
        "    def value(self): return 1\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    mod = importlib.import_module("shapemod")
    inst = mod.Thing()
    old_ns = dict(mod.__dict__)
    mod_file.write_text(
        "from PySide6.QtCore import QObject, Signal, Slot\n"
        "class Thing(QObject):\n"
        "    ping = Signal()\n"
        "    def value(self): return 2\n")
    importlib.reload(mod)
    changed, notes = _patch_classes(old_ns, mod)
    assert not changed and inst.value() == 2          # body swap reached the live instance
    old_ns = dict(mod.__dict__)
    mod_file.write_text(
        "from PySide6.QtCore import QObject, Signal, Slot\n"
        "class Thing(QObject):\n"
        "    ping = Signal()\n"
        "    pong = Signal(int)\n"
        "    def value(self): return 3\n")
    importlib.reload(mod)
    changed, notes = _patch_classes(old_ns, mod)
    assert changed and any("pong" in n for n in notes)
    sys.modules.pop("shapemod", None)
