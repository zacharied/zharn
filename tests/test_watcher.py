"""Watcher (harness/shell.py) over a temp root, in poll mode (inotify is broken on this machine)."""
import os
import time

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

from harness.shell import Watcher

POLL_MS = 30
QUIET_MS = 400  # several poll ticks + the 80ms debounce: enough to prove nothing is coming


@pytest.fixture(scope="module")
def qapp():
    # Lazy (not at import): a bare QCoreApplication created at collection time would break
    # test_app, which needs a QGuiApplication for its QML engine.
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture
def root(tmp_path):
    (tmp_path / "a.py").write_text("a = 1\n")
    (tmp_path / "b.py").write_text("b = 1\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.qml").write_text("import QtQuick\nItem {}\n")
    return tmp_path


@pytest.fixture
def watcher(qapp, root):
    w = Watcher([root], poll_ms=POLL_MS, force_poll=True)
    emissions = []
    w.changed.connect(emissions.append)
    w.emissions = emissions
    yield w
    w._poll.stop()
    w._debounce.stop()


def wait_for(cond, timeout_ms=3000, step=20):
    t0 = time.time()
    while time.time() - t0 < timeout_ms / 1000:
        QTest.qWait(step)
        if cond():
            return True
    return False


def touch(path, text):
    """Write different content and bump mtime by a full second: FS timestamp granularity may be
    coarser than the gap between fixture setup and the edit."""
    path.write_text(text)
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))


def test_mode_is_poll_when_forced(watcher):
    assert watcher.mode == "poll"


def test_modifying_existing_py_file_emits_its_absolute_path(watcher, root):
    target = root / "a.py"
    touch(target, "a = 2\n")
    assert wait_for(lambda: watcher.emissions)
    assert str(target) in watcher.emissions[0]
    assert os.path.isabs(watcher.emissions[0][0])


def test_new_qml_file_is_picked_up_on_next_tick(watcher, root):
    new = root / "sub" / "d.qml"
    new.write_text("import QtQuick\nRectangle {}\n")
    assert wait_for(lambda: watcher.emissions)
    assert str(new) in watcher.emissions[0]
    assert str(new) in watcher.paths()


def test_txt_file_is_ignored(watcher, root):
    (root / "notes.txt").write_text("hi\n")
    QTest.qWait(QUIET_MS)
    assert watcher.emissions == []
    assert str(root / "notes.txt") not in watcher.paths()


def test_pycache_contents_are_ignored(watcher, root):
    cache = root / "__pycache__"
    cache.mkdir()
    (cache / "x.py").write_text("x = 1\n")
    QTest.qWait(QUIET_MS)
    assert watcher.emissions == []
    assert not any(str(cache) in p for p in watcher.paths())


def test_transient_temp_file_does_not_emit(watcher, root):
    tmp = root / ".a.py.swp"
    tmp.write_bytes(b"swap")
    QTest.qWait(POLL_MS)
    tmp.unlink()
    QTest.qWait(QUIET_MS)
    assert watcher.emissions == []


def test_rapid_edits_collapse_into_one_emission(watcher, root):
    a, b = root / "a.py", root / "b.py"
    touch(a, "a = 2\n")
    touch(b, "b = 2\n")
    assert wait_for(lambda: watcher.emissions)
    QTest.qWait(QUIET_MS)  # give a hypothetical second emission every chance to arrive
    assert len(watcher.emissions) == 1
    assert {str(a), str(b)} <= set(watcher.emissions[0])


def test_deleting_watched_file_emits_without_error(watcher, root):
    target = root / "a.py"
    target.unlink()
    assert watcher._mtime(str(target)) is None
    assert wait_for(lambda: watcher.emissions)
    assert str(target) not in watcher.paths()
    QTest.qWait(QUIET_MS)  # further ticks over the missing file must not raise either
